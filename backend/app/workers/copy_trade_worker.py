from __future__ import annotations
import asyncio
import logging
from sqlalchemy import select
from app.config import get_settings
from app.database import async_session
from app.models.callout import Callout
from app.models.copy_trade_config import CopyTradeConfig
from app.models.user import User, Tier
from app.services.copy_trade_executor import execute_buy

settings = get_settings()
logger = logging.getLogger(__name__)

_last_processed_callout_id: int = 0


async def _get_new_callouts(db, since_id: int) -> list:
    result = await db.execute(
        select(Callout)
        .where(Callout.id > since_id, Callout.signal.in_(["buy"]))
        .order_by(Callout.id.asc())
        .limit(50)
    )
    return result.scalars().all()


async def _get_eligible_configs(db) -> list:
    result = await db.execute(
        select(CopyTradeConfig)
        .join(User, User.id == CopyTradeConfig.user_id)
        .where(
            CopyTradeConfig.enabled == True,
            User.tier == Tier.legend,
            CopyTradeConfig.trading_wallet_pubkey.isnot(None),
        )
    )
    return result.scalars().all()


async def _initialize_last_id(db) -> int:
    result = await db.execute(
        select(Callout.id).order_by(Callout.id.desc()).limit(1)
    )
    row = result.scalar_one_or_none()
    return row or 0


async def run_copy_trade_worker():
    """Background worker that polls for new callouts and executes copy trades."""
    global _last_processed_callout_id

    logger.info("Copy trade worker started")

    if not settings.copy_trade_enabled:
        logger.info("Copy trading is globally disabled, worker will poll but not trade")

    await asyncio.sleep(10)

    async with async_session() as db:
        _last_processed_callout_id = await _initialize_last_id(db)
        logger.info(f"Copy trade worker initialized, starting from callout ID {_last_processed_callout_id}")

    while True:
        try:
            if not settings.copy_trade_enabled:
                await asyncio.sleep(settings.copy_trade_worker_interval)
                continue

            async with async_session() as db:
                callouts = await _get_new_callouts(db, _last_processed_callout_id)
                if not callouts:
                    await asyncio.sleep(settings.copy_trade_worker_interval)
                    continue

                configs = await _get_eligible_configs(db)
                if not configs:
                    _last_processed_callout_id = max(c.id for c in callouts)
                    await asyncio.sleep(settings.copy_trade_worker_interval)
                    continue

                logger.info(f"Processing {len(callouts)} new callouts for {len(configs)} active configs")

                for callout in callouts:
                    for config in configs:
                        try:
                            trade = await execute_buy(config, callout, db)
                            if trade:
                                logger.info(
                                    f"Trade executed: {callout.token_symbol} "
                                    f"status={trade.tx_status.value} "
                                    f"user={config.user_id[:8]}..."
                                )
                        except Exception as e:
                            logger.error(f"Error executing trade for callout {callout.id}, user {config.user_id}: {e}")

                _last_processed_callout_id = max(c.id for c in callouts)
                await db.commit()

        except asyncio.CancelledError:
            logger.info("Copy trade worker cancelled")
            break
        except Exception as e:
            logger.error(f"Copy trade worker error: {e}")

        await asyncio.sleep(settings.copy_trade_worker_interval)
