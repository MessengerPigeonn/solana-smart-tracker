"""X/Twitter social scanning via SocialData.tools API.

Searches for CTO (Community Takeover) signals -- mentions of token symbols
alongside CTO-related keywords, and monitors known CTO caller accounts.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SOCIALDATA_API = "https://api.socialdata.tools"

# Known CTO caller accounts to monitor
KNOWN_CTO_CALLERS = [
    "100xgemfinder",
    "caborachama",
    "MustStopMurad",
    "blaboringboring",
    "DegenKingSOL",
]


class SocialScanner:
    """Scans X/Twitter for CTO signals using SocialData.tools API."""

    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)
        self._cache: dict[str, tuple[float, dict]] = {}
        self._cache_ttl = 300  # 5 minutes

    def _get_api_key(self) -> str:
        return settings.socialdata_api_key

    async def _api_get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET request to SocialData.tools API."""
        api_key = self._get_api_key()
        if not api_key:
            return {}

        async with self._semaphore:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{SOCIALDATA_API}{path}",
                    params=params or {},
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                return resp.json()

    async def search_cto_mentions(
        self, token_symbol: str, token_address: str
    ) -> dict:
        """Search X for CTO/community takeover mentions of a specific token.

        Returns {mention_count, top_tweets, cto_signal, callers}.
        cto_signal = True if 3+ unique accounts mention CTO within 24h.
        """
        cache_key = f"cto_{token_address}"
        cached = self._cache.get(cache_key)
        if cached:
            ts, result = cached
            if time.monotonic() - ts < self._cache_ttl:
                return result

        query = (
            f'("${token_symbol}" OR "{token_address[:12]}") '
            f'("CTO" OR "community takeover" OR "takeover" OR "revive")'
        )

        try:
            data = await self._api_get(
                "/twitter/search",
                params={"query": f"{query} within_time:24h", "type": "Latest"},
            )
        except Exception as e:
            logger.debug(f"SocialScanner: CTO mention search failed for {token_symbol}: {e}")
            return {"mention_count": 0, "top_tweets": [], "cto_signal": False, "callers": []}

        tweets = data.get("tweets", [])
        unique_authors = set()
        callers = []
        top_tweets = []

        for tweet in tweets[:50]:
            user = tweet.get("user", {})
            username = user.get("screen_name", "")
            unique_authors.add(username.lower())
            if len(top_tweets) < 5:
                top_tweets.append({
                    "text": tweet.get("full_text", "")[:200],
                    "author": username,
                    "engagement": (
                        tweet.get("favorite_count", 0)
                        + tweet.get("retweet_count", 0)
                    ),
                    "created_at": tweet.get("tweet_created_at", ""),
                })
            if username.lower() in [c.lower() for c in KNOWN_CTO_CALLERS]:
                callers.append(username)

        result = {
            "mention_count": len(tweets),
            "top_tweets": top_tweets,
            "cto_signal": len(unique_authors) >= 3,
            "callers": list(set(callers)),
        }
        self._cache[cache_key] = (time.monotonic(), result)
        return result

    async def search_token_buzz(
        self, token_symbol: str, token_address: str
    ) -> dict:
        """Broader search for any social buzz around a token.

        Returns {mention_count, sentiment, velocity}.
        """
        cache_key = f"buzz_{token_address}"
        cached = self._cache.get(cache_key)
        if cached:
            ts, result = cached
            if time.monotonic() - ts < self._cache_ttl:
                return result

        query = f'"${token_symbol}" OR "{token_address[:12]}" min_faves:5'

        try:
            data = await self._api_get(
                "/twitter/search",
                params={"query": query, "type": "Latest"},
            )
        except Exception as e:
            logger.debug(f"SocialScanner: buzz search failed for {token_symbol}: {e}")
            return {"mention_count": 0, "sentiment": "neutral", "velocity": 0.0}

        tweets = data.get("tweets", [])
        mention_count = len(tweets)

        total_engagement = sum(
            t.get("favorite_count", 0) + t.get("retweet_count", 0)
            for t in tweets
        )
        avg_engagement = total_engagement / max(mention_count, 1)

        sentiment = "neutral"
        if avg_engagement > 50:
            sentiment = "positive"
        elif avg_engagement > 20:
            sentiment = "mild_positive"

        velocity = mention_count / 24.0

        result = {
            "mention_count": mention_count,
            "sentiment": sentiment,
            "velocity": round(velocity, 2),
        }
        self._cache[cache_key] = (time.monotonic(), result)
        return result

    async def check_cto_callers(
        self, token_symbol: str, token_address: str
    ) -> list[dict]:
        """Search for mentions by known CTO caller accounts.

        Returns list of {caller, tweet_text, engagement, posted_at}.
        """
        cache_key = f"callers_{token_address}"
        cached = self._cache.get(cache_key)
        if cached:
            ts, result = cached
            if time.monotonic() - ts < self._cache_ttl:
                return result

        results = []
        for caller in KNOWN_CTO_CALLERS[:5]:
            query = f'from:{caller} ("${token_symbol}" OR "{token_address[:12]}") within_time:48h'
            try:
                data = await self._api_get(
                    "/twitter/search",
                    params={"query": query, "type": "Latest"},
                )
                tweets = data.get("tweets", [])
                for tweet in tweets[:2]:
                    results.append({
                        "caller": caller,
                        "tweet_text": tweet.get("full_text", "")[:200],
                        "engagement": (
                            tweet.get("favorite_count", 0)
                            + tweet.get("retweet_count", 0)
                        ),
                        "posted_at": tweet.get("tweet_created_at", ""),
                    })
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.debug(f"SocialScanner: caller check failed for {caller}: {e}")

        self._cache[cache_key] = (time.monotonic(), results)
        return results

    async def scan_new_communities(self, db: AsyncSession) -> list[dict]:
        """Search for newly forming communities around faded tokens we track.

        Returns tokens with emerging social signals.
        """
        from app.models.callout import Callout, Signal
        from app.models.token import ScannedToken

        result = await db.execute(
            select(Callout.token_address, Callout.token_symbol)
            .join(ScannedToken, ScannedToken.address == Callout.token_address)
            .where(
                Callout.signal.in_([Signal.buy, Signal.watch]),
                ScannedToken.is_faded == True,  # noqa: E712
            )
            .distinct()
            .limit(20)
        )
        faded_tokens = result.all()

        emerging = []
        for token_address, token_symbol in faded_tokens:
            try:
                cto_data = await self.search_cto_mentions(token_symbol, token_address)
                if cto_data.get("cto_signal") or cto_data.get("mention_count", 0) >= 3:
                    emerging.append({
                        "token_address": token_address,
                        "token_symbol": token_symbol,
                        "mention_count": cto_data["mention_count"],
                        "cto_signal": cto_data["cto_signal"],
                        "callers": cto_data.get("callers", []),
                    })
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.debug(f"SocialScanner: community scan failed for {token_symbol}: {e}")

        return emerging


social_scanner = SocialScanner()
