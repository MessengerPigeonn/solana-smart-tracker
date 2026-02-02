from __future__ import annotations
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.trader_snapshot import TraderSnapshot
from app.models.token import ScannedToken


async def get_wallet_pnl_analytics(db: AsyncSession, wallet_address: str) -> dict:
    """Get comprehensive PnL analytics for a wallet."""
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
            "avg_trade_size": 0,
            "best_trade": 0,
            "worst_trade": 0,
            "recent_trades": [],
            "tokens_traded": 0,
            "patterns": [],
        }

    total_pnl = sum(s.estimated_pnl for s in snapshots)
    wins = sum(1 for s in snapshots if s.estimated_pnl > 0)
    unique_tokens = set(s.token_address for s in snapshots)
    win_rate = (wins / len(snapshots) * 100) if snapshots else 0
    avg_size = sum(s.volume_buy + s.volume_sell for s in snapshots) / len(snapshots) if snapshots else 0
    best = max((s.estimated_pnl for s in snapshots), default=0)
    worst = min((s.estimated_pnl for s in snapshots), default=0)

    # Detect patterns
    patterns = []
    if win_rate > 70:
        patterns.append("High win rate trader")
    if len(unique_tokens) > 10:
        patterns.append("Diversified across many tokens")
    buy_heavy = [s for s in snapshots if s.volume_buy > s.volume_sell * 2]
    if len(buy_heavy) > len(snapshots) * 0.7:
        patterns.append("Accumulator — mostly buys")
    sell_heavy = [s for s in snapshots if s.volume_sell > s.volume_buy * 2]
    if len(sell_heavy) > len(snapshots) * 0.7:
        patterns.append("Distributor — mostly sells")

    # Recent trades with token symbols
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
        "total_pnl": round(total_pnl, 2),
        "trade_count": len(snapshots),
        "win_rate": round(win_rate, 1),
        "avg_trade_size": round(avg_size, 2),
        "best_trade": round(best, 2),
        "worst_trade": round(worst, 2),
        "recent_trades": recent_trades,
        "tokens_traded": len(unique_tokens),
        "patterns": patterns,
    }
