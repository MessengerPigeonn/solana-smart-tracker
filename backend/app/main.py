from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import init_db

settings = get_settings()

# Import workers (will be started in lifespan)
worker_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()

    # Start background workers
    from app.workers.scan_worker import run_scan_worker
    from app.workers.callout_worker import run_callout_worker
    from app.workers.print_scan_worker import run_print_scan_worker
    from app.workers.copy_trade_worker import run_copy_trade_worker

    worker_tasks.append(asyncio.create_task(run_scan_worker()))
    worker_tasks.append(asyncio.create_task(run_callout_worker()))
    worker_tasks.append(asyncio.create_task(run_print_scan_worker()))
    worker_tasks.append(asyncio.create_task(run_copy_trade_worker()))

    yield

    # Shutdown
    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)


app = FastAPI(
    title="Solana Smart Money Tracker",
    description="Smart money analysis and callouts for Solana memecoins",
    version="1.0.0",
    lifespan=lifespan,
)

_origins = [settings.frontend_url.rstrip("/"), "http://localhost:3000", "http://localhost:3001"]
if settings.extra_cors_origins:
    _origins.extend([o.strip().rstrip("/") for o in settings.extra_cors_origins.split(",") if o.strip()])
# Deduplicate
_origins = list(dict.fromkeys(_origins))

logger = logging.getLogger(__name__)
logger.info("CORS allowed origins: %s", _origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
from app.api import auth, tokens, callouts, wallets, smart_money, payments, copy_trade

app.include_router(auth.router)
app.include_router(tokens.router)
app.include_router(callouts.router)
app.include_router(wallets.router)
app.include_router(smart_money.router)
app.include_router(payments.router)
app.include_router(copy_trade.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
