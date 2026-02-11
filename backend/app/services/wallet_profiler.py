from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

HELIUS_API = "https://api.helius.xyz/v0"


@dataclass
class WalletProfile:
    address: str
    age_days: float = 0.0
    total_tx_count: int = 0
    first_tx_timestamp: int = 0
    warmup_score: float = 0.0
    is_fresh: bool = False


class WalletProfiler:
    """Profile wallet age and detect warmup patterns."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)
        self._cache: dict[str, tuple[float, WalletProfile]] = {}
        self._cache_ttl = 600  # 10 minutes

    async def _helius_get(self, path: str, params: Optional[dict] = None) -> list | dict:
        async with self._semaphore:
            all_params = {"api-key": settings.helius_api_key}
            if params:
                all_params.update(params)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{HELIUS_API}{path}", params=all_params)
                resp.raise_for_status()
                return resp.json()

    async def profile_wallet(self, address: str) -> WalletProfile:
        """Profile a wallet's age and transaction pattern.
        Uses 1 Helius API call per wallet.
        """
        if address in self._cache:
            ts, profile = self._cache[address]
            if time.monotonic() - ts < self._cache_ttl:
                return profile

        profile = WalletProfile(address=address)

        try:
            txs = await self._helius_get(
                f"/addresses/{address}/transactions",
                params={"limit": 50},
            )
        except Exception as e:
            logger.debug(f"WalletProfiler: failed to fetch txs for {address[:8]}: {e}")
            self._cache[address] = (time.monotonic(), profile)
            return profile

        if not isinstance(txs, list) or len(txs) == 0:
            self._cache[address] = (time.monotonic(), profile)
            return profile

        profile.total_tx_count = len(txs)

        # Oldest tx is last in the list (newest first from API)
        oldest_tx = txs[-1]
        newest_tx = txs[0]
        first_ts = oldest_tx.get("timestamp", 0)
        profile.first_tx_timestamp = first_ts

        if first_ts > 0:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            age_seconds = now_ts - first_ts
            profile.age_days = max(age_seconds / 86400, 0)

            if profile.age_days < 3:
                profile.is_fresh = True
                profile.warmup_score += 0.2
            elif profile.age_days < 7:
                profile.is_fresh = True

        # Check for warmup patterns
        has_normal_transfer = False
        all_tiny = True
        swap_only = True

        for tx in txs:
            tx_type = tx.get("type", "")

            # Check for non-SWAP transactions
            if tx_type != "SWAP":
                swap_only = False

            # Check native transfer amounts
            for nt in tx.get("nativeTransfers", []):
                amount_sol = (nt.get("amount", 0) or 0) / 1e9  # lamports to SOL
                if amount_sol > 0.01:
                    all_tiny = False
                if nt.get("fromUserAccount") == address or nt.get("toUserAccount") == address:
                    if tx_type not in ("SWAP", "COMPRESSED_NFT_MINT"):
                        has_normal_transfer = True

            # Check token transfer amounts
            for tt in tx.get("tokenTransfers", []):
                amount = abs(tt.get("tokenAmount", 0) or 0)
                if amount > 0.01:
                    all_tiny = False

        # Warmup heuristic: fresh wallet with many tiny txs
        if profile.age_days < 7 and profile.total_tx_count >= 10 and all_tiny:
            profile.warmup_score += 0.8

        # Only SWAP txs (no normal transfers) = suspicious
        if swap_only and profile.total_tx_count >= 5:
            profile.warmup_score += 0.3

        # Cap at 1.0
        profile.warmup_score = min(profile.warmup_score, 1.0)

        self._cache[address] = (time.monotonic(), profile)
        return profile

    async def batch_profile_wallets(
        self, addresses: list[str], max_concurrent: int = 3
    ) -> list[WalletProfile]:
        """Profile up to 10 wallets with rate limiting."""
        addresses = addresses[:10]
        profiles = []
        sem = asyncio.Semaphore(max_concurrent)

        async def _profile_one(addr: str) -> WalletProfile:
            async with sem:
                result = await self.profile_wallet(addr)
                await asyncio.sleep(0.3)  # Rate limit
                return result

        tasks = [_profile_one(addr) for addr in addresses]
        profiles = await asyncio.gather(*tasks, return_exceptions=True)
        return [p for p in profiles if isinstance(p, WalletProfile)]


wallet_profiler = WalletProfiler()
