from __future__ import annotations
import asyncio
import logging
from app.database import async_session
from app.services.callout_engine import generate_callouts

logger = logging.getLogger(__name__)


async def run_callout_worker():
    """Background worker that analyzes scanned data and generates callouts."""
    logger.info("Callout worker started")

    # Brief wait for initial scan data to populate
    await asyncio.sleep(5)

    while True:
        try:
            async with async_session() as db:
                callouts = await generate_callouts(db)
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
