from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.prediction import Prediction
from app.services.odds_provider import odds_provider, SPORT_KEYS, ACTIVE_SPORTS, PROP_MARKETS

logger = logging.getLogger(__name__)
settings = get_settings()

MIN_CONFIDENCE = settings.prediction_min_confidence
MIN_EDGE = settings.prediction_min_edge / 100  # convert pct to decimal
MIN_BOOKMAKERS = 4
DEDUP_HOURS = 24
PARLAY_MIN_CONFIDENCE = 80
PARLAY_MIN_COMBINED = 55

# Sport reliability weights for scoring
SPORT_WEIGHTS = {
    "basketball_nba": 1.0,
    "americanfootball_nfl": 1.0,
    "baseball_mlb": 0.9,
    "icehockey_nhl": 0.9,
    "mma_mixed_martial_arts": 0.8,
    "soccer_epl": 0.95,
}

# Sharp book classification — Pinnacle/BetOnline set efficient lines
SHARP_BOOKS = {"pinnacle", "betonlineag", "williamhill_us"}
MID_BOOKS = {"betrivers", "unibet_us", "bovada", "betmgm"}
SOFT_BOOKS = {"draftkings", "fanduel", "pointsbetus", "superbook", "twinspires"}

BOOK_WEIGHTS = {}
for _b in SHARP_BOOKS:
    BOOK_WEIGHTS[_b] = 2.0
for _b in MID_BOOKS:
    BOOK_WEIGHTS[_b] = 1.0
for _b in SOFT_BOOKS:
    BOOK_WEIGHTS[_b] = 0.7


# ── Odds helpers ────────────────────────────────────────────────────

def american_to_implied(odds: int | float) -> float:
    """Convert American odds to implied probability (0-1)."""
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def implied_to_american(prob: float) -> int:
    """Convert implied probability (0-1) to American odds."""
    if prob <= 0 or prob >= 1:
        return 0
    if prob >= 0.5:
        return int(-prob / (1 - prob) * 100)
    return int((1 - prob) / prob * 100)


def calculate_parlay_odds(legs_odds: list[int | float]) -> int:
    """Calculate combined American odds for a parlay from individual legs."""
    combined_decimal = 1.0
    for odds in legs_odds:
        if odds > 0:
            combined_decimal *= (odds / 100) + 1
        else:
            combined_decimal *= (100 / abs(odds)) + 1
    combined_decimal -= 1  # remove the stake
    if combined_decimal >= 1:
        return int(combined_decimal * 100)
    return int(-100 / combined_decimal)


# ── Sharp book helpers ──────────────────────────────────────────────

