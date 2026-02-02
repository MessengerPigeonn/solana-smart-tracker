from __future__ import annotations
import asyncio
import httpx
from typing import Optional
from app.config import get_settings

settings = get_settings()

BIRDEYE_BASE = "https://public-api.birdeye.so"


class BirdeyeClient:
    def __init__(self):
        self.api_key = settings.birdeye_api_key
        self.headers = {
            "X-API-KEY": self.api_key,
            "x-chain": "solana",
        }
        self._semaphore = asyncio.Semaphore(settings.birdeye_rate_limit)

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{BIRDEYE_BASE}{path}",
                    headers=self.headers,
                    params=params or {},
                )
                resp.raise_for_status()
                return resp.json()

    async def get_token_list(
        self,
        sort_by: str = "v24hUSD",
        sort_type: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch tokens sorted by volume."""
        data = await self._get(
            "/defi/tokenlist",
            params={
                "sort_by": sort_by,
                "sort_type": sort_type,
                "offset": offset,
                "limit": limit,
            },
        )
        return data.get("data", {}).get("tokens", [])

    async def get_trending_tokens(
        self,
        offset: int = 0,
        limit: int = 20,
    ) -> list[dict]:
        """Fetch trending tokens ranked by trending score.
        Note: Max limit is 20 per request. Does not accept sort params."""
        data = await self._get(
            "/defi/token_trending",
            params={
                "offset": offset,
                "limit": min(limit, 20),
            },
        )
        return data.get("data", {}).get("tokens", [])

    async def get_token_trades(
        self,
        address: str,
        tx_type: str = "all",
        sort_type: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch recent trades for a token with wallet addresses and volumes."""
        data = await self._get(
            "/defi/txs/token",
            params={
                "address": address,
                "tx_type": tx_type,
                "sort_type": sort_type,
                "offset": offset,
                "limit": limit,
            },
        )
        return data.get("data", {}).get("items", [])

    async def get_token_overview(self, address: str) -> Optional[dict]:
        """Get detailed token info including real price changes (5m, 1h, 24h)."""
        data = await self._get(
            "/defi/token_overview",
            params={"address": address},
        )
        return data.get("data")

    async def get_token_overview_batch(self, addresses: list[str]) -> dict[str, dict]:
        """Call token_overview for multiple tokens, returning {address: overview_data}.
        Rate-limited with 0.3s spacing between calls."""
        results = {}
        for address in addresses:
            try:
                overview = await self.get_token_overview(address)
                if overview:
                    results[address] = overview
                await asyncio.sleep(0.3)
            except Exception:
                continue
        return results

    async def search_token(self, query: str) -> list[dict]:
        """Search tokens by symbol or address."""
        data = await self._get(
            "/defi/v3/search",
            params={"keyword": query, "chain": "solana", "target": "token", "sort_by": "volume_24h_usd", "sort_type": "desc"},
        )
        items = data.get("data", {}).get("items", [])
        return items if isinstance(items, list) else []

    async def get_token_security(self, address: str) -> Optional[dict]:
        """Get token security info."""
        data = await self._get(
            "/defi/token_security",
            params={"address": address},
        )
        return data.get("data")

    async def get_top_traders(
        self, address: str, time_frame: str = "24h", sort_type: str = "desc", sort_by: str = "volume", offset: int = 0, limit: int = 10
    ) -> list[dict]:
        """Get top traders for a token."""
        data = await self._get(
            "/defi/v2/tokens/top_traders",
            params={
                "address": address,
                "time_frame": time_frame,
                "sort_type": sort_type,
                "sort_by": sort_by,
                "offset": offset,
                "limit": limit,
            },
        )
        return data.get("data", {}).get("items", [])

    async def get_price(self, address: str) -> Optional[float]:
        """Get current price for a token."""
        data = await self._get(
            "/defi/price",
            params={"address": address},
        )
        return data.get("data", {}).get("value")

    async def get_price_volume(self, address: str, time_type: str = "24h") -> Optional[dict]:
        """Get price and volume data."""
        data = await self._get(
            "/defi/price_volume/single",
            params={"address": address, "type": time_type},
        )
        return data.get("data")

    async def get_new_listings(
        self,
        min_listing_time: int,
        max_listing_time: int,
        min_liquidity: float = 1000,
        sort_by: str = "recent_listing_time",
        sort_type: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch recently listed tokens via /defi/v3/token/list with time filters."""
        data = await self._get(
            "/defi/v3/token/list",
            params={
                "min_listing_time": min_listing_time,
                "max_listing_time": max_listing_time,
                "min_liquidity": min_liquidity,
                "sort_by": sort_by,
                "sort_type": sort_type,
                "offset": offset,
                "limit": limit,
            },
        )
        return data.get("data", {}).get("items", [])

    async def get_token_holders(self, address: str, limit: int = 20) -> list[dict]:
        """Fetch top holders for a token via /defi/v3/token/holder."""
        data = await self._get(
            "/defi/v3/token/holder",
            params={"address": address, "limit": limit},
        )
        return data.get("data", {}).get("items", [])

    async def get_token_creation_info(self, address: str) -> Optional[dict]:
        """Get token creation info (timestamp, tx) via /defi/token_creation_info."""
        data = await self._get(
            "/defi/token_creation_info",
            params={"address": address},
        )
        return data.get("data")

    async def get_token_security_batch(self, addresses: list[str]) -> dict[str, dict]:
        """Batch wrapper around get_token_security with 0.3s spacing."""
        results = {}
        for address in addresses:
            try:
                security = await self.get_token_security(address)
                if security:
                    results[address] = security
                await asyncio.sleep(0.3)
            except Exception:
                continue
        return results


birdeye_client = BirdeyeClient()
