"""Helius webhook lifecycle management.

Registers an enhanced webhook with Helius to receive real-time SWAP
notifications for high-reputation smart wallets, and periodically
refreshes the tracked address list.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models.smart_wallet import SmartWallet
from app.models.cto_wallet import CTOWallet

logger = logging.getLogger(__name__)
settings = get_settings()

HELIUS_API = "https://api.helius.xyz/v0"
WEBHOOK_URL = "https://solana-smart-tracker-production.up.railway.app/api/webhooks/helius"
MIN_REPUTATION_SCORE = 50.0
REFRESH_INTERVAL_SECONDS = 600  # 10 minutes

# In-memory webhook state
_webhook_id: Optional[str] = None


CTO_MIN_REPUTATION = 30.0


async def _get_high_rep_wallets() -> list[str]:
    """Fetch wallet addresses with reputation_score > MIN_REPUTATION_SCORE.

    Also includes CTO wallets with reputation > CTO_MIN_REPUTATION.
    """
    async with async_session() as session:
        result = await session.execute(
            select(SmartWallet.wallet_address).where(
                SmartWallet.reputation_score > MIN_REPUTATION_SCORE
            )
        )
        addresses = [row[0] for row in result.all()]

        # Include CTO wallets with rep > 30
        cto_result = await session.execute(
            select(CTOWallet.wallet_address).where(
                CTOWallet.reputation_score > CTO_MIN_REPUTATION
            )
        )
        cto_addresses = [row[0] for row in cto_result.all()]
        # Merge without duplicates
        existing = set(addresses)
        for addr in cto_addresses:
            if addr not in existing:
                addresses.append(addr)

    logger.info(
        "helius_webhooks: found %d wallets (smart: %d, CTO: %d) with sufficient rep",
        len(addresses), len(addresses) - len(cto_addresses), len(cto_addresses),
    )
    return addresses


def get_webhook_id() -> Optional[str]:
    """Return the current Helius webhook ID (or None if not registered)."""
    return _webhook_id


async def register_webhook() -> Optional[str]:
    """Register (or re-register) an enhanced Helius webhook for SWAP events.

    Returns the webhook ID on success, None on failure.
    """
    global _webhook_id

    addresses = await _get_high_rep_wallets()
    if not addresses:
        logger.warning("helius_webhooks: no high-rep wallets found, skipping registration")
        return None

    if not settings.helius_api_key:
        logger.error("helius_webhooks: helius_api_key not configured, cannot register webhook")
        return None

    # If we already have a webhook, delete it first so we don't leak
    if _webhook_id:
        await delete_webhook()

    payload = {
        "webhookURL": WEBHOOK_URL,
        "transactionTypes": ["SWAP"],
        "accountAddresses": addresses,
        "webhookType": "enhanced",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{HELIUS_API}/webhooks",
                params={"api-key": settings.helius_api_key},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            _webhook_id = data.get("webhookID")
            logger.info(
                "helius_webhooks: registered webhook %s tracking %d addresses",
                _webhook_id, len(addresses),
            )
            return _webhook_id
    except httpx.HTTPStatusError as e:
        logger.error("helius_webhooks: registration failed HTTP %s — %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.error("helius_webhooks: registration failed — %s", e)

    return None


async def delete_webhook() -> bool:
    """Delete the current Helius webhook."""
    global _webhook_id

    if not _webhook_id:
        logger.debug("helius_webhooks: no webhook to delete")
        return True

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                f"{HELIUS_API}/webhooks/{_webhook_id}",
                params={"api-key": settings.helius_api_key},
            )
            resp.raise_for_status()
            logger.info("helius_webhooks: deleted webhook %s", _webhook_id)
            _webhook_id = None
            return True
    except Exception as e:
        logger.error("helius_webhooks: failed to delete webhook %s — %s", _webhook_id, e)
        _webhook_id = None  # Clear anyway to avoid stale reference
        return False


async def refresh_tracked_addresses() -> bool:
    """Update the webhook with the current set of high-rep wallets.

    Uses PUT to update the existing webhook's accountAddresses in place.
    Falls back to full re-registration if PUT fails.
    """
    global _webhook_id

    addresses = await _get_high_rep_wallets()
    if not addresses:
        logger.warning("helius_webhooks: no high-rep wallets, nothing to track")
        return False

    if not _webhook_id:
        logger.info("helius_webhooks: no active webhook, doing full registration")
        result = await register_webhook()
        return result is not None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{HELIUS_API}/webhooks/{_webhook_id}",
                params={"api-key": settings.helius_api_key},
                json={
                    "webhookURL": WEBHOOK_URL,
                    "transactionTypes": ["SWAP"],
                    "accountAddresses": addresses,
                    "webhookType": "enhanced",
                },
            )
            resp.raise_for_status()
            logger.info(
                "helius_webhooks: refreshed webhook %s — now tracking %d addresses",
                _webhook_id, len(addresses),
            )
            return True
    except Exception as e:
        logger.warning("helius_webhooks: PUT refresh failed (%s), re-registering", e)
        result = await register_webhook()
        return result is not None


async def run_webhook_refresh_loop() -> None:
    """Background loop that refreshes tracked addresses every REFRESH_INTERVAL_SECONDS.

    Also handles initial registration on first run.
    """
    # Initial registration
    try:
        await register_webhook()
    except Exception as e:
        logger.error("helius_webhooks: initial registration failed — %s", e)

    while True:
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
        try:
            await refresh_tracked_addresses()
        except Exception as e:
            logger.error("helius_webhooks: refresh loop error — %s", e)
