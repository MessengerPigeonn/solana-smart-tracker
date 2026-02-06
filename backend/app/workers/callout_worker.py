from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.database import async_session
from app.models.callout import Callout
from app.models.token import ScannedToken
from app.services.callout_engine import generate_callouts
from app.services.data_provider import data_provider

logger = logging.getLogger(__name__)


MAX_PEAK_MULTIPLIER = 50  # reject peaks beyond 50x callout mcap
PEAK_UPDATE_DAYS = 30  # Track peak market cap for callouts up to 30 days


async def _update_peak_market_caps(db):
    """Update peak_market_cap for recent callouts using current token data."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=PEAK_UPDATE_DAYS)
    result = await db.execute(
        select(Callout).where(
            Callout.created_at >= cutoff,
            Callout.market_cap.isnot(None),
            Callout.market_cap > 0,
        )
    )
    callouts = result.scalars().all()
    if not callouts:
        return

    addresses = list(set(c.token_address for c in callouts))
    token_result = await db.execute(
        select(ScannedToken).where(ScannedToken.address.in_(addresses))
    )
    tokens_by_addr = {t.address: t for t in token_result.scalars().all()}

    # Fetch fallback market caps for tokens not in scanned_tokens
    missing_addresses = [a for a in addresses if a not in tokens_by_addr]
    fallback_mcaps = {}
    if missing_addresses:
        try:
            overviews = await data_provider.get_token_overview_batch(missing_addresses)
            for addr, overview in overviews.items():
                mcap = overview.get("marketCap") or overview.get("mc") or 0
                if mcap > 0:
                    fallback_mcaps[addr] = mcap
            if fallback_mcaps:
                logger.info(
                    f"Fetched {len(fallback_mcaps)} fallback market caps "
                    f"for tokens not in scanned_tokens"
                )
        except Exception as e:
            logger.warning(f"Failed to fetch fallback market caps: {e}")

    updated = 0
    corrected = 0
    for callout in callouts:
        # Correct existing peaks that exceed the cap (clean up prior bad data)
        if (callout.peak_market_cap
                and callout.peak_market_cap > callout.market_cap * MAX_PEAK_MULTIPLIER):
            callout.peak_market_cap = None
            corrected += 1

        token = tokens_by_addr.get(callout.token_address)
        if token and token.market_cap > 0:
            # Sanity check: reject absurd market caps (mcap/liquidity > 200x is bad data)
            if token.liquidity > 0 and token.market_cap / token.liquidity > 200:
                continue
            current_mcap = token.market_cap
        elif callout.token_address in fallback_mcaps:
            current_mcap = fallback_mcaps[callout.token_address]
        else:
            continue

        if current_mcap > callout.market_cap * MAX_PEAK_MULTIPLIER:
            continue

        old_peak = callout.peak_market_cap or 0
        if current_mcap > old_peak:
            callout.peak_market_cap = current_mcap
            updated += 1

    if updated or corrected:
        logger.info(
            f"Peak market caps: {updated} updated, {corrected} corrected (reset bad data)"
        )


async def run_callout_worker():
    """Background worker that analyzes scanned data and generates callouts."""
    logger.info("Callout worker started")

    # Brief wait for initial scan data to populate
    await asyncio.sleep(5)

    while True:
        try:
            async with async_session() as db:
                callouts = await generate_callouts(db)
                await _update_peak_market_caps(db)
                await db.commit()
                if callouts:
                    logger.info(
                        f"Generated {len(callouts)} callouts: "
                        + ", ".join(f"{c.token_symbol}({c.signal.value}:{c.score})" for c in callouts)
                    )
        except asyncio.CancelledError:
            logger.info("Callout worker cancelled")
            break
        except Exception as e:
            logger.error(f"Callout worker error: {e}")

        await asyncio.sleep(30)  # Run every 30s to match faster scan cycle
