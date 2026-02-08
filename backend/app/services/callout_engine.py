from __future__ import annotations
import math
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.token import ScannedToken
from app.models.trader_snapshot import TraderSnapshot
from app.models.callout import Callout, Signal
from app.models.smart_wallet import SmartWallet
from app.models.token_snapshot import TokenSnapshot

logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────────────
BUY_THRESHOLD = 55
WATCH_THRESHOLD = 38
MIN_LIQUIDITY = 5000
MIN_LIQUIDITY_MICRO = 1000

# ── Dedup & Repin ───────────────────────────────────────────────────────
BUY_WATCH_DEDUP_HOURS = 72
SELL_DEDUP_HOURS = 24
REPIN_SCORE_DELTA = 10
REPIN_COOLDOWN_HOURS = 6

# ── Wallet classification weights for smart wallet signal ───────────────
WALLET_TYPE_WEIGHTS = {
    "sniper": 3.0,
    "kol": 2.0,
    "whale": 2.0,
    "insider": 1.5,
    "smart_money": 1.0,
    "unknown": 0.0,
}


# ═══════════════════════════════════════════════════════════════════════
# Helper: Volume Velocity from TokenSnapshot history
# ═══════════════════════════════════════════════════════════════════════

async def _get_volume_velocity(db: AsyncSession, token_address: str) -> float:
    """Calculate rate of volume change across recent snapshots.
    Returns multiplier: 1.0 = stable, >1.0 = accelerating, <1.0 = declining."""
    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    result = await db.execute(
        select(TokenSnapshot)
        .where(
            TokenSnapshot.token_address == token_address,
            TokenSnapshot.snapshot_at >= two_hours_ago,
        )
        .order_by(TokenSnapshot.snapshot_at.asc())
    )
    snapshots = result.scalars().all()
    if len(snapshots) < 3:
        return 1.0

    recent = snapshots[-3:]  # last 3 cycles
    deltas = []
    for s1, s2 in zip(recent, recent[1:]):
        if s1.volume > 0:
            deltas.append((s2.volume - s1.volume) / s1.volume)
        else:
            deltas.append(0.0)
    return 1.0 + sum(deltas) / len(deltas)


# ═══════════════════════════════════════════════════════════════════════
# Helper: Smart wallet lookup for a set of wallet addresses
# ═══════════════════════════════════════════════════════════════════════

async def _lookup_smart_wallets(db: AsyncSession, wallet_addresses: list[str]) -> dict[str, SmartWallet]:
    """Look up SmartWallet records for given addresses. Returns {addr: SmartWallet}."""
    if not wallet_addresses:
        return {}
    result = await db.execute(
        select(SmartWallet).where(SmartWallet.wallet_address.in_(wallet_addresses))
    )
    wallets = result.scalars().all()
    return {w.wallet_address: w for w in wallets}


def _weighted_smart_wallet_score(smart_wallets: dict[str, SmartWallet], max_pts: float) -> float:
    """Score based on smart wallet classifications. Weighted sum capped at max_pts."""
    if not smart_wallets:
        return 0.0
    weighted_sum = sum(
        WALLET_TYPE_WEIGHTS.get(w.label, 0.0) for w in smart_wallets.values()
    )
    # Normalize: ~10 weighted points = full score
    return max_pts * min(weighted_sum / 10.0, 1.0)


# ═══════════════════════════════════════════════════════════════════════
# Quality gate (unchanged from original)
# ═══════════════════════════════════════════════════════════════════════

def _passes_quality_gate(token: ScannedToken) -> bool:
    """Reject tokens with no market cap or clearly insufficient liquidity."""
    if token.market_cap <= 0:
        return False
    if token.liquidity > 0:
        min_liq = MIN_LIQUIDITY_MICRO if token.scan_source == "print_scan" else MIN_LIQUIDITY
        if token.liquidity < min_liq:
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════
# MICRO-CAP SCORING (print_scan, mcap < $500K) — 100 pts + bonuses
# ═══════════════════════════════════════════════════════════════════════

