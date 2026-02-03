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
    created_at: datetime

    @computed_field
    @property
    def dexscreener_url(self) -> str:
        return f"https://dexscreener.com/solana/{self.token_address}"

    model_config = {"from_attributes": True}


class CalloutListResponse(BaseModel):
    callouts: List[CalloutResponse]
    total: int
