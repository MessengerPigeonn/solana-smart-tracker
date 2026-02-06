from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Text, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sport: Mapped[str] = mapped_column(String(20), nullable=False)
    league: Mapped[str] = mapped_column(String(50), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    home_team: Mapped[str] = mapped_column(String(100), nullable=False)
    away_team: Mapped[str] = mapped_column(String(100), nullable=False)
    commence_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bet_type: Mapped[str] = mapped_column(String(20), nullable=False)
    pick: Mapped[str] = mapped_column(String(200), nullable=False)
    pick_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    best_odds: Mapped[float] = mapped_column(Float, nullable=False)
    best_bookmaker: Mapped[str] = mapped_column(String(50), nullable=False)
    implied_probability: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    edge: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    parlay_legs: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=None)
    result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default=None)
    actual_score: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default=None)
    pnl_units: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
