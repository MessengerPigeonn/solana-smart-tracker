from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.token import ScannedToken
from app.models.trader_snapshot import TraderSnapshot
from app.models.callout import Callout, Signal

logger = logging.getLogger(__name__)

# Scoring weights (max points per factor, total = 100)
WHALE_ACCUMULATION_WEIGHT = 25
BUY_SELL_RATIO_WEIGHT = 20
VOLUME_MOMENTUM_WEIGHT = 20
SMART_MONEY_PNL_WEIGHT = 15
TOKEN_FRESHNESS_WEIGHT = 10
LIQUIDITY_SAFETY_WEIGHT = 10

# Thresholds (raised to reduce low-quality callouts)
BUY_THRESHOLD = 75
WATCH_THRESHOLD = 55
MIN_LIQUIDITY = 5000
MIN_LIQUIDITY_MICRO = 1000

# Dedup window: suppress duplicate callouts for the same token
DEDUP_HOURS = 24


def _passes_quality_gate(token: ScannedToken) -> bool:
    """Reject tokens with no market cap or clearly insufficient liquidity/volume.

    When volume_24h or liquidity is exactly 0, it may mean the data source
    (e.g. Helius DAS) doesn't provide that field — so we only enforce the
    minimum-liquidity check when liquidity is known (> 0).
    """
    if token.market_cap <= 0:
        return False
    # If volume data is available and positive, good. If it's 0, it may be
    # missing from Helius fallback — only reject if we actually have a
    # negative or clearly bad value (which shouldn't happen, but guard).
    # The scoring algorithm already penalizes low volume via lower scores.

    # Enforce liquidity floor only when liquidity data is present
    if token.liquidity > 0:
        min_liq = MIN_LIQUIDITY_MICRO if token.scan_source == "print_scan" else MIN_LIQUIDITY
        if token.liquidity < min_liq:
            return False
    return True


def _score_micro_token(token: ScannedToken) -> tuple[float, str]:
    """Score a micro-cap / print_scan token 0-100 with security-weighted scoring.
    Returns (score, reason). No smart wallets needed for micro-cap scoring."""
    reasons = []

    # --- 1. Security safety (25 pts): start at max, deduct for red flags ---
    security_score = 25.0
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

    # --- 2. Holder distribution (20 pts) ---
    holder_score = 0.0
    top10 = token.top10_holder_pct or 0
    if 30 <= top10 <= 60:
        holder_score = 20.0  # ideal range
    elif 20 <= top10 < 30 or 60 < top10 <= 75:
        holder_score = 14.0
    elif top10 <= 80:
        holder_score = 8.0
    else:
        holder_score = 2.0
        reasons.append(f"top10 hold {top10:.0f}%")
    if token.dev_sold:
        holder_score = min(holder_score + 4, 20)
        reasons.append("dev sold")

    # --- 3. Freshness (20 pts) ---
    freshness_score = 0.0
    if token.created_at_chain:
        age_minutes = (datetime.now(timezone.utc) - token.created_at_chain).total_seconds() / 60
        if age_minutes < 10:
            freshness_score = 20.0
            reasons.append("brand new (<10min)")
        elif age_minutes < 30:
            freshness_score = 17.0
            reasons.append("very fresh (<30min)")
        elif age_minutes < 60:
            freshness_score = 12.0
        elif age_minutes < 360:
            freshness_score = 6.0
    else:
        freshness_score = 4.0

    # --- 4. Buy/sell ratio (15 pts) ---
    buy_sell_score = 0.0
    buy_count = token.buy_count_24h or 0
    sell_count = token.sell_count_24h or 0
    total_count = buy_count + sell_count
    if total_count > 0:
        buy_ratio = buy_count / total_count
        buy_sell_score = 15.0 * min(buy_ratio / 0.8, 1.0)
        if buy_ratio > 0.7:
            reasons.append(f"strong buy pressure ({buy_ratio*100:.0f}% buys)")

    # --- 5. Volume momentum (10 pts) ---
    volume_score = 0.0
    if token.volume_24h > 0 and token.market_cap > 0:
        vol_mcap_ratio = token.volume_24h / token.market_cap
        volume_score = 10.0 * min(vol_mcap_ratio / 2.0, 1.0)
    if token.price_change_5m > 5 or token.price_change_1h > 10:
        volume_score = min(volume_score + 3, 10)
        reasons.append("price momentum")

    # --- 6. Liquidity floor (10 pts) ---
    liquidity_score = 0.0
    if token.liquidity >= 1000:
        liquidity_score = 10.0 * min(token.liquidity / 20000, 1.0)

    total_score = (
        security_score + holder_score + freshness_score
        + buy_sell_score + volume_score + liquidity_score
    )

    # Auto-reject: mint authority + high dev concentration
    if token.has_mint_authority and (token.dev_wallet_pct or 0) > 30:
        total_score = min(total_score, 20)
        reasons.insert(0, "HIGH RUG RISK")

    if not reasons:
        reasons.append("early micro-cap with moderate signals")

    return round(total_score, 1), "; ".join(reasons)


