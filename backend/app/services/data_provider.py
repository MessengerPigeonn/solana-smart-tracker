from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional

import httpx

from app.services.birdeye import birdeye_client
from app.services.helius import helius_client
from app.services.jupiter_price import jupiter_price_client
from app.services.dexscreener import dexscreener_client

logger = logging.getLogger(__name__)

# Birdeye health cooldown in seconds
BIRDEYE_COOLDOWN_SECONDS = 300  # 5 minutes


class TokenDataProvider:
    """Fallback wrapper: Birdeye (primary) → Helius → Jupiter.

    Tracks Birdeye health state and automatically falls back to Helius/Jupiter
    when Birdeye returns 401, 429, or times out. After a 5-minute cooldown,
    Birdeye is retried.
    """

    def __init__(self):
        self._birdeye_healthy = True
        self._birdeye_cooldown_until = 0.0

    # ── health tracking ────────────────────────────────────────────

    def _is_birdeye_healthy(self) -> bool:
        """Check if Birdeye should be attempted."""
        if self._birdeye_healthy:
            return True
        if time.monotonic() >= self._birdeye_cooldown_until:
            logger.info("Birdeye cooldown expired, retrying")
            self._birdeye_healthy = True
            return True
        return False

    def _mark_birdeye_unhealthy(self, error: Exception):
        """Mark Birdeye as unhealthy after a failure."""
        self._birdeye_healthy = False
        self._birdeye_cooldown_until = time.monotonic() + BIRDEYE_COOLDOWN_SECONDS
        logger.warning(
            f"Birdeye marked unhealthy for {BIRDEYE_COOLDOWN_SECONDS}s: {error}"
        )

    def _is_retriable_error(self, error: Exception) -> bool:
        """Check if the error should trigger a fallback."""
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in (401, 429, 403, 500, 502, 503)
        if isinstance(error, (httpx.TimeoutException, httpx.ConnectError)):
            return True
        return False

    # ── trending / token list (Birdeye → DexScreener) ──────────────

    async def get_trending_tokens(
        self, offset: int = 0, limit: int = 20
    ) -> list[dict]:
        """Birdeye primary, DexScreener fallback for trending tokens."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.get_trending_tokens(offset=offset, limit=limit)
                if result:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_trending_tokens failed: {e}")

        # Fallback to DexScreener
        try:
            logger.info("Using DexScreener fallback for trending tokens")
            return await dexscreener_client.get_trending_tokens(limit=limit)
        except Exception as e:
            logger.warning(f"DexScreener get_trending_tokens also failed: {e}")
            return []

    async def get_token_list(
        self,
        sort_by: str = "v24hUSD",
        sort_type: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Birdeye primary, DexScreener fallback for token lists."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.get_token_list(
                    sort_by=sort_by, sort_type=sort_type, offset=offset, limit=limit
                )
                if result:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_token_list failed: {e}")

        # Fallback to DexScreener latest pairs
        try:
            logger.info("Using DexScreener fallback for token list")
            return await dexscreener_client.get_latest_token_profiles(limit=limit)
        except Exception as e:
            logger.warning(f"DexScreener get_latest_token_profiles also failed: {e}")
            return []

    # ── token overview (Birdeye → Helius) ──────────────────────────

    async def get_token_overview(self, address: str) -> Optional[dict]:
        """Birdeye primary, Helius fallback (partial data — no price changes)."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.get_token_overview(address)
                if result:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_token_overview failed for {address}: {e}")

        # Fallback to Helius
        try:
            logger.info(f"Using Helius fallback for token overview: {address}")
            return await helius_client.get_token_overview(address)
        except Exception as e:
            logger.warning(f"Helius get_token_overview also failed for {address}: {e}")
            return None

    async def get_token_overview_batch(self, addresses: list[str]) -> dict[str, dict]:
        """Birdeye primary, Helius fallback for batch overview."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.get_token_overview_batch(addresses)
                if result:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_token_overview_batch failed: {e}")

        # Fallback to Helius
        try:
            logger.info(f"Using Helius fallback for batch overview ({len(addresses)} tokens)")
            return await helius_client.get_token_overview_batch(addresses)
        except Exception as e:
            logger.warning(f"Helius get_token_overview_batch also failed: {e}")
            return {}

    # ── token trades (Birdeye → Helius) ────────────────────────────

    async def get_token_trades(
        self,
        address: str,
        tx_type: str = "all",
        sort_type: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Birdeye primary, Helius Enhanced Transactions fallback."""
        if self._is_birdeye_healthy():
            try:
                return await birdeye_client.get_token_trades(
                    address=address, tx_type=tx_type, sort_type=sort_type,
                    offset=offset, limit=limit,
                )
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_token_trades failed for {address}: {e}")

        # Fallback to Helius
        try:
            logger.info(f"Using Helius fallback for token trades: {address}")
            return await helius_client.get_token_trades(
                address=address, tx_type=tx_type, sort_type=sort_type,
                offset=offset, limit=limit,
            )
        except Exception as e:
            logger.warning(f"Helius get_token_trades also failed for {address}: {e}")
            return []

    # ── token security (Birdeye → Helius) ──────────────────────────

    async def get_token_security(self, address: str) -> Optional[dict]:
        """Birdeye primary, Helius fallback (full coverage via DAS)."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.get_token_security(address)
                if result:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_token_security failed for {address}: {e}")

        # Fallback to Helius
        try:
            logger.info(f"Using Helius fallback for token security: {address}")
            return await helius_client.get_token_security(address)
        except Exception as e:
            logger.warning(f"Helius get_token_security also failed for {address}: {e}")
            return None

    async def get_token_security_batch(self, addresses: list[str]) -> dict[str, dict]:
        """Birdeye primary, Helius fallback for batch security."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.get_token_security_batch(addresses)
                if result:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_token_security_batch failed: {e}")

        # Fallback to Helius
        try:
            logger.info(f"Using Helius fallback for batch security ({len(addresses)} tokens)")
            return await helius_client.get_token_security_batch(addresses)
        except Exception as e:
            logger.warning(f"Helius get_token_security_batch also failed: {e}")
            return {}

    # ── token holders (Birdeye → Helius) ───────────────────────────

    async def get_token_holders(self, address: str, limit: int = 20) -> list[dict]:
        """Birdeye primary, Helius fallback (full coverage via RPC)."""
        if self._is_birdeye_healthy():
            try:
                return await birdeye_client.get_token_holders(address, limit=limit)
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_token_holders failed for {address}: {e}")

        # Fallback to Helius
        try:
            logger.info(f"Using Helius fallback for token holders: {address}")
            return await helius_client.get_token_holders(address, limit=limit)
        except Exception as e:
            logger.warning(f"Helius get_token_holders also failed for {address}: {e}")
            return []

    # ── top traders (Birdeye only, degrades gracefully) ────────────

    async def get_top_traders(
        self,
        address: str,
        time_frame: str = "24h",
        sort_type: str = "desc",
        sort_by: str = "volume",
        offset: int = 0,
        limit: int = 10,
    ) -> list[dict]:
        """Birdeye only — too expensive to replicate via Helius transaction parsing."""
        if not self._is_birdeye_healthy():
            logger.debug("Birdeye unhealthy, skipping get_top_traders")
            return []
        try:
            return await birdeye_client.get_top_traders(
                address=address, time_frame=time_frame, sort_type=sort_type,
                sort_by=sort_by, offset=offset, limit=limit,
            )
        except Exception as e:
            if self._is_retriable_error(e):
                self._mark_birdeye_unhealthy(e)
            else:
                logger.warning(f"get_top_traders failed for {address}: {e}")
            return []

    # ── new listings (Birdeye → DexScreener) ───────────────────────

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
        """Birdeye primary, DexScreener fallback for new listing discovery."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.get_new_listings(
                    min_listing_time=min_listing_time,
                    max_listing_time=max_listing_time,
                    min_liquidity=min_liquidity,
                    sort_by=sort_by, sort_type=sort_type,
                    offset=offset, limit=limit,
                )
                if result:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_new_listings failed: {e}")

        # Fallback to DexScreener latest pairs
        try:
            logger.info("Using DexScreener fallback for new listings")
            return await dexscreener_client.get_latest_token_profiles(limit=limit)
        except Exception as e:
            logger.warning(f"DexScreener get_latest_token_profiles also failed: {e}")
            return []

    # ── search token (Birdeye → Helius address-only) ───────────────

    async def search_token(self, query: str) -> list[dict]:
        """Birdeye primary (name/symbol/address), Helius fallback (address only)."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.search_token(query)
                if result:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye search_token failed for '{query}': {e}")

        # Fallback to Helius (address lookup only)
        try:
            logger.info(f"Using Helius fallback for token search: {query}")
            return await helius_client.search_token(query)
        except Exception as e:
            logger.warning(f"Helius search_token also failed for '{query}': {e}")
            return []

    # ── price (Birdeye → Jupiter) ──────────────────────────────────

    async def get_price(self, address: str) -> Optional[float]:
        """Birdeye primary, Jupiter Price API fallback (free, no key)."""
        if self._is_birdeye_healthy():
            try:
                result = await birdeye_client.get_price(address)
                if result is not None:
                    return result
            except Exception as e:
                if self._is_retriable_error(e):
                    self._mark_birdeye_unhealthy(e)
                else:
                    logger.warning(f"Birdeye get_price failed for {address}: {e}")

        # Fallback to Jupiter
        try:
            logger.info(f"Using Jupiter fallback for price: {address}")
            return await jupiter_price_client.get_price(address)
        except Exception as e:
            logger.warning(f"Jupiter get_price also failed for {address}: {e}")
            return None

    # ── passthrough methods (no fallback needed) ───────────────────

    async def get_price_volume(self, address: str, time_type: str = "24h") -> Optional[dict]:
        """Birdeye only — no equivalent in Helius/Jupiter."""
        if not self._is_birdeye_healthy():
            return None
        try:
            return await birdeye_client.get_price_volume(address, time_type=time_type)
        except Exception as e:
            if self._is_retriable_error(e):
                self._mark_birdeye_unhealthy(e)
            else:
                logger.warning(f"get_price_volume failed for {address}: {e}")
            return None

    async def get_token_creation_info(self, address: str) -> Optional[dict]:
        """Birdeye only — no equivalent in Helius."""
        if not self._is_birdeye_healthy():
            return None
        try:
            return await birdeye_client.get_token_creation_info(address)
        except Exception as e:
            if self._is_retriable_error(e):
                self._mark_birdeye_unhealthy(e)
            else:
                logger.warning(f"get_token_creation_info failed for {address}: {e}")
            return None


data_provider = TokenDataProvider()
