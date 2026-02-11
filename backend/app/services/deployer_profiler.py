from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

HELIUS_API = "https://api.helius.xyz/v0"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"


@dataclass
class DeployerProfile:
    deployer_address: str = ""
    tokens_created: int = 0
    tokens_rugged: int = 0
    rug_rate: float = 0.0
    is_serial_rugger: bool = False


class DeployerProfiler:
    """Detect serial rugger deployers."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)
        self._cache: dict[str, tuple[float, DeployerProfile]] = {}
        self._cache_ttl = 3600  # 1 hour

    async def _helius_get(self, path: str, params: Optional[dict] = None) -> list | dict:
        async with self._semaphore:
            all_params = {"api-key": settings.helius_api_key}
            if params:
                all_params.update(params)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{HELIUS_API}{path}", params=all_params)
                resp.raise_for_status()
                return resp.json()

    async def _dexscreener_check(self, token_address: str) -> Optional[float]:
        """Check token liquidity via DexScreener. Returns liquidity in USD or None."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{DEXSCREENER_API}/{token_address}")
                if resp.status_code != 200:
                    return None
                data = resp.json()
                pairs = data.get("pairs") or []
                if not pairs:
                    return 0.0  # No pairs = dead token
                # Sum liquidity across all pairs
                total_liq = sum(
                    float(p.get("liquidity", {}).get("usd", 0) or 0)
                    for p in pairs
                )
                return total_liq
        except Exception:
            return None

    async def profile_deployer(self, token_address: str) -> DeployerProfile:
        """Get the deployer's history for a token."""
        if token_address in self._cache:
            ts, profile = self._cache[token_address]
            if time.monotonic() - ts < self._cache_ttl:
                return profile

        profile = DeployerProfile()

        try:
            # Step 1: Find the deployer by looking at earliest transactions for token
            txs = await self._helius_get(
                f"/addresses/{token_address}/transactions",
                params={"limit": 50},
            )
            if not isinstance(txs, list) or not txs:
                self._cache[token_address] = (time.monotonic(), profile)
                return profile

            # Find the creation/mint transaction (earliest, non-SWAP)
            deployer = ""
            for tx in reversed(txs):  # Oldest first
                tx_type = tx.get("type", "")
                if tx_type in ("CREATE", "TOKEN_MINT", "CREATE_ACCOUNT"):
                    deployer = tx.get("feePayer", "")
                    break
                # Also check if it's a very early tx with token mint instructions
                if not deployer and tx.get("feePayer"):
                    # Fallback: the fee payer of the very first tx
                    deployer = tx.get("feePayer", "")

            if not deployer:
                self._cache[token_address] = (time.monotonic(), profile)
                return profile

            profile.deployer_address = deployer

            # Step 2: Get deployer's other token creations
            deployer_txs = await self._helius_get(
                f"/addresses/{deployer}/transactions",
                params={"limit": 50},
            )
            if not isinstance(deployer_txs, list):
                self._cache[token_address] = (time.monotonic(), profile)
                return profile

            # Find token creation transactions
            created_tokens = set()
            for tx in deployer_txs:
                tx_type = tx.get("type", "")
                if tx_type in ("CREATE", "TOKEN_MINT", "CREATE_ACCOUNT"):
                    # Extract token mints from token transfers
                    for tt in tx.get("tokenTransfers", []):
                        mint = tt.get("mint", "")
                        if mint and len(mint) > 30:
                            created_tokens.add(mint)

            # Remove the current token from the set
            created_tokens.discard(token_address)

            profile.tokens_created = len(created_tokens) + 1  # +1 for current token

            if not created_tokens:
                self._cache[token_address] = (time.monotonic(), profile)
                return profile

            # Step 3: Check each created token's liquidity via DexScreener
            rugged = 0
            checked = 0
            for other_token in list(created_tokens)[:8]:  # Max 8 to limit API calls
                liq = await self._dexscreener_check(other_token)
                if liq is not None:
                    checked += 1
                    if liq < 100:  # Less than $100 liquidity = rugged/dead
                        rugged += 1
                await asyncio.sleep(0.3)  # Rate limit DexScreener

            profile.tokens_rugged = rugged
            if checked > 0:
                profile.rug_rate = rugged / checked
            profile.is_serial_rugger = profile.tokens_created >= 3 and rugged >= 2

        except Exception as e:
            logger.warning(f"DeployerProfiler: failed for {token_address[:8]}: {e}")

        self._cache[token_address] = (time.monotonic(), profile)
        if profile.is_serial_rugger:
            logger.info(
                f"DeployerProfiler: serial rugger detected for {token_address[:8]} — "
                f"deployer {profile.deployer_address[:8]}, "
                f"{profile.tokens_rugged}/{profile.tokens_created} rugged"
            )
        return profile


deployer_profiler = DeployerProfiler()
