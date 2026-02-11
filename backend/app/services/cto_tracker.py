"""CTO (Community Takeover) wallet tracking and revival detection.

Combines on-chain CTO wallet detection with X/Twitter social signals
to identify tokens undergoing community takeovers.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.callout import Callout, Signal
from app.models.token import ScannedToken
from app.models.cto_wallet import CTOWallet
from app.services.helius import helius_client
from app.services.onchain_analyzer import onchain_analyzer
from app.services.social_scanner import social_scanner
from app.services.hot_tokens import add_hot_token

logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────────
DEATH_THRESHOLD = 0.20       # token "dead" when mcap < 20% of peak
MIN_PEAK_MULTIPLE = 5.0      # token must have peaked >= 5x to qualify
CTO_WALLET_MIN_TOKENS = 2    # wallet must accumulate 2+ dead tokens to be tagged

# Protocol/exchange addresses to exclude from CTO wallet discovery
_EXCLUDED_IDENTITY_TYPES = {"exchange", "protocol", "bridge", "dex", "lending"}


class CTOTracker:
    """Tracks wallets known to successfully CTO tokens and detects revivals."""

    def __init__(self):
        self._cto_wallet_set: set[str] = set()
        self._cto_set_updated_at: float = 0
        self._cto_set_ttl = 300  # 5 min cache

    # ── Public methods ──────────────────────────────────────────────

    async def discover_cto_wallets(self, db: AsyncSession) -> None:
        """Periodic discovery of new CTO wallets (every 60 min).

        Finds wallets that accumulate multiple dead/faded tokens.
        """
        # Query callouts where peak >= 5x callout mcap and current mcap < 20% of peak
        result = await db.execute(
            select(Callout)
            .join(ScannedToken, ScannedToken.address == Callout.token_address)
            .where(
                Callout.signal.in_([Signal.buy, Signal.watch]),
                Callout.peak_market_cap.isnot(None),
                Callout.market_cap.isnot(None),
                Callout.market_cap > 0,
                Callout.peak_market_cap >= Callout.market_cap * MIN_PEAK_MULTIPLE,
                ScannedToken.market_cap > 0,
                ScannedToken.market_cap < Callout.peak_market_cap * DEATH_THRESHOLD,
            )
        )
        dead_callouts = result.scalars().all()
        if not dead_callouts:
            logger.info("CTO discovery: no dead tokens found")
            return

        logger.info(f"CTO discovery: found {len(dead_callouts)} dead/faded tokens")

        # For each dead token, get recent traders
        wallet_token_map: dict[str, list[str]] = {}  # wallet -> [token_addresses]
        for callout in dead_callouts[:20]:
            try:
                traders = await onchain_analyzer.get_recent_traders(callout.token_address)
                for trader in traders:
                    wallet = trader["wallet"]
                    # Only consider wallets that are buying (volume_buy > volume_sell)
                    if trader.get("volume_buy", 0) > trader.get("volume_sell", 0):
                        if wallet not in wallet_token_map:
                            wallet_token_map[wallet] = []
                        if callout.token_address not in wallet_token_map[wallet]:
                            wallet_token_map[wallet].append(callout.token_address)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.debug(f"CTO discovery: trader fetch failed for {callout.token_address[:8]}: {e}")

        # Wallets accumulating 2+ dead tokens = CTO candidates
        candidates = {
            wallet: tokens
            for wallet, tokens in wallet_token_map.items()
            if len(tokens) >= CTO_WALLET_MIN_TOKENS
        }
        if not candidates:
            logger.info("CTO discovery: no CTO wallet candidates found")
            return

        # Filter out exchanges/protocols via Helius Identity
        candidate_addrs = list(candidates.keys())[:100]
        try:
            identities = await helius_client.batch_wallet_identity(candidate_addrs)
        except Exception:
            identities = {}

        now = datetime.now(timezone.utc)
        upserted = 0

        for wallet, token_list in candidates.items():
            identity = identities.get(wallet, {})
            identity_type = identity.get("type", "") or ""
            if identity_type.lower() in _EXCLUDED_IDENTITY_TYPES:
                continue

            # Upsert CTOWallet
            existing = await db.execute(
                select(CTOWallet).where(CTOWallet.wallet_address == wallet)
            )
            cto_wallet = existing.scalar_one_or_none()

            if cto_wallet:
                cto_wallet.total_accumulations = len(token_list)
                cto_wallet.last_seen = now
                if identity_type:
                    cto_wallet.helius_identity_type = identity_type
                    cto_wallet.helius_identity_name = identity.get("name", "")
            else:
                # Get funding source for new CTO wallets
                funded_by = None
                try:
                    funded_data = await helius_client.get_funded_by(wallet)
                    if funded_data:
                        funded_by = funded_data.get("funder") or funded_data.get("address")
                except Exception:
                    pass

                cto_wallet = CTOWallet(
                    wallet_address=wallet,
                    total_accumulations=len(token_list),
                    helius_identity_type=identity_type or None,
                    helius_identity_name=identity.get("name") or None,
                    funded_by=funded_by,
                    first_seen=now,
                    last_seen=now,
                )
                db.add(cto_wallet)

            cto_wallet.reputation_score = self._compute_cto_reputation(cto_wallet)
            upserted += 1

        await db.flush()
        logger.info(f"CTO discovery: upserted {upserted} CTO wallets from {len(candidates)} candidates")

        # Refresh in-memory set
        self._cto_wallet_set = set(candidates.keys())
        self._cto_set_updated_at = time.monotonic()

    async def check_cto_accumulation(self, db: AsyncSession, token_address: str) -> dict:
        """Check if known CTO wallets are accumulating a token.

        Returns {cto_wallets, cto_count, is_cto_signal}.
        """
        try:
            early_buyers = await onchain_analyzer.get_early_buyers(token_address, limit=50)
        except Exception:
            return {"cto_wallets": [], "cto_count": 0, "is_cto_signal": False}

        if not early_buyers:
            return {"cto_wallets": [], "cto_count": 0, "is_cto_signal": False}

        buyer_addrs = [b["wallet"] for b in early_buyers]

        # Cross-reference against CTOWallet table
        result = await db.execute(
            select(CTOWallet).where(CTOWallet.wallet_address.in_(buyer_addrs))
        )
        cto_wallets = result.scalars().all()

        cto_list = [
            {
                "wallet": w.wallet_address,
                "successful_ctos": w.successful_ctos,
                "reputation": w.reputation_score,
                "label": w.label,
            }
            for w in cto_wallets
        ]

        return {
            "cto_wallets": cto_list,
            "cto_count": len(cto_list),
            "is_cto_signal": len(cto_list) >= 1,
        }

    async def scan_cto_wallet_activity(self, db: AsyncSession) -> None:
        """Monitor known CTO wallets for new activity (every 10 min).

        For top 20 CTO wallets by reputation, fetch recent txs.
        If buying a faded callout token, add to hot token queue.
        """
        result = await db.execute(
            select(CTOWallet)
            .where(CTOWallet.reputation_score > 0)
            .order_by(CTOWallet.reputation_score.desc())
            .limit(20)
        )
        top_wallets = result.scalars().all()
        if not top_wallets:
            return

        # Get set of faded token addresses for matching
        faded_result = await db.execute(
            select(ScannedToken.address).where(ScannedToken.is_faded == True)  # noqa: E712
        )
        faded_addresses = {row[0] for row in faded_result.all()}

        # Also include tokens from callouts where peak was high but current is low
        callout_result = await db.execute(
            select(Callout.token_address)
            .where(
                Callout.peak_market_cap.isnot(None),
                Callout.market_cap.isnot(None),
                Callout.market_cap > 0,
                Callout.peak_market_cap >= Callout.market_cap * MIN_PEAK_MULTIPLE,
            )
        )
        for row in callout_result.all():
            faded_addresses.add(row[0])

        detected = 0
        for wallet in top_wallets:
            try:
                txs = await helius_client._api_get(
                    f"/addresses/{wallet.wallet_address}/transactions",
                    params={"limit": 10, "type": "SWAP"},
                )
                if not isinstance(txs, list):
                    continue

                for tx in txs:
                    if tx.get("type") != "SWAP":
                        continue
                    # Check if buying a faded token
                    for transfer in tx.get("tokenTransfers", []):
                        mint = transfer.get("mint", "")
                        if (
                            mint in faded_addresses
                            and transfer.get("toUserAccount") == wallet.wallet_address
                        ):
                            add_hot_token(mint, reason="cto_accumulation", wallet=wallet.wallet_address)
                            detected += 1

                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"CTO activity scan failed for {wallet.wallet_address[:8]}: {e}")

        if detected:
            logger.info(f"CTO wallet activity: detected {detected} faded token buys")

    async def scan_social_cto_signals(self, db: AsyncSession) -> None:
        """Social monitoring for CTO signals (every 10 min).

        Scans faded tokens for X/Twitter CTO mentions and known caller activity.
        """
        # Get faded tokens
        faded_result = await db.execute(
            select(ScannedToken)
            .where(ScannedToken.is_faded == True)  # noqa: E712
            .limit(10)
        )
        faded_tokens = faded_result.scalars().all()

        # Also get tokens from callouts where peak was high (not yet flagged as faded)
        if len(faded_tokens) < 10:
            callout_result = await db.execute(
                select(ScannedToken)
                .join(Callout, Callout.token_address == ScannedToken.address)
                .where(
                    Callout.peak_market_cap.isnot(None),
                    Callout.market_cap.isnot(None),
                    Callout.market_cap > 0,
                    Callout.peak_market_cap >= Callout.market_cap * MIN_PEAK_MULTIPLE,
                    ScannedToken.market_cap > 0,
                    ScannedToken.market_cap < Callout.peak_market_cap * DEATH_THRESHOLD,
                )
                .limit(10 - len(faded_tokens))
            )
            faded_tokens.extend(callout_result.scalars().all())

        detected = 0
        for token in faded_tokens:
            try:
                cto_data = await social_scanner.search_cto_mentions(token.symbol, token.address)
                mention_count = cto_data.get("mention_count", 0)
                token.social_cto_mentions = mention_count

                if cto_data.get("cto_signal"):
                    add_hot_token(token.address, reason="cto_social_signal")
                    detected += 1

                # Also check known CTO callers
                caller_data = await social_scanner.check_cto_callers(token.symbol, token.address)
                if caller_data:
                    add_hot_token(
                        token.address,
                        reason=f"cto_caller:{caller_data[0]['caller']}",
                    )
                    detected += 1

                await asyncio.sleep(0.3)
            except Exception as e:
                logger.debug(f"Social CTO scan failed for {token.symbol}: {e}")

        await db.flush()
        if detected:
            logger.info(f"Social CTO signals: detected {detected} tokens with CTO buzz")

    def get_cto_wallet_set(self) -> set[str]:
        """In-memory cache of CTO wallet addresses for webhook fast lookup."""
        return self._cto_wallet_set

    async def refresh_cto_wallet_set(self, db: AsyncSession) -> None:
        """Refresh the in-memory CTO wallet set from DB."""
        if time.monotonic() - self._cto_set_updated_at < self._cto_set_ttl:
            return

        result = await db.execute(
            select(CTOWallet.wallet_address).where(CTOWallet.reputation_score > 0)
        )
        self._cto_wallet_set = {row[0] for row in result.all()}
        self._cto_set_updated_at = time.monotonic()

    # ── Private helpers ─────────────────────────────────────────────

    def _compute_cto_reputation(self, wallet: CTOWallet) -> float:
        """Score 0-100 based on CTO track record."""
        score = 0.0

        # Successful CTOs (max 40 pts)
        score += min(wallet.successful_ctos * 15, 40)

        # Total accumulations show activity (max 20 pts)
        score += min(wallet.total_accumulations * 5, 20)

        # Best revival multiple (max 25 pts)
        if wallet.best_revival_multiple >= 100:
            score += 25
        elif wallet.best_revival_multiple >= 20:
            score += 20
        elif wallet.best_revival_multiple >= 5:
            score += 12
        elif wallet.best_revival_multiple >= 2:
            score += 6

        # Entry timing: avg drop pct shows they buy deep dips (max 15 pts)
        if wallet.avg_entry_drop_pct >= 90:
            score += 15
        elif wallet.avg_entry_drop_pct >= 80:
            score += 12
        elif wallet.avg_entry_drop_pct >= 50:
            score += 6

        return min(score, 100.0)


cto_tracker = CTOTracker()
