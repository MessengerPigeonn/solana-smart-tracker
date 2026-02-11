from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import delete, select
from app.config import get_settings
from app.database import async_session
from app.models.token import ScannedToken
from app.models.token_snapshot import TokenSnapshot
from app.models.trader_snapshot import TraderSnapshot
from app.services.scanner import (
    scan_trending_tokens,
    enrich_tokens_with_overview,
    fetch_top_traders_for_token,
    update_smart_money_counts,
    analyze_token_trades,
)
from app.services.wallet_classifier import update_wallet_stats, seed_known_wallets, discover_smart_wallets, mark_bundler_wallets, decay_recent_stats
from app.services.rugcheck import rugcheck_client
from app.services.social_signals import social_signal_service
from app.services.onchain_analyzer import onchain_analyzer
from app.services.bundle_analyzer import bundle_analyzer
from app.services.deployer_profiler import deployer_profiler
from app.services.early_buyer_tracker import early_buyer_tracker
from app.services.cross_token_intel import cross_token_intel
from app.services.hot_tokens import get_and_clear_hot_tokens, add_hot_token
from app.services.data_provider import data_provider
from app.services.cto_tracker import cto_tracker

logger = logging.getLogger(__name__)
settings = get_settings()

# Volume spike threshold: current volume > N x average of last 6 snapshots
VOLUME_SPIKE_MULTIPLIER = 5


