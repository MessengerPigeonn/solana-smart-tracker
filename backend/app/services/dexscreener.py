from __future__ import annotations
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

DEXSCREENER_API = "https://api.dexscreener.com"


class DexScreenerClient:
    """Lightweight client for DexScreener public API (free, no auth required).

    Used as a fallback discovery source when Birdeye is rate-limited.
    Provides trending tokens and token search on Solana.
    """

    async def _get(self, path: str, params: Optional[dict] = None) -> dict | list:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{DEXSCREENER_API}{path}",
                params=params or {},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_trending_tokens(self, limit: int = 50) -> list[dict]:
        """Fetch trending token pairs on Solana via /token-boosts/top/v1.

        Returns list of dicts normalized to Birdeye-compatible format:
        {address, symbol, name, price, mc, liquidity, v24hUSD, ...}
        """
        try:
            data = await self._get("/token-boosts/top/v1")
        except Exception as e:
            logger.warning(f"DexScreener trending fetch failed: {e}")
            return []

        if not isinstance(data, list):
            return []

        results = []
        seen = set()
        for item in data:
            if item.get("chainId") != "solana":
                continue
            address = item.get("tokenAddress", "")
            if not address or address in seen:
                continue
            seen.add(address)
            results.append({
                "address": address,
                "symbol": item.get("symbol", "???"),
                "name": item.get("name", "Unknown"),
                "price": 0,
                "mc": 0,
                "marketcap": 0,
                "liquidity": 0,
                "v24hUSD": 0,
            })
            if len(results) >= limit:
                break

        logger.info(f"DexScreener: discovered {len(results)} trending Solana tokens")
        return results

    async def get_latest_token_profiles(self, limit: int = 50) -> list[dict]:
        """Fetch latest token profiles via /token-profiles/latest/v1.

        Returns list of dicts normalized to Birdeye-compatible format.
        Used as fallback for new listing / token list discovery.
        """
        try:
            data = await self._get("/token-profiles/latest/v1")
        except Exception as e:
            logger.warning(f"DexScreener latest profiles fetch failed: {e}")
            return []

        if not isinstance(data, list):
            return []

        results = []
        seen = set()
        for item in data:
            if item.get("chainId") != "solana":
                continue
            address = item.get("tokenAddress", "")
            if not address or address in seen:
                continue
            seen.add(address)
            results.append({
                "address": address,
                "symbol": item.get("symbol", "???"),
                "name": item.get("name", "Unknown"),
                "price": 0,
                "mc": 0,
                "marketcap": 0,
                "liquidity": 0,
                "v24hUSD": 0,
                "market_cap": 0,
            })
            if len(results) >= limit:
                break

        logger.info(f"DexScreener: discovered {len(results)} latest Solana token profiles")
        return results

    async def get_token_pairs(self, address: str) -> list[dict]:
        """Fetch all trading pairs for a token via /token-pairs/v1/solana/{address}.

        Returns raw pair data from DexScreener.
        """
        try:
            data = await self._get(f"/token-pairs/v1/solana/{address}")
        except Exception as e:
            logger.warning(f"DexScreener token pairs fetch failed for {address}: {e}")
            return []

        if isinstance(data, list):
            return data
        return data.get("pairs", []) if isinstance(data, dict) else []

    async def search_token(self, query: str) -> list[dict]:
        """Search for a token on DexScreener by address or name.

        Returns list of dicts normalized to Birdeye-compatible format.
        """
        try:
            data = await self._get("/latest/dex/search", params={"q": query})
        except Exception as e:
            logger.warning(f"DexScreener search failed for '{query}': {e}")
            return []

        pairs = data.get("pairs", []) if isinstance(data, dict) else []
        results = []
        seen = set()
        for pair in pairs:
            if pair.get("chainId") != "solana":
                continue
            base = pair.get("baseToken", {})
            address = base.get("address", "")
            if not address or address in seen:
                continue
            seen.add(address)

            mc = pair.get("marketCap") or pair.get("fdv") or 0
            liq_data = pair.get("liquidity", {})
            liq = liq_data.get("usd", 0) if isinstance(liq_data, dict) else 0
            price_usd = float(pair.get("priceUsd") or 0)

            results.append({
                "address": address,
                "symbol": base.get("symbol", "???"),
                "name": base.get("name", "Unknown"),
                "price": price_usd,
                "liquidity": liq,
                "market_cap": mc,
                "volume_24h_usd": 0,
                "price_change_24h_percent": 0,
            })

        return results


dexscreener_client = DexScreenerClient()
