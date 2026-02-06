from __future__ import annotations
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, Text, DateTime, JSON, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class TradeSide(str, enum.Enum):
    buy = "buy"
    sell = "sell"


class TxStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


class SellTrigger(str, enum.Enum):
    take_profit = "take_profit"
    stop_loss = "stop_loss"
    manual = "manual"
    trailing_stop = "trailing_stop"


class CopyTrade(Base):
    __tablename__ = "copy_trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    callout_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("callouts.id"), nullable=False, index=True
    )
    token_address: Mapped[str] = mapped_column(String(44), nullable=False, index=True)
    token_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[TradeSide] = mapped_column(SAEnum(TradeSide), nullable=False)
    sol_amount: Mapped[float] = mapped_column(Float, nullable=False)
    token_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    price_at_execution: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    slippage_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    tx_signature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, default=None)
    tx_status: Mapped[TxStatus] = mapped_column(
        SAEnum(TxStatus), default=TxStatus.pending, nullable=False
    )
    jupiter_route: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    parent_trade_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("copy_trades.id"), nullable=True, default=None
    )
    sell_trigger: Mapped[Optional[SellTrigger]] = mapped_column(
        SAEnum(SellTrigger), nullable=True, default=None
    )
    pnl_sol: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", backref="copy_trades")
    callout = relationship("Callout", backref="copy_trades")
    parent_trade = relationship("CopyTrade", remote_side="CopyTrade.id", backref="child_trades")