async def _score_micro_token(db: AsyncSession, token: ScannedToken) -> tuple[float, str, list[str], dict]:
    """Score a micro-cap / print_scan token 0-100 with enhanced security-weighted scoring.
    Returns (score, reason, smart_wallet_list, score_breakdown)."""
    reasons = []
    breakdown = {}

    # --- 1. Security Safety (25 pts) ---
    security_score = 25.0
    rugcheck = None
    try:
        from app.services.rugcheck import rugcheck_client
        rugcheck = await rugcheck_client.get_token_report(token.address)
    except Exception:
        pass

    if rugcheck:
        # Use Rugcheck full analysis
        for risk in rugcheck.get("risks", []):
            level = risk.get("level", "")
            if level in ("danger", "critical"):
                security_score -= 10
            elif level in ("warn", "warning"):
                security_score -= 3
            elif level == "info":
                security_score -= 1
        # LP lock bonus
        if rugcheck.get("lp_locked"):
            security_score = min(security_score + 3, 25)
    else:
        # Fallback to basic checks
        if token.has_mint_authority:
            security_score -= 12
            reasons.append("mint authority active")
        if token.has_freeze_authority:
            security_score -= 8
            reasons.append("freeze authority active")
        if token.is_mutable:
            security_score -= 5
            reasons.append("metadata mutable")
    security_score = max(security_score, 0)
    breakdown["security"] = round(security_score, 1)

    # --- 2. Early Buyer Quality (15 pts) ---
    early_buyer_score = 0.0
    early_smart_count = 0
    micro_early_data = False
    try:
        from app.services.onchain_analyzer import onchain_analyzer
        early_buyers = await onchain_analyzer.get_early_buyers(token.address, limit=20)
        if early_buyers:
            micro_early_data = True
            buyer_wallets = [b["wallet"] for b in early_buyers]
            smart_wallets_map = await _lookup_smart_wallets(db, buyer_wallets)
            early_smart_count = len(smart_wallets_map)
            early_buyer_score = 15.0 * min(early_smart_count / 5.0, 1.0)
            if early_smart_count > 0:
                reasons.append(f"{early_smart_count} smart wallets in first 20 buyers")
    except Exception as e:
        logger.debug(f"Early buyer analysis failed for {token.symbol}: {e}")
    # Neutral baseline when data source is unavailable
    if not micro_early_data:
        early_buyer_score = 7.0
    breakdown["early_buyers"] = round(early_buyer_score, 1)

    # --- 3. Holder Distribution (15 pts) ---
    holder_score = 0.0
    top10 = token.top10_holder_pct or 0
    if 30 <= top10 <= 60:
        holder_score = 15.0
    elif 20 <= top10 < 30 or 60 < top10 <= 75:
        holder_score = 10.5
    elif top10 <= 80:
        holder_score = 6.0
    else:
        holder_score = 1.5
        reasons.append(f"top10 hold {top10:.0f}%")
    if token.dev_sold:
        holder_score = min(holder_score + 3, 15)
        reasons.append("dev sold")
    if (token.dev_wallet_pct or 0) < 5:
        holder_score = min(holder_score + 2, 15)
    breakdown["holders"] = round(holder_score, 1)

    # --- 4. Volume Velocity (12 pts) ---
    velocity = await _get_volume_velocity(db, token.address)
    if velocity > 2.0:
        vol_vel_score = 12.0
        reasons.append("volume accelerating")
    elif velocity > 1.5:
        vol_vel_score = 9.0
    elif velocity > 1.2:
        vol_vel_score = 7.0
    elif velocity > 1.0:
        vol_vel_score = 4.0
    else:
        vol_vel_score = 2.0
    # Fallback: also consider raw volume/mcap ratio
    if token.volume_24h > 0 and token.market_cap > 0:
        vol_mcap = token.volume_24h / token.market_cap
        vol_vel_score = max(vol_vel_score, 12.0 * min(vol_mcap / 2.0, 1.0))
    breakdown["volume_velocity"] = round(vol_vel_score, 1)

    # --- 5. Freshness (10 pts) — exponential decay ---
    freshness_score = 0.5  # minimum
    if token.created_at_chain:
        age_minutes = (datetime.now(timezone.utc) - token.created_at_chain).total_seconds() / 60
        freshness_score = max(10.0 * math.exp(-age_minutes / 30.0), 0.5)
        if age_minutes < 10:
            reasons.append("brand new (<10min)")
        elif age_minutes < 30:
            reasons.append("very fresh (<30min)")
    else:
        freshness_score = 2.0
    breakdown["freshness"] = round(freshness_score, 1)

    # --- 6. Buy Pressure (8 pts) ---
    buy_sell_score = 0.0
    buy_count = token.buy_count_24h or 0
    sell_count = token.sell_count_24h or 0
    total_count = buy_count + sell_count
    if total_count > 0:
        buy_ratio = buy_count / total_count
        buy_sell_score = 8.0 * min(buy_ratio / 0.8, 1.0)
        if buy_ratio > 0.7:
            reasons.append(f"strong buy pressure ({buy_ratio*100:.0f}% buys)")
    breakdown["buy_pressure"] = round(buy_sell_score, 1)

    # --- 7. Liquidity Floor (5 pts) ---
    liquidity_score = 0.0
    if token.liquidity >= 1000:
        liquidity_score = 5.0 * min(token.liquidity / 20000, 1.0)
    breakdown["liquidity"] = round(liquidity_score, 1)

    # --- 8. Social Signal (5 pts) ---
    social_score = 0.0
    if token.social_mention_count > 0:
        social_score = min(token.social_mention_count * 0.8, 5.0)
    else:
        # Neutral baseline when social data isn't collected yet
        social_score = 2.5
    breakdown["social"] = round(social_score, 1)

    # --- 9. Wallet Overlap Bonus (+5) ---
    overlap_bonus = 0.0
    # Check if reputable wallets from early buyers are also in other recent runners
    if early_smart_count >= 3:
        overlap_bonus = 5.0
        reasons.append("smart wallet overlap with other tokens")
    elif not micro_early_data:
        # Neutral baseline when SmartWallet DB isn't populated yet
        overlap_bonus = 2.0
    breakdown["wallet_overlap"] = round(overlap_bonus, 1)

    # --- 10. Anti-Rug Gate (-30 penalty) ---
    penalty = 0.0
    if rugcheck:
        penalty -= rugcheck.get("critical_risk_count", 0) * 10
    if token.has_mint_authority and (token.dev_wallet_pct or 0) > 30:
        penalty -= 15
        reasons.insert(0, "HIGH RUG RISK")
    if (token.top10_holder_pct or 0) > 90:
        penalty -= 5
    penalty = max(penalty, -30)
    breakdown["anti_rug"] = round(penalty, 1)

    total_score = (
        security_score + early_buyer_score + holder_score + vol_vel_score
        + freshness_score + buy_sell_score + liquidity_score + social_score
        + overlap_bonus + penalty
    )
    total_score = round(max(min(total_score, 100), 0), 1)

    if not reasons:
        reasons.append("early micro-cap with moderate signals")

    # Collect smart wallet addresses from early buyers
    smart_wallet_list = []
    if early_smart_count > 0:
        try:
            smart_wallet_list = [b["wallet"] for b in early_buyers if b["wallet"] in smart_wallets_map]
        except Exception:
            pass

    return total_score, "; ".join(reasons), smart_wallet_list, breakdown


