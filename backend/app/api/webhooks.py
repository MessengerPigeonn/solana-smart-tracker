"""Webhook endpoints for external service callbacks.

The Helius endpoint receives enhanced transaction notifications for SWAP
events involving tracked smart wallets.  It is unauthenticated because
Helius calls it directly — we validate the payload structure instead.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from app.services.hot_tokens import add_hot_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# ── Convergence tracker ───────────────────────────────────────────────
# Maps token_address -> [(wallet, timestamp)] for detecting multi-wallet
# convergence on the same token within a short window.
_convergence_tracker: dict[str, list[tuple[str, float]]] = {}
CONVERGENCE_WINDOW_SECONDS = 300  # 5 minutes
CONVERGENCE_THRESHOLD = 3  # wallets buying the same token

# Well-known non-meme tokens to ignore (SOL wrappers, stables, etc.)
_IGNORED_MINTS = {
    "So11111111111111111111111111111111111111112",   # Wrapped SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",   # USDT
}


def _prune_convergence(token: str, now: float) -> None:
    """Remove entries older than the convergence window."""
    if token not in _convergence_tracker:
        return
    cutoff = now - CONVERGENCE_WINDOW_SECONDS
    _convergence_tracker[token] = [
        (w, ts) for w, ts in _convergence_tracker[token] if ts >= cutoff
    ]
    if not _convergence_tracker[token]:
        del _convergence_tracker[token]


def _track_convergence(token: str, wallet: str) -> Optional[int]:
    """Record a wallet buying a token and return the convergence count.

    Returns the number of distinct tracked wallets that bought this token
    within the convergence window, or None if the wallet was already
    recorded.
    """
    now = time.time()
    _prune_convergence(token, now)

    entries = _convergence_tracker.get(token, [])
    # Skip if this wallet already recorded for this token in the window
    if any(w == wallet for w, _ in entries):
        return len(set(w for w, _ in entries))

    entries.append((wallet, now))
    _convergence_tracker[token] = entries

    distinct = len(set(w for w, _ in entries))
    return distinct


def _parse_swap_event(tx: dict) -> Optional[dict]:
    """Extract buy/sell info from a single Helius enhanced transaction.

    Returns a dict with keys: wallet, token_address, direction ("BUY"/"SELL")
    or None if the transaction is not a usable swap.
    """
    fee_payer = tx.get("feePayer")
    if not fee_payer:
        return None

    token_transfers = tx.get("tokenTransfers")
    if not token_transfers or not isinstance(token_transfers, list):
        return None

    # Look for a token (not SOL/stables) transferred TO the feePayer = BUY
    # or FROM the feePayer = SELL
    for transfer in token_transfers:
        mint = transfer.get("mint", "")
        if not mint or mint in _IGNORED_MINTS:
            continue

        to_account = transfer.get("toUserAccount", "")
        from_account = transfer.get("fromUserAccount", "")

        if to_account == fee_payer:
            return {"wallet": fee_payer, "token_address": mint, "direction": "BUY"}
        elif from_account == fee_payer:
            return {"wallet": fee_payer, "token_address": mint, "direction": "SELL"}

    return None


@router.post("/helius")
async def helius_webhook(request: Request):
    """Receive enhanced transaction notifications from Helius.

    Helius sends an array of enhanced transaction objects.  We parse each
    for SWAP events, detect buys by tracked wallets, and queue the bought
    tokens for the scan_worker.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Helius sends a JSON array of transactions
    if not isinstance(payload, list):
        # Some webhook payloads wrap in an object — try to extract
        if isinstance(payload, dict):
            payload = payload.get("data", payload.get("transactions", [payload]))
        if not isinstance(payload, list):
            logger.warning("helius_webhook: unexpected payload type %s", type(payload).__name__)
            raise HTTPException(status_code=400, detail="Expected array of transactions")

    buy_count = 0
    for tx in payload:
        if not isinstance(tx, dict):
            continue

        # Only process SWAP transactions
        tx_type = tx.get("type", "")
        if tx_type != "SWAP":
            continue

        parsed = _parse_swap_event(tx)
        if not parsed or parsed["direction"] != "BUY":
            continue

        token = parsed["token_address"]
        wallet = parsed["wallet"]
        buy_count += 1

        # Track convergence
        convergence_count = _track_convergence(token, wallet)

        if convergence_count is not None and convergence_count >= CONVERGENCE_THRESHOLD:
            wallets_in_window = [w for w, _ in _convergence_tracker.get(token, [])]
            logger.info(
                "CONVERGENCE SIGNAL: %d tracked wallets bought %s within %ds — wallets: %s",
                convergence_count, token[:8], CONVERGENCE_WINDOW_SECONDS,
                [w[:8] for w in wallets_in_window],
            )
            add_hot_token(
                token,
                reason=f"convergence:{convergence_count}_wallets_in_{CONVERGENCE_WINDOW_SECONDS}s",
                wallet=wallet,
            )
        else:
            add_hot_token(
                token,
                reason=f"smart_wallet_buy",
                wallet=wallet,
            )

    logger.debug("helius_webhook: processed %d buy events from %d transactions", buy_count, len(payload))
    return {"status": "ok", "processed": buy_count}
