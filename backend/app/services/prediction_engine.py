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


# ── Scoring ─────────────────────────────────────────────────────────

def score_pick(
    edge: float, num_agreeing: int, best_odds: int | float, sport: str
) -> float:
    """Score a pick 0-100.

    Weighted factors:
    - Edge (40%): higher edge = higher score
    - Consensus (25%): more bookmakers agreeing = more reliable
    - Odds value (15%): moderate plus odds preferred (best value zone is +100 to +250)
    - Sport reliability (10%): major sports weighted higher
    - Line sharpness (10%): more bookmakers = sharper line
    """
    # Edge component: 0-40 points. 2% edge = 20pts, 5% edge = 40pts
    edge_pct = edge * 100
    edge_score = min(edge_pct * 8, 40)

    # Consensus: 0-25 points.
    consensus_score = min(num_agreeing * 5, 25)

    # Odds value: 0-15 points. Sweet spot is +100 to +250
    if best_odds > 0:
        if 100 <= best_odds <= 250:
            odds_score = 15
        elif best_odds < 100:
            odds_score = 10
        else:
            odds_score = max(15 - (best_odds - 250) * 0.03, 5)
    else:
        # Negative odds: less value, cap at 10
        odds_score = max(10 + best_odds * 0.02, 3)

    # Sport reliability: 0-10 points
    sport_weight = SPORT_WEIGHTS.get(sport, 0.8)
    sport_score = sport_weight * 10

    # Line sharpness: 0-10 points
    sharpness_score = min(num_agreeing * 1.5, 10)

    total = edge_score + consensus_score + odds_score + sport_score + sharpness_score
    return round(min(total, 100), 1)


# ── Market analyzers ────────────────────────────────────────────────

def _analyze_moneyline(event: dict, sport: str) -> list[dict]:
    """Analyze h2h (moneyline) market for a single event."""
    picks = []
    bookmakers = event.get("bookmakers", [])
    if len(bookmakers) < MIN_BOOKMAKERS:
        return picks

    home_team = event.get("home_team", "")
    away_team = event.get("away_team", "")

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

        implied_probs = [american_to_implied(p) for p, _ in entries]
        consensus_prob = sum(implied_probs) / len(implied_probs)

        # Find best odds (highest price = lowest implied prob = most value)
        best_entry = max(entries, key=lambda x: x[0])
        best_price, best_book = best_entry
        best_prob = american_to_implied(best_price)

        edge = consensus_prob - best_prob
        if edge < MIN_EDGE:
            continue

        num_agreeing = sum(1 for p, _ in entries if american_to_implied(p) < consensus_prob + 0.01)
        confidence = score_pick(edge, num_agreeing, best_price, sport)

        reasons = []
        reasons.append(f"{team} ML at {best_price:+.0f}")
        reasons.append(f"consensus implied: {consensus_prob*100:.1f}%, best implied: {best_prob*100:.1f}%")
        reasons.append(f"edge: {edge*100:.1f}% across {len(entries)} books")

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

    return picks


def _analyze_spread(event: dict, sport: str) -> list[dict]:
    """Analyze spreads market for a single event."""
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

        implied_probs = [american_to_implied(pr) for _, pr, _ in near_consensus]
        consensus_prob = sum(implied_probs) / len(implied_probs)

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

        if edge < MIN_EDGE:
            continue

        num_agreeing = sum(1 for _, pr, _ in near_consensus if american_to_implied(pr) < consensus_prob + 0.01)
        confidence = score_pick(edge, num_agreeing, best_price, sport)

        reasons = []
        reasons.append(f"spread {best_point:+.1f} at {best_price}")
        if point_advantage > 0:
            reasons.append(f"{point_advantage:.1f}pt better than consensus {consensus_point:+.1f}")
        reasons.append(f"edge: {edge*100:.1f}% across {len(entries)} books")

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

        implied_probs = [american_to_implied(pr) for _, pr, _ in near_consensus]
        consensus_prob = sum(implied_probs) / len(implied_probs)

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

        num_agreeing = sum(1 for _, pr, _ in near_consensus if american_to_implied(pr) < consensus_prob + 0.01)
        confidence = score_pick(edge, num_agreeing, best_price, sport)

        reasons = []
        reasons.append(f"{side} {best_point} at {best_price}")
        reasons.append(f"consensus line: {consensus_point}, edge: {edge*100:.1f}%")
        reasons.append(f"{len(entries)} books offering totals")

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

    return picks


