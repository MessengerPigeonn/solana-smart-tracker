from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.models.user import User, Tier
from app.models.token import ScannedToken
from app.models.trader_snapshot import TraderSnapshot
from app.schemas.token import TokenListItem, TokenListResponse, TokenDetail, TraderInfo
from app.middleware.auth import get_optional_user
from app.services.data_provider import data_provider

router = APIRouter(prefix="/api/tokens", tags=["tokens"])

VALID_SORT_COLUMNS = {
    "volume_24h", "smart_money_count", "price_change_24h", "price_change_1h",
    "price_change_5m", "market_cap", "liquidity", "buy_count_24h",
    "unique_wallets_24h", "top_buyer_concentration", "last_scanned",
    "rug_risk_score",
}


@router.get("", response_model=TokenListResponse)
async def list_tokens(
    sort_by: str = Query("volume_24h"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    token_type: Optional[str] = Query(None, pattern="^(memecoin|defi|stablecoin|unknown)$"),
    mcap_min: Optional[float] = Query(None, ge=0),
    mcap_max: Optional[float] = Query(None, ge=0),
    scan_source: Optional[str] = Query(None, pattern="^(trending|print_scan)$"),
    has_signal: Optional[bool] = Query(None),
    addresses: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    # If addresses parameter is provided, return only those tokens (bypass other filters)
    if addresses:
        addr_list = [a.strip() for a in addresses.split(",") if a.strip()]
        if not addr_list:
            return TokenListResponse(tokens=[], total=0)
        addr_list = addr_list[:200]
        result = await db.execute(
            select(ScannedToken).where(ScannedToken.address.in_(addr_list))
        )
        tokens = result.scalars().all()
        return TokenListResponse(
            tokens=[TokenListItem.model_validate(t) for t in tokens],
            total=len(tokens),
        )

    # Free users: limit to 10 results
    if not user or user.tier == Tier.free:
        limit = min(limit, 10)

    # Validate sort column
    if sort_by not in VALID_SORT_COLUMNS:
        sort_by = "volume_24h"

    column = getattr(ScannedToken, sort_by)
    order_clause = column.desc() if order == "desc" else column.asc()

    # Build filter conditions
    conditions = []
    if token_type:
        conditions.append(ScannedToken.token_type == token_type)
    if mcap_min is not None:
        conditions.append(ScannedToken.market_cap >= mcap_min)
    if mcap_max is not None:
        conditions.append(ScannedToken.market_cap <= mcap_max)
    if scan_source:
        conditions.append(ScannedToken.scan_source == scan_source)

    base_query = select(ScannedToken)
    if conditions:
        base_query = base_query.where(and_(*conditions))

    count_result = await db.execute(
        select(func.count(ScannedToken.id)).where(and_(*conditions)) if conditions
        else select(func.count(ScannedToken.id))
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        base_query.order_by(order_clause).offset(offset).limit(limit)
    )
    tokens = result.scalars().all()

    return TokenListResponse(
        tokens=[TokenListItem.model_validate(t) for t in tokens],
        total=total,
    )


@router.get("/search", response_model=TokenListResponse)
async def search_tokens(
    q: str = Query(..., min_length=1),
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    limit = 10 if (not user or user.tier == Tier.free) else 50

    # Search locally first
    result = await db.execute(
        select(ScannedToken).where(
            (ScannedToken.symbol.ilike(f"%{q}%"))
            | (ScannedToken.name.ilike(f"%{q}%"))
            | (ScannedToken.address == q)
        ).limit(limit)
    )
    tokens = result.scalars().all()

    # If no local results and query looks like a ticker, try Birdeye
    if not tokens:
        try:
            search_results = await data_provider.search_token(q)
            items = []
            for sr in search_results[:limit]:
                items.append(TokenListItem(
                    address=sr.get("address", ""),
                    symbol=sr.get("symbol", "???"),
                    name=sr.get("name", "Unknown"),
                    price=sr.get("price", 0) or 0,
                    volume_24h=sr.get("volume_24h_usd", 0) or 0,
                    liquidity=sr.get("liquidity", 0) or 0,
                    market_cap=sr.get("market_cap", 0) or 0,
                    price_change_5m=0,
                    price_change_1h=0,
                    price_change_24h=sr.get("price_change_24h_percent", 0) or 0,
                    smart_money_count=0,
                    last_scanned=None,
                ))
            return TokenListResponse(tokens=items, total=len(items))
        except Exception:
            pass

    return TokenListResponse(
        tokens=[TokenListItem.model_validate(t) for t in tokens],
        total=len(tokens),
    )


@router.get("/{address}", response_model=TokenDetail)
async def get_token_detail(
    address: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScannedToken).where(ScannedToken.address == address)
    )
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # Get top traders
    trader_result = await db.execute(
        select(TraderSnapshot)
        .where(TraderSnapshot.token_address == address)
        .order_by(TraderSnapshot.estimated_pnl.desc())
        .limit(20)
    )
    traders = trader_result.scalars().all()

    return TokenDetail(
        **TokenListItem.model_validate(token).model_dump(),
        top_traders=[TraderInfo.model_validate(t) for t in traders],
    )
