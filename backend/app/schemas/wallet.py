from __future__ import annotations
from datetime import datetime
from typing import List
from pydantic import BaseModel


class AddWalletRequest(BaseModel):
    wallet_address: str
    label: str = ""


class WalletResponse(BaseModel):
    id: int
    wallet_address: str
    label: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WalletTrade(BaseModel):
    token_address: str
    token_symbol: str
    volume_buy: float
    volume_sell: float
    estimated_pnl: float
    scanned_at: datetime


class WalletAnalytics(BaseModel):
    wallet_address: str
    total_pnl: float
    trade_count: int
    win_rate: float
    recent_trades: List[WalletTrade]
    tokens_traded: int


class OverlapEntry(BaseModel):
    wallet: str
    tokens: List[str]
    total_pnl: float
    overlap_count: int


class OverlapResponse(BaseModel):
    overlaps: List[OverlapEntry]
    threshold: int


class TopWalletEntry(BaseModel):
    wallet: str
    total_pnl: float
    trade_count: int
    tokens_traded: int
    win_rate: float
