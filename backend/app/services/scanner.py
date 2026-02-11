from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.token import ScannedToken
from app.models.trader_snapshot import TraderSnapshot
from app.services.data_provider import data_provider
from app.services.onchain_analyzer import onchain_analyzer

logger = logging.getLogger(__name__)

# Known stablecoins and wrapped tokens to filter out (lowercase symbols)
STABLECOIN_SYMBOLS = {
    "usdc", "usdt", "pyusd", "dai", "usd1", "busd", "tusd", "frax",
    "usdd", "usdp", "gusd", "susd", "lusd", "eurc", "usde",
}
WRAPPED_SYMBOLS = {
    "wsol", "sol", "weth", "wbtc", "cbbtc", "msol", "jitosol",
    "bsol", "stsol", "tbtc", "steth",
}
# Known blue-chip addresses to always skip
SKIP_ADDRESSES = {
    "So11111111111111111111111111111111111111112",   # Wrapped SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo",  # PYUSD
}

# Market cap bounds for memecoin range
MIN_MCAP = 10_000        # $10K minimum
MAX_MCAP = 50_000_000    # $50M maximum
MAX_MCAP_FILTER = 500_000_000  # $500M — anything above is blue-chip
MIN_LIQUIDITY = 1_000    # $1K minimum at scan time (callout engine keeps $5K gate)


def _classify_token(symbol: str, name: str, market_cap: float, liquidity: float) -> str:
    """Classify a token based on its characteristics."""
    sym = symbol.lower()
    name_lower = name.lower()

    if sym in STABLECOIN_SYMBOLS:
        return "stablecoin"
    if sym in WRAPPED_SYMBOLS:
        return "defi"
    if market_cap > MAX_MCAP_FILTER:
        return "defi"

    # Heuristic: small cap with high volume/liquidity ratio = likely memecoin
    if market_cap <= MAX_MCAP:
        return "memecoin"
    # Tokens in $50M-$500M with meme-like names
    meme_keywords = {"doge", "shib", "pepe", "bonk", "cat", "dog", "inu", "moon", "rocket", "frog", "wojak", "chad", "meme", "pump"}
    if any(kw in name_lower or kw in sym for kw in meme_keywords):
        return "memecoin"

    return "unknown"


def _should_skip_token(t: dict) -> bool:
    """Return True if this token should be filtered out."""
    address = t.get("address", "")
    symbol = (t.get("symbol", "") or "").lower()
    mc = t.get("mc", 0) or t.get("marketcap", 0) or t.get("market_cap", 0) or 0
    liq = t.get("liquidity", 0) or 0

    if address in SKIP_ADDRESSES:
        return True
    if symbol in STABLECOIN_SYMBOLS or symbol in WRAPPED_SYMBOLS:
        return True
    if mc > MAX_MCAP_FILTER:
        return True
    if liq < MIN_LIQUIDITY and liq > 0:
        return True
    return False


def _is_memecoin_range(t: dict) -> bool:
    """Check if token falls within the memecoin market cap range."""
    mc = t.get("mc", 0) or t.get("marketcap", 0) or t.get("market_cap", 0) or 0
    return MIN_MCAP <= mc <= MAX_MCAP


async def discover_tokens(limit: int = 50) -> list[dict]:
    """Multi-source token discovery pipeline.
    Source 1: Trending tokens from Birdeye
    Source 2: Volume-sorted tokens with filtering
    Returns deduplicated list of token dicts.
    """
    seen_addresses = set()
    discovered = []

    # Source 1: Trending tokens (paginate in batches of 20, max limit from API)
    try:
        pages = (min(limit, 60) + 19) // 20  # up to 3 pages of 20
        for page in range(pages):
            trending = await data_provider.get_trending_tokens(offset=page * 20, limit=20)
            if not trending:
                break
            for t in trending:
                addr = t.get("address", "")
                if not addr or addr in seen_addresses:
                    continue
                if _should_skip_token(t):
                    continue
                seen_addresses.add(addr)
                discovered.append(t)
            await asyncio.sleep(0.3)
    except Exception as e:
        logger.warning(f"Failed to fetch trending tokens: {e}")

    # Source 2: Volume-sorted tokens, filtered
    try:
        volume_tokens = await data_provider.get_token_list(limit=limit)
        for t in volume_tokens:
            addr = t.get("address", "")
            if not addr or addr in seen_addresses:
                continue
            if _should_skip_token(t):
                continue
            # For volume source, prefer memecoin range
            if _is_memecoin_range(t):
                seen_addresses.add(addr)
                discovered.append(t)
    except Exception as e:
        logger.warning(f"Failed to fetch volume tokens: {e}")

    return discovered