# ═══════════════════════════════════════════════════════════════════════
# TRENDING TOKEN SCORING (mcap >= $500K) — 100 pts + bonuses
# ═══════════════════════════════════════════════════════════════════════

async def score_token(
    db: AsyncSession, token: ScannedToken
) -> tuple[float, str, list[str], dict]:
    """Score a token 0-100 based on enhanced 12-factor model.
    Returns (score, reason, smart_wallet_list, score_breakdown).
    """
    # Route micro-cap print_scan tokens to dedicated scorer
    if token.market_cap < 500_000 and token.scan_source == "print_scan":
        return await _score_micro_token(db, token)

    reasons = []
    breakdown = {}

    # Fetch recent trader snapshots (last 2 hours)
    two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    result = await db.execute(
        select(TraderSnapshot).where(
            TraderSnapshot.token_address == token.address,
            TraderSnapshot.scanned_at >= two_hours_ago,
        )
    )
    snapshots = result.scalars().all()
    total_traders = len(snapshots)
    buyers = [s for s in snapshots if s.volume_buy > s.volume_sell]
    sellers = [s for s in snapshots if s.volume_sell > s.volume_buy]
    profitable_buyers = [s for s in buyers if s.estimated_pnl > 0]
    all_buyer_wallets = list(set(s.wallet for s in buyers))

    # Look up smart wallets for all buyers
    smart_wallets_map = await _lookup_smart_wallets(db, all_buyer_wallets)
    smart_wallet_list = list(smart_wallets_map.keys())

    # --- 1. Smart Wallet Signal (20 pts) ---
    smart_wallet_score = _weighted_smart_wallet_score(smart_wallets_map, 20.0)
    # Fallback to scanner's smart_money_count when SmartWallet DB is sparse
    if token.smart_money_count > 0 and smart_wallet_score < 5:
        smart_wallet_score = max(smart_wallet_score, 20.0 * min(token.smart_money_count / 5.0, 1.0))
    # Neutral baseline when both SmartWallet DB and scanner have no data
    if smart_wallet_score == 0 and not smart_wallets_map and (token.smart_money_count or 0) == 0:
        smart_wallet_score = 8.0
    if smart_wallet_score > 8:
        classified = [w.label for w in smart_wallets_map.values() if w.label != "unknown"]
        if classified:
            reasons.append(f"{len(smart_wallets_map)} smart wallets ({', '.join(set(classified))})")
        elif token.smart_money_count > 0:
            reasons.append(f"{token.smart_money_count} smart money wallets accumulating")
        else:
            reasons.append(f"{len(smart_wallets_map)} profitable wallets buying")
    breakdown["smart_wallet"] = round(smart_wallet_score, 1)

    # --- 2. Volume Velocity (15 pts) ---
    velocity = await _get_volume_velocity(db, token.address)
    if velocity > 2.0:
        vol_vel_score = 15.0
        reasons.append("volume surging")
    elif velocity > 1.5:
        vol_vel_score = 12.0
        reasons.append("volume accelerating")
    elif velocity > 1.2:
        vol_vel_score = 9.0
    elif velocity > 1.0:
        vol_vel_score = 6.0
    elif velocity > 0.8:
        vol_vel_score = 3.0
    else:
        vol_vel_score = 1.0
    # Fallback: volume spike ratio from trader snapshots
    if token.volume_24h > 0 and snapshots:
        avg_hourly = token.volume_24h / 24
        recent_buy_volume = sum(s.volume_buy for s in snapshots)
        if avg_hourly > 0 and recent_buy_volume > 0:
            spike_ratio = min(recent_buy_volume / avg_hourly, 3) / 3
            fallback_vol = 15.0 * spike_ratio
            vol_vel_score = max(vol_vel_score, fallback_vol)
    breakdown["volume_velocity"] = round(vol_vel_score, 1)

    # --- 3. Buy Pressure (12 pts) ---
    buy_sell_score = 0.0
    buy_count = token.buy_count_24h or len(buyers)
    sell_count = token.sell_count_24h or len(sellers)
    total_count = buy_count + sell_count
    if total_count > 0:
        buy_ratio = buy_count / total_count
        buy_sell_score = 12.0 * min(buy_ratio / 0.8, 1.0)
        if buy_ratio > 0.65:
            reasons.append(f"strong buy pressure ({buy_ratio*100:.0f}% buys)")
    breakdown["buy_pressure"] = round(buy_sell_score, 1)

    # --- 4. Early Buyer Quality (12 pts) ---
    early_buyer_score = 0.0
    early_smart_count = 0
    early_data_available = False
    try:
        from app.services.onchain_analyzer import onchain_analyzer
        early_buyers = await onchain_analyzer.get_early_buyers(token.address, limit=20)
        if early_buyers:
            early_data_available = True
            early_wallet_addrs = [b["wallet"] for b in early_buyers]
            early_smart = await _lookup_smart_wallets(db, early_wallet_addrs)
            early_smart_count = len(early_smart)
            early_buyer_score = 12.0 * min(early_smart_count / 5.0, 1.0)
            if early_smart_count > 0:
                reasons.append(f"{early_smart_count} smart wallets in first 20 buyers")
                # Add early smart wallets to the smart_wallet_list
                for addr in early_smart:
                    if addr not in smart_wallets_map:
                        smart_wallet_list.append(addr)
    except Exception as e:
        logger.debug(f"Early buyer analysis failed for {token.symbol}: {e}")
    # Neutral baseline when data source is unavailable
    if not early_data_available:
        early_buyer_score = 6.0
    breakdown["early_buyers"] = round(early_buyer_score, 1)

    # --- 5. Price Momentum (10 pts) ---
    momentum_score = 0.0
    pc5m = token.price_change_5m or 0
    pc1h = token.price_change_1h or 0
    # Composite: 5m weighted 0.6, 1h weighted 0.4
    raw_momentum = (pc5m * 0.6 + pc1h * 0.4)
    if raw_momentum > 20:
        momentum_score = 10.0
    elif raw_momentum > 10:
        momentum_score = 8.0
    elif raw_momentum > 5:
        momentum_score = 6.0
    elif raw_momentum > 0:
        momentum_score = 3.0
    else:
        momentum_score = 0.0
    # Acceleration bonus: both 5m and 1h positive
    if pc5m > 5 and pc1h > 5:
        momentum_score = min(momentum_score + 2, 10)
        reasons.append("price momentum")
    breakdown["momentum"] = round(momentum_score, 1)

    # --- 6. Token Freshness (8 pts) — exponential decay ---
    freshness_score = 0.5
    if token.created_at_chain:
        age_hours = (datetime.now(timezone.utc) - token.created_at_chain).total_seconds() / 3600
        freshness_score = max(8.0 * math.exp(-age_hours / 6.0), 0.5)
        if age_hours < 1:
            reasons.append("new token with early momentum")
    else:
        freshness_score = 1.6  # ~20% of max when unknown
    breakdown["freshness"] = round(freshness_score, 1)

    # --- 7. Holder Distribution (8 pts) ---
    holder_score = 0.0
    top10 = token.top10_holder_pct or 0
    if 30 <= top10 <= 60:
        holder_score = 8.0
    elif 20 <= top10 < 30 or 60 < top10 <= 75:
        holder_score = 5.6
    elif top10 <= 85:
        holder_score = 3.0
    else:
        holder_score = 1.0
    if (token.dev_wallet_pct or 0) < 5 and top10 > 0:
        holder_score = min(holder_score + 1.5, 8)
    breakdown["holders"] = round(holder_score, 1)

    # --- 8. Liquidity Health (5 pts) ---
    liquidity_score = 0.0
    if token.liquidity > 0 and token.market_cap > 0:
        liq_ratio = token.liquidity / token.market_cap
        liquidity_score = 5.0 * min(liq_ratio / 0.1, 1.0)
    # LP lock bonus from Rugcheck
    rugcheck = None
    try:
        if token.rugcheck_score is not None:
            # Already fetched during enrichment
            if token.rugcheck_score > 70:
                liquidity_score = min(liquidity_score + 1, 5)
    except Exception:
        pass
    breakdown["liquidity"] = round(liquidity_score, 1)

    # --- 9. Security Score (5 pts) ---
    sec_score = 0.0
    if token.rugcheck_score is not None:
        # rugcheck_score is safety 0-100 (100 = safe)
        sec_score = 5.0 * (token.rugcheck_score / 100.0)
    else:
        # Fallback: assume clean unless basic checks fail
        sec_score = 4.0
        if token.has_mint_authority:
            sec_score -= 1.5
        if token.has_freeze_authority:
            sec_score -= 1.0
        if token.is_mutable:
            sec_score -= 0.5
        sec_score = max(sec_score, 0)
    breakdown["security"] = round(sec_score, 1)

    # --- 10. Social Signal (5 pts) ---
    social_score = 0.0
    if token.social_mention_count > 0:
        social_score = min(token.social_mention_count * 0.8, 3.0)
        if token.social_velocity > 0:
            social_score = min(social_score + token.social_velocity * 2, 5.0)
    else:
        # Neutral baseline when social data isn't being collected yet
        social_score = 2.5
    breakdown["social"] = round(social_score, 1)

    # --- 11. Wallet Overlap Bonus (+5) ---
    overlap_bonus = 0.0
    # If 3+ reputable wallets (from SmartWallet DB with reputation > 60) are buying
    reputable_count = sum(
        1 for w in smart_wallets_map.values() if w.reputation_score >= 60
    )
    if reputable_count >= 3:
        overlap_bonus = 5.0
        reasons.append("multiple reputable wallets converging")
    elif not smart_wallets_map:
        # Neutral baseline when SmartWallet DB isn't populated yet
        overlap_bonus = 2.0
    breakdown["wallet_overlap"] = round(overlap_bonus, 1)

    # --- 12. Anti-Rug Gate (-20 penalty) ---
    penalty = 0.0
    # Rugcheck critical risks
    if token.rugcheck_score is not None and token.rugcheck_score < 30:
        penalty -= 10
    # Insider concentration
    if (token.top10_holder_pct or 0) > 80:
        penalty -= 5
    if (token.dev_wallet_pct or 0) > 40:
        penalty -= 5
        reasons.append("high insider concentration")
    # Mint authority on trending = mild concern
    if token.has_mint_authority:
        penalty -= 3
    penalty = max(penalty, -20)
    breakdown["anti_rug"] = round(penalty, 1)

    # ── Total ────────────────────────────────────────────────────────
    total_score = (
        smart_wallet_score + vol_vel_score + buy_sell_score + early_buyer_score
        + momentum_score + freshness_score + holder_score + liquidity_score
        + sec_score + social_score + overlap_bonus + penalty
    )
    total_score = round(max(min(total_score, 100), 0), 1)

    if len(sellers) > len(buyers) * 2:
        reasons.append("heavy selling pressure")
    if not reasons:
        reasons.append("moderate activity with mixed signals")

    reason = "; ".join(reasons)
    return total_score, reason, smart_wallet_list, breakdown


