from __future__ import annotations
import asyncio
import logging
from app.config import get_settings
from app.database import async_session
from app.services.scanner import (
    scan_trending_tokens,
    fetch_top_traders_for_token,
    update_smart_money_counts,
    analyze_token_trades,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_scan_worker():
    """Background worker that runs two interleaved loops:
    - Trending scan every 30 seconds
    - Trade analysis for top tokens every 60 seconds
    """
    logger.info("Scan worker started")
    cycle = 0

    while True:
        try:
            async with async_session() as db:
                # Every cycle (30s): Fetch and enrich trending tokens
                tokens = await scan_trending_tokens(db, limit=50)
                logger.info(f"Scanned {len(tokens)} tokens (cycle {cycle})")

                # Fetch top traders for top 20 tokens by smart money count / volume
                sorted_tokens = sorted(
                    tokens,
                    key=lambda t: (t.smart_money_count, t.volume_24h),
                    reverse=True,
                )
                for token in sorted_tokens[:20]:
                    try:
                        await fetch_top_traders_for_token(db, token.address, pages=2)
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.warning(f"Failed to fetch traders for {token.symbol}: {e}")

                # Every other cycle (60s): Run trade analysis on top 30
                if cycle % 2 == 0:
                    analyzed_addresses = set()
                    for token in sorted_tokens[:30]:
                        try:
                            await analyze_token_trades(db, token.address)
                            analyzed_addresses.add(token.address)
                            await asyncio.sleep(0.3)
                        except Exception as e:
                            logger.warning(f"Failed trade analysis for {token.symbol}: {e}")

                    # Also analyze newly discovered tokens so they get trade data
                    # before their first scoring pass
                    new_tokens = [
                        t for t in tokens
                        if (t.smart_money_count or 0) == 0
                        and t.address not in analyzed_addresses
                    ]
                    for token in new_tokens:
                        try:
                            await analyze_token_trades(db, token.address)
                            await asyncio.sleep(0.3)
                        except Exception as e:
                            logger.warning(f"Failed trade analysis for new token {token.symbol}: {e}")
                    if new_tokens:
                        logger.info(f"Analyzed {len(new_tokens)} newly discovered tokens")

                # Update smart money counts
                await update_smart_money_counts(db)
                await db.commit()

        except asyncio.CancelledError:
            logger.info("Scan worker cancelled")
            break
        except Exception as e:
            logger.error(f"Scan worker error: {e}")

        cycle += 1
        await asyncio.sleep(30)  # 30 second base interval
