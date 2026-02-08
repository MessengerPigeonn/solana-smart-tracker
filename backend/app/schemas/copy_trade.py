from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


# -- Take profit tier --

class TakeProfitTier(BaseModel):
    gain_pct: float = Field(..., ge=1, le=100000, description="Sell when price increases by this %")
    sell_pct: float = Field(..., ge=1, le=100, description="Percentage of remaining position to sell")


# -- Config schemas --

class CopyTradeConfigUpdate(BaseModel):
    signal_types: Optional[List[str]] = None
    max_trade_sol: Optional[float] = Field(None, gt=0, le=10)
    max_daily_sol: Optional[float] = Field(None, gt=0, le=100)
    slippage_bps: Optional[int] = Field(None, ge=50, le=5000)
    take_profit_pct: Optional[float] = Field(None, ge=1, le=10000)
    take_profit_tiers: Optional[List[TakeProfitTier]] = None
    stop_loss_pct: Optional[float] = Field(None, ge=1, le=100)
    cooldown_seconds: Optional[int] = Field(None, ge=0, le=3600)
    min_score: Optional[float] = Field(None, ge=0, le=100)
    max_rug_risk: Optional[float] = Field(None, ge=0, le=100)
    min_liquidity: Optional[float] = Field(None, ge=0)
    min_market_cap: Optional[float] = Field(None, ge=0)
    skip_print_scan: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_nulls(cls, data: dict) -> dict:
        """Allow explicit null values for optional numeric fields to clear them."""
        return data


class CopyTradeConfigResponse(BaseModel):
    id: int
    user_id: str
    enabled: bool
    signal_types: list = ["buy"]
    max_trade_sol: float = 0.5
    max_daily_sol: float = 5.0
    slippage_bps: int = 500
    take_profit_pct: Optional[float] = None
    take_profit_tiers: Optional[List[TakeProfitTier]] = None
    stop_loss_pct: Optional[float] = None
    cooldown_seconds: int = 60
    min_score: float = 75.0
    max_rug_risk: Optional[float] = None
    min_liquidity: float = 5000.0
    min_market_cap: float = 10000.0
    skip_print_scan: bool = True
    trading_wallet_pubkey: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# -- Trading wallet schemas --

class TradingWalletResponse(BaseModel):
    id: int
    user_id: str
    public_key: str
    balance_sol: float = 0.0
    balance_updated_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TradingWalletGenerateResponse(TradingWalletResponse):
    """One-time response that includes the private key at wallet generation."""
    private_key: str


# -- Trade schemas --

class CopyTradeResponse(BaseModel):
    id: int
    user_id: str
    callout_id: int
    token_address: str
    token_symbol: str
    side: str
    sol_amount: float
    token_amount: float
    price_at_execution: float
    slippage_bps: int
    tx_signature: Optional[str] = None
    tx_status: str
    error_message: Optional[str] = None
    parent_trade_id: Optional[int] = None
    sell_trigger: Optional[str] = None
    pnl_sol: Optional[float] = None
    pnl_pct: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CopyTradeListResponse(BaseModel):
    trades: List[CopyTradeResponse]
    total: int


class OpenPositionResponse(BaseModel):
    trade_id: int
    callout_id: int
    token_address: str
    token_symbol: str
    entry_sol: float
    token_amount: float
    entry_price: float
    current_price: Optional[float] = None
    unrealized_pnl_sol: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    created_at: datetime


class ManualSellRequest(BaseModel):
    sell_pct: float = Field(100.0, ge=1, le=100, description="Percentage of position to sell")
