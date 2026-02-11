"""Hot token queue for real-time smart wallet swap signals.

Tokens detected via Helius webhooks are queued here and consumed by
scan_worker each cycle.  The module is intentionally simple: a dict
protected by a threading-style guard (asyncio is single-threaded so a
plain dict is safe, but we keep the API explicit for clarity).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# {token_address: {reason: str, added_at: float, wallets: [str, ...]}}
hot_token_queue: dict[str, dict] = {}


def add_hot_token(address: str, reason: str, wallet: Optional[str] = None) -> None:
    """Add a token to the hot queue (or append the wallet if already present)."""
    now = time.time()
    if address in hot_token_queue:
        entry = hot_token_queue[address]
        if wallet and wallet not in entry["wallets"]:
            entry["wallets"].append(wallet)
        # Keep the most recent reason
        entry["reason"] = reason
        logger.info(
            "hot_tokens: updated %s — %d wallets, reason=%s",
            address[:8], len(entry["wallets"]), reason,
        )
    else:
        hot_token_queue[address] = {
            "reason": reason,
            "added_at": now,
            "wallets": [wallet] if wallet else [],
        }
        logger.info("hot_tokens: added %s reason=%s wallet=%s", address[:8], reason, wallet)


def get_and_clear_hot_tokens() -> dict[str, dict]:
    """Return all queued hot tokens and clear the queue.

    Called by scan_worker each cycle to pick up webhook-detected tokens.
    """
    if not hot_token_queue:
        return {}
    snapshot = dict(hot_token_queue)
    hot_token_queue.clear()
    logger.info("hot_tokens: flushed %d tokens to scan_worker", len(snapshot))
    return snapshot
