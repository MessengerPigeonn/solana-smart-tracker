from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete
from app.database import async_session
from app.models.token import ScannedToken
from app.models.callout import Callout
from app.services.print_scanner import run_print_scan
from app.services.rugcheck import rugcheck_client
from app.services.social_signals import social_signal_service
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

                # Enrich with Rugcheck security scores
                for token in tokens:
                    if token.rug_risk_score > 70:
                        continue  # Skip high-risk tokens to save API calls
                    try:
                        report = await rugcheck_client.get_token_report(token.address)
                        if report:
                            token.rugcheck_score = report.get("safety_score")
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.debug(f"Rugcheck enrichment failed for {token.symbol}: {e}")

                # Enrich with social signals (only for tokens scoring > 30 in rug risk)
                for token in tokens[:5]:  # Rate limit: only top 5 per cycle
                    try:
                        social = await social_signal_service.get_social_data(token.address)
                        if social:
                            token.social_mention_count = social.get("mention_count", 0)
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.debug(f"Social enrichment failed for {token.symbol}: {e}")

                # Callout generation handled solely by callout_worker (avoids race conditions)

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
