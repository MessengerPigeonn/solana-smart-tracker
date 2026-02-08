from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import delete, select
from app.config import get_settings
from app.database import async_session
from app.models.token_snapshot import TokenSnapshot
from app.models.trader_snapshot import TraderSnapshot
from app.services.scanner import (
    scan_trending_tokens,
    fetch_top_traders_for_token,
    update_smart_money_counts,
    analyze_token_trades,
)
from app.services.wallet_classifier import update_wallet_stats
from app.services.rugcheck import rugcheck_client
from app.services.social_signals import social_signal_service
from app.services.onchain_analyzer import onchain_analyzer

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

                # Upsert wallet stats into SmartWallet DB
                wallet_updates = 0
                for token in sorted_tokens[:20]:
                    try:
                        recent = datetime.now(timezone.utc) - timedelta(hours=2)
                        snap_result = await db.execute(
                            select(TraderSnapshot).where(
                                TraderSnapshot.token_address == token.address,
                                TraderSnapshot.scanned_at >= recent,
                            )
                        )
                        trader_snaps = snap_result.scalars().all()
                        for ts in trader_snaps:
                            try:
                                await update_wallet_stats(db, ts.wallet, {
                                    "estimated_pnl": ts.estimated_pnl,
                                    "token_market_cap": token.market_cap,
                                })
                                wallet_updates += 1
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Wallet stats update failed for {token.symbol}: {e}")

                # Helius fallback: if Birdeye produced no trader snapshots,
                # use Helius recent traders to populate SmartWallet DB
                if wallet_updates == 0:
                    for token in sorted_tokens[:10]:
                        try:
                            traders = await onchain_analyzer.get_recent_traders(token.address)
                            for trader in traders:
                                try:
                                    await update_wallet_stats(db, trader["wallet"], {
                                        "estimated_pnl": trader.get("estimated_pnl", 0),
                                        "token_market_cap": token.market_cap,
                                    })
                                    wallet_updates += 1
                                except Exception:
                                    pass
                            await asyncio.sleep(0.3)
                        except Exception as e:
                            logger.debug(f"Helius trader fallback failed for {token.symbol}: {e}")
                    if wallet_updates > 0:
                        logger.info(f"SmartWallet: populated {wallet_updates} entries via Helius fallback")

                # Flush wallet stats to ensure they persist
                if wallet_updates > 0:
                    try:
                        await db.flush()
                    except Exception:
                        pass

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

                # Save token snapshots for volume velocity tracking
                for token in tokens:
                    try:
                        snapshot = TokenSnapshot(
                            token_address=token.address,
                            price=token.price,
                            volume=token.volume_24h,
                            market_cap=token.market_cap,
                            buy_count=token.buy_count_24h,
                            sell_count=token.sell_count_24h,
                            holder_count=token.holder_count,
                        )
                        db.add(snapshot)
                    except Exception:
                        pass

                # Every other cycle (60s): Enrich top tokens with Rugcheck + social + early buyers
                if cycle % 2 == 1:
                    enrich_tokens = sorted_tokens[:10]

                    # Rugcheck security scores
                    for token in enrich_tokens:
                        if token.rugcheck_score is not None:
                            continue  # Already enriched
                        try:
                            report = await rugcheck_client.get_token_report(token.address)
                            if report:
                                token.rugcheck_score = report.get("safety_score")
                            await asyncio.sleep(0.4)
                        except Exception as e:
                            logger.debug(f"Rugcheck enrichment failed for {token.symbol}: {e}")

                    # Social signals
                    for token in enrich_tokens:
                        if token.social_mention_count > 0:
                            continue  # Already enriched
                        try:
                            social = await social_signal_service.get_social_data(token.address)
                            if social:
                                token.social_mention_count = social.get("mention_count", 0)
                                token.social_velocity = social.get("velocity", 0.0)
                            await asyncio.sleep(0.3)
                        except Exception as e:
                            logger.debug(f"Social enrichment failed for {token.symbol}: {e}")

                    # Early buyer analysis via Helius
                    for token in enrich_tokens[:5]:  # Top 5 to limit Helius API usage
                        if token.early_buyer_smart_count > 0:
                            continue
                        try:
                            early_buyers = await onchain_analyzer.get_early_buyers(token.address, limit=20)
                            if early_buyers:
                                # Feed early buyers into SmartWallet DB
                                for buyer in early_buyers:
                                    try:
                                        await update_wallet_stats(db, buyer["wallet"], {
                                            "estimated_pnl": 0,
                                            "token_market_cap": token.market_cap,
                                        })
                                    except Exception:
                                        pass
                                # Look up which early buyers are in SmartWallet DB
                                from app.services.wallet_classifier import get_smart_wallets_for_token
                                buyer_addrs = [b["wallet"] for b in early_buyers]
                                smart_map = await get_smart_wallets_for_token(db, buyer_addrs)
                                token.early_buyer_smart_count = len(smart_map)
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Early buyer analysis failed for {token.symbol}: {e}")

                    logger.info(f"Enriched {len(enrich_tokens)} tokens with rugcheck/social/early-buyer data")

                # Every 20 cycles (~10 min): cleanup old snapshots
                if cycle % 20 == 0 and cycle > 0:
                    try:
                        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
                        await db.execute(
                            delete(TokenSnapshot).where(TokenSnapshot.snapshot_at < cutoff)
                        )
                        logger.info("Cleaned up old token snapshots")
                    except Exception as e:
                        logger.warning(f"Snapshot cleanup failed: {e}")

                await db.commit()

        except asyncio.CancelledError:
            logger.info("Scan worker cancelled")
            break
        except Exception as e:
            logger.error(f"Scan worker error: {e}")

        cycle += 1
        await asyncio.sleep(30)  # 30 second base interval
