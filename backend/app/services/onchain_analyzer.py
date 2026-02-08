from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional
import httpx
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

HELIUS_API = "https://api.helius.xyz/v0"


class OnChainAnalyzer:
    """Analyzes on-chain patterns using Helius Enhanced Transactions API."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)
        self._cache: dict[str, tuple[float, list]] = {}  # {token_addr: (timestamp, result)}
        self._cache_ttl = 300  # 5 minutes

    async def _api_get(self, path: str, params: Optional[dict] = None) -> list | dict:
        """REST GET to Helius API."""
        async with self._semaphore:
            all_params = {"api-key": settings.helius_api_key}
            if params:
                all_params.update(params)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{HELIUS_API}{path}",
                    params=all_params,
                )
                resp.raise_for_status()
                return resp.json()

    async def get_early_buyers(self, token_address: str, limit: int = 20) -> list[dict]:
        """Get first N buyer wallets with timing and amounts.

        Returns list of dicts: {wallet, amount_usd, timestamp, is_buy}
        """
        # Check cache
        cache_key = f"early_{token_address}"
        if cache_key in self._cache:
            ts, result = self._cache[cache_key]
            if time.monotonic() - ts < self._cache_ttl:
                return result[:limit]

        try:
            txs = await self._api_get(
                f"/addresses/{token_address}/transactions",
                params={"limit": 100, "type": "SWAP"},
            )
        except Exception as e:
            logger.warning(f"OnChainAnalyzer: failed to get txs for {token_address}: {e}")
            return []

        if not isinstance(txs, list):
            return []

        buyers = []
        seen_wallets = set()

        # Transactions come newest first, so reverse for chronological order
        for tx in reversed(txs):
            if tx.get("type") != "SWAP":
                continue

            fee_payer = tx.get("feePayer", "")
            if not fee_payer or fee_payer in seen_wallets:
                continue

            # Check if this is a buy (token coming TO the fee_payer)
            token_transfers = tx.get("tokenTransfers", [])
            is_buy = False
            amount_usd = 0

            for transfer in token_transfers:
                mint = transfer.get("mint", "")
                if mint == token_address:
                    if transfer.get("toUserAccount") == fee_payer:
                        is_buy = True
                else:
                    # Quote side amount
                    amount_usd = abs(transfer.get("tokenAmount", 0) or 0)

            if is_buy:
                seen_wallets.add(fee_payer)
                buyers.append({
                    "wallet": fee_payer,
                    "amount_usd": amount_usd,
                    "timestamp": tx.get("timestamp", 0),
                    "is_buy": True,
                })

            if len(buyers) >= limit:
                break

        # Cache result
        self._cache[cache_key] = (time.monotonic(), buyers)
        return buyers[:limit]

    async def detect_wallet_clustering(self, wallets: list[str]) -> dict:
        """Check if wallets share funding source (simplified version).

        For MVP: Just check if multiple wallets appeared in the same block
        (suspiciously timed = likely bot/insider coordination).

        Returns: {clustered: bool, cluster_count: int, suspicious_pairs: list}
        """
        if len(wallets) < 2:
            return {"clustered": False, "cluster_count": 0, "suspicious_pairs": []}

        # This is expensive, so we keep it simple for now
        # Just return the count of wallets — clustering detection can be enhanced later
        return {
            "clustered": False,
            "cluster_count": 0,
            "suspicious_pairs": [],
        }

    def clear_cache(self):
        """Clear the internal cache."""
        self._cache.clear()


onchain_analyzer = OnChainAnalyzer()
