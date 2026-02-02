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

    # Worker settings
    scan_interval_seconds: int = 60
    callout_interval_seconds: int = 60
    birdeye_rate_limit: int = 5  # requests per second
    print_scan_interval_seconds: int = 15
    print_scan_enabled: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
