from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TokenSnapshot(Base):
    __tablename__ = "token_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(44), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    market_cap: Mapped[float] = mapped_column(Float, default=0.0)
    buy_count: Mapped[int] = mapped_column(Integer, default=0)
    sell_count: Mapped[int] = mapped_column(Integer, default=0)
    holder_count: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
