from __future__ import annotations
import logging
from collections import defaultdict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.trader_snapshot import TraderSnapshot

logger = logging.getLogger(__name__)


async def find_smart_money_overlaps(
    db: AsyncSession,
    token_addresses: list[str],
    threshold: int = 2,
) -> list[dict]:
    """
    Find wallets that appear as traders across multiple tokens.
    Returns wallets that trade in >= threshold tokens from the given list.
    """
    if not token_addresses:
        return []

    result = await db.execute(
        select(TraderSnapshot.wallet, TraderSnapshot.token_address, TraderSnapshot.estimated_pnl)
        .where(TraderSnapshot.token_address.in_(token_addresses))
    )
    rows = result.all()

    wallet_tokens: dict[str, list[str]] = defaultdict(list)
    wallet_pnl: dict[str, float] = defaultdict(float)

    for wallet, token_addr, pnl in rows:
        if token_addr not in wallet_tokens[wallet]:
            wallet_tokens[wallet].append(token_addr)
        wallet_pnl[wallet] += pnl or 0

    overlaps = []
    for wallet, tokens in wallet_tokens.items():
        if len(tokens) >= threshold:
            overlaps.append({
                "wallet": wallet,
                "tokens": tokens,
                "total_pnl": wallet_pnl[wallet],
                "overlap_count": len(tokens),
            })

    overlaps.sort(key=lambda x: x["overlap_count"], reverse=True)
    return overlaps


async def get_top_profitable_wallets(
    db: AsyncSession, limit: int = 50
) -> list[dict]:
    """Get the most profitable wallets across all scanned tokens."""
    result = await db.execute(
        select(
            TraderSnapshot.wallet,
            func.sum(TraderSnapshot.estimated_pnl).label("total_pnl"),
            func.count(TraderSnapshot.id).label("trade_count"),
            func.count(func.distinct(TraderSnapshot.token_address)).label("tokens_traded"),
        )
        .group_by(TraderSnapshot.wallet)
        .order_by(func.sum(TraderSnapshot.estimated_pnl).desc())
        .limit(limit)
    )
    rows = result.all()

    wallets = []
    for wallet, total_pnl, trade_count, tokens_traded in rows:
        # Calculate win rate
        win_result = await db.execute(
            select(func.count(TraderSnapshot.id))
            .where(
                TraderSnapshot.wallet == wallet,
                TraderSnapshot.estimated_pnl > 0,
            )
        )
        wins = win_result.scalar() or 0
        win_rate = (wins / trade_count * 100) if trade_count > 0 else 0

        wallets.append({
            "wallet": wallet,
            "total_pnl": total_pnl or 0,
            "trade_count": trade_count,
            "tokens_traded": tokens_traded,
            "win_rate": round(win_rate, 1),
        })

    return wallets


async def get_wallet_analytics(db: AsyncSession, wallet_address: str) -> dict:
    """Get analytics for a specific wallet."""
    result = await db.execute(
        select(TraderSnapshot)
        .where(TraderSnapshot.wallet == wallet_address)
        .order_by(TraderSnapshot.scanned_at.desc())
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return {
            "wallet_address": wallet_address,
            "total_pnl": 0,
            "trade_count": 0,
            "win_rate": 0,
            "recent_trades": [],
            "tokens_traded": 0,
        }

    total_pnl = sum(s.estimated_pnl for s in snapshots)
    wins = sum(1 for s in snapshots if s.estimated_pnl > 0)
    unique_tokens = set(s.token_address for s in snapshots)
    win_rate = (wins / len(snapshots) * 100) if snapshots else 0

    # Get token symbols for recent trades
    from app.models.token import ScannedToken
    recent_trades = []
    for s in snapshots[:20]:
        token_result = await db.execute(
            select(ScannedToken.symbol).where(ScannedToken.address == s.token_address)
        )
        symbol = token_result.scalar() or "???"
        recent_trades.append({
            "token_address": s.token_address,
            "token_symbol": symbol,
            "volume_buy": s.volume_buy,
            "volume_sell": s.volume_sell,
            "estimated_pnl": s.estimated_pnl,
            "scanned_at": s.scanned_at.isoformat(),
        })

    return {
        "wallet_address": wallet_address,
        "total_pnl": total_pnl,
        "trade_count": len(snapshots),
        "win_rate": round(win_rate, 1),
        "recent_trades": recent_trades,
        "tokens_traded": len(unique_tokens),
    }
