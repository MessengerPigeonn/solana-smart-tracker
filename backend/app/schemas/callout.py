from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, computed_field


class CalloutResponse(BaseModel):
    id: int
    token_address: str
    token_symbol: str
    signal: str
    score: float
    reason: str
    smart_wallets: List[str] = []
    price_at_callout: float
    scan_source: str = "trending"
    token_name: Optional[str] = None
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    liquidity: Optional[float] = None
    holder_count: Optional[int] = None
    rug_risk_score: Optional[float] = None
    peak_market_cap: Optional[float] = None
    repinned_at: Optional[datetime] = None
    score_breakdown: Optional[dict] = None
    security_score: Optional[float] = None
    social_mentions: Optional[int] = None
    early_smart_buyers: Optional[int] = None
    volume_velocity: Optional[float] = None
    created_at: datetime

    @computed_field
    @property
    def dexscreener_url(self) -> str:
        return f"https://dexscreener.com/solana/{self.token_address}"

    model_config = {"from_attributes": True}


class CalloutListResponse(BaseModel):
    callouts: List[CalloutResponse]
    total: int


class MilestoneCountsResponse(BaseModel):
    pct_20: int = 0
    pct_40: int = 0
    pct_60: int = 0
    pct_80: int = 0
    x2: int = 0
    x5: int = 0
    x10: int = 0
    x50: int = 0
    x100: int = 0


class CalloutStatsResponse(BaseModel):
    total_calls: int
    avg_multiplier: Optional[float] = None
    avg_ath_multiplier: Optional[float] = None
    win_rate: Optional[float] = None
    best_call_symbol: Optional[str] = None
    best_call_address: Optional[str] = None
    best_call_ath_multiplier: Optional[float] = None
    buy_signals: int = 0
    watch_signals: int = 0
    sell_signals: int = 0
    milestones: MilestoneCountsResponse = MilestoneCountsResponse()


class TopCalloutResponse(BaseModel):
    callout: CalloutResponse
    ath_multiplier: float
    current_multiplier: Optional[float] = None
    current_market_cap: Optional[float] = None
