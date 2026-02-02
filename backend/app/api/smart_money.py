from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, Tier
from app.schemas.wallet import OverlapResponse, OverlapEntry, TopWalletEntry
from app.middleware.auth import require_tier
from app.services.analyzer import find_smart_money_overlaps, get_top_profitable_wallets

router = APIRouter(prefix="/api/smart-money", tags=["smart-money"])


@router.get("/overlaps", response_model=OverlapResponse)
async def get_overlaps(
    tokens: str = Query(..., description="Comma-separated token addresses"),
    threshold: int = Query(2, ge=2, le=10),
    user: User = Depends(require_tier(Tier.pro)),
    db: AsyncSession = Depends(get_db),
):
    token_list = [t.strip() for t in tokens.split(",") if t.strip()]
    overlaps = await find_smart_money_overlaps(db, token_list, threshold)

    return OverlapResponse(
        overlaps=[OverlapEntry(**o) for o in overlaps],
        threshold=threshold,
    )


@router.get("/top", response_model=List[TopWalletEntry])
async def get_top_wallets(
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    wallets = await get_top_profitable_wallets(db, limit)
    return [TopWalletEntry(**w) for w in wallets]
