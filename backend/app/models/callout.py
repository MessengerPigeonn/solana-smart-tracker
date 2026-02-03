from __future__ import annotations
import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, Text, DateTime, JSON, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Signal(str, enum.Enum):
    buy = "buy"
    sell = "sell"
    watch = "watch"


class Callout(Base):
    __tablename__ = "callouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(44), nullable=False, index=True)
    token_symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    signal: Mapped[Signal] = mapped_column(SAEnum(Signal), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    smart_wallets: Mapped[dict] = mapped_column(JSON, default=list)
    price_at_callout: Mapped[float] = mapped_column(Float, nullable=False)
    scan_source: Mapped[str] = mapped_column(String(20), default="trending")
    token_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    market_cap: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    volume_24h: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    liquidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    holder_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
    rug_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
