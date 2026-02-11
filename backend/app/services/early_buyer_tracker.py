from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

HELIUS_API = "https://api.helius.xyz/v0"


@dataclass
class BuyerStatus:
    wallet: str
    status: str = "UNKNOWN"  # HOLDING, BOUGHT_MORE, SOLD_PART, SOLD_ALL, TRANSFERRED
    buy_count: int = 0
    sell_count: int = 0
    first_buy_ts: int = 0
    last_activity_ts: int = 0


@dataclass
class EarlyBuyerReport:
    token_address: str
    buyers_checked: int = 0
    holding_count: int = 0
    bought_more_count: int = 0
    sold_part_count: int = 0
    sold_all_count: int = 0
    hold_rate: float = 0.0
    smart_hold_rate: float = 0.0
    avg_hold_hours: float = 0.0
    bought_more_rate: float = 0.0
    conviction_score: float = 0.0
    statuses: list = field(default_factory=list)


class EarlyBuyerTracker:
    """Track early buyer behavior — holding vs dumping."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)
        self._cache: dict[str, tuple[float, EarlyBuyerReport]] = {}
        self._cache_ttl = 300  # 5 minutes

    async def _helius_get(self, path: str, params: Optional[dict] = None) -> list | dict:
        async with self._semaphore:
            all_params = {"api-key": settings.helius_api_key}
            if params:
                all_params.update(params)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{HELIUS_API}{path}", params=all_params)
                resp.raise_for_status()
                return resp.json()

    async def _classify_buyer(
        self, wallet: str, token_address: str, original_buy_ts: int
    ) -> BuyerStatus:
        """Check a single buyer's current status for this token."""
        status = BuyerStatus(wallet=wallet, first_buy_ts=original_buy_ts)

        try:
            txs = await self._helius_get(
                f"/addresses/{wallet}/transactions",
                params={"limit": 20, "type": "SWAP"},
            )
            if not isinstance(txs, list):
                return status

            buy_count = 0
            sell_count = 0
            last_ts = 0

            for tx in txs:
                # Filter to transactions involving this token
                token_transfers = tx.get("tokenTransfers", [])
                involves_token = any(
                    tt.get("mint") == token_address for tt in token_transfers
                )
                if not involves_token:
                    continue

                fee_payer = tx.get("feePayer", "")
                ts = tx.get("timestamp", 0)
                if ts > last_ts:
                    last_ts = ts

                is_buy = False
                is_sell = False
                for tt in token_transfers:
                    if tt.get("mint") == token_address:
                        if tt.get("toUserAccount") == fee_payer:
                            is_buy = True
                        elif tt.get("fromUserAccount") == fee_payer:
                            is_sell = True

                if is_buy:
                    buy_count += 1
                if is_sell:
                    sell_count += 1

            status.buy_count = buy_count
            status.sell_count = sell_count
            status.last_activity_ts = last_ts

            # Classify
            if sell_count == 0 and buy_count > 0:
                if buy_count > 1:
                    status.status = "BOUGHT_MORE"
                else:
                    status.status = "HOLDING"
            elif sell_count > 0 and buy_count > sell_count:
                status.status = "SOLD_PART"
            elif sell_count > 0 and sell_count >= buy_count:
                status.status = "SOLD_ALL"
            else:
                status.status = "HOLDING"

        except Exception as e:
            logger.debug(f"EarlyBuyerTracker: classify failed for {wallet[:8]}: {e}")

        return status

    async def analyze_early_buyers(
        self,
        token_address: str,
        early_buyers: list[dict],
        smart_wallet_addresses: Optional[list[str]] = None,
    ) -> EarlyBuyerReport:
        """Analyze hold/dump behavior of early buyers.

        early_buyers: list of dicts with 'wallet' and 'timestamp' keys
        smart_wallet_addresses: list of wallet addresses known to be smart wallets
        """
        cache_key = f"ebt_{token_address}"
        if cache_key in self._cache:
            ts, report = self._cache[cache_key]
            if time.monotonic() - ts < self._cache_ttl:
                return report

        report = EarlyBuyerReport(token_address=token_address)
        smart_set = set(smart_wallet_addresses or [])

        # Check up to 10 buyers
        buyers_to_check = early_buyers[:10]
        if not buyers_to_check:
            self._cache[cache_key] = (time.monotonic(), report)
            return report

        # Classify each buyer
        statuses = []
        for buyer in buyers_to_check:
            wallet = buyer.get("wallet", "")
            buy_ts = buyer.get("timestamp", 0)
            if not wallet:
                continue
            status = await self._classify_buyer(wallet, token_address, buy_ts)
            statuses.append(status)
            await asyncio.sleep(0.3)  # Rate limit

        if not statuses:
            self._cache[cache_key] = (time.monotonic(), report)
            return report

        report.buyers_checked = len(statuses)
        report.statuses = statuses

        # Count categories
        now_ts = int(datetime.now(timezone.utc).timestamp())
        hold_hours_sum = 0.0
        smart_holding = 0
        smart_total = 0

        for s in statuses:
            if s.status in ("HOLDING", "BOUGHT_MORE"):
                report.holding_count += 1
                if s.status == "BOUGHT_MORE":
                    report.bought_more_count += 1
            elif s.status == "SOLD_PART":
                report.sold_part_count += 1
            elif s.status == "SOLD_ALL":
                report.sold_all_count += 1

            # Calculate hold time
            if s.first_buy_ts > 0:
                hold_seconds = now_ts - s.first_buy_ts
                hold_hours_sum += hold_seconds / 3600

            # Smart wallet tracking
            if s.wallet in smart_set:
                smart_total += 1
                if s.status in ("HOLDING", "BOUGHT_MORE"):
                    smart_holding += 1

        total = report.buyers_checked
        report.hold_rate = (report.holding_count + report.bought_more_count) / max(total, 1)
        report.bought_more_rate = report.bought_more_count / max(total, 1)
        report.avg_hold_hours = hold_hours_sum / max(total, 1)
        report.smart_hold_rate = smart_holding / max(smart_total, 1) if smart_total > 0 else report.hold_rate

        # Conviction score formula
        report.conviction_score = (
            report.hold_rate * 40
            + report.smart_hold_rate * 30
            + (min(report.avg_hold_hours, 24) / 24) * 20
            + report.bought_more_rate * 10
        )
        report.conviction_score = round(min(report.conviction_score, 100), 1)

        self._cache[cache_key] = (time.monotonic(), report)
        logger.info(
            f"EarlyBuyerTracker: {token_address[:8]} — "
            f"hold_rate={report.hold_rate:.0%}, conviction={report.conviction_score:.0f}, "
            f"checked={report.buyers_checked}"
        )
        return report


early_buyer_tracker = EarlyBuyerTracker()
