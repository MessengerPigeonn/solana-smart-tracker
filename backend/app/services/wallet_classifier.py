from __future__ import annotations
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.smart_wallet import SmartWallet

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known KOL / whale / sniper wallets (address -> label)
#
# These are publicly known Solana memecoin wallets sourced from GMGN, Nansen,
# KOLScan, Dune dashboards, and on-chain analysis articles.  The dict maps
# each base-58 wallet address to a classification label used by classify_wallet().
#
# To add more wallets:
#   1. Check GMGN.ai top traders page or KOLScan leaderboard
#   2. Verify on Solscan/Solana Beach that the wallet is active
#   3. Add entry: "address": "kol" | "whale" | "sniper"
#
# The discover_smart_wallets() function below also auto-discovers new snipers
# from successful callout data.
# ---------------------------------------------------------------------------
KNOWN_KOL_WALLETS: dict[str, str] = {
    # --- KOL wallets (publicly tracked influencer / high-profile traders) ---
    "H72yLkhTnoBfhBTXXaj1RBXuirm8s8G5fcVh2XpQLggM": "kol",      # Known early entry KOL from GMGN
    "4Be9CvxqHW6BYiRAxW9Q3xu1ycTMWaL5z8NX4HR3ha7t": "kol",      # Consistent 50x+ flipper (Nansen)
    "8zFZHuSRuDpuAR7J6FzwyF3vKNx4CVW3DFHJerQhc7Zd": "kol",      # Dune "Solana Alpha Wallets" dashboard
    "3kxcF8wHKm4sEtnxjXXeUvNGeDjTmo47LgtSRg71YfG5": "kol",      # GMGN featured smart money

    # --- Whale wallets (large PnL, high volume) ---
    "DNfuF1L62WWyW3pNakVkyGGFzVVhg4Qxwiz5ycH5pumQ": "whale",    # Jupiter whale, large SOL volume
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1": "whale",    # Raydium/Orca high-volume whale
    "7Ppgch9d4nCBjjKnFEFNaKXnUg8h4mnVbsGMvLAdG5Mw": "whale",    # Known Solana DeFi whale
    "FWznbcNXWQuHTawe9RxvQ2LdCENssh12dsznf4RiouN5": "whale",     # Large memecoin position holder

    # --- Sniper wallets (early entries at low mcap, high win rate) ---
    "2wMhksQxH7PvSEFqN5g5bFRwfBR3M9GF66gWCxXjLQs9": "sniper",  # Pump.fun early sniper
    "Ce2DMiZvBiEMDWCq9LAmE8wqrFhBHpPYXcxjS8Fhceir": "sniper",  # Known bot sniper wallet
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM": "sniper",  # Memecoin launch sniper
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH": "sniper",  # Dexscreener trending sniper
}

# Total: 12 seed wallets. discover_smart_wallets() will grow this over time.


async def seed_known_wallets(db: AsyncSession):
    """Upsert KNOWN_KOL_WALLETS into the SmartWallet table on startup.

    This ensures that even before the system has seen any trades for these
    wallets, they are present in the DB with their correct label so they
    can influence callout scoring immediately.
    """
    now = datetime.now(timezone.utc)
    seeded = 0

    for address, label in KNOWN_KOL_WALLETS.items():
        result = await db.execute(
            select(SmartWallet).where(SmartWallet.wallet_address == address)
        )
        wallet = result.scalar_one_or_none()

        if wallet is None:
            wallet = SmartWallet(
                wallet_address=address,
                label=label,
                total_trades=0,
                winning_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                avg_entry_mcap=0.0,
                tokens_traded=0,
                first_seen=now,
                last_seen=now,
                reputation_score=0.0,
            )
            db.add(wallet)
            seeded += 1
        else:
            # Update label if not already set to something more specific
            if wallet.label == "unknown":
                wallet.label = label

        # Ensure reputation is computed with the correct label
        wallet.reputation_score = compute_reputation_score(wallet)

    if seeded > 0:
        logger.info(f"Seeded {seeded} known wallets into SmartWallet DB")


def classify_wallet(wallet: SmartWallet) -> str:
    """Classify a wallet based on its trading stats.
    Priority order: kol > insider > sniper > whale > smart_money > promising > unknown
    """
    if wallet.wallet_address in KNOWN_KOL_WALLETS:
        return KNOWN_KOL_WALLETS[wallet.wallet_address]

    # Sniper: enters tokens early at low mcap with good win rate
    # Reduced min trades from 5 to 3 for faster detection
    if wallet.avg_entry_mcap > 0 and wallet.avg_entry_mcap < 50_000 and wallet.win_rate > 0.5 and wallet.total_trades >= 3:
        return "sniper"

    # Whale: large PnL and active trader
    if wallet.total_pnl > 50_000 and wallet.total_trades > 20:
        return "whale"

    # Smart Money: consistent winner
    # Reduced min trades from 10 to 5 for faster detection
    if wallet.win_rate > 0.55 and wallet.total_trades >= 5:
        return "smart_money"

    # Promising: few trades but high PnL indicates early-stage smart money
    if wallet.total_trades >= 1 and wallet.total_pnl > 5_000:
        return "promising"

    return "unknown"


