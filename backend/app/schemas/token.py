from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class TokenListItem(BaseModel):
    address: str
    symbol: str
    name: str
    price: float
    volume_24h: float
    liquidity: float
    market_cap: float
    price_change_5m: float
    price_change_1h: float
    price_change_24h: float
    smart_money_count: int
    token_type: str = "unknown"
    created_at_chain: Optional[datetime] = None
    buy_count_24h: int = 0
    sell_count_24h: int = 0
    unique_wallets_24h: int = 0
    top_buyer_concentration: float = 0.0
    has_mint_authority: Optional[bool] = None
    has_freeze_authority: Optional[bool] = None
    is_mutable: Optional[bool] = None
    holder_count: int = 0
    top10_holder_pct: float = 0.0
    dev_wallet_pct: float = 0.0
    dev_sold: Optional[bool] = None
    scan_source: str = "trending"
    rug_risk_score: float = 0.0
    last_scanned: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TraderInfo(BaseModel):
    wallet: str
    volume_buy: float
    volume_sell: float
    trade_count_buy: int
    trade_count_sell: int
    estimated_pnl: float
    scanned_at: datetime

    model_config = {"from_attributes": True}


class TokenDetail(TokenListItem):
    top_traders: List[TraderInfo] = []


class TokenListResponse(BaseModel):
    tokens: List[TokenListItem]
    total: int
