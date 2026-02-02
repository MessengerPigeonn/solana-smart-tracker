from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.token import ScannedToken
from app.services.birdeye import birdeye_client
from app.services.scanner import (
    STABLECOIN_SYMBOLS,
    WRAPPED_SYMBOLS,
    SKIP_ADDRESSES,
    enrich_tokens_with_overview,
)

logger = logging.getLogger(__name__)

# PrintScan constants
PRINT_MIN_MCAP = 1_000         # $1K
PRINT_MAX_MCAP = 500_000       # $500K
PRINT_MIN_LIQUIDITY = 1_000    # $1K (lower than trending's $5K)
LISTING_LOOKBACK_MINUTES = 60
MAX_TOKENS_PER_SCAN = 15       # rate limit budget


def _should_skip_print_token(t: dict) -> bool:
    """Return True if this token should be filtered out of print scan results."""
    address = t.get("address", "")
    symbol = (t.get("symbol", "") or "").lower()

    if address in SKIP_ADDRESSES:
        return True
    if symbol in STABLECOIN_SYMBOLS or symbol in WRAPPED_SYMBOLS:
        return True
    return False


async def discover_new_listings(lookback_minutes: int = LISTING_LOOKBACK_MINUTES) -> list[dict]:
    """Discover newly listed tokens within the lookback window."""
    now = datetime.now(timezone.utc)
    min_listing_time = int((now - timedelta(minutes=lookback_minutes)).timestamp())
    max_listing_time = int(now.timestamp())

    try:
        tokens = await birdeye_client.get_new_listings(
            min_listing_time=min_listing_time,
            max_listing_time=max_listing_time,
            min_liquidity=PRINT_MIN_LIQUIDITY,
            limit=50,
        )
    except Exception as e:
        logger.warning(f"PrintScan: failed to fetch new listings: {e}")
        return []

    filtered = []
    for t in tokens:
        if _should_skip_print_token(t):
            continue
        mc = t.get("mc", 0) or t.get("marketcap", 0) or t.get("market_cap", 0) or 0
        if mc < PRINT_MIN_MCAP or mc > PRINT_MAX_MCAP:
            continue
        filtered.append(t)

    return filtered[:MAX_TOKENS_PER_SCAN]


def _compute_rug_risk_score(security: dict, holder_count: int, top10_pct: float, dev_pct: float) -> float:
    """Compute rug risk score 0-100 from security and holder data."""
    score = 0.0

    if security.get("isMintable") or security.get("mintAuthority"):
        score += 30
    if security.get("isFreezable") or security.get("freezeAuthority"):
        score += 20
    if security.get("isMutable", False):
        score += 10
    if top10_pct > 80:
        score += 15
    if dev_pct > 20:
        score += 10
    if holder_count < 10:
        score += 15

    return min(score, 100)


async def enrich_with_security(addresses: list[str]) -> dict[str, dict]:
    """Fetch security info for each token and compute rug risk fields.

    Returns {address: {has_mint_authority, has_freeze_authority, is_mutable, _raw: raw_api_data}}.
    """
    security_batch = await birdeye_client.get_token_security_batch(addresses)
    results = {}

    for address, sec in security_batch.items():
        has_mint = bool(sec.get("isMintable") or sec.get("mintAuthority"))
        has_freeze = bool(sec.get("isFreezable") or sec.get("freezeAuthority"))
        is_mutable = bool(sec.get("isMutable", False))

        results[address] = {
            "has_mint_authority": has_mint,
            "has_freeze_authority": has_freeze,
            "is_mutable": is_mutable,
            "_raw": sec,
        }

    return results


async def enrich_with_holders(addresses: list[str]) -> dict[str, dict]:
    """Fetch holder data for each token and compute distribution metrics.

    Returns {address: {holder_count, top10_holder_pct, dev_wallet_pct, dev_sold}}.
    """
    results = {}

    for address in addresses:
        try:
            holders = await birdeye_client.get_token_holders(address, limit=20)
            await asyncio.sleep(0.3)
        except Exception:
            continue

        if not holders:
            results[address] = {
                "holder_count": 0,
                "top10_holder_pct": 0.0,
                "dev_wallet_pct": 0.0,
                "dev_sold": None,
            }
            continue

        def _safe_balance(h: dict) -> float:
            val = h.get("uiAmount") or h.get("amount") or 0
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        holder_count = len(holders)
        total_balance = sum(_safe_balance(h) for h in holders)

        # Top 10 holder percentage
        sorted_holders = sorted(holders, key=_safe_balance, reverse=True)
        top10_balance = sum(_safe_balance(h) for h in sorted_holders[:10])
        top10_pct = (top10_balance / total_balance * 100) if total_balance > 0 else 0

        # Dev wallet: assume first holder / largest holder is creator
        dev_balance = _safe_balance(sorted_holders[0]) if sorted_holders else 0
        dev_pct = (dev_balance / total_balance * 100) if total_balance > 0 else 0

        # dev_sold: if the largest holder has 0 balance, they likely sold
        dev_sold = dev_balance == 0 if sorted_holders else None

        results[address] = {
            "holder_count": holder_count,
            "top10_holder_pct": round(top10_pct, 2),
            "dev_wallet_pct": round(dev_pct, 2),
            "dev_sold": dev_sold,
        }

    return results


async def run_print_scan(db: AsyncSession) -> list[ScannedToken]:
    """Full PrintScan pipeline: discover → enrich overview → enrich security → enrich holders → upsert."""

    # Step 1: Discover new listings
    raw_tokens = await discover_new_listings()
    if not raw_tokens:
        logger.debug("PrintScan: no new listings found")
        return []

    logger.info(f"PrintScan: discovered {len(raw_tokens)} new micro-cap tokens")

    # Step 2: Enrich with overview data (reuses scanner.py logic, tags with print_scan)
    scanned = await enrich_tokens_with_overview(db, raw_tokens, scan_source="print_scan")

    addresses = [t.address for t in scanned]

    # Step 3: Enrich with security info
    security_data = await enrich_with_security(addresses)

    # Step 4: Enrich with holder data
    holder_data = await enrich_with_holders(addresses)

    # Step 5: Apply security + holder enrichment to DB records and compute rug risk
    for token in scanned:
        sec = security_data.get(token.address, {})
        holders = holder_data.get(token.address, {})

        token.has_mint_authority = sec.get("has_mint_authority")
        token.has_freeze_authority = sec.get("has_freeze_authority")
        token.is_mutable = sec.get("is_mutable")

        token.holder_count = holders.get("holder_count", 0)
        token.top10_holder_pct = holders.get("top10_holder_pct", 0.0)
        token.dev_wallet_pct = holders.get("dev_wallet_pct", 0.0)
        token.dev_sold = holders.get("dev_sold")

        # Compute final rug risk score with all data (use raw API response)
        token.rug_risk_score = _compute_rug_risk_score(
            sec.get("_raw", sec),
            token.holder_count,
            token.top10_holder_pct,
            token.dev_wallet_pct,
        )

    await db.flush()
    logger.info(f"PrintScan: enriched {len(scanned)} tokens with security + holder data")
    return scanned
