from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CTOWallet(Base):
    __tablename__ = "cto_wallets"

    wallet_address: Mapped[str] = mapped_column(String(44), primary_key=True)
    label: Mapped[str] = mapped_column(String(30), default="cto_accumulator")
    successful_ctos: Mapped[int] = mapped_column(Integer, default=0)
    total_accumulations: Mapped[int] = mapped_column(Integer, default=0)
    avg_entry_drop_pct: Mapped[float] = mapped_column(Float, default=0.0)
    best_revival_multiple: Mapped[float] = mapped_column(Float, default=0.0)
    helius_identity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default=None)
    helius_identity_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    funded_by: Mapped[Optional[str]] = mapped_column(String(44), nullable=True, default=None)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reputation_score: Mapped[float] = mapped_column(Float, default=0.0)
