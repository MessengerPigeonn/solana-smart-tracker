from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, computed_field


class PredictionResponse(BaseModel):
    id: int
    sport: str
    league: str
    event_id: str
    home_team: str
    away_team: str
    commence_time: datetime
    bet_type: str
    pick: str
    pick_detail: dict = {}
    best_odds: float
    best_bookmaker: str
    implied_probability: float
    confidence: float
    edge: float
    reasoning: str
    parlay_legs: Optional[list] = None
    result: Optional[str] = None
    actual_score: Optional[str] = None
    pnl_units: Optional[float] = None
    settled_at: Optional[datetime] = None
    created_at: datetime

    @computed_field
    @property
    def odds_display(self) -> str:
        """Format American odds nicely (e.g. +150, -110)."""
        odds = self.best_odds
        if odds >= 0:
            return f"+{int(odds)}"
        return str(int(odds))

    model_config = {"from_attributes": True}


class PredictionListResponse(BaseModel):
    predictions: List[PredictionResponse]
    total: int


class PredictionStatsResponse(BaseModel):
    total_predictions: int
    win_rate: Optional[float] = None
    roi_pct: Optional[float] = None
    current_streak: int = 0
    best_sport: Optional[str] = None
    sport_breakdown: Dict[str, dict] = {}
