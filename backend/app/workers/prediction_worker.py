from __future__ import annotations
import asyncio
import logging
from app.database import async_session
from app.config import get_settings
from app.services.prediction_engine import generate_predictions, settle_predictions

settings = get_settings()
logger = logging.getLogger(__name__)


async def run_prediction_worker():
    """Background worker that polls odds, generates predictions, and settles results."""
    logger.info("Prediction worker started")

    # Brief wait for other services to initialize
    await asyncio.sleep(10)

    while True:
        try:
            if not settings.prediction_enabled:
                await asyncio.sleep(60)
                continue

            async with async_session() as db:
                new_predictions = await generate_predictions(db)
                if new_predictions:
                    logger.info(
                        f"Generated {len(new_predictions)} predictions: "
                        + ", ".join(
                            f"{p.sport}/{p.bet_type}:{p.confidence}"
                            for p in new_predictions[:10]
                        )
                    )

                settled = await settle_predictions(db)
                if settled:
                    logger.info(f"Settled {settled} predictions")

                await db.commit()

        except asyncio.CancelledError:
            logger.info("Prediction worker cancelled")
            break
        except Exception as e:
            logger.error(f"Prediction worker error: {e}")

        await asyncio.sleep(settings.prediction_worker_interval)
