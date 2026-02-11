from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ScannedToken(Base):
    __tablename__ = "scanned_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(44), unique=True, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    volume_24h: Mapped[float] = mapped_column(Float, default=0.0)
    liquidity: Mapped[float] = mapped_column(Float, default=0.0)
    market_cap: Mapped[float] = mapped_column(Float, default=0.0)
    price_change_5m: Mapped[float] = mapped_column(Float, default=0.0)
    price_change_1h: Mapped[float] = mapped_column(Float, default=0.0)
    price_change_24h: Mapped[float] = mapped_column(Float, default=0.0)
    smart_money_count: Mapped[int] = mapped_column(Integer, default=0)

    # New fields for memecoin scanner overhaul
    token_type: Mapped[str] = mapped_column(String(20), default="unknown")  # memecoin / defi / stablecoin / unknown
    created_at_chain: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    buy_count_24h: Mapped[int] = mapped_column(Integer, default=0)
    sell_count_24h: Mapped[int] = mapped_column(Integer, default=0)
    unique_wallets_24h: Mapped[int] = mapped_column(Integer, default=0)
    top_buyer_concentration: Mapped[float] = mapped_column(Float, default=0.0)  # % of buy volume from top 5 wallets

    # Security fields (PrintScan)
    has_mint_authority: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)
    has_freeze_authority: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)
    is_mutable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)

    # Holder distribution (PrintScan)
    holder_count: Mapped[int] = mapped_column(Integer, default=0)
    top10_holder_pct: Mapped[float] = mapped_column(Float, default=0.0)
    dev_wallet_pct: Mapped[float] = mapped_column(Float, default=0.0)
    dev_sold: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)

    # Discovery metadata
    scan_source: Mapped[str] = mapped_column(String(20), default="trending")
    rug_risk_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Enhanced callout rework fields
    social_mention_count: Mapped[int] = mapped_column(Integer, default=0)
    social_velocity: Mapped[float] = mapped_column(Float, default=0.0)
    rugcheck_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    early_buyer_smart_count: Mapped[int] = mapped_column(Integer, default=0)

    # Bundle detection fields
    bundle_pct: Mapped[float] = mapped_column(Float, default=0.0)       # % of early supply from bundled wallets
    bundle_held_pct: Mapped[float] = mapped_column(Float, default=0.0)  # % still held by bundle wallets
    bundle_wallet_count: Mapped[int] = mapped_column(Integer, default=0)
    bundle_risk: Mapped[str] = mapped_column(String(10), default="none") # none/low/medium/high

    last_scanned: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
