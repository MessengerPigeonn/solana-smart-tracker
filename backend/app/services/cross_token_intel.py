from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet_token_appearance import WalletTokenAppearance

logger = logging.getLogger(__name__)


class CrossTokenIntel:
    """Detect coordinated buying across multiple token launches."""

    async def check_coordinated_buying(
        self, db: AsyncSession, wallet_addresses: list[str], current_token: str = ""
    ) -> dict:
        """Check if any of these wallets appeared as early buyers in other recent tokens.

        Returns: {overlap_wallets, overlap_count, is_coordinated, overlap_tokens}
        """
        if not wallet_addresses:
            return {"overlap_wallets": [], "overlap_count": 0, "is_coordinated": False, "overlap_tokens": []}

        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

        # Find wallets that appeared in OTHER tokens in last 7 days
        result = await db.execute(
            select(
                WalletTokenAppearance.wallet_address,
                func.count(func.distinct(WalletTokenAppearance.token_address)).label("token_count"),
            )
            .where(
                WalletTokenAppearance.wallet_address.in_(wallet_addresses),
                WalletTokenAppearance.appeared_at >= seven_days_ago,
                WalletTokenAppearance.token_address != current_token,
            )
            .group_by(WalletTokenAppearance.wallet_address)
            .having(func.count(func.distinct(WalletTokenAppearance.token_address)) >= 1)
        )
        rows = result.all()

        overlap_wallets = [row[0] for row in rows]
        overlap_count = len(overlap_wallets)
        is_coordinated = overlap_count >= 3

        # Get the tokens they overlapped on
        overlap_tokens = []
        if overlap_wallets:
            token_result = await db.execute(
                select(func.distinct(WalletTokenAppearance.token_address))
                .where(
                    WalletTokenAppearance.wallet_address.in_(overlap_wallets),
                    WalletTokenAppearance.appeared_at >= seven_days_ago,
                    WalletTokenAppearance.token_address != current_token,
                )
            )
            overlap_tokens = [row[0] for row in token_result.all()]

        if is_coordinated:
            logger.info(
                f"CrossTokenIntel: coordinated buying detected — "
                f"{overlap_count} wallets appeared in {len(overlap_tokens)} other tokens"
            )

        return {
            "overlap_wallets": overlap_wallets,
            "overlap_count": overlap_count,
            "is_coordinated": is_coordinated,
            "overlap_tokens": overlap_tokens[:10],
        }

    async def record_appearances(
        self, db: AsyncSession, token_address: str, wallets: list[dict]
    ):
        """Record wallet appearances for future cross-referencing.

        wallets: list of dicts with 'wallet' and 'role' keys
        """
        now = datetime.now(timezone.utc)
        recorded = 0

        for w in wallets:
            wallet_addr = w.get("wallet", "")
            role = w.get("role", "early_buyer")
            if not wallet_addr:
                continue

            # Check if already recorded for this token
            existing = await db.execute(
                select(WalletTokenAppearance).where(
                    WalletTokenAppearance.wallet_address == wallet_addr,
                    WalletTokenAppearance.token_address == token_address,
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                continue

            appearance = WalletTokenAppearance(
                wallet_address=wallet_addr,
                token_address=token_address,
                appeared_at=now,
                role=role,
            )
            db.add(appearance)
            recorded += 1

        if recorded > 0:
            logger.debug(f"CrossTokenIntel: recorded {recorded} appearances for {token_address[:8]}")


cross_token_intel = CrossTokenIntel()