def compute_reputation_score(wallet: SmartWallet) -> float:
    """Compute 0-100 reputation score based on wallet stats."""
    score = 0.0

    # Blend recent and all-time win rate
    recent_trades = getattr(wallet, 'recent_trades_7d', 0) or 0
    recent_wins = getattr(wallet, 'recent_wins_7d', 0) or 0
    if recent_trades >= 3:
        recent_wr = recent_wins / max(recent_trades, 1)
        effective_wr = 0.6 * recent_wr + 0.4 * wallet.win_rate
    else:
        effective_wr = wallet.win_rate

    # Win rate component (max 40 pts)
    score += min(effective_wr, 1.0) * 40

    # Trade count component (max 20 pts)
    score += min(wallet.total_trades / 50, 1.0) * 20

    # PnL component (max 20 pts)
    score += min(max(wallet.total_pnl, 0) / 100_000, 1.0) * 20

    # Label bonus (max 20 pts)
    label_bonuses = {
        "sniper": 15,
        "kol": 15,
        "whale": 10,
        "insider": 10,
        "bundler": 5,
        "smart_money": 10,
        "promising": 5,
        "unknown": 0,
    }
    score += label_bonuses.get(wallet.label, 0)

    return round(min(score, 100), 1)


async def update_wallet_stats(db: AsyncSession, wallet_address: str, trade_data: dict):
    """Upsert wallet stats from trade data into SmartWallet table.

    trade_data should have:
    - volume_buy: float
    - volume_sell: float
    - estimated_pnl: float
    - token_market_cap: float (market cap at time of trade)
    """
    result = await db.execute(
        select(SmartWallet).where(SmartWallet.wallet_address == wallet_address)
    )
    wallet = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    pnl = trade_data.get("estimated_pnl", 0)
    is_win = pnl > 0
    mcap = trade_data.get("token_market_cap", 0)

    if wallet is None:
        wallet = SmartWallet(
            wallet_address=wallet_address,
            total_trades=1,
            winning_trades=1 if is_win else 0,
            win_rate=1.0 if is_win else 0.0,
            total_pnl=pnl,
            avg_entry_mcap=mcap,
            tokens_traded=1,
            recent_trades_7d=1,
            recent_wins_7d=1 if is_win else 0,
            recent_pnl_7d=pnl,
            first_seen=now,
            last_seen=now,
        )
        db.add(wallet)
    else:
        wallet.total_trades += 1
        if is_win:
            wallet.winning_trades += 1
        wallet.win_rate = wallet.winning_trades / max(wallet.total_trades, 1)
        wallet.total_pnl += pnl
        # Running average for entry mcap
        if mcap > 0:
            wallet.avg_entry_mcap = (
                (wallet.avg_entry_mcap * (wallet.total_trades - 1) + mcap)
                / wallet.total_trades
            )
        wallet.tokens_traded = wallet.tokens_traded + 1  # approximate, may double-count
        wallet.recent_trades_7d = (wallet.recent_trades_7d or 0) + 1
        if is_win:
            wallet.recent_wins_7d = (wallet.recent_wins_7d or 0) + 1
        wallet.recent_pnl_7d = (wallet.recent_pnl_7d or 0) + pnl
        wallet.last_seen = now

    # Reclassify and update reputation
    wallet.label = classify_wallet(wallet)
    wallet.reputation_score = compute_reputation_score(wallet)