def weighted_consensus_prob(entries: list[tuple]) -> float:
    """Weighted average implied probability — sharp books get 2x weight.

    entries: list of (price, bookmaker_key) or (price, point, bookmaker_key)
    Returns weighted average implied probability.
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for entry in entries:
        if len(entry) == 2:
            price, book = entry
        else:
            price, _, book = entry[0], entry[1] if len(entry) > 2 else None, entry[-1]
        w = BOOK_WEIGHTS.get(book, 1.0)
        weighted_sum += american_to_implied(price) * w
        total_weight += w
    return weighted_sum / total_weight if total_weight > 0 else 0.5


def sharp_book_agreement(entries: list[tuple], consensus_prob: float) -> int:
    """Count how many sharp books agree this side has value.

    A sharp book "agrees" if its implied prob is within 2% of consensus
    (i.e. not pricing it significantly differently).
    """
    count = 0
    for entry in entries:
        book = entry[-1]
        if book not in SHARP_BOOKS:
            continue
        price = entry[0]
        book_prob = american_to_implied(price)
        # Sharp book agrees if its line is within 2% of consensus
        if abs(book_prob - consensus_prob) <= 0.02:
            count += 1
    return count


# ── Scoring ─────────────────────────────────────────────────────────

def score_pick(
    edge: float,
    sharp_agreement: int,
    best_odds: int | float,
    sport: str,
    num_books: int = 0,
    consensus_prob: float = 0.5,
) -> float:
    """Score a pick 0-100. Data-driven weights from 51-bet analysis.

    Weighted factors:
    - Edge (35%): Only factor correlated with winning. 4% = 14pts, 10% = 35pts.
    - Implied Hit Rate (25%): Favor bets in -150 to +200 range (33-60% implied).
    - Sharp Agreement (20%): How many sharp books back this side.
    - Book Consensus (10%): Total books offering similar line.
    - Sport Reliability (10%): Major sports weighted higher.
    """
    # Edge component: 0-35 points. Linear: 4% = 14pts, 10% = 35pts
    edge_pct = edge * 100
    edge_score = min(edge_pct * 3.5, 35)

    # Implied hit rate: 0-25 points. Sweet spot is 33-60% implied (roughly -150 to +200)
    # Extreme longshots and extreme chalk both score low
    if 0.33 <= consensus_prob <= 0.60:
        hit_rate_score = 25.0
    elif 0.25 <= consensus_prob < 0.33:
        hit_rate_score = 18.0  # slight longshot
    elif 0.60 < consensus_prob <= 0.70:
        hit_rate_score = 18.0  # moderate favorite
    elif consensus_prob > 0.70:
        hit_rate_score = 10.0  # heavy chalk, low payout
    else:
        hit_rate_score = 8.0   # big longshot (<25%)

    # Sharp agreement: 0-20 points. 0 sharps = 0, 1 = 10, 2+ = 20
    if sharp_agreement >= 2:
        sharp_score = 20.0
    elif sharp_agreement == 1:
        sharp_score = 10.0
    else:
        sharp_score = 0.0

    # Book consensus: 0-10 points
    book_score = min(num_books * 1.5, 10)

    # Sport reliability: 0-10 points
    sport_weight = SPORT_WEIGHTS.get(sport, 0.8)
    sport_score = sport_weight * 10

    total = edge_score + hit_rate_score + sharp_score + book_score + sport_score
    return round(min(total, 100), 1)


# ── Market analyzers ────────────────────────────────────────────────

def _analyze_moneyline(event: dict, sport: str) -> list[dict]:
    """Analyze h2h (moneyline) market for a single event."""
    picks = []
    bookmakers = event.get("bookmakers", [])
    if len(bookmakers) < MIN_BOOKMAKERS:
        return picks

    # Collect moneyline outcomes: {team: [(price, bookmaker), ...]}
    ml_data: dict[str, list[tuple]] = {}
    for bm in bookmakers:
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                name = outcome.get("name", "")
                price = outcome.get("price")
                if name and price is not None:
                    ml_data.setdefault(name, []).append((price, bm.get("key", "")))

    for team, entries in ml_data.items():
        if len(entries) < MIN_BOOKMAKERS:
            continue

        consensus_prob = weighted_consensus_prob(entries)

        # Find best odds (highest price = lowest implied prob = most value)
        best_entry = max(entries, key=lambda x: x[0])
        best_price, best_book = best_entry
        best_prob = american_to_implied(best_price)

        edge = consensus_prob - best_prob
        if edge < MIN_EDGE:
            continue

        sharps = sharp_book_agreement(entries, consensus_prob)
        num_books = sum(1 for p, _ in entries if abs(american_to_implied(p) - consensus_prob) <= 0.01)
        confidence = score_pick(edge, sharps, best_price, sport, num_books, consensus_prob)

        reasons = []
        reasons.append(f"{team} ML at {best_price:+.0f}")
        reasons.append(f"consensus implied: {consensus_prob*100:.1f}%, best implied: {best_prob*100:.1f}%")
        reasons.append(f"edge: {edge*100:.1f}% across {len(entries)} books")
        if sharps >= 2:
            reasons.append(f"{sharps} sharp books agree")
        elif sharps == 0:
            reasons.append("no sharp book agreement")

        picks.append({
            "bet_type": "moneyline",
            "pick": f"{team} ML",
            "best_odds": best_price,
            "line": None,
            "confidence": confidence,
            "edge": round(edge, 4),
            "best_bookmaker": best_book,
            "implied_probability": round(best_prob, 4),
            "consensus_prob": round(consensus_prob, 4),
            "num_bookmakers": len(entries),
            "reasoning": "; ".join(reasons),
        })

    # Only return the single best ML pick per event (not both teams)
    if len(picks) > 1:
        picks.sort(key=lambda x: x["confidence"], reverse=True)
        return picks[:1]
    return picks


def _analyze_spread(event: dict, sport: str) -> list[dict]:
    """Analyze spreads market for a single event.

    Gated behind config: spreads disabled by default (35% WR, -3.42u in production).
    If enabled, requires much higher edge threshold and sharp book agreement.
    """
    if not settings.prediction_spreads_enabled:
        return []

    min_edge_spread = settings.prediction_min_edge_spread / 100

    picks = []
    bookmakers = event.get("bookmakers", [])
    if len(bookmakers) < MIN_BOOKMAKERS:
        return picks

    spread_data: dict[str, list[tuple]] = {}
    for bm in bookmakers:
        for market in bm.get("markets", []):
            if market.get("key") != "spreads":
                continue
            for outcome in market.get("outcomes", []):
                name = outcome.get("name", "")
                price = outcome.get("price")
                point = outcome.get("point")
                if name and price is not None and point is not None:
                    spread_data.setdefault(name, []).append((point, price, bm.get("key", "")))

    for team, entries in spread_data.items():
        if len(entries) < MIN_BOOKMAKERS:
            continue

        points = [p for p, _, _ in entries]
        consensus_point = sorted(points)[len(points) // 2]

        near_consensus = [(p, pr, bk) for p, pr, bk in entries if abs(p - consensus_point) <= 0.5]
        if len(near_consensus) < MIN_BOOKMAKERS:
            continue

        consensus_prob = weighted_consensus_prob([(pr, bk) for _, pr, bk in near_consensus])

        best_entry = max(entries, key=lambda x: (-x[0] if consensus_point < 0 else x[0], x[1]))
        best_point, best_price, best_book = best_entry
        best_prob = american_to_implied(best_price)

        edge = consensus_prob - best_prob
        point_advantage = 0
        if consensus_point < 0:
            point_advantage = consensus_point - best_point
        else:
            point_advantage = best_point - consensus_point
        if point_advantage > 0:
            edge += 0.01 * point_advantage

        if edge < min_edge_spread:
            continue

        # Require at least 1 sharp book to agree
        sharps = sharp_book_agreement([(pr, bk) for _, pr, bk in entries], consensus_prob)
        if sharps < 1:
            continue

        num_books = sum(1 for _, pr, _ in near_consensus if abs(american_to_implied(pr) - consensus_prob) <= 0.01)
        confidence = score_pick(edge, sharps, best_price, sport, num_books, consensus_prob)

        reasons = []
        reasons.append(f"spread {best_point:+.1f} at {best_price}")
        if point_advantage > 0:
            reasons.append(f"{point_advantage:.1f}pt better than consensus {consensus_point:+.1f}")
        reasons.append(f"edge: {edge*100:.1f}% across {len(entries)} books, {sharps} sharp")

        picks.append({
            "bet_type": "spread",
            "pick": f"{team} {best_point:+.1f}",
            "best_odds": best_price,
            "line": best_point,
            "confidence": confidence,
            "edge": round(edge, 4),
            "best_bookmaker": best_book,
            "implied_probability": round(best_prob, 4),
            "consensus_prob": round(consensus_prob, 4),
            "num_bookmakers": len(entries),
            "reasoning": "; ".join(reasons),
        })

    # Only return the single best spread pick per event (not both teams)
    if len(picks) > 1:
        picks.sort(key=lambda x: x["confidence"], reverse=True)
        return picks[:1]
    return picks


def _analyze_total(event: dict, sport: str) -> list[dict]:
    """Analyze totals (over/under) market for a single event."""
    picks = []
    bookmakers = event.get("bookmakers", [])
    if len(bookmakers) < MIN_BOOKMAKERS:
        return picks

    home_team = event.get("home_team", "")
    away_team = event.get("away_team", "")

    total_data: dict[str, list[tuple]] = {}
    for bm in bookmakers:
        for market in bm.get("markets", []):
            if market.get("key") != "totals":
                continue
            for outcome in market.get("outcomes", []):
                name = outcome.get("name", "")
                price = outcome.get("price")
                point = outcome.get("point")
                if name and price is not None and point is not None:
                    total_data.setdefault(name, []).append((point, price, bm.get("key", "")))

    for side, entries in total_data.items():
        if len(entries) < MIN_BOOKMAKERS:
            continue

        points = [p for p, _, _ in entries]
        consensus_point = sorted(points)[len(points) // 2]

        near_consensus = [(p, pr, bk) for p, pr, bk in entries if abs(p - consensus_point) <= 0.5]
        if len(near_consensus) < MIN_BOOKMAKERS:
            continue

        consensus_prob = weighted_consensus_prob([(pr, bk) for _, pr, bk in near_consensus])

        if side == "Over":
            best_entry = min(entries, key=lambda x: (x[0], -x[1]))
        else:
            best_entry = max(entries, key=lambda x: (x[0], x[1]))

        best_point, best_price, best_book = best_entry
        best_prob = american_to_implied(best_price)

        edge = consensus_prob - best_prob
        point_diff = abs(best_point - consensus_point)
        if point_diff >= 0.5:
            edge += 0.01 * point_diff

        if edge < MIN_EDGE:
            continue

        sharps = sharp_book_agreement([(pr, bk) for _, pr, bk in entries], consensus_prob)
        num_books = sum(1 for _, pr, _ in near_consensus if abs(american_to_implied(pr) - consensus_prob) <= 0.01)
        confidence = score_pick(edge, sharps, best_price, sport, num_books, consensus_prob)

        reasons = []
        reasons.append(f"{side} {best_point} at {best_price}")
        reasons.append(f"consensus line: {consensus_point}, edge: {edge*100:.1f}%")
        reasons.append(f"{len(entries)} books offering totals")
        if sharps >= 2:
            reasons.append(f"{sharps} sharp books agree")

        picks.append({
            "bet_type": "total",
            "pick": f"{home_team}/{away_team} {side} {best_point}",
            "best_odds": best_price,
            "line": best_point,
            "confidence": confidence,
            "edge": round(edge, 4),
            "best_bookmaker": best_book,
            "implied_probability": round(best_prob, 4),
            "consensus_prob": round(consensus_prob, 4),
            "num_bookmakers": len(entries),
            "reasoning": "; ".join(reasons),
        })

    # Only return the single best total pick per event (Over or Under, not both)
    if len(picks) > 1:
        picks.sort(key=lambda x: x["confidence"], reverse=True)
        return picks[:1]
    return picks


PROP_MARKET_LABELS: dict[str, str] = {
    "player_pass_tds": "Pass TDs",
    "player_pass_yds": "Pass Yds",
    "player_rush_yds": "Rush Yds",
    "player_anytime_td": "Anytime TD",
    "player_points": "Points",
    "player_rebounds": "Rebounds",
    "player_assists": "Assists",
    "player_threes": "Threes",
    "batter_total_bases": "Total Bases",
    "pitcher_strikeouts": "Strikeouts",
}


def _analyze_player_props(event_data: dict, sport: str) -> list[dict]:
    """Analyze player prop markets for a single event.

    Handles two patterns:
    A. Over/Under props (pass yds, rush yds, points, etc.) — both Over AND Under
    B. Anytime/Yes-No props (anytime TD) — both Yes AND No
    """
    picks = []
    bookmakers = event_data.get("bookmakers", [])
    if len(bookmakers) < 3:  # props available from fewer books
        return picks

    # Collect all prop outcomes across bookmakers
    # Key: (player_name, market_key, description) -> [(price, point_or_None, bookmaker)]
    prop_data: dict[tuple, list[tuple]] = {}

    for bm in bookmakers:
        for market in bm.get("markets", []):
            market_key = market.get("key", "")
            for outcome in market.get("outcomes", []):
                # Per-event endpoint: name="Over"/"Under"/"Yes", description="Player Name"
                side = outcome.get("name", "")        # "Over", "Under", "Yes", "No"
                player = outcome.get("description", "")  # player name
                price = outcome.get("price")
                point = outcome.get("point")  # None for anytime props
                if player and price is not None and side:
                    key = (player, market_key, side)
                    prop_data.setdefault(key, []).append(
                        (price, point, bm.get("key", ""))
                    )

    processed = set()

    for (player, market_key, desc), entries in prop_data.items():
        if len(entries) < 3:
            continue

        group_key = (player, market_key, desc)
        if group_key in processed:
            continue
        processed.add(group_key)

        is_over = desc == "Over"
        is_under = desc == "Under"
        is_yes = desc == "Yes"
        is_no = desc == "No"

        if not (is_over or is_under or is_yes or is_no):
            continue

        market_label = PROP_MARKET_LABELS.get(market_key, market_key.replace("player_", "").replace("_", " ").title())

        if is_over or is_under:
            # Over/Under prop: has point values
            points = [pt for _, pt, _ in entries if pt is not None]
            if not points:
                continue
            consensus_line = sorted(points)[len(points) // 2]

            # Filter entries near consensus line
            near = [(pr, pt, bk) for pr, pt, bk in entries
                    if pt is not None and abs(pt - consensus_line) <= 0.5]
            if len(near) < 3:
                continue

            consensus_prob = weighted_consensus_prob([(pr, bk) for pr, _, bk in near])

            if is_over:
                # Best Over: lowest line with best price
                best_entry = min(entries, key=lambda x: (x[1] if x[1] is not None else 999, -x[0]))
            else:
                # Best Under: highest line with best price
                best_entry = max(entries, key=lambda x: (x[1] if x[1] is not None else -999, x[0]))

            best_price, best_point, best_book = best_entry
            if best_point is None:
                continue
            best_prob = american_to_implied(best_price)

            edge = consensus_prob - best_prob
            # Line advantage bonus
            if is_over:
                line_diff = consensus_line - best_point
            else:
                line_diff = best_point - consensus_line
            if line_diff > 0:
                edge += 0.01 * line_diff

            if edge < MIN_EDGE:
                continue

            pick_text = f"{player} {desc} {best_point} {market_label}"

            sharps = sharp_book_agreement([(pr, bk) for pr, _, bk in entries], consensus_prob)
            num_books = sum(1 for pr, _, _ in near if abs(american_to_implied(pr) - consensus_prob) <= 0.01)
            confidence = score_pick(edge, sharps, best_price, sport, num_books, consensus_prob)

            reasons = [
                f"{pick_text} at {best_price:+.0f}",
                f"consensus line: {consensus_line}, consensus prob: {consensus_prob*100:.1f}%",
                f"edge: {edge*100:.1f}% across {len(entries)} books",
            ]
            if sharps:
                reasons.append(f"{sharps} sharp books agree")

            picks.append({
                "bet_type": "player_prop",
                "pick": pick_text,
                "best_odds": best_price,
                "line": best_point,
                "confidence": confidence,
                "edge": round(edge, 4),
                "best_bookmaker": best_book,
                "implied_probability": round(best_prob, 4),
                "consensus_prob": round(consensus_prob, 4),
                "num_bookmakers": len(entries),
                "reasoning": "; ".join(reasons),
                "prop_market": market_key,
            })

        elif is_yes or is_no:
            # Anytime prop (e.g. anytime TD scorer)
            consensus_prob = weighted_consensus_prob([(pr, bk) for pr, _, bk in entries])

            best_entry = max(entries, key=lambda x: x[0])
            best_price, _, best_book = best_entry
            best_prob = american_to_implied(best_price)

            edge = consensus_prob - best_prob
            if edge < MIN_EDGE:
                continue

            if is_yes:
                pick_text = f"{player} {market_label}"
            else:
                pick_text = f"{player} No {market_label}"

            sharps = sharp_book_agreement([(pr, bk) for pr, _, bk in entries], consensus_prob)
            num_books = sum(1 for pr, _, _ in entries if abs(american_to_implied(pr) - consensus_prob) <= 0.01)
            confidence = score_pick(edge, sharps, best_price, sport, num_books, consensus_prob)

            reasons = [
                f"{pick_text} at {best_price:+.0f}",
                f"consensus prob: {consensus_prob*100:.1f}%, best implied: {best_prob*100:.1f}%",
                f"edge: {edge*100:.1f}% across {len(entries)} books",
            ]
            if sharps:
                reasons.append(f"{sharps} sharp books agree")

            picks.append({
                "bet_type": "player_prop",
                "pick": pick_text,
                "best_odds": best_price,
                "line": None,
                "confidence": confidence,
                "edge": round(edge, 4),
                "best_bookmaker": best_book,
                "implied_probability": round(best_prob, 4),
                "consensus_prob": round(consensus_prob, 4),
                "num_bookmakers": len(entries),
                "reasoning": "; ".join(reasons),
                "prop_market": market_key,
                "_player": player,
                "_market_key": market_key,
            })

    # Deduplicate: one pick per (player, market) — keep the side with highest confidence
    best_per_player_market: dict[tuple, dict] = {}
    for pick in picks:
        key = (pick["_player"], pick["_market_key"])
        if key not in best_per_player_market or pick["confidence"] > best_per_player_market[key]["confidence"]:
            best_per_player_market[key] = pick
    # Clean up internal keys
    result = []
    for pick in best_per_player_market.values():
        pick.pop("_player", None)
        pick.pop("_market_key", None)
        result.append(pick)
    return result


def analyze_event(event: dict, sport: str) -> list[dict]:
    """Analyze one game event. Returns potential picks with scores."""
    picks = []
    picks.extend(_analyze_moneyline(event, sport))
    picks.extend(_analyze_spread(event, sport))
    picks.extend(_analyze_total(event, sport))
    return picks


def build_parlay(picks: list[dict], max_legs: int = 3) -> Optional[dict]:
    """If 3+ picks have confidence >= 80, combine top 2-3 into a parlay.

    Only suggests parlays where combined confidence >= 55%.
    """
    eligible = [p for p in picks if p["confidence"] >= PARLAY_MIN_CONFIDENCE]
    if len(eligible) < 3:
        return None

    eligible.sort(key=lambda x: x["confidence"], reverse=True)
    legs = eligible[:max_legs]

    combined_prob = 1.0
    leg_odds = []
    leg_details = []
    for leg in legs:
        # Use consensus prob as the hit rate (more realistic than best-book prob)
        implied = leg.get("consensus_prob", leg.get("implied_probability", 0.5))
        combined_prob *= implied
        leg_odds.append(leg["best_odds"])
        leg_details.append({
            "pick": leg["pick"],
            "odds": leg["best_odds"],
            "confidence": leg["confidence"],
            "sport": leg.get("_sport_display", ""),
            "event": leg.get("_event_name", ""),
        })

    combined_confidence = combined_prob * 100
    if combined_confidence < PARLAY_MIN_COMBINED:
        return None

    parlay_odds = calculate_parlay_odds(leg_odds)

    reasons = [f"{len(legs)}-leg parlay"]
    for ld in leg_details:
        reasons.append(f"{ld['pick']} ({ld['odds']:+.0f}, {ld['confidence']:.0f}% conf)")
    reasons.append(f"combined confidence: {combined_confidence:.1f}%")

    return {
        "bet_type": "parlay",
        "pick": " + ".join(ld["pick"] for ld in leg_details),
        "best_odds": parlay_odds,
        "best_bookmaker": "multi",
        "implied_probability": round(1 - combined_prob, 4),
        "confidence": round(combined_confidence, 1),
        "edge": round(sum(l.get("edge", 0) for l in legs) / len(legs), 4),
        "reasoning": "; ".join(reasons),
        "parlay_legs": leg_details,
    }


# ── Main entry points (called by worker) ────────────────────────────

async def generate_predictions(db: AsyncSession) -> list[Prediction]:
    """Run odds analysis on all active sports and generate predictions.

    Flow:
    1. For each active sport, fetch odds via odds_provider
    2. For each event, run analyze_event
    3. Filter picks by min_confidence and min_edge
    4. Dedup: don't re-predict same event+bet_type if already predicted in last 24h
    5. Check for parlay opportunities
    6. Create Prediction model instances, add to DB
    7. Return new predictions
    """
    all_picks = []  # (pick_dict, event_dict, sport_key, sport_display)
    events_analyzed = 0

    for sport_key in ACTIVE_SPORTS:
        # Map key back to display name
        sport_display = sport_key
        for display, key in SPORT_KEYS.items():
            if key == sport_key:
                sport_display = display
                break

        try:
            events = await odds_provider.get_odds(sport_key)
            if not events:
                continue

            for event in events:
                events_analyzed += 1
                picks = analyze_event(event, sport_key)
                for pick in picks:
                    if pick["confidence"] >= MIN_CONFIDENCE and pick["edge"] >= MIN_EDGE:
                        # Tag pick with sport display and event name for parlay
                        pick["_sport_display"] = sport_display
                        pick["_event_name"] = f"{event.get('away_team', '')} @ {event.get('home_team', '')}"
                        all_picks.append((pick, event, sport_key, sport_display))

                # Player props: only for sports with prop markets and events within 72h
                prop_markets_str = PROP_MARKETS.get(sport_key)
                if prop_markets_str:
                    ct_raw = event.get("commence_time")
                    if ct_raw:
                        try:
                            ct = datetime.fromisoformat(ct_raw.replace("Z", "+00:00"))
                            hours_until = (ct - datetime.now(timezone.utc)).total_seconds() / 3600
                            if 0 < hours_until <= 72:
                                eid = event.get("id", "")
                                logger.info(f"Fetching props for {sport_display} event {eid} ({hours_until:.0f}h out)")
                                try:
                                    prop_data = await odds_provider.get_event_odds(
                                        sport_key, eid, prop_markets_str
                                    )
                                    prop_picks = _analyze_player_props(prop_data, sport_key)
                                    qualifying = [p for p in prop_picks if p["confidence"] >= MIN_CONFIDENCE and p["edge"] >= MIN_EDGE]
                                    logger.info(f"Props for {eid}: {len(prop_picks)} analyzed, {len(qualifying)} qualifying")
                                    for pick in qualifying:
                                        pick["_sport_display"] = sport_display
                                        pick["_event_name"] = f"{event.get('away_team', '')} @ {event.get('home_team', '')}"
                                        all_picks.append((pick, event, sport_key, sport_display))
                                except Exception as pe:
                                    logger.warning(f"Props fetch failed for {eid}: {pe}")
                        except (ValueError, AttributeError):
                            pass
        except Exception as e:
            logger.error(f"Failed to fetch/analyze odds for {sport_key}: {e}")
            continue

    if not all_picks:
        logger.info(f"No qualifying picks from {events_analyzed} events analyzed")
        return []

    # Dedup: check what we already predicted in the last 24h
    # For player_prop, use (event_id, bet_type, pick) to allow multiple different props per event
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(hours=DEDUP_HOURS)
    existing_result = await db.execute(
        select(Prediction.event_id, Prediction.bet_type, Prediction.pick).where(
            Prediction.created_at >= dedup_cutoff,
        )
    )
    existing_keys = set()
    for row in existing_result:
        if row[1] == "player_prop":
            existing_keys.add((row[0], row[1], row[2]))
        else:
            existing_keys.add((row[0], row[1]))

    new_predictions = []
    parlay_candidates = []

    for pick, event, sport_key, sport_display in all_picks:
        event_id = event.get("id", "")
        bet_type = pick["bet_type"]

        if bet_type == "player_prop":
            dedup_key = (event_id, bet_type, pick["pick"])
        else:
            dedup_key = (event_id, bet_type)
        if dedup_key in existing_keys:
            continue

        # Parse commence_time
        commence_time = datetime.now(timezone.utc)
        ct_raw = event.get("commence_time")
        if ct_raw:
            try:
                commence_time = datetime.fromisoformat(ct_raw.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        home_team = event.get("home_team", "")
        away_team = event.get("away_team", "")
        league = event.get("sport_title", sport_display)

        # Build pick_detail with extra data
        pick_detail = {}
        if pick.get("line") is not None:
            pick_detail["line"] = pick["line"]
        if pick.get("consensus_prob") is not None:
            pick_detail["consensus_prob"] = pick["consensus_prob"]
        if pick.get("num_bookmakers"):
            pick_detail["num_bookmakers"] = pick["num_bookmakers"]
        if pick.get("prop_market"):
            pick_detail["prop_market"] = pick["prop_market"]

        prediction = Prediction(
            sport=sport_display,
            league=league,
            event_id=event_id,
            home_team=home_team,
            away_team=away_team,
            commence_time=commence_time,
            bet_type=bet_type,
            pick=pick["pick"],
            pick_detail=pick_detail,
            best_odds=pick["best_odds"],
            best_bookmaker=pick["best_bookmaker"],
            implied_probability=pick["implied_probability"],
            confidence=pick["confidence"],
            edge=pick["edge"],
            reasoning=pick["reasoning"],
            result="pending",
            created_at=datetime.now(timezone.utc),
        )
        db.add(prediction)
        new_predictions.append(prediction)
        existing_keys.add(dedup_key)
        parlay_candidates.append(pick)

    # Check for parlay opportunity across all new picks
    parlay = build_parlay(parlay_candidates)
    if parlay:
        parlay_event_id = f"parlay_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"
        if (parlay_event_id, "parlay") not in existing_keys:
            parlay_prediction = Prediction(
                sport="Multi",
                league="Parlay",
                event_id=parlay_event_id,
                home_team="Multi",
                away_team="Multi",
                commence_time=datetime.now(timezone.utc),
                bet_type="parlay",
                pick=parlay["pick"][:200],
                pick_detail={},
                best_odds=parlay["best_odds"],
                best_bookmaker=parlay["best_bookmaker"],
                implied_probability=parlay["implied_probability"],
                confidence=parlay["confidence"],
                edge=parlay["edge"],
                reasoning=parlay["reasoning"],
                parlay_legs=parlay.get("parlay_legs"),
                result="pending",
                created_at=datetime.now(timezone.utc),
            )
            db.add(parlay_prediction)
            new_predictions.append(parlay_prediction)

    await db.flush()
    logger.info(
        f"Generated {len(new_predictions)} predictions from {events_analyzed} events "
        f"({len(all_picks)} picks passed filters)"
    )
    return new_predictions


async def settle_predictions(db: AsyncSession) -> int:
    """Settle pending predictions by matching against completed game scores."""
    result = await db.execute(
        select(Prediction).where(Prediction.result == "pending")
    )
    pending = result.scalars().all()
    if not pending:
        return 0

    # Group pending predictions by sport key for batch score fetching
    sport_predictions: dict[str, list] = {}
    for pred in pending:
        sport_key = SPORT_KEYS.get(pred.sport)
        if not sport_key:
            if pred.sport in ACTIVE_SPORTS:
                sport_key = pred.sport
            else:
                continue
        sport_predictions.setdefault(sport_key, []).append(pred)

    # Fetch scores for each sport
    scores_by_event: dict[str, dict] = {}
    for sport_key in sport_predictions:
        try:
            scores = await odds_provider.get_scores(sport_key, days_from=3)
            for score_event in scores:
                if score_event.get("completed"):
                    scores_by_event[score_event.get("id", "")] = score_event
        except Exception as e:
            logger.error(f"Failed to fetch scores for {sport_key}: {e}")
            continue

    settled_count = 0

    for pred in pending:
        # Skip parlays
        if pred.bet_type == "parlay":
            continue

        # Player props: void when game completes (no player stat API for settlement)
        if pred.bet_type == "player_prop":
            score_event = scores_by_event.get(pred.event_id)
            if score_event:
                event_scores = score_event.get("scores", [])
                if len(event_scores) >= 2:
                    home = score_event.get("home_team", "")
                    away = score_event.get("away_team", "")
                    hs = next((float(s.get("score", 0)) for s in event_scores if s.get("name") == home), 0)
                    aws = next((float(s.get("score", 0)) for s in event_scores if s.get("name") == away), 0)
                    pred.result = "void"
                    pred.actual_score = f"{away} {int(aws)} - {home} {int(hs)}"[:50]
                    pred.pnl_units = 0.0
                    pred.settled_at = datetime.now(timezone.utc)
                    settled_count += 1
            continue

        score_event = scores_by_event.get(pred.event_id)
        if not score_event:
            continue

        event_scores = score_event.get("scores")
        if not event_scores or len(event_scores) < 2:
            continue

        home_team = score_event.get("home_team", "")
        away_team = score_event.get("away_team", "")

        score_lookup: dict[str, float] = {}
        for s in event_scores:
            team_name = s.get("name", "")
            try:
                score_val = float(s.get("score", 0))
            except (ValueError, TypeError):
                score_val = 0
            score_lookup[team_name] = score_val

        home_score = score_lookup.get(home_team, 0)
        away_score = score_lookup.get(away_team, 0)
        actual_score_str = f"{away_team} {int(away_score)} - {home_team} {int(home_score)}"[:50]

        prediction_result = "pending"
        pnl = 0.0

        if pred.bet_type == "moneyline":
            pick_team = pred.pick.replace(" ML", "").strip()
            pick_score = score_lookup.get(pick_team)
            opponent_score = None
            if pick_score is None:
                for team_name, team_score in score_lookup.items():
                    if pick_team in team_name or team_name in pick_team:
                        pick_score = team_score
                        opp = [v for k, v in score_lookup.items() if k != team_name]
                        opponent_score = opp[0] if opp else 0
                        break
                else:
                    continue
            else:
                opp = [v for k, v in score_lookup.items() if k != pick_team]
                opponent_score = opp[0] if opp else 0

            if pick_score > opponent_score:
                prediction_result = "win"
            elif pick_score < opponent_score:
                prediction_result = "loss"
            else:
                prediction_result = "push"

        elif pred.bet_type == "spread":
            parts = pred.pick.rsplit(" ", 1)
            if len(parts) != 2:
                continue
            pick_team = parts[0].strip()
            spread_line = (pred.pick_detail or {}).get("line")
            if spread_line is None:
                try:
                    spread_line = float(parts[1])
                except ValueError:
                    continue

            pick_score = score_lookup.get(pick_team)
            opponent_score = None
            if pick_score is None:
                for team_name, team_score in score_lookup.items():
                    if pick_team in team_name or team_name in pick_team:
                        pick_score = team_score
                        opp = [v for k, v in score_lookup.items() if k != team_name]
                        opponent_score = opp[0] if opp else 0
                        break
                else:
                    continue
            else:
                opp = [v for k, v in score_lookup.items() if k != pick_team]
                opponent_score = opp[0] if opp else 0

            adjusted_score = pick_score + spread_line
            if adjusted_score > opponent_score:
                prediction_result = "win"
            elif adjusted_score < opponent_score:
                prediction_result = "loss"
            else:
                prediction_result = "push"

        elif pred.bet_type == "total":
            total_line = (pred.pick_detail or {}).get("line")
            if total_line is None:
                continue
            actual_total = home_score + away_score
            is_over = "Over" in pred.pick

            if is_over:
                if actual_total > total_line:
                    prediction_result = "win"
                elif actual_total < total_line:
                    prediction_result = "loss"
                else:
                    prediction_result = "push"
            else:
                if actual_total < total_line:
                    prediction_result = "win"
                elif actual_total > total_line:
                    prediction_result = "loss"
                else:
                    prediction_result = "push"

        # Calculate PnL units
        if prediction_result == "win":
            if pred.best_odds > 0:
                pnl = pred.best_odds / 100.0
            else:
                pnl = 100.0 / abs(pred.best_odds)
        elif prediction_result == "loss":
            pnl = -1.0
        else:
            pnl = 0.0

        pred.result = prediction_result
        pred.actual_score = actual_score_str
        pred.pnl_units = round(pnl, 2)
        pred.settled_at = datetime.now(timezone.utc)
        settled_count += 1

    if settled_count:
        logger.info(f"Settled {settled_count} predictions from {len(pending)} pending")

    return settled_count
