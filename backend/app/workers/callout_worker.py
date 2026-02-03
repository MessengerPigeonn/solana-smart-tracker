from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.database import async_session
from app.models.callout import Callout
from app.models.token import ScannedToken
from app.services.callout_engine import generate_callouts

logger = logging.getLogger(__name__)


async def _update_peak_market_caps(db):
    """Update peak_market_cap for recent callouts using current token data."""
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(Callout).where(
            Callout.created_at >= seven_days_ago,
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

    updated = 0
    for callout in callouts:
        token = tokens_by_addr.get(callout.token_address)
        if not token or token.market_cap <= 0:
            continue

        # Sanity check: reject absurd market caps (mcap/liquidity > 500x is bad data)
        if token.liquidity > 0 and token.market_cap / token.liquidity > 500:
            continue

        # Cap at 100x vs callout market cap to filter garbage data
        current_mcap = token.market_cap
        if current_mcap > callout.market_cap * 100:
            continue

        old_peak = callout.peak_market_cap or 0
        if current_mcap > old_peak:
            callout.peak_market_cap = current_mcap
            updated += 1

    if updated:
        logger.info(f"Updated peak_market_cap for {updated} callouts")


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
