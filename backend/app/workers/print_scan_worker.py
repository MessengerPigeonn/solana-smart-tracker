from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete
from app.database import async_session
from app.models.token import ScannedToken
from app.models.callout import Callout
from app.services.print_scanner import run_print_scan
from app.services.callout_engine import generate_callouts

logger = logging.getLogger(__name__)


async def run_print_scan_worker():
    """Background worker for PrintScan micro-cap token discovery.
    - 15-second cycle: discover + enrich new micro-cap tokens
    - Every other cycle (30s): generate callouts for print_scan tokens
    - Cleanup: delete print_scan tokens older than 24h with no callout
    """
    logger.info("PrintScan worker started")
    cycle = 0

    # Brief wait for DB to initialize
    await asyncio.sleep(8)

    while True:
        try:
            async with async_session() as db:
                # Every cycle (15s): discover and enrich
                tokens = await run_print_scan(db)
                logger.info(f"PrintScan: processed {len(tokens)} tokens (cycle {cycle})")

                # Every other cycle (30s): generate callouts
                if cycle % 2 == 0:
                    callouts = await generate_callouts(db)
                    if callouts:
                        ps_callouts = [c for c in callouts if c.scan_source == "print_scan"]
                        if ps_callouts:
                            logger.info(
                                f"PrintScan: generated {len(ps_callouts)} callouts: "
                                + ", ".join(f"{c.token_symbol}({c.signal.value}:{c.score})" for c in ps_callouts)
                            )

                # Every 20 cycles (~5 min): cleanup old print_scan tokens with no callouts
                if cycle % 20 == 0 and cycle > 0:
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                    # Find print_scan tokens older than 24h
                    old_tokens = await db.execute(
                        select(ScannedToken.address).where(
                            ScannedToken.scan_source == "print_scan",
                            ScannedToken.last_scanned < cutoff,
                        )
                    )
                    old_addresses = [row[0] for row in old_tokens.all()]

                    if old_addresses:
                        # Only delete those without callouts
                        has_callouts = await db.execute(
                            select(Callout.token_address).where(
                                Callout.token_address.in_(old_addresses)
                            )
                        )
                        keep_addresses = set(row[0] for row in has_callouts.all())
                        delete_addresses = [a for a in old_addresses if a not in keep_addresses]

                        if delete_addresses:
                            await db.execute(
                                delete(ScannedToken).where(
                                    ScannedToken.address.in_(delete_addresses)
                                )
                            )
                            logger.info(f"PrintScan: cleaned up {len(delete_addresses)} stale tokens")

                await db.commit()

        except asyncio.CancelledError:
            logger.info("PrintScan worker cancelled")
            break
        except Exception as e:
            logger.error(f"PrintScan worker error: {e}")

        cycle += 1
        await asyncio.sleep(15)  # 15 second base interval
