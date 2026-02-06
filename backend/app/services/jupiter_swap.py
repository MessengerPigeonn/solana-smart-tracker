from __future__ import annotations
import asyncio
import logging
from typing import Optional
import httpx
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000


class JupiterSwapService:
    def __init__(self):
        self.base_url = settings.jupiter_swap_api_url

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount_lamports: int,
        slippage_bps: int = 500,
    ) -> Optional[dict]:
        """Get a swap quote from Jupiter V6 API."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.base_url}/quote",
                    params={
                        "inputMint": input_mint,
                        "outputMint": output_mint,
                        "amount": str(amount_lamports),
                        "slippageBps": slippage_bps,
                        "onlyDirectRoutes": "false",
                        "asLegacyTransaction": "false",
                    },
                )
                if resp.status_code != 200:
                    logger.error(f"Jupiter quote error {resp.status_code}: {resp.text}")
                    return None
                return resp.json()
        except Exception as e:
            logger.error(f"Jupiter quote request failed: {e}")
            return None

    async def get_swap_transaction(
        self,
        quote: dict,
        user_pubkey: str,
    ) -> Optional[dict]:
        """Get a serialized swap transaction from Jupiter V6 API."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.base_url}/swap",
                    json={
                        "quoteResponse": quote,
                        "userPublicKey": user_pubkey,
                        "wrapAndUnwrapSol": True,
                        "dynamicComputeUnitLimit": True,
                        "prioritizationFeeLamports": "auto",
                    },
                )
                if resp.status_code != 200:
                    logger.error(f"Jupiter swap error {resp.status_code}: {resp.text}")
                    return None
                return resp.json()
        except Exception as e:
            logger.error(f"Jupiter swap request failed: {e}")
            return None

    async def execute_swap(
        self,
        swap_transaction: str,
        keypair_bytes: bytes,
    ) -> Optional[str]:
        """Sign and send a swap transaction to Solana.

        Returns the transaction signature on success, None on failure.
        """
        try:
            from solders.keypair import Keypair
            from solders.transaction import VersionedTransaction
            import base64

            raw_tx = base64.b64decode(swap_transaction)
            tx = VersionedTransaction.from_bytes(raw_tx)

            kp = Keypair.from_bytes(keypair_bytes)
            signed_tx = VersionedTransaction(tx.message, [kp])

            helius_rpc = f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
            encoded_tx = base64.b64encode(bytes(signed_tx)).decode("utf-8")

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    helius_rpc,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "sendTransaction",
                        "params": [
                            encoded_tx,
                            {
                                "skipPreflight": False,
                                "preflightCommitment": "confirmed",
                                "encoding": "base64",
                                "maxRetries": 3,
                            },
                        ],
                    },
                )
                result = resp.json()
                if "error" in result:
                    logger.error(f"Solana sendTransaction error: {result['error']}")
                    return None
                signature = result.get("result")
                logger.info(f"Transaction sent: {signature}")
                return signature

        except ImportError:
            logger.error("solders package not installed. Cannot sign transactions.")
            return None
        except Exception as e:
            logger.error(f"Execute swap failed: {e}")
            return None

    async def confirm_transaction(self, signature: str, timeout_seconds: int = 30) -> bool:
        """Wait for a transaction to be confirmed."""
        helius_rpc = f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"
        elapsed = 0
        interval = 2

        while elapsed < timeout_seconds:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        helius_rpc,
                        json={
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "getSignatureStatuses",
                            "params": [[signature], {"searchTransactionHistory": False}],
                        },
                    )
                    result = resp.json()
                    statuses = result.get("result", {}).get("value", [])
                    if statuses and statuses[0]:
                        status = statuses[0]
                        if status.get("confirmationStatus") in ("confirmed", "finalized"):
                            if status.get("err") is None:
                                return True
                            else:
                                logger.error(f"Transaction {signature} failed: {status['err']}")
                                return False
            except Exception as e:
                logger.warning(f"Error checking tx status: {e}")

            await asyncio.sleep(interval)
            elapsed += interval

        logger.warning(f"Transaction {signature} not confirmed within {timeout_seconds}s")
        return False


jupiter_swap = JupiterSwapService()
