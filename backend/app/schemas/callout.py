from __future__ import annotations
from datetime import datetime
from typing import List
from pydantic import BaseModel


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
    created_at: datetime

    model_config = {"from_attributes": True}


class CalloutListResponse(BaseModel):
    callouts: List[CalloutResponse]
    total: int