async def run_scan_worker():
    """Background worker that runs two interleaved loops:
    - Trending scan every 30 seconds
    - Trade analysis for top tokens every 60 seconds
    """
    logger.info("Scan worker started")
    cycle = 0

    # Seed known wallets on first run
    try:
        async with async_session() as db:
            await seed_known_wallets(db)
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to seed known wallets on startup: {e}")

    while True:
        try:
            async with async_session() as db:
                # ── Hot token fast-track: pick up webhook/volume-spike tokens ──
                hot_tokens = get_and_clear_hot_tokens()
                hot_token_addresses: set[str] = set()
                if hot_tokens:
                    logger.info(
                        f"Fast-tracking {len(hot_tokens)} hot tokens: "
                        + ", ".join(
                            f"{addr[:8]}({info['reason']})"
                            for addr, info in hot_tokens.items()
                        )
                    )
                    hot_token_addresses = set(hot_tokens.keys())

                # Every cycle (30s): Fetch and enrich trending tokens
                tokens = await scan_trending_tokens(db, limit=50)
                logger.info(f"Scanned {len(tokens)} tokens (cycle {cycle})")

                # Merge hot tokens that weren't already discovered
                scanned_addresses = {t.address for t in tokens}
                missing_hot = hot_token_addresses - scanned_addresses
                if missing_hot:
                    # Fetch overview data for hot tokens not in the scan
                    hot_token_dicts = [{"address": addr} for addr in missing_hot]
                    try:
                        hot_enriched = await enrich_tokens_with_overview(
                            db, hot_token_dicts, scan_source="hot_token"
                        )
                        tokens.extend(hot_enriched)
                        logger.info(
                            f"Added {len(hot_enriched)} hot tokens to scan "
                            f"(total now {len(tokens)})"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to enrich hot tokens: {e}")

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

                # ── Volume spike detection → hot_token_queue ──
                # Compare current volume to avg of last 6 snapshots (~3 min)
                for token in tokens:
                    try:
                        three_min_ago = datetime.now(timezone.utc) - timedelta(minutes=3)
                        snap_result = await db.execute(
                            select(TokenSnapshot)
                            .where(
                                TokenSnapshot.token_address == token.address,
                                TokenSnapshot.snapshot_at >= three_min_ago,
                            )
                            .order_by(TokenSnapshot.snapshot_at.desc())
                            .limit(6)
                        )
                        recent_snaps = snap_result.scalars().all()
                        if len(recent_snaps) >= 3:
                            avg_volume = sum(s.volume for s in recent_snaps) / len(recent_snaps)
                            if avg_volume > 0 and token.volume_24h > avg_volume * VOLUME_SPIKE_MULTIPLIER:
                                add_hot_token(
                                    token.address,
                                    reason="volume_spike",
                                )
                                logger.info(
                                    f"Volume spike detected for {token.symbol}: "
                                    f"current={token.volume_24h:.0f} vs avg={avg_volume:.0f} "
                                    f"({token.volume_24h/avg_volume:.1f}x)"
                                )
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
                    for token in enrich_tokens[:15]:  # Top 15 for broader early buyer coverage
                        if token.early_buyer_smart_count > 0:
                            continue
                        try:
                            early_buyers = await onchain_analyzer.get_early_buyers(token.address, limit=50)
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

                    # Bundle detection via Helius
                    for token in enrich_tokens[:10]:
                        if (getattr(token, "bundle_wallet_count", 0) or 0) > 0:
                            continue  # Already analyzed
                        try:
                            analysis = await bundle_analyzer.analyze_token(token.address)
                            token.bundle_pct = analysis.estimated_bundle_pct
                            token.bundle_held_pct = analysis.estimated_held_pct
                            token.bundle_wallet_count = analysis.bundle_wallet_count
                            token.bundle_risk = analysis.risk_level
                            # Mark bundler wallets in SmartWallet DB
                            if analysis.bundle_wallets:
                                await mark_bundler_wallets(db, analysis.bundle_wallets)
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Bundle analysis failed for {token.symbol}: {e}")

                    # Deployer profiling — serial rugger detection
                    for token in enrich_tokens[:10]:
                        if (getattr(token, "deployer_rug_count", 0) or 0) > 0:
                            continue  # Already profiled
                        try:
                            dp = await deployer_profiler.profile_deployer(token.address)
                            if dp.deployer_address:
                                token.deployer_address = dp.deployer_address
                                token.deployer_rug_count = dp.tokens_rugged
                                token.deployer_token_count = dp.tokens_created
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Deployer profiling failed for {token.symbol}: {e}")

                    # Early buyer behavior tracking — conviction score
                    for token in enrich_tokens[:10]:
                        if getattr(token, "conviction_score", None) is not None:
                            continue  # Already analyzed
                        try:
                            early_buyers = await onchain_analyzer.get_early_buyers(token.address, limit=20)
                            if early_buyers and len(early_buyers) >= 3:
                                # Get smart wallet addresses for hold rate calc
                                buyer_addrs = [b["wallet"] for b in early_buyers]
                                from app.services.wallet_classifier import get_smart_wallets_for_token
                                smart_map = await get_smart_wallets_for_token(db, buyer_addrs)
                                smart_addrs = list(smart_map.keys())

                                report = await early_buyer_tracker.analyze_early_buyers(
                                    token.address, early_buyers, smart_wallet_addresses=smart_addrs
                                )
                                token.early_buyer_hold_rate = report.hold_rate
                                token.conviction_score = report.conviction_score

                                # Record appearances for cross-token intel
                                appearance_data = [
                                    {"wallet": b["wallet"], "role": "early_buyer"}
                                    for b in early_buyers[:20]
                                ]
                                await cross_token_intel.record_appearances(db, token.address, appearance_data)

                                # Also record bundler wallets if any
                                if (getattr(token, "bundle_wallet_count", 0) or 0) > 0:
                                    from app.services.bundle_analyzer import bundle_analyzer as ba
                                    cached = ba._cache.get(token.address)
                                    if cached:
                                        _, analysis = cached
                                        bundler_data = [
                                            {"wallet": w, "role": "bundler"}
                                            for w in analysis.bundle_wallets[:10]
                                        ]
                                        await cross_token_intel.record_appearances(db, token.address, bundler_data)

                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Early buyer tracking failed for {token.symbol}: {e}")

                    # CTO accumulation check
                    for token in enrich_tokens[:10]:
                        try:
                            cto_result = await cto_tracker.check_cto_accumulation(db, token.address)
                            token.cto_wallet_count = cto_result.get("cto_count", 0)
                            if cto_result.get("is_cto_signal"):
                                add_hot_token(token.address, reason="cto_accumulation")
                        except Exception as e:
                            logger.debug(f"CTO accumulation check failed for {token.symbol}: {e}")

                    logger.info(f"Enriched {len(enrich_tokens)} tokens with rugcheck/social/early-buyer/bundle/deployer/conviction/cto data")

                # Every 20 cycles (~10 min): scan CTO wallet activity + social signals
                if cycle % 20 == 0 and cycle > 0:
                    try:
                        await cto_tracker.scan_cto_wallet_activity(db)
                    except Exception as e:
                        logger.warning(f"CTO wallet activity scan failed: {e}")
                    try:
                        await cto_tracker.scan_social_cto_signals(db)
                    except Exception as e:
                        logger.warning(f"Social CTO signal scan failed: {e}")

                # Every 120 cycles (~60 min): discover new CTO wallets
                if cycle % 120 == 0 and cycle > 0:
                    try:
                        await cto_tracker.discover_cto_wallets(db)
                    except Exception as e:
                        logger.warning(f"CTO wallet discovery failed: {e}")

                # Every 120 cycles (~60 min): discover new smart wallets from successful callouts
                if cycle % 120 == 0 and cycle > 0:
                    try:
                        await discover_smart_wallets(db)
                    except Exception as e:
                        logger.warning(f"Smart wallet discovery failed: {e}")

                # Every 2880 cycles (~24h): decay recent wallet stats
                if cycle % 2880 == 0 and cycle > 0:
                    try:
                        await decay_recent_stats(db)
                    except Exception as e:
                        logger.warning(f"Wallet stats decay failed: {e}")

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