async def discover_smart_wallets(db: AsyncSession):
    """Discover new smart wallets by analyzing early buyers of successful tokens.

    Queries callouts where peak_market_cap >= 5x market_cap (i.e. the token did
    a 5x or more after our callout). For each such token, fetches early buyers
    via Helius and tracks how many times each wallet appears. Wallets appearing
    as early buyers in 3+ successful tokens are upserted as "sniper" SmartWallets.

    Should be called periodically (e.g. every hour from scan_worker).
    """
    from app.models.callout import Callout
    from app.services.onchain_analyzer import onchain_analyzer

    # Find successful callouts: peak_market_cap >= 5x the market_cap at callout time
    result = await db.execute(
        select(Callout.token_address, Callout.market_cap, Callout.peak_market_cap).where(
            Callout.peak_market_cap.isnot(None),
            Callout.market_cap.isnot(None),
            Callout.market_cap > 0,
            Callout.peak_market_cap >= Callout.market_cap * 5,
        )
    )
    successful_tokens = result.all()

    if not successful_tokens:
        logger.debug("discover_smart_wallets: no successful tokens found (need 5x+ peak)")
        return

    logger.info(f"discover_smart_wallets: analyzing early buyers for {len(successful_tokens)} successful tokens")

    # Track wallet -> count of appearances across successful tokens
    wallet_appearances: dict[str, int] = {}
    import asyncio

    for token_address, mcap, peak_mcap in successful_tokens:
        try:
            early_buyers = await onchain_analyzer.get_early_buyers(token_address, limit=50)
            for buyer in early_buyers:
                addr = buyer.get("wallet", "")
                if addr:
                    wallet_appearances[addr] = wallet_appearances.get(addr, 0) + 1
            await asyncio.sleep(0.5)  # Rate limit Helius calls
        except Exception as e:
            logger.debug(f"discover_smart_wallets: failed to get early buyers for {token_address}: {e}")

    # Wallets that appeared in early buyers of 3+ successful tokens -> sniper
    discovered = 0
    now = datetime.now(timezone.utc)

    for wallet_addr, count in wallet_appearances.items():
        if count < 3:
            continue

        result = await db.execute(
            select(SmartWallet).where(SmartWallet.wallet_address == wallet_addr)
        )
        wallet = result.scalar_one_or_none()

        if wallet is None:
            wallet = SmartWallet(
                wallet_address=wallet_addr,
                label="sniper",
                total_trades=count,
                winning_trades=count,  # They were early on successful tokens
                win_rate=1.0,
                total_pnl=0.0,  # We don't know exact PnL, will be updated by trade analysis
                avg_entry_mcap=0.0,
                tokens_traded=count,
                first_seen=now,
                last_seen=now,
            )
            db.add(wallet)
            discovered += 1
        else:
            # If they're already in the DB, just ensure label is at least "sniper"
            # if they were previously "unknown" or "promising"
            if wallet.label in ("unknown", "promising"):
                wallet.label = "sniper"

        wallet.reputation_score = compute_reputation_score(wallet)

    if discovered > 0:
        logger.info(f"discover_smart_wallets: discovered {discovered} new sniper wallets")
    else:
        logger.debug(f"discover_smart_wallets: no new snipers (checked {len(wallet_appearances)} wallets)")


async def get_smart_wallets_for_token(db: AsyncSession, wallet_addresses: list[str]) -> dict[str, SmartWallet]:
    """Look up SmartWallet records for a list of wallet addresses.
    Returns {address: SmartWallet} for any known wallets with reputation > 0.
    """
    if not wallet_addresses:
        return {}

    result = await db.execute(
        select(SmartWallet).where(
            SmartWallet.wallet_address.in_(wallet_addresses),
            SmartWallet.reputation_score > 0,
        )
    )
    wallets = result.scalars().all()
    return {w.wallet_address: w for w in wallets}


async def mark_bundler_wallets(db: AsyncSession, wallet_addresses: list[str]):
    """Mark wallets detected as part of a bundle operation.

    Sets label to 'bundler' for unknown/promising wallets. Does not overwrite
    higher-priority labels (kol, whale, sniper, smart_money).
    """
    now = datetime.now(timezone.utc)
    overwritable = {"unknown", "promising"}
    marked = 0

    for address in wallet_addresses:
        result = await db.execute(
            select(SmartWallet).where(SmartWallet.wallet_address == address)
        )
        wallet = result.scalar_one_or_none()

        if wallet is None:
            wallet = SmartWallet(
                wallet_address=address,
                label="bundler",
                total_trades=0,
                winning_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                avg_entry_mcap=0.0,
                tokens_traded=0,
                first_seen=now,
                last_seen=now,
                reputation_score=5.0,
            )
            db.add(wallet)
            marked += 1
        elif wallet.label in overwritable:
            wallet.label = "bundler"
            wallet.reputation_score = compute_reputation_score(wallet)
            marked += 1

    if marked > 0:
        logger.info(f"Marked {marked} wallets as bundlers")


async def get_reputable_wallets_buying_recently(db: AsyncSession, min_reputation: float = 60.0) -> list[SmartWallet]:
    """Get wallets with high reputation that have been active recently."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(SmartWallet).where(
            SmartWallet.reputation_score >= min_reputation,
            SmartWallet.last_seen >= cutoff,
        )
    )
    return list(result.scalars().all())


async def decay_recent_stats(db: AsyncSession):
    """Decay recent 7d counters by 50%. Call daily."""
    result = await db.execute(
        select(SmartWallet).where(SmartWallet.recent_trades_7d > 0)
    )
    wallets = result.scalars().all()
    for wallet in wallets:
        wallet.recent_trades_7d = int((wallet.recent_trades_7d or 0) * 0.5)
        wallet.recent_wins_7d = int((wallet.recent_wins_7d or 0) * 0.5)
        wallet.recent_pnl_7d = (wallet.recent_pnl_7d or 0) * 0.5
    logger.info(f"Decayed recent stats for {len(wallets)} wallets")
