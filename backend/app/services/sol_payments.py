from __future__ import annotations
import logging
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.user import User, Tier
from app.models.payment import Payment, PaymentMethod

logger = logging.getLogger(__name__)

settings = get_settings()

# USD prices per tier
TIER_USD = {
    "pro": 199,
    "legend": 999,
}

# Discount for paying with SOL (10% off)
SOL_DISCOUNT = 0.10

TIER_DURATION_DAYS = {
    "pro": 30,
    "legend": 30,
}

SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# SOL native mint address for Jupiter price lookup
SOL_MINT = "So11111111111111111111111111111111111111112"

# Cache for SOL price (avoid hammering Jupiter on every request)
_sol_price_cache: dict[str, float | datetime] = {"price": 0.0, "fetched_at": datetime.min}
SOL_PRICE_CACHE_SECONDS = 60


async def _fetch_jupiter_price() -> float | None:
    """Try Jupiter Price API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.jup.ag/price/v2",
                params={"ids": SOL_MINT},
            )
            resp.raise_for_status()
            data = resp.json()
            token_data = data.get("data", {}).get(SOL_MINT)
            if token_data and token_data.get("price"):
                return float(token_data["price"])
    except Exception as e:
        logger.warning(f"Jupiter price fetch failed: {e}")
    return None


async def _fetch_coingecko_price() -> float | None:
    """Try CoinGecko free API as fallback."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "solana", "vs_currencies": "usd"},
            )
            resp.raise_for_status()
            data = resp.json()
            price = data.get("solana", {}).get("usd")
            if price:
                return float(price)
    except Exception as e:
        logger.warning(f"CoinGecko price fetch failed: {e}")
    return None


async def _fetch_dexscreener_price() -> float | None:
    """Try DexScreener API — get SOL price from the SOL/USDC pair."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.dexscreener.com/token-pairs/v1/solana/{SOL_MINT}",
            )
            resp.raise_for_status()
            pairs = resp.json()
            if isinstance(pairs, list):
                for pair in pairs:
                    price_usd = pair.get("priceUsd")
                    if price_usd:
                        return float(price_usd)
    except Exception as e:
        logger.warning(f"DexScreener SOL price fetch failed: {e}")
    return None


async def get_sol_usd_price() -> float:
    """Fetch current SOL/USD price. Tries Jupiter then CoinGecko. Cached for 60s."""
    cached_at = _sol_price_cache.get("fetched_at", datetime.min)
    if isinstance(cached_at, datetime) and (datetime.now() - cached_at).total_seconds() < SOL_PRICE_CACHE_SECONDS:
        price = _sol_price_cache.get("price", 0.0)
        if isinstance(price, (int, float)) and price > 0:
            return float(price)

    # Try Jupiter, then CoinGecko, then DexScreener
    price = await _fetch_jupiter_price()
    if not price:
        price = await _fetch_coingecko_price()
    if not price:
        price = await _fetch_dexscreener_price()

    if price and price > 0:
        _sol_price_cache["price"] = price
        _sol_price_cache["fetched_at"] = datetime.now()
        return price

    # Fallback to stale cached price if available
    cached = _sol_price_cache.get("price", 0.0)
    if isinstance(cached, (int, float)) and cached > 0:
        logger.warning(f"Using stale cached SOL price: {cached}")
        return float(cached)

    raise RuntimeError("Unable to fetch SOL price from any source")


async def get_tier_sol_amount(tier: str) -> float:
    """Calculate the discounted SOL amount for a tier based on live SOL/USD price."""
    usd_price = TIER_USD.get(tier)
    if not usd_price:
        raise ValueError(f"Invalid tier: {tier}")
    sol_price = await get_sol_usd_price()
    discounted_usd = usd_price * (1 - SOL_DISCOUNT)
    return round(discounted_usd / sol_price, 4)


async def verify_sol_payment(
    db: AsyncSession,
    user: User,
    tx_signature: str,
    tier: str,
) -> bool:
    """
    Verify a SOL transfer on-chain.
    Checks that the transaction transferred the correct amount to the treasury wallet.
    """
    expected_amount = await get_tier_sol_amount(tier)

    # Fetch transaction from Solana RPC
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            SOLANA_RPC,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    tx_signature,
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
                ],
            },
        )
        data = resp.json()

    result = data.get("result")
    if not result:
        return False

    # Check transaction was successful
    meta = result.get("meta", {})
    if meta.get("err") is not None:
        return False

    # Check for SOL transfer to treasury
    treasury = settings.sol_treasury_wallet
    if not treasury:
        return False

    # Parse pre/post balances to find transfer
    account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
    pre_balances = meta.get("preBalances", [])
    post_balances = meta.get("postBalances", [])

    treasury_index = None
    for i, key in enumerate(account_keys):
        pubkey = key if isinstance(key, str) else key.get("pubkey", "")
        if pubkey == treasury:
            treasury_index = i
            break

    if treasury_index is None:
        return False

    # Calculate SOL received (in lamports, 1 SOL = 1e9 lamports)
    received_lamports = post_balances[treasury_index] - pre_balances[treasury_index]
    received_sol = received_lamports / 1e9

    if received_sol < expected_amount * 0.99:  # Allow 1% tolerance
        return False

    # Check for duplicate payment
    existing = await db.execute(
        select(Payment).where(Payment.tx_signature == tx_signature)
    )
    if existing.scalar_one_or_none():
        return False

    # Activate subscription
    tier_enum = Tier.pro if tier == "pro" else Tier.legend
    duration = TIER_DURATION_DAYS.get(tier, 30)

    user.tier = tier_enum
    user.subscription_expires = datetime.now(timezone.utc) + timedelta(days=duration)

    payment = Payment(
        user_id=user.id,
        method=PaymentMethod.sol,
        amount=expected_amount,
        tier=tier_enum,
        tx_signature=tx_signature,
    )
    db.add(payment)
    await db.flush()
    return True
