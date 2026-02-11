from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SmartWallet(Base):
    __tablename__ = "smart_wallets"

    wallet_address: Mapped[str] = mapped_column(String(44), primary_key=True)
    label: Mapped[str] = mapped_column(String(20), default="unknown")  # whale/kol/sniper/insider/smart_money/promising/unknown
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    avg_entry_mcap: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_traded: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    reputation_score: Mapped[float] = mapped_column(Float, default=0.0)
