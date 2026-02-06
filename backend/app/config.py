from __future__ import annotations
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./smart_tracker.db"
    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    birdeye_api_key: str = ""
    helius_api_key: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""
    stripe_legend_price_id: str = ""

    sol_treasury_wallet: str = ""

    frontend_url: str = "http://localhost:3000"
    extra_cors_origins: str = ""  # comma-separated additional origins for production

    # Worker settings
    scan_interval_seconds: int = 60
    callout_interval_seconds: int = 60
    birdeye_rate_limit: int = 5  # requests per second
    helius_rate_limit: int = 5  # requests per second
    print_scan_interval_seconds: int = 15
    print_scan_enabled: bool = True

    # Copy trade settings
    copy_trade_encryption_key: str = ""  # 32-byte hex key for AES-256-GCM
    copy_trade_enabled: bool = False  # global kill switch
    copy_trade_max_sol_per_trade: float = 1.0
    copy_trade_max_sol_per_day: float = 10.0
    copy_trade_worker_interval: int = 5  # seconds
    jupiter_swap_api_url: str = "https://quote-api.jup.ag/v6"

    # Prediction settings
    the_odds_api_key: str = ""
    prediction_enabled: bool = False  # kill switch
    prediction_worker_interval: int = 900  # 15 minutes in seconds
    prediction_min_confidence: float = 65.0
    prediction_min_edge: float = 2.0  # minimum 2% edge

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
