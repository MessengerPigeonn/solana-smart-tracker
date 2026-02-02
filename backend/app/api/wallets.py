from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, Tier
from app.models.tracked_wallet import TrackedWallet
from app.schemas.wallet import AddWalletRequest, WalletResponse, WalletAnalytics
from app.middleware.auth import get_current_user, require_tier
from app.services.wallet_analytics import get_wallet_pnl_analytics

router = APIRouter(prefix="/api/wallets", tags=["wallets"])

WALLET_LIMITS = {Tier.free: 0, Tier.pro: 10, Tier.legend: 50}


@router.get("", response_model=List[WalletResponse])
async def list_wallets(
    user: User = Depends(require_tier(Tier.pro)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TrackedWallet)
        .where(TrackedWallet.user_id == user.id)
        .order_by(TrackedWallet.created_at.desc())
    )
    wallets = result.scalars().all()
    return [WalletResponse.model_validate(w) for w in wallets]


@router.post("", response_model=WalletResponse, status_code=status.HTTP_201_CREATED)
async def add_wallet(
    req: AddWalletRequest,
    user: User = Depends(require_tier(Tier.pro)),
    db: AsyncSession = Depends(get_db),
):
    # Check wallet limit
    count_result = await db.execute(
        select(TrackedWallet).where(TrackedWallet.user_id == user.id)
    )
    current_count = len(count_result.scalars().all())
    limit = WALLET_LIMITS.get(user.tier, 0)

    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Wallet limit reached ({limit}). Upgrade your tier for more.",
        )

    # Check for duplicate
    existing = await db.execute(
        select(TrackedWallet).where(
            TrackedWallet.user_id == user.id,
            TrackedWallet.wallet_address == req.wallet_address,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wallet already tracked",
        )

    # Validate address format (basic check for Solana base58)
    if not (32 <= len(req.wallet_address) <= 44):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Solana wallet address",
        )

    wallet = TrackedWallet(
        user_id=user.id,
        wallet_address=req.wallet_address,
        label=req.label or req.wallet_address[:8],
    )
    db.add(wallet)
    await db.flush()
    return WalletResponse.model_validate(wallet)


@router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_wallet(
    wallet_id: int,
    user: User = Depends(require_tier(Tier.pro)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TrackedWallet).where(
            TrackedWallet.id == wallet_id,
            TrackedWallet.user_id == user.id,
        )
    )
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    await db.delete(wallet)


@router.get("/{address}/analytics", response_model=WalletAnalytics)
async def wallet_analytics(
    address: str,
    user: User = Depends(require_tier(Tier.pro)),
    db: AsyncSession = Depends(get_db),
):
    analytics = await get_wallet_pnl_analytics(db, address)
    return WalletAnalytics(**analytics)