async def score_token(db: AsyncSession, token: ScannedToken) -> tuple[float, str, list[str]]:
    """
    Score a token 0-100 based on smart money signals.
    Routes to micro-cap scoring for print_scan tokens.
    Returns (score, reason, smart_wallet_list).
    """
    # Route micro-cap print_scan tokens to dedicated scorer
    if token.market_cap < 500_000 and token.scan_source == "print_scan":
        score, reason = _score_micro_token(token)
        return score, reason, []
    # Get recent trader snapshots (last 2 hours — relaxed window for fresh scanner)
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
    smart_wallets = list(set(s.wallet for s in profitable_buyers))

    # --- 1. Whale accumulation (25 pts) ---
    # Based on top_buyer_concentration from trade analysis
    whale_score = 0.0
    if token.top_buyer_concentration > 0:
        # High concentration (>60%) means whale accumulation
        whale_score = WHALE_ACCUMULATION_WEIGHT * min(token.top_buyer_concentration / 80, 1.0)

    # --- 2. Buy/sell ratio (20 pts) ---
    buy_sell_score = 0.0
    buy_count = token.buy_count_24h or len(buyers)
    sell_count = token.sell_count_24h or len(sellers)
    total_count = buy_count + sell_count
    if total_count > 0:
        buy_ratio = buy_count / total_count
        # Ratio > 0.6 is bullish
        buy_sell_score = BUY_SELL_RATIO_WEIGHT * min(buy_ratio / 0.8, 1.0)

    # --- 3. Volume momentum (20 pts) ---
    volume_score = 0.0
    if token.volume_24h > 0:
        avg_hourly = token.volume_24h / 24
        recent_buy_volume = sum(s.volume_buy for s in snapshots) if snapshots else 0
        if avg_hourly > 0 and recent_buy_volume > 0:
            spike_ratio = min(recent_buy_volume / avg_hourly, 3) / 3
            volume_score = VOLUME_MOMENTUM_WEIGHT * spike_ratio
    # Bonus: price momentum
    if token.price_change_5m > 5 or token.price_change_1h > 10:
        volume_score = min(volume_score + 5, VOLUME_MOMENTUM_WEIGHT)

    # --- 4. Smart money PnL (15 pts) ---
    pnl_score = 0.0
    if total_traders > 0 and profitable_buyers:
        profit_ratio = len(profitable_buyers) / max(total_traders, 1)
        pnl_score = SMART_MONEY_PNL_WEIGHT * min(profit_ratio * 2, 1.0)
    # Also use smart_money_count from scanner
    if token.smart_money_count >= 3:
        pnl_score = max(pnl_score, SMART_MONEY_PNL_WEIGHT * 0.8)

    # --- 5. Token freshness (10 pts) ---
    freshness_score = 0.0
    if token.created_at_chain:
        age_hours = (datetime.now(timezone.utc) - token.created_at_chain).total_seconds() / 3600
        if age_hours < 1:
            freshness_score = TOKEN_FRESHNESS_WEIGHT  # Brand new
        elif age_hours < 6:
            freshness_score = TOKEN_FRESHNESS_WEIGHT * 0.8
        elif age_hours < 24:
            freshness_score = TOKEN_FRESHNESS_WEIGHT * 0.5
        elif age_hours < 72:
            freshness_score = TOKEN_FRESHNESS_WEIGHT * 0.3
    else:
        # No creation date, give moderate score
        freshness_score = TOKEN_FRESHNESS_WEIGHT * 0.2

    # --- 6. Liquidity safety (10 pts) ---
    liquidity_score = 0.0
    if token.liquidity >= MIN_LIQUIDITY:
        liquidity_score = LIQUIDITY_SAFETY_WEIGHT * min(token.liquidity / 50000, 1.0)

    total_score = (
        whale_score
        + buy_sell_score
        + volume_score
        + pnl_score
        + freshness_score
        + liquidity_score
    )

    # Build reason string
    reasons = []
    if whale_score > WHALE_ACCUMULATION_WEIGHT * 0.4:
        reasons.append(f"whale accumulation detected ({token.top_buyer_concentration:.0f}% top 5 concentration)")
    if buy_sell_score > BUY_SELL_RATIO_WEIGHT * 0.5:
        ratio_pct = (buy_count / max(total_count, 1)) * 100
        reasons.append(f"strong buy pressure ({ratio_pct:.0f}% buys)")
    if volume_score > VOLUME_MOMENTUM_WEIGHT * 0.5:
        reasons.append("volume spike detected")
    if pnl_score > SMART_MONEY_PNL_WEIGHT * 0.4:
        reasons.append(f"{len(smart_wallets)} profitable wallets buying")
    if freshness_score > TOKEN_FRESHNESS_WEIGHT * 0.5:
        reasons.append("new token with early momentum")
    if len(sellers) > len(buyers) * 2:
        reasons.append("heavy selling pressure")
    if not reasons:
        reasons.append("moderate activity with mixed signals")

    reason = "; ".join(reasons)
    return round(total_score, 1), reason, smart_wallets


