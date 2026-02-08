from __future__ import annotations
import asyncio
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class SocialSignalService:
    """Lightweight social signal tracker using DexScreener data."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(2)

    async def get_social_data(self, token_address: str) -> dict:
        """Get social signal data for a token.

        Uses DexScreener pair data which may include social links.
        Returns: {mention_count: int, velocity: float, has_socials: bool, social_links: list}
        """
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return self._parse_social_data(data)
            except Exception as e:
                logger.debug(f"Social signal fetch failed for {token_address}: {e}")
                return {"mention_count": 0, "velocity": 0.0, "has_socials": False, "social_links": []}

    def _parse_social_data(self, data: dict) -> dict:
        """Parse DexScreener response for social signals."""
        pairs = data.get("pairs", [])
        if not pairs:
            return {"mention_count": 0, "velocity": 0.0, "has_socials": False, "social_links": []}

        pair = pairs[0]  # Use first/primary pair
        info = pair.get("info", {})
        socials = info.get("socials", [])
        websites = info.get("websites", [])

        social_links = []
        has_twitter = False
        has_telegram = False

        for social in socials:
            social_type = social.get("type", "").lower()
            url = social.get("url", "")
            if url:
                social_links.append({"type": social_type, "url": url})
            if social_type == "twitter":
                has_twitter = True
            if social_type == "telegram":
                has_telegram = True

        for website in websites:
            url = website.get("url", "")
            if url:
                social_links.append({"type": "website", "url": url})

        # Basic mention count heuristic based on social presence
        mention_count = 0
        if has_twitter:
            mention_count += 3
        if has_telegram:
            mention_count += 2
        if websites:
            mention_count += 1

        # Volume-based social signal: high txn count suggests social activity
        txns = pair.get("txns", {})
        h1_buys = txns.get("h1", {}).get("buys", 0)
        h1_sells = txns.get("h1", {}).get("sells", 0)
        total_h1 = h1_buys + h1_sells
        if total_h1 > 100:
            mention_count += 2  # High activity = likely social buzz
        elif total_h1 > 50:
            mention_count += 1

        return {
            "mention_count": mention_count,
            "velocity": 0.0,  # Calculated from changes between scans
            "has_socials": bool(social_links),
            "social_links": social_links,
        }

    @staticmethod
    def calculate_velocity(current_count: int, previous_count: int, hours_elapsed: float) -> float:
        """Calculate mention velocity (growth rate per hour)."""
        if hours_elapsed <= 0 or previous_count <= 0:
            return 0.0
        growth = (current_count - previous_count) / max(previous_count, 1)
        return round(growth / hours_elapsed, 4)


social_signal_service = SocialSignalService()
