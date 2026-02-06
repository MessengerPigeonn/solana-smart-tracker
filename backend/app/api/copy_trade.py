from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User, Tier
from app.models.copy_trade_config import CopyTradeConfig
from app.models.copy_trade import CopyTrade, TradeSide, TxStatus, SellTrigger
from app.models.trading_wallet import TradingWallet
from app.schemas.copy_trade import (
    CopyTradeConfigUpdate, CopyTradeConfigResponse,
    TradingWalletResponse, TradingWalletGenerateResponse,
    CopyTradeResponse, CopyTradeListResponse,
    OpenPositionResponse, ManualSellRequest,
)
from app.middleware.auth import require_tier
from app.services.trading_wallet_service import generate_wallet, get_wallet_balance

router = APIRouter(prefix="/api/copy-trade", tags=["copy-trade"])


@router.get("/config", response_model=CopyTradeConfigResponse)
async def get_config(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CopyTradeConfig).where(CopyTradeConfig.user_id == user.id))
    config = result.scalar_one_or_none()
    if not config:
        config = CopyTradeConfig(user_id=user.id)
        db.add(config)
        await db.flush()
    return CopyTradeConfigResponse.model_validate(config)


@router.put("/config", response_model=CopyTradeConfigResponse)
async def update_config(
    updates: CopyTradeConfigUpdate,
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CopyTradeConfig).where(CopyTradeConfig.user_id == user.id))
    config = result.scalar_one_or_none()
    if not config:
        config = CopyTradeConfig(user_id=user.id)
        db.add(config)
        await db.flush()
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    await db.flush()
    return CopyTradeConfigResponse.model_validate(config)


@router.post("/config/enable", response_model=CopyTradeConfigResponse)
async def enable_bot(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CopyTradeConfig).where(CopyTradeConfig.user_id == user.id))
    config = result.scalar_one_or_none()
    if not config:
        config = CopyTradeConfig(user_id=user.id)
        db.add(config)
        await db.flush()
    if not config.trading_wallet_pubkey:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Generate a trading wallet first")
    config.enabled = True
    await db.flush()
    return CopyTradeConfigResponse.model_validate(config)


@router.post("/config/disable", response_model=CopyTradeConfigResponse)
async def disable_bot(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(CopyTradeConfig).where(CopyTradeConfig.user_id == user.id))
    config = result.scalar_one_or_none()
    if not config:
        config = CopyTradeConfig(user_id=user.id)
        db.add(config)
        await db.flush()
    config.enabled = False
    await db.flush()
    return CopyTradeConfigResponse.model_validate(config)


@router.post("/wallet/generate", response_model=TradingWalletGenerateResponse)
async def generate_trading_wallet(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(TradingWallet).where(TradingWallet.user_id == user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Trading wallet already exists")
    wallet_data = generate_wallet()
    wallet = TradingWallet(
        user_id=user.id, public_key=wallet_data["public_key"],
        encrypted_private_key=wallet_data["encrypted_private_key"],
        encryption_iv=wallet_data["encryption_iv"],
    )
    db.add(wallet)
    await db.flush()
    config_result = await db.execute(select(CopyTradeConfig).where(CopyTradeConfig.user_id == user.id))
    config = config_result.scalar_one_or_none()
    if not config:
        config = CopyTradeConfig(user_id=user.id, trading_wallet_pubkey=wallet.public_key)
        db.add(config)
    else:
        config.trading_wallet_pubkey = wallet.public_key
    # Return wallet with one-time private key — never returned again
    base = TradingWalletResponse.model_validate(wallet)
    return TradingWalletGenerateResponse(**base.model_dump(), private_key=wallet_data["private_key_bs58"])


@router.get("/wallet", response_model=Optional[TradingWalletResponse])
async def get_wallet(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TradingWallet).where(TradingWallet.user_id == user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        return None
    return TradingWalletResponse.model_validate(wallet)


@router.post("/wallet/refresh-balance", response_model=TradingWalletResponse)
async def refresh_wallet_balance(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TradingWallet).where(TradingWallet.user_id == user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=404, detail="No trading wallet found")
    balance = await get_wallet_balance(wallet.public_key)
    if balance is not None:
        wallet.balance_sol = balance
        wallet.balance_updated_at = datetime.now(timezone.utc)
    return TradingWalletResponse.model_validate(wallet)


@router.get("/trades", response_model=CopyTradeListResponse)
async def list_trades(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    side: Optional[str] = Query(None, pattern="^(buy|sell)$"),
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    query = select(CopyTrade).where(CopyTrade.user_id == user.id)
    count_query = select(func.count()).select_from(CopyTrade).where(CopyTrade.user_id == user.id)
    if side:
        query = query.where(CopyTrade.side == side)
        count_query = count_query.where(CopyTrade.side == side)
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.order_by(CopyTrade.created_at.desc()).offset(offset).limit(limit))
    trades = result.scalars().all()
    return CopyTradeListResponse(
        trades=[CopyTradeResponse.model_validate(t) for t in trades], total=total,
    )


@router.get("/positions", response_model=list)
async def get_positions(
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    buy_result = await db.execute(
        select(CopyTrade).where(
            CopyTrade.user_id == user.id, CopyTrade.side == TradeSide.buy,
            CopyTrade.tx_status == TxStatus.confirmed,
        ).order_by(CopyTrade.created_at.desc())
    )
    buys = buy_result.scalars().all()
    sell_result = await db.execute(
        select(CopyTrade).where(
            CopyTrade.user_id == user.id, CopyTrade.side == TradeSide.sell,
            CopyTrade.tx_status == TxStatus.confirmed, CopyTrade.parent_trade_id.isnot(None),
        )
    )
    sold_by_parent = {}
    for sell in sell_result.scalars().all():
        sold_by_parent[sell.parent_trade_id] = sold_by_parent.get(sell.parent_trade_id, 0) + sell.token_amount
    positions = []
    for buy in buys:
        remaining = buy.token_amount - sold_by_parent.get(buy.id, 0)
        if remaining <= 0:
            continue
        positions.append(OpenPositionResponse(
            trade_id=buy.id, callout_id=buy.callout_id,
            token_address=buy.token_address, token_symbol=buy.token_symbol,
            entry_sol=buy.sol_amount, token_amount=remaining,
            entry_price=buy.price_at_execution, created_at=buy.created_at,
        ))
    return positions


@router.post("/positions/{trade_id}/sell")
async def manual_sell(
    trade_id: int,
    req: ManualSellRequest,
    user: User = Depends(require_tier(Tier.legend)),
    db: AsyncSession = Depends(get_db),
):
    from app.services.copy_trade_executor import execute_sell
    result = await db.execute(
        select(CopyTrade).where(
            CopyTrade.id == trade_id, CopyTrade.user_id == user.id,
            CopyTrade.side == TradeSide.buy, CopyTrade.tx_status == TxStatus.confirmed,
        )
    )
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    config_result = await db.execute(select(CopyTradeConfig).where(CopyTradeConfig.user_id == user.id))
    config = config_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=400, detail="Copy trade not configured")
    sell_trade = await execute_sell(trade=trade, config=config, db=db, sell_pct=req.sell_pct, trigger=SellTrigger.manual)
    if not sell_trade:
        raise HTTPException(status_code=500, detail="Failed to execute sell")
    return CopyTradeResponse.model_validate(sell_trade)
