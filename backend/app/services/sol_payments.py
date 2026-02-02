from __future__ import annotations
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.models.user import User, Tier
from app.models.payment import Payment, PaymentMethod

settings = get_settings()

# SOL prices per tier (in SOL)
TIER_PRICES_SOL = {
    "pro": 1.0,
    "legend": 5.0,
}

TIER_DURATION_DAYS = {
    "pro": 30,
    "legend": 30,
}

SOLANA_RPC = "https://api.mainnet-beta.solana.com"


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
    expected_amount = TIER_PRICES_SOL.get(tier)
    if not expected_amount:
        raise ValueError(f"Invalid tier: {tier}")

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
