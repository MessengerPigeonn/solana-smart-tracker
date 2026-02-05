from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from typing import Optional
from app.database import get_db, async_session
from app.models.user import User, Tier
from app.models.callout import Callout
from app.models.token import ScannedToken
from app.schemas.callout import CalloutResponse, CalloutListResponse, CalloutStatsResponse, TopCalloutResponse, MilestoneCountsResponse
from app.middleware.auth import get_optional_user, require_tier

router = APIRouter(prefix="/api/callouts", tags=["callouts"])


@router.get("", response_model=CalloutListResponse)
async def list_callouts(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    signal: Optional[str] = Query(None, pattern="^(buy|sell|watch)$"),
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    # Free users: last 5 only, delayed 5 min
    is_free = not user or user.tier == Tier.free
    five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    if is_free:
        limit = min(limit, 5)

    query = select(Callout)

    if signal:
        query = query.where(Callout.signal == signal)

    if is_free:
        query = query.where(Callout.created_at <= five_min_ago)

    count_query = select(func.count()).select_from(Callout)
    if signal:
        count_query = count_query.where(Callout.signal == signal)
    if is_free:
        count_query = count_query.where(Callout.created_at <= five_min_ago)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Sort by repinned_at if set, otherwise created_at — repinned callouts float to top
    sort_key = func.coalesce(Callout.repinned_at, Callout.created_at)
    result = await db.execute(
        query.order_by(sort_key.desc()).offset(offset).limit(limit)
    )
    callouts = result.scalars().all()

    return CalloutListResponse(
        callouts=[CalloutResponse.model_validate(c) for c in callouts],
        total=total,
    )


@router.get("/stats", response_model=CalloutStatsResponse)
async def callout_stats(
    db: AsyncSession = Depends(get_db),
):
    """Aggregated stats from the last 100 buy/watch callouts."""
    result = await db.execute(
        select(Callout)
        .where(Callout.signal.in_(["buy", "watch"]))
        .order_by(Callout.created_at.desc())
        .limit(100)
    )
    callouts = result.scalars().all()
    total_calls = len(callouts)

    if total_calls == 0:
        return CalloutStatsResponse(total_calls=0)

    buy_signals = sum(1 for c in callouts if c.signal.value == "buy")
    watch_signals = sum(1 for c in callouts if c.signal.value == "watch")
    sell_signals = 0  # These are buy/watch only

    # Get current market caps for multiplier computation
    addresses = list(set(c.token_address for c in callouts))
    token_result = await db.execute(
        select(ScannedToken).where(ScannedToken.address.in_(addresses))
    )
    tokens_by_addr = {t.address: t for t in token_result.scalars().all()}

    current_multipliers = []
    ath_multipliers = []
    best_ath = 0.0
    best_symbol = None
    best_address = None

    for c in callouts:
        if not c.market_cap or c.market_cap <= 0:
            continue

        # Current multiplier (cap at 50x to filter garbage data)
        token = tokens_by_addr.get(c.token_address)
        if token and token.market_cap > 0:
            mult = token.market_cap / c.market_cap
            if mult <= 50:
                # If coin peaked >= 1.2x, floor at 1.2x benchmark
                if c.peak_market_cap and c.peak_market_cap > 0:
                    peak_mult = c.peak_market_cap / c.market_cap
                    if peak_mult >= 1.2:
                        mult = max(mult, 1.2)
                current_multipliers.append(mult)

        # ATH multiplier (cap at 50x)
        if c.peak_market_cap and c.peak_market_cap > 0:
            ath_mult = c.peak_market_cap / c.market_cap
            if ath_mult <= 50:
                ath_multipliers.append(ath_mult)
                if ath_mult > best_ath:
                    best_ath = ath_mult
                    best_symbol = c.token_symbol
                    best_address = c.token_address

    avg_mult = round(sum(current_multipliers) / len(current_multipliers), 2) if current_multipliers else None
    avg_ath = round(sum(ath_multipliers) / len(ath_multipliers), 2) if ath_multipliers else None
    win_rate = round(sum(1 for m in current_multipliers if m >= 1.0) / len(current_multipliers) * 100, 1) if current_multipliers else None

    # Milestone counts based on ATH multipliers
    milestones = MilestoneCountsResponse(
        pct_20=sum(1 for m in ath_multipliers if m >= 1.2),
        pct_40=sum(1 for m in ath_multipliers if m >= 1.4),
        pct_60=sum(1 for m in ath_multipliers if m >= 1.6),
        pct_80=sum(1 for m in ath_multipliers if m >= 1.8),
        x2=sum(1 for m in ath_multipliers if m >= 2.0),
        x5=sum(1 for m in ath_multipliers if m >= 5.0),
        x10=sum(1 for m in ath_multipliers if m >= 10.0),
        x50=sum(1 for m in ath_multipliers if m >= 50.0),
        x100=sum(1 for m in ath_multipliers if m >= 100.0),
    )

    return CalloutStatsResponse(
        total_calls=total_calls,
        avg_multiplier=avg_mult,
        avg_ath_multiplier=avg_ath,
        win_rate=win_rate,
        best_call_symbol=best_symbol,
        best_call_address=best_address,
        best_call_ath_multiplier=round(best_ath, 2) if best_ath > 0 else None,
        buy_signals=buy_signals,
        watch_signals=watch_signals,
        sell_signals=sell_signals,
        milestones=milestones,
    )


@router.get("/top", response_model=Optional[TopCalloutResponse])
async def top_callout(
    db: AsyncSession = Depends(get_db),
):
    """Best performing callout from the past 3 days based on ATH multiplier."""
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    result = await db.execute(
        select(Callout).where(
            Callout.created_at >= three_days_ago,
            Callout.signal.in_(["buy", "watch"]),
            Callout.market_cap.isnot(None),
            Callout.market_cap > 0,
            Callout.peak_market_cap.isnot(None),
            Callout.peak_market_cap > 0,
        )
    )
    callouts = result.scalars().all()

    if not callouts:
        return None

    # Also get current market caps
    addresses = list(set(c.token_address for c in callouts))
    token_result = await db.execute(
        select(ScannedToken).where(ScannedToken.address.in_(addresses))
    )
    tokens_by_addr = {t.address: t for t in token_result.scalars().all()}

    best = None
    best_ath_mult = 0.0

    for c in callouts:
        ath_mult = c.peak_market_cap / c.market_cap
        # Filter garbage data (>50x is unreliable)
        if ath_mult > 50:
            continue
        if ath_mult > best_ath_mult:
            best_ath_mult = ath_mult
            best = c

    if not best:
        return None

    token = tokens_by_addr.get(best.token_address)
    current_mcap = token.market_cap if token and token.market_cap > 0 else None
    current_mult = None
    if current_mcap and best.market_cap > 0:
        m = current_mcap / best.market_cap
        if m <= 50:
            current_mult = round(m, 2)

    return TopCalloutResponse(
        callout=CalloutResponse.model_validate(best),
        ath_multiplier=round(best_ath_mult, 2),
        current_multiplier=current_mult,
        current_market_cap=current_mcap,
    )


@router.get("/stream")
async def callout_stream(
    user: User = Depends(require_tier(Tier.pro)),
):
    """SSE endpoint for real-time callout updates. Requires Pro tier."""

    async def event_generator():
        last_id = 0
        while True:
            async with async_session() as db:
                query = select(Callout).where(Callout.id > last_id).order_by(Callout.created_at.desc()).limit(10)
                result = await db.execute(query)
                callouts = result.scalars().all()

                for callout in reversed(callouts):
                    last_id = callout.id
                    data = CalloutResponse.model_validate(callout).model_dump_json()
                    yield {"event": "callout", "data": data}

            await asyncio.sleep(5)

    return EventSourceResponse(event_generator())
