from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from typing import Optional
from app.database import get_db, async_session
from app.models.user import User, Tier
from app.models.callout import Callout
from app.schemas.callout import CalloutResponse, CalloutListResponse
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

    result = await db.execute(
        query.order_by(Callout.created_at.desc()).offset(offset).limit(limit)
    )
    callouts = result.scalars().all()

    return CalloutListResponse(
        callouts=[CalloutResponse.model_validate(c) for c in callouts],
        total=total,
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