def _analyze_player_props(event_data: dict, sport: str) -> list[dict]:
    """Analyze player prop markets for a single event.

    Handles two patterns:
    A. Over/Under props (pass yds, rush yds, points, etc.)
    B. Anytime/Yes-No props (anytime TD)
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
                name = outcome.get("name", "")
                description = outcome.get("description", "")  # "Over"/"Under" or "Yes"
                price = outcome.get("price")
                point = outcome.get("point")  # None for anytime props
                if name and price is not None and description:
                    key = (name, market_key, description)
                    prop_data.setdefault(key, []).append(
                        (price, point, bm.get("key", ""))
                    )

    # Group by (player, market) to analyze
    # For over/under: analyze Over and Under separately
    # For anytime: only "Yes" matters
    processed = set()

    for (player, market_key, desc), entries in prop_data.items():
        if len(entries) < 3:
            continue

        group_key = (player, market_key, desc)
        if group_key in processed:
            continue
        processed.add(group_key)

        # Skip "Under" and "No" — we only generate picks for Over/Yes
        if desc in ("Under", "No"):
            continue

        is_over_under = desc == "Over"
        is_anytime = desc == "Yes"

        if not is_over_under and not is_anytime:
            continue

        if is_over_under:
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

            implied_probs = [american_to_implied(pr) for pr, _, _ in near]
            consensus_prob = sum(implied_probs) / len(implied_probs)

            # Best entry: lowest line with best price for Over
            best_entry = min(entries, key=lambda x: (x[1] if x[1] is not None else 999, -x[0]))
            best_price, best_point, best_book = best_entry
            if best_point is None:
                continue
            best_prob = american_to_implied(best_price)

            edge = consensus_prob - best_prob
            # Line advantage bonus
            line_diff = consensus_line - best_point
            if line_diff > 0:
                edge += 0.01 * line_diff

            if edge < MIN_EDGE:
                continue

            # Format market name nicely
            market_label = market_key.replace("player_", "").replace("_", " ").title()
            pick_text = f"{player} Over {best_point} {market_label}"

            num_agreeing = sum(1 for pr, _, _ in near
                               if american_to_implied(pr) < consensus_prob + 0.01)
            confidence = score_pick(edge, num_agreeing, best_price, sport)

            reasons = [
                f"{pick_text} at {best_price:+.0f}",
                f"consensus line: {consensus_line}, consensus prob: {consensus_prob*100:.1f}%",
                f"edge: {edge*100:.1f}% across {len(entries)} books",
            ]

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

        elif is_anytime:
            # Anytime prop (e.g. anytime TD scorer): no point, just Yes price
            implied_probs = [american_to_implied(pr) for pr, _, _ in entries]
            consensus_prob = sum(implied_probs) / len(implied_probs)

            best_entry = max(entries, key=lambda x: x[0])
            best_price, _, best_book = best_entry
            best_prob = american_to_implied(best_price)

            edge = consensus_prob - best_prob
            if edge < MIN_EDGE:
                continue

            market_label = market_key.replace("player_", "").replace("_", " ").title()
            pick_text = f"{player} {market_label}"

            num_agreeing = sum(1 for pr, _, _ in entries
                               if american_to_implied(pr) < consensus_prob + 0.01)
            confidence = score_pick(edge, num_agreeing, best_price, sport)

            reasons = [
                f"{pick_text} at {best_price:+.0f}",
                f"consensus prob: {consensus_prob*100:.1f}%, best implied: {best_prob*100:.1f}%",
                f"edge: {edge*100:.1f}% across {len(entries)} books",
            ]

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
            })

    return picks


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
        implied = 1.0 - leg.get("implied_probability", 0.5)
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

                # Player props: only for sports with prop markets and events within 48h
                prop_markets_str = PROP_MARKETS.get(sport_key)
                if prop_markets_str:
                    ct_raw = event.get("commence_time")
                    if ct_raw:
                        try:
                            ct = datetime.fromisoformat(ct_raw.replace("Z", "+00:00"))
                            hours_until = (ct - datetime.now(timezone.utc)).total_seconds() / 3600
                            if 0 < hours_until <= 48:
                                eid = event.get("id", "")
                                try:
                                    prop_data = await odds_provider.get_event_odds(
                                        sport_key, eid, prop_markets_str
                                    )
                                    prop_picks = _analyze_player_props(prop_data, sport_key)
                                    for pick in prop_picks:
                                        if pick["confidence"] >= MIN_CONFIDENCE and pick["edge"] >= MIN_EDGE:
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
        # Skip parlays and player props (no player stat API for settlement yet)
        if pred.bet_type in ("parlay", "player_prop"):
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
        actual_score_str = f"{away_team} {int(away_score)} - {home_team} {int(home_score)}"

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
