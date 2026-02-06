from __future__ import annotations
import asyncio
import logging
from typing import Optional
import httpx
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Sport keys mapping: display_name -> API key
SPORT_KEYS = {
    "NBA": "basketball_nba",
    "NFL": "americanfootball_nfl",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
    "UFC": "mma_mixed_martial_arts",
    "Soccer": "soccer_epl",
}

ACTIVE_SPORTS = list(SPORT_KEYS.values())


class OddsProvider:
    """Client for The Odds API v4, following the BirdeyeClient singleton pattern."""

    def __init__(self):
        self.api_key = settings.the_odds_api_key
        self._semaphore = asyncio.Semaphore(5)
        self.requests_remaining: Optional[int] = None
        self.requests_used: Optional[int] = None

    def _update_credits(self, headers: httpx.Headers):
        remaining = headers.get("x-requests-remaining")
        used = headers.get("x-requests-used")
        if remaining is not None:
            self.requests_remaining = int(remaining)
        if used is not None:
            self.requests_used = int(used)
        if self.requests_remaining is not None and self.requests_remaining < 50:
            logger.warning(f"The Odds API credits low: {self.requests_remaining} remaining")

    async def _get(self, path: str, params: Optional[dict] = None) -> list | dict:
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=30) as client:
                all_params = {"apiKey": self.api_key}
                if params:
                    all_params.update(params)
                resp = await client.get(f"{ODDS_API_BASE}{path}", params=all_params)
                resp.raise_for_status()
                self._update_credits(resp.headers)
                return resp.json()

    async def get_sports(self) -> list[dict]:
        """List all available sports."""
        return await self._get("/sports")

    async def get_odds(
        self,
        sport_key: str,
        regions: str = "us,us2,eu",
        markets: str = "h2h,spreads,totals",
        odds_format: str = "american",
    ) -> list[dict]:
        """Fetch odds for all upcoming events in a sport."""
        return await self._get(
            f"/sports/{sport_key}/odds",
            params={
                "regions": regions,
                "markets": markets,
                "oddsFormat": odds_format,
            },
        )

    async def get_scores(
        self, sport_key: str, days_from: int = 3
    ) -> list[dict]:
        """Fetch completed game scores for settlement."""
        return await self._get(
            f"/sports/{sport_key}/scores",
            params={"daysFrom": days_from},
        )


# Module-level singleton
odds_provider = OddsProvider()
