from __future__ import annotations
import asyncio
import logging
import time
import httpx
from typing import Optional
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
HELIUS_API = "https://api.helius.xyz/v0"
HELIUS_WALLET_API = "https://api.helius.xyz/v1"


class HeliusClient:
    def __init__(self):
        self.api_key = settings.helius_api_key
        self._semaphore = asyncio.Semaphore(settings.helius_rate_limit)
        self._identity_cache: dict[str, tuple[float, Optional[dict]]] = {}
        self._funded_by_cache: dict[str, tuple[float, Optional[dict]]] = {}

    # ── low-level helpers ──────────────────────────────────────────

    async def _rpc(self, method: str, params: list | dict) -> dict:
        """JSON-RPC 2.0 call to Helius RPC (DAS + standard Solana RPC)."""
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    HELIUS_RPC,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": method,
                        "params": params,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise Exception(f"Helius RPC error: {data['error']}")
                return data.get("result", {})

    async def _api_get(self, path: str, params: Optional[dict] = None) -> list | dict:
        """REST GET to Helius API (Enhanced Transactions, etc.)."""
        async with self._semaphore:
            all_params = {"api-key": self.api_key}
            if params:
                all_params.update(params)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{HELIUS_API}{path}",
                    params=all_params,
                )
                resp.raise_for_status()
                return resp.json()

    # ── token overview (DAS getAsset) ──────────────────────────────

    async def get_token_overview(self, address: str) -> Optional[dict]:
        """Fetch token metadata + price via DAS getAsset.

        Returns dict with keys matching what scanner.py expects from Birdeye:
        symbol, name, price, marketCap, liquidity, supply, authorities, etc.
        Price changes (5m/1h/24h) are NOT available from Helius and will be 0.
        """
        try:
            result = await self._rpc("getAsset", {"id": address})
        except Exception as e:
            logger.warning(f"Helius getAsset failed for {address}: {e}")
            return None

        if not result:
            return None

        content = result.get("content", {})
        metadata = content.get("metadata", {})
        token_info = result.get("token_info", {})
        price_info = token_info.get("price_info", {})

        supply_raw = token_info.get("supply", 0) or 0
        decimals = token_info.get("decimals", 0) or 0
        ui_supply = supply_raw / (10 ** decimals) if decimals > 0 else supply_raw
        price = price_info.get("price_per_token", 0) or 0

        return {
            "symbol": token_info.get("symbol") or metadata.get("symbol", ""),
            "name": metadata.get("name", ""),
            "price": price,
            "marketCap": ui_supply * price if price else 0,
            "liquidity": 0,  # not available from DAS
            "v24hUSD": 0,  # not available from DAS
            # Price changes not available from Helius
            "priceChange5mPercent": 0,
            "priceChange1hPercent": 0,
            "priceChange24hPercent": 0,
            # Buy/sell counts not available
            "buy24h": 0,
            "sell24h": 0,
            "uniqueWallet24h": 0,
            # Authorities (useful for security)
            "_authorities": result.get("authorities", []),
            "_mutable": result.get("mutable", False),
            "_supply": ui_supply,
        }

    async def get_token_overview_batch(self, addresses: list[str]) -> dict[str, dict]:
        """Batch token overview via sequential getAsset calls with spacing."""
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

    # ── token security (DAS getAsset) ──────────────────────────────

    async def get_token_security(self, address: str) -> Optional[dict]:
        """Extract security info from DAS getAsset.

        Returns dict compatible with Birdeye security response format:
        mintAuthority, freezeAuthority, isMutable, etc.
        """
        try:
            result = await self._rpc("getAsset", {"id": address})
        except Exception as e:
            logger.warning(f"Helius getAsset (security) failed for {address}: {e}")
            return None

        if not result:
            return None

        authorities = result.get("authorities", [])
        token_info = result.get("token_info", {})

        # Extract authorities
        mint_authority = token_info.get("mint_authority")
        freeze_authority = token_info.get("freeze_authority")

        # Check update authority from authorities list
        update_authority = None
        for auth in authorities:
            if "update" in (auth.get("scope", "") or "").lower():
                update_authority = auth.get("address")
                break

        is_mutable = result.get("mutable", False)

        return {
            "mintAuthority": mint_authority,
            "freezeAuthority": freeze_authority,
            "isMintable": mint_authority is not None,
            "isFreezable": freeze_authority is not None,
            "isMutable": is_mutable,
            "updateAuthority": update_authority,
        }

    async def get_token_security_batch(self, addresses: list[str]) -> dict[str, dict]:
        """Batch security info via sequential getAsset calls."""
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

    # ── token holders (Solana RPC via Helius) ──────────────────────

    async def get_token_holders(self, address: str, limit: int = 20) -> list[dict]:
        """Fetch top holders using getTokenLargestAccounts (standard Solana RPC).

        Returns list of holder dicts with uiAmount fields compatible with
        what print_scanner.py expects.
        """
        try:
            result = await self._rpc("getTokenLargestAccounts", [address])
        except Exception as e:
            logger.warning(f"Helius getTokenLargestAccounts failed for {address}: {e}")
            return []

        accounts = result.get("value", [])
        holders = []
        for acc in accounts[:limit]:
            holders.append({
                "address": acc.get("address", ""),
                "uiAmount": float(acc.get("uiAmount") or acc.get("uiAmountString", 0) or 0),
                "amount": acc.get("amount", "0"),
                "decimals": acc.get("decimals", 0),
            })
        return holders

    # ── token trades (Enhanced Transactions API) ───────────────────

    async def get_token_trades(
        self,
        address: str,
        tx_type: str = "all",
        sort_type: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch recent transactions for a token via Enhanced Transactions API.

        Parses swap transactions into buy/sell format compatible with
        what scanner.py's analyze_token_trades expects.
        """
        try:
            txs = await self._api_get(
                f"/addresses/{address}/transactions",
                params={"limit": min(limit, 100), "type": "SWAP"},
            )
        except Exception as e:
            logger.warning(f"Helius enhanced transactions failed for {address}: {e}")
            return []

        if not isinstance(txs, list):
            return []

        trades = []
        for tx in txs:
            parsed = self._parse_swap_tx(tx, address)
            if parsed:
                trades.append(parsed)

        return trades[:limit]

    def _parse_swap_tx(self, tx: dict, token_address: str) -> Optional[dict]:
        """Parse an Enhanced Transaction into a trade dict matching Birdeye format.

        Returns dict with: side, owner, base (token), quote (SOL/USDC) amounts.
        """
        tx_type = tx.get("type", "")
        if tx_type != "SWAP":
            return None

        fee_payer = tx.get("feePayer", "")
        token_transfers = tx.get("tokenTransfers", [])
        if not token_transfers:
            return None

        # Find the token transfer for our target token
        token_in = None   # token coming to fee_payer = buy
        token_out = None  # token leaving fee_payer = sell
        quote_transfer = None

        for transfer in token_transfers:
            mint = transfer.get("mint", "")
            if mint == token_address:
                if transfer.get("toUserAccount") == fee_payer:
                    token_in = transfer
                elif transfer.get("fromUserAccount") == fee_payer:
                    token_out = transfer
            else:
                # This is the quote side (SOL, USDC, etc.)
                quote_transfer = transfer

        if not token_in and not token_out:
            return None

        side = "buy" if token_in else "sell"
        token_transfer = token_in or token_out

        token_amount = abs(token_transfer.get("tokenAmount", 0) or 0)

        quote_amount = 0
        quote_price = 0
        if quote_transfer:
            quote_amount = abs(quote_transfer.get("tokenAmount", 0) or 0)

        return {
            "side": side,
            "owner": fee_payer,
            "base": {
                "uiAmount": token_amount,
                "nearestPrice": 0,
                "price": 0,
            },
            "quote": {
                "uiAmount": quote_amount,
                "nearestPrice": 1 if quote_amount > 0 else 0,
                "price": 1 if quote_amount > 0 else 0,
            },
        }

    # ── search token (address-only via DAS) ────────────────────────

    async def search_token(self, query: str) -> list[dict]:
        """Search for a token by address using DAS getAsset.

        Only works for exact address lookups (not name/symbol search).
        Returns list with single result in Birdeye-compatible format.
        """
        # Only attempt if query looks like a Solana address (base58, 32-44 chars)
        if len(query) < 32 or len(query) > 44:
            return []

        try:
            result = await self._rpc("getAsset", {"id": query})
        except Exception:
            return []

        if not result:
            return []

        content = result.get("content", {})
        metadata = content.get("metadata", {})
        token_info = result.get("token_info", {})
        price_info = token_info.get("price_info", {})

        return [{
            "address": query,
            "symbol": token_info.get("symbol") or metadata.get("symbol", "???"),
            "name": metadata.get("name", "Unknown"),
            "price": price_info.get("price_per_token", 0) or 0,
            "volume_24h_usd": 0,
            "liquidity": 0,
            "market_cap": 0,
            "price_change_24h_percent": 0,
        }]


    # ── Wallet Identity API (v1) ─────────────────────────────────────

    async def get_wallet_identity(self, address: str) -> Optional[dict]:
        """GET /v1/wallet/{address}/identity -- returns identity info or None."""
        cache_entry = self._identity_cache.get(address)
        if cache_entry:
            ts, result = cache_entry
            if time.monotonic() - ts < 86400:  # 24h
                return result

        try:
            async with self._semaphore:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        f"{HELIUS_WALLET_API}/wallet/{address}/identity",
                        params={"api-key": self.api_key},
                    )
                    if resp.status_code == 404:
                        self._identity_cache[address] = (time.monotonic(), None)
                        return None
                    resp.raise_for_status()
                    data = resp.json()
                    self._identity_cache[address] = (time.monotonic(), data)
                    return data
        except httpx.HTTPStatusError:
            return None
        except Exception as e:
            logger.debug(f"Helius wallet identity failed for {address}: {e}")
            return None

    async def batch_wallet_identity(self, addresses: list[str]) -> dict[str, dict]:
        """POST /v1/wallet/batch-identity -- up to 100 addresses."""
        results = {}
        uncached = []

        for addr in addresses:
            cache_entry = self._identity_cache.get(addr)
            if cache_entry:
                ts, result = cache_entry
                if time.monotonic() - ts < 86400 and result is not None:
                    results[addr] = result
                    continue
            uncached.append(addr)

        if not uncached:
            return results

        try:
            async with self._semaphore:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{HELIUS_WALLET_API}/wallet/batch-identity",
                        params={"api-key": self.api_key},
                        json={"addresses": uncached[:100]},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    now = time.monotonic()
                    for item in data if isinstance(data, list) else []:
                        addr = item.get("address") or item.get("wallet", "")
                        if addr:
                            self._identity_cache[addr] = (now, item)
                            results[addr] = item
        except Exception as e:
            logger.debug(f"Helius batch wallet identity failed: {e}")

        return results

    async def get_funded_by(self, address: str) -> Optional[dict]:
        """GET /v1/wallet/{address}/funded-by -- traces first SOL funder."""
        cache_entry = self._funded_by_cache.get(address)
        if cache_entry:
            ts, result = cache_entry
            if time.monotonic() - ts < 3600:  # 1h TTL
                return result

        try:
            async with self._semaphore:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        f"{HELIUS_WALLET_API}/wallet/{address}/funded-by",
                        params={"api-key": self.api_key},
                    )
                    if resp.status_code == 404:
                        self._funded_by_cache[address] = (time.monotonic(), None)
                        return None
                    resp.raise_for_status()
                    data = resp.json()
                    self._funded_by_cache[address] = (time.monotonic(), data)
                    return data
        except httpx.HTTPStatusError:
            return None
        except Exception as e:
            logger.debug(f"Helius funded-by failed for {address}: {e}")
            return None


helius_client = HeliusClient()