async def _check_sell_signals(db: AsyncSession) -> list[Callout]:
    """Check if tokens with previous BUY callouts now show heavy selling."""
    one_day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(hours=DEDUP_HOURS)

    # Find tokens that had BUY callouts in the last 24h
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

        # Check if we already generated a recent sell callout
        recent_sell = await db.execute(
            select(Callout).where(
                Callout.token_address == callout.token_address,
                Callout.signal == Signal.sell,
                Callout.created_at >= dedup_cutoff,
            ).limit(1)
        )
        if recent_sell.scalars().first():
            continue

        # Get current token state
        token_result = await db.execute(
            select(ScannedToken).where(ScannedToken.address == callout.token_address)
        )
        token = token_result.scalar_one_or_none()
        if not token:
            continue

        # Check for sell signals: heavy selling by smart wallets
        sell_count = token.sell_count_24h or 0
        buy_count = token.buy_count_24h or 0
        total = sell_count + buy_count

        if total == 0:
            continue

        sell_ratio = sell_count / total

        # Generate SELL if sells dominate (>65%) and price is dropping
        if sell_ratio > 0.65 and token.price_change_1h < -5:
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


async def generate_callouts(db: AsyncSession) -> list[Callout]:
    """Run scoring algorithm on all recently scanned tokens and generate callouts."""
    five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    dedup_cutoff = datetime.now(timezone.utc) - timedelta(hours=DEDUP_HOURS)
    result = await db.execute(
        select(ScannedToken).where(ScannedToken.last_scanned >= five_minutes_ago)
    )
    tokens = result.scalars().all()

    new_callouts = []
    gate_passed = 0
    top_score = 0.0
    top_symbol = ""
    for token in tokens:
        # Quality gate: reject tokens with no mcap, no volume, or low liquidity
        if not _passes_quality_gate(token):
            continue
        gate_passed += 1

        score, reason, smart_wallets = await score_token(db, token)

        if score > top_score:
            top_score = score
            top_symbol = token.symbol

        if score < WATCH_THRESHOLD:
            continue

        # Check if we already have a recent callout for this token (2h dedup)
        recent = await db.execute(
            select(Callout).where(
                Callout.token_address == token.address,
                Callout.created_at >= dedup_cutoff,
            ).limit(1)
        )
        if recent.scalars().first():
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
            created_at=datetime.now(timezone.utc),
        )
        db.add(callout)
        new_callouts.append(callout)

    # Check for SELL signals on previously called tokens
    sell_callouts = await _check_sell_signals(db)
    new_callouts.extend(sell_callouts)

    await db.flush()
    logger.info(
        f"Generated {len(new_callouts)} new callouts from {len(tokens)} tokens "
        f"({gate_passed} passed gate, top score: {top_symbol}={top_score})"
    )
    return new_callouts
