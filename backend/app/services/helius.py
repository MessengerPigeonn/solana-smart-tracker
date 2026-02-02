from __future__ import annotations
import httpx
from typing import Optional
from app.config import get_settings

settings = get_settings()

HELIUS_BASE = "https://api.helius.xyz/v0"


class HeliusClient:
    def __init__(self):
        self.api_key = settings.helius_api_key

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        all_params = {"api-key": self.api_key}
        if params:
            all_params.update(params)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{HELIUS_BASE}{path}",
                params=all_params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{HELIUS_BASE}{path}",
                params={"api-key": self.api_key},
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_token_metadata(self, mint_addresses: list[str]) -> list[dict]:
        """Get metadata for one or more token mint addresses."""
        data = await self._post("/token-metadata", {"mintAccounts": mint_addresses})
        return data if isinstance(data, list) else []

    async def get_transaction_history(
        self,
        address: str,
        before: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get parsed transaction history for an address."""
        params = {"limit": limit}
        if before:
            params["before"] = before
        return await self._get(f"/addresses/{address}/transactions", params=params)

    async def get_balances(self, address: str) -> dict:
        """Get token balances for a wallet."""
        return await self._get(f"/addresses/{address}/balances")


helius_client = HeliusClient()
