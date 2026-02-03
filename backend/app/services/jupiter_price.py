from __future__ import annotations
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

JUPITER_PRICE_API = "https://api.jup.ag/price/v2"


class JupiterPriceClient:
    """Lightweight client for Jupiter Price API v2 (free, no auth required)."""

    async def get_price(self, address: str) -> Optional[float]:
        """Get current price for a single token.

        Returns price as float or None if unavailable.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    JUPITER_PRICE_API,
                    params={"ids": address},
                )
                resp.raise_for_status()
                data = resp.json()
                token_data = data.get("data", {}).get(address)
                if token_data and token_data.get("price"):
                    return float(token_data["price"])
                return None
        except Exception as e:
            logger.warning(f"Jupiter price fetch failed for {address}: {e}")
            return None

    async def get_prices(self, addresses: list[str]) -> dict[str, float]:
        """Get current prices for multiple tokens (batch, up to 100 per call).

        Returns {address: price} for tokens with available prices.
        """
        if not addresses:
            return {}

        results = {}
        # Jupiter allows up to 100 addresses per request
        for i in range(0, len(addresses), 100):
            batch = addresses[i:i + 100]
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        JUPITER_PRICE_API,
                        params={"ids": ",".join(batch)},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    for addr in batch:
                        token_data = data.get("data", {}).get(addr)
                        if token_data and token_data.get("price"):
                            results[addr] = float(token_data["price"])
            except Exception as e:
                logger.warning(f"Jupiter batch price fetch failed: {e}")
                continue

        return results


jupiter_price_client = JupiterPriceClient()
