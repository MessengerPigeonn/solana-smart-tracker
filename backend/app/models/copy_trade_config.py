from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, DateTime, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CopyTradeConfig(Base):
    __tablename__ = "copy_trade_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    signal_types: Mapped[dict] = mapped_column(JSON, default=lambda: ["buy"])
    max_trade_sol: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    max_daily_sol: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    slippage_bps: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    take_profit_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    take_profit_tiers: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=None)
    stop_loss_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    min_score: Mapped[float] = mapped_column(Float, default=75.0, nullable=False)
    max_rug_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    min_liquidity: Mapped[float] = mapped_column(Float, default=5000.0, nullable=False)
    min_market_cap: Mapped[float] = mapped_column(Float, default=10000.0, nullable=False)
    skip_print_scan: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    skip_bundled_tokens: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    strict_safety: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trading_wallet_pubkey: Mapped[Optional[str]] = mapped_column(
        String(44), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", backref="copy_trade_config")