# ═══════════════════════════════════════════════════════════════════════
# SELL SIGNAL DETECTION (unchanged logic)
# ═══════════════════════════════════════════════════════════════════════

async def _check_sell_signals(db: AsyncSession) -> list[Callout]:
    """Check if tokens with previous BUY callouts now show heavy selling."""
    one_day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(hours=SELL_DEDUP_HOURS)

    result = await db.execute(
        select(Callout).where(
            Callout.signal == Signal.buy,
            Callout.created_at >= one_day_ago,
        )
    )
    buy_callouts = result.scalars().all()

    sell_callouts = []
    seen_tokens = set()

    for callout in buy_callouts:
        if callout.token_address in seen_tokens:
            continue

        recent_sell = await db.execute(
            select(Callout).where(
                Callout.token_address == callout.token_address,
                Callout.signal == Signal.sell,
                Callout.created_at >= dedup_cutoff,
            ).limit(1)
        )
        if recent_sell.scalars().first():
            continue

        token_result = await db.execute(
            select(ScannedToken).where(ScannedToken.address == callout.token_address)
        )
        token = token_result.scalar_one_or_none()
        if not token:
            continue

        sell_count = token.sell_count_24h or 0
        buy_count = token.buy_count_24h or 0
        total = sell_count + buy_count
        if total == 0:
            continue

        sell_ratio = sell_count / total
        if sell_ratio > 0.65 and token.price_change_1h < -5 and token.market_cap > 0:
            seen_tokens.add(callout.token_address)
            sell_callout = Callout(
                token_address=token.address,
                token_symbol=token.symbol,
                signal=Signal.sell,
                score=round(sell_ratio * 100, 1),
                reason=f"Heavy selling after BUY signal; {sell_ratio*100:.0f}% sells, price down {token.price_change_1h:.1f}% in 1h",
                smart_wallets=callout.smart_wallets or [],
                price_at_callout=token.price,
                scan_source=token.scan_source or "trending",
                token_name=token.name,
                market_cap=token.market_cap,
                volume_24h=token.volume_24h,
                liquidity=token.liquidity,
                holder_count=token.holder_count,
                rug_risk_score=token.rug_risk_score,
                created_at=datetime.now(timezone.utc),
            )
            db.add(sell_callout)
            sell_callouts.append(sell_callout)

    return sell_callouts


# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY: generate_callouts
# ═══════════════════════════════════════════════════════════════════════

async def generate_callouts(db: AsyncSession) -> list[Callout]:
    """Run enhanced 12-factor scoring on all recently scanned tokens and generate callouts."""
    five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    result = await db.execute(
        select(ScannedToken).where(ScannedToken.last_scanned >= five_minutes_ago)
    )
    tokens = result.scalars().all()

    new_callouts = []
    gate_passed = 0
    top_score = 0.0
    top_symbol = ""

    for token in tokens:
        if not _passes_quality_gate(token):
            continue
        gate_passed += 1

        score, reason, smart_wallets, breakdown = await score_token(db, token)

        if score > top_score:
            top_score = score
            top_symbol = token.symbol

        if score < WATCH_THRESHOLD:
            continue

        # Calculate volume velocity for storage
        velocity = await _get_volume_velocity(db, token.address)

        # Check for existing buy/watch callout within dedup window
        dedup_cutoff = datetime.now(timezone.utc) - timedelta(hours=BUY_WATCH_DEDUP_HOURS)
        existing_result = await db.execute(
            select(Callout).where(
                Callout.token_address == token.address,
                Callout.signal.in_([Signal.buy, Signal.watch]),
                Callout.created_at >= dedup_cutoff,
            ).limit(1)
        )
        existing_callout = existing_result.scalars().first()

        if existing_callout:
            # Repin if score gained significantly and cooldown passed
            repin_cutoff = datetime.now(timezone.utc) - timedelta(hours=REPIN_COOLDOWN_HOURS)
            already_repinned_recently = (
                existing_callout.repinned_at and existing_callout.repinned_at >= repin_cutoff
            )
            created_recently = existing_callout.created_at >= repin_cutoff

            if (
                score >= existing_callout.score + REPIN_SCORE_DELTA
                and not already_repinned_recently
                and not created_recently
            ):
                existing_callout.score = score
                existing_callout.reason = reason
                existing_callout.repinned_at = datetime.now(timezone.utc)
                existing_callout.score_breakdown = breakdown
                existing_callout.volume_velocity = velocity
                if score >= BUY_THRESHOLD and existing_callout.signal == Signal.watch:
                    existing_callout.signal = Signal.buy
                if smart_wallets:
                    existing_callout.smart_wallets = smart_wallets
                new_callouts.append(existing_callout)
                logger.info(f"Repinned {token.symbol} (score {existing_callout.score} -> {score})")
            continue

        signal = Signal.buy if score >= BUY_THRESHOLD else Signal.watch

        callout = Callout(
            token_address=token.address,
            token_symbol=token.symbol,
            signal=signal,
            score=score,
            reason=reason,
            smart_wallets=smart_wallets,
            price_at_callout=token.price,
            scan_source=token.scan_source or "trending",
            token_name=token.name,
            market_cap=token.market_cap,
            volume_24h=token.volume_24h,
            liquidity=token.liquidity,
            holder_count=token.holder_count,
            rug_risk_score=token.rug_risk_score,
            # New enhanced fields
            score_breakdown=breakdown,
            security_score=token.rugcheck_score,
            social_mentions=token.social_mention_count,
            early_smart_buyers=token.early_buyer_smart_count,
            volume_velocity=velocity,
            created_at=datetime.now(timezone.utc),
        )
        db.add(callout)
        new_callouts.append(callout)

    # Check for SELL signals
    sell_callouts = await _check_sell_signals(db)
    new_callouts.extend(sell_callouts)

    await db.flush()
    logger.info(
        f"Generated {len(new_callouts)} new callouts from {len(tokens)} tokens "
        f"({gate_passed} passed gate, top score: {top_symbol}={top_score})"
    )
    return new_callouts
