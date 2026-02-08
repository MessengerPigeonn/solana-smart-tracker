from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.smart_wallet import SmartWallet

logger = logging.getLogger(__name__)

# Known KOL wallets (can be extended)
KNOWN_KOL_WALLETS = set()  # Add known Solana KOL wallet addresses here


def classify_wallet(wallet: SmartWallet) -> str:
    """Classify a wallet based on its trading stats.
    Priority order: kol > insider > sniper > whale > smart_money > unknown
    """
    if wallet.wallet_address in KNOWN_KOL_WALLETS:
        return "kol"

    # Sniper: enters tokens early at low mcap with good win rate
    if wallet.avg_entry_mcap > 0 and wallet.avg_entry_mcap < 50_000 and wallet.win_rate > 0.5 and wallet.total_trades >= 5:
        return "sniper"

    # Whale: large PnL and active trader
    if wallet.total_pnl > 50_000 and wallet.total_trades > 20:
        return "whale"

    # Smart Money: consistent winner
    if wallet.win_rate > 0.55 and wallet.total_trades > 10:
        return "smart_money"

    return "unknown"


def compute_reputation_score(wallet: SmartWallet) -> float:
    """Compute 0-100 reputation score based on wallet stats."""
    score = 0.0

    # Win rate component (max 40 pts)
    score += min(wallet.win_rate, 1.0) * 40

    # Trade count component (max 20 pts)
    score += min(wallet.total_trades / 50, 1.0) * 20

    # PnL component (max 20 pts)
    score += min(max(wallet.total_pnl, 0) / 100_000, 1.0) * 20

    # Label bonus (max 20 pts)
    label_bonuses = {
        "sniper": 15,
        "kol": 15,
        "whale": 10,
        "insider": 10,
        "smart_money": 10,
        "unknown": 0,
    }
    score += label_bonuses.get(wallet.label, 0)

    return round(min(score, 100), 1)


async def update_wallet_stats(db: AsyncSession, wallet_address: str, trade_data: dict):
    """Upsert wallet stats from trade data into SmartWallet table.

    trade_data should have:
    - volume_buy: float
    - volume_sell: float
    - estimated_pnl: float
    - token_market_cap: float (market cap at time of trade)
    """
    result = await db.execute(
        select(SmartWallet).where(SmartWallet.wallet_address == wallet_address)
    )
    wallet = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    pnl = trade_data.get("estimated_pnl", 0)
    is_win = pnl > 0
    mcap = trade_data.get("token_market_cap", 0)

    if wallet is None:
        wallet = SmartWallet(
            wallet_address=wallet_address,
            total_trades=1,
            winning_trades=1 if is_win else 0,
            win_rate=1.0 if is_win else 0.0,
            total_pnl=pnl,
            avg_entry_mcap=mcap,
            tokens_traded=1,
            first_seen=now,
            last_seen=now,
        )
        db.add(wallet)
    else:
        wallet.total_trades += 1
        if is_win:
            wallet.winning_trades += 1
        wallet.win_rate = wallet.winning_trades / max(wallet.total_trades, 1)
        wallet.total_pnl += pnl
        # Running average for entry mcap
        if mcap > 0:
            wallet.avg_entry_mcap = (
                (wallet.avg_entry_mcap * (wallet.total_trades - 1) + mcap)
                / wallet.total_trades
            )
        wallet.tokens_traded = wallet.tokens_traded + 1  # approximate, may double-count
        wallet.last_seen = now

    # Reclassify and update reputation
    wallet.label = classify_wallet(wallet)
    wallet.reputation_score = compute_reputation_score(wallet)


async def get_smart_wallets_for_token(db: AsyncSession, wallet_addresses: list[str]) -> dict[str, SmartWallet]:
    """Look up SmartWallet records for a list of wallet addresses.
    Returns {address: SmartWallet} for any known wallets with reputation > 0.
    """
    if not wallet_addresses:
        return {}

    result = await db.execute(
        select(SmartWallet).where(
            SmartWallet.wallet_address.in_(wallet_addresses),
            SmartWallet.reputation_score > 0,
        )
    )
    wallets = result.scalars().all()
    return {w.wallet_address: w for w in wallets}


async def get_reputable_wallets_buying_recently(db: AsyncSession, min_reputation: float = 60.0) -> list[SmartWallet]:
    """Get wallets with high reputation that have been active recently."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(SmartWallet).where(
            SmartWallet.reputation_score >= min_reputation,
            SmartWallet.last_seen >= cutoff,
        )
    )
    return list(result.scalars().all())
