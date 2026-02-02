from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TraderSnapshot(Base):
    __tablename__ = "trader_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(
        String(44), ForeignKey("scanned_tokens.address"), nullable=False, index=True
    )
    wallet: Mapped[str] = mapped_column(String(44), nullable=False, index=True)
    volume_buy: Mapped[float] = mapped_column(Float, default=0.0)
    volume_sell: Mapped[float] = mapped_column(Float, default=0.0)
    trade_count_buy: Mapped[int] = mapped_column(Integer, default=0)
    trade_count_sell: Mapped[int] = mapped_column(Integer, default=0)
    estimated_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