async def enrich_tokens_with_overview(
    db: AsyncSession, tokens: list[dict], scan_source: str = "trending"
) -> list[ScannedToken]:
    """For each discovered token, fetch token_overview for real price change data
    and upsert into the database."""
    addresses = [t.get("address", "") for t in tokens if t.get("address")]

    # Batch fetch overviews
    overviews = await data_provider.get_token_overview_batch(addresses)

    scanned = []
    for t in tokens:
        address = t.get("address", "")
        if not address:
            continue

        overview = overviews.get(address, {})
        symbol = (overview.get("symbol") or t.get("symbol", "???"))[:20]
        name = (overview.get("name") or t.get("name", "Unknown"))[:100]
        mc = overview.get("marketCap") or overview.get("mc") or t.get("mc", 0) or t.get("marketcap", 0) or t.get("market_cap", 0) or 0
        liq = overview.get("liquidity") or t.get("liquidity", 0) or 0

        token_type = _classify_token(symbol, name, mc, liq)

        # Parse creation time from overview
        created_at_chain = None
        creation_ts = overview.get("createdAt") or overview.get("createAt") or overview.get("creationTime")
        if creation_ts:
            try:
                created_at_chain = datetime.fromtimestamp(creation_ts, tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                pass

        # Real price change data from overview (exact field names from Birdeye API)
        price_change_5m = overview.get("priceChange5mPercent", 0) or t.get("price24hChangePercent", 0) or 0
        price_change_1h = overview.get("priceChange1hPercent", 0) or 0
        price_change_24h = overview.get("priceChange24hPercent", 0) or t.get("price24hChangePercent", 0) or 0

        # Buy/sell counts from overview (exact field names from Birdeye API)
        buy_24h = overview.get("buy24h", 0) or 0
        sell_24h = overview.get("sell24h", 0) or 0
        unique_wallets = overview.get("uniqueWallet24h", 0) or overview.get("holder", 0) or 0

        token_fields = {
            "address": address,
            "symbol": symbol,
            "name": name,
            "price": overview.get("price") or t.get("price", 0) or 0,
            "volume_24h": overview.get("v24hUSD") or t.get("v24hUSD", 0) or t.get("volume24hUSD", 0) or 0,
            "liquidity": liq,
            "market_cap": mc,
            "price_change_5m": price_change_5m,
            "price_change_1h": price_change_1h,
            "price_change_24h": price_change_24h,
            "token_type": token_type,
            "created_at_chain": created_at_chain,
            "buy_count_24h": buy_24h,
            "sell_count_24h": sell_24h,
            "unique_wallets_24h": unique_wallets,
            "scan_source": scan_source,
            "last_scanned": datetime.now(timezone.utc),
        }

        result = await db.execute(
            select(ScannedToken).where(ScannedToken.address == address)
        )
        existing = result.scalar_one_or_none()

        if existing:
            for key, val in token_fields.items():
                if key != "address":
                    setattr(existing, key, val)
            scanned.append(existing)
        else:
            token = ScannedToken(**token_fields)
            db.add(token)
            scanned.append(token)

    await db.flush()
    return scanned


async def analyze_token_trades(
    db: AsyncSession, token_address: str
) -> dict:
    """Fetch recent trades for a token and analyze whale activity.
    Returns analysis dict with buy/sell metrics."""
    try:
        trades = await data_provider.get_token_trades(address=token_address, limit=50)
    except Exception as e:
        logger.warning(f"Failed to fetch trades for {token_address}: {e}")
        return {}

    if not trades:
        return {}

    buy_wallets = {}
    sell_wallets = {}
    total_buy_volume = 0
    total_sell_volume = 0

    for trade in trades:
        side = (trade.get("side", "") or "").lower()
        wallet = trade.get("owner", "")
        if not wallet or not side:
            continue

        # Calculate USD volume from the quote side (SOL amount * SOL price)
        quote = trade.get("quote", {})
        amount_usd = abs(quote.get("uiAmount", 0) or 0) * (quote.get("nearestPrice", 0) or quote.get("price", 0) or 0)
        if amount_usd == 0:
            # Fallback: try base side
            base = trade.get("base", {})
            amount_usd = abs(base.get("uiAmount", 0) or 0) * (base.get("nearestPrice", 0) or base.get("price", 0) or 0)

        if side == "buy":
            total_buy_volume += amount_usd
            buy_wallets[wallet] = buy_wallets.get(wallet, 0) + amount_usd
        elif side == "sell":
            total_sell_volume += amount_usd
            sell_wallets[wallet] = sell_wallets.get(wallet, 0) + amount_usd

    unique_buyers = len(buy_wallets)
    unique_sellers = len(sell_wallets)

    # Top 5 buyer concentration
    top_buyer_concentration = 0.0
    if total_buy_volume > 0 and buy_wallets:
        sorted_buyers = sorted(buy_wallets.values(), reverse=True)
        top5_volume = sum(sorted_buyers[:5])
        top_buyer_concentration = (top5_volume / total_buy_volume) * 100

    # Update token with trade analysis data
    result = await db.execute(
        select(ScannedToken).where(ScannedToken.address == token_address)
    )
    token = result.scalar_one_or_none()
    if token:
        token.buy_count_24h = unique_buyers
        token.sell_count_24h = unique_sellers
        token.unique_wallets_24h = unique_buyers + unique_sellers
        token.top_buyer_concentration = top_buyer_concentration

    return {
        "buy_wallets": buy_wallets,
        "sell_wallets": sell_wallets,
        "total_buy_volume": total_buy_volume,
        "total_sell_volume": total_sell_volume,
        "unique_buyers": unique_buyers,
        "unique_sellers": unique_sellers,
        "top_buyer_concentration": top_buyer_concentration,
    }


async def fetch_top_traders_for_token(
    db: AsyncSession, token_address: str, pages: int = 2, per_page: int = 10
) -> list[TraderSnapshot]:
    """Fetch top traders for a token and store snapshots.

    Primary: Birdeye top traders API.
    Fallback: Helius recent traders (on-chain swap aggregation) when Birdeye
    returns no results (e.g. 401/429 or empty response).
    """
    snapshots = []

    # --- Primary: Birdeye top traders ---
    for page in range(pages):
        traders = await data_provider.get_top_traders(
            address=token_address,
            offset=page * per_page,
            limit=per_page,
        )
        for trader in traders:
            wallet = trader.get("owner", "") or trader.get("address", "")
            if not wallet:
                continue

            volume_buy = trader.get("volumeBuy", 0) or 0
            volume_sell = trader.get("volumeSell", 0) or 0

            snapshot = TraderSnapshot(
                token_address=token_address,
                wallet=wallet,
                volume_buy=volume_buy,
                volume_sell=volume_sell,
                trade_count_buy=trader.get("tradeBuy", 0) or 0,
                trade_count_sell=trader.get("tradeSell", 0) or 0,
                estimated_pnl=volume_sell - volume_buy,
                scanned_at=datetime.now(timezone.utc),
            )
            db.add(snapshot)
            snapshots.append(snapshot)

    # --- Fallback: Helius recent traders when Birdeye returned nothing ---
    if not snapshots:
        try:
            helius_traders = await onchain_analyzer.get_recent_traders(token_address)
            for trader in helius_traders:
                wallet = trader.get("wallet", "")
                if not wallet:
                    continue

                snapshot = TraderSnapshot(
                    token_address=token_address,
                    wallet=wallet,
                    volume_buy=trader.get("volume_buy", 0) or 0,
                    volume_sell=trader.get("volume_sell", 0) or 0,
                    trade_count_buy=trader.get("trade_count_buy", 0) or 0,
                    trade_count_sell=trader.get("trade_count_sell", 0) or 0,
                    estimated_pnl=trader.get("estimated_pnl", 0) or 0,
                    scanned_at=datetime.now(timezone.utc),
                )
                db.add(snapshot)
                snapshots.append(snapshot)

            if snapshots:
                logger.info(
                    f"Helius fallback: fetched {len(snapshots)} traders for {token_address[:8]}"
                )
        except Exception as e:
            logger.warning(f"Helius trader fallback failed for {token_address[:8]}: {e}")

    await db.flush()
    return snapshots


async def update_smart_money_counts(db: AsyncSession):
    """Update smart_money_count for each scanned token based on trader PnL history."""
    result = await db.execute(select(ScannedToken))
    tokens = result.scalars().all()

    for token in tokens:
        trader_result = await db.execute(
            select(TraderSnapshot).where(
                TraderSnapshot.token_address == token.address,
                TraderSnapshot.estimated_pnl > 0,
            )
        )
        profitable_traders = trader_result.scalars().all()
        unique_wallets = set(t.wallet for t in profitable_traders)
        token.smart_money_count = len(unique_wallets)

    await db.flush()


async def scan_trending_tokens(db: AsyncSession, limit: int = 50) -> list[ScannedToken]:
    """Full scan pipeline: discover, enrich with overview data, and persist."""
    tokens_data = await discover_tokens(limit=limit)
    logger.info(f"Discovered {len(tokens_data)} tokens after filtering")

    scanned = await enrich_tokens_with_overview(db, tokens_data)
    return scanned
