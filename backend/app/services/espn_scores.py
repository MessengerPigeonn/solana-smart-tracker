from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ESPN public scoreboard endpoints per sport
ESPN_ENDPOINTS: dict[str, str] = {
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "Soccer": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
    "UFC": "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard",
}

CACHE_TTL_SECONDS = 30


@dataclass
class LiveGameScore:
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    clock: Optional[str]
    period: Optional[str]
    status: str  # "in_progress" | "halftime" | "final" | "scheduled"
    sport: str


@dataclass
class _CacheEntry:
    data: list[LiveGameScore]
    timestamp: float


class ESPNScoreProvider:
    """Fetches live game scores from ESPN's public scoreboard API."""

    def __init__(self) -> None:
        self._cache: dict[str, _CacheEntry] = {}

    async def get_live_scores(self, sport: str) -> list[LiveGameScore]:
        """Return live game scores for a sport, using a 30s in-memory cache."""
        now = time.time()
        entry = self._cache.get(sport)
        if entry and (now - entry.timestamp) < CACHE_TTL_SECONDS:
            return entry.data

        url = ESPN_ENDPOINTS.get(sport)
        if not url:
            return []

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("ESPN fetch failed for %s: %s", sport, e)
            # Return stale cache if available
            return entry.data if entry else []

        scores: list[LiveGameScore] = []
        for event in data.get("events", []):
            for comp in event.get("competitions", []):
                parsed = self._parse_competition(comp, sport)
                if parsed:
                    scores.append(parsed)

        self._cache[sport] = _CacheEntry(data=scores, timestamp=now)
        return scores

    def _parse_competition(
        self, comp: dict, sport: str
    ) -> Optional[LiveGameScore]:
        """Extract teams, scores, clock, period, and status from an ESPN competition."""
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return None

        home_team = ""
        away_team = ""
        home_score = 0
        away_score = 0

        for c in competitors:
            team_obj = c.get("team", {})
            name = (
                team_obj.get("displayName")
                or team_obj.get("shortDisplayName")
                or team_obj.get("name")
                or team_obj.get("abbreviation", "")
            )
            score = int(c.get("score", 0) or 0)
            if c.get("homeAway") == "home":
                home_team = name
                home_score = score
            else:
                away_team = name
                away_score = score

        # Parse status
        status_obj = comp.get("status", {})
        status_type = status_obj.get("type", {})
        espn_state = status_type.get("state", "")  # "pre", "in", "post"

        clock = status_obj.get("displayClock")
        period_val = status_obj.get("period", 0)

        if espn_state == "pre":
            status = "scheduled"
        elif espn_state == "post":
            status = "final"
        elif espn_state == "in":
            # Check for halftime
            detail = status_type.get("shortDetail", "")
            description = status_type.get("description", "")
            if "halftime" in detail.lower() or "halftime" in description.lower():
                status = "halftime"
            else:
                status = "in_progress"
        else:
            status = "scheduled"

        period_str = self._format_period(period_val, sport)

        return LiveGameScore(
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            clock=clock if status in ("in_progress", "halftime") else None,
            period=period_str if status in ("in_progress", "halftime") else None,
            status=status,
            sport=sport,
        )

    @staticmethod
    def _format_period(period: int, sport: str) -> Optional[str]:
        """Format the period/quarter/inning display string."""
        if not period:
            return None

        if sport in ("NBA", "NFL"):
            suffixes = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
            label = "Q" if sport == "NBA" else "Q"
            return f"{label}{suffixes.get(period, f'{period}OT')}" if period <= 4 else f"OT{period - 4}"
        elif sport == "NHL":
            suffixes = {1: "1st", 2: "2nd", 3: "3rd"}
            return suffixes.get(period, f"OT{period - 3}") if period <= 3 else f"OT{period - 3}"
        elif sport == "MLB":
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(period if period < 4 else 0, "th")
            return f"{period}{suffix}"
        elif sport == "Soccer":
            return f"{period}H"
        elif sport == "UFC":
            return f"R{period}"
        return str(period)

    @staticmethod
    def match_team(espn_name: str, our_name: str) -> bool:
        """Fuzzy team name matching.

        Handles cases like:
        - "Los Angeles Lakers" matches "Lakers", "LA Lakers", "Los Angeles Lakers"
        - "Manchester United" matches "Man United", "Manchester United"
        """
        if not espn_name or not our_name:
            return False

        espn_lower = espn_name.lower().strip()
        our_lower = our_name.lower().strip()

        # Exact match
        if espn_lower == our_lower:
            return True

        # One contains the other
        if espn_lower in our_lower or our_lower in espn_lower:
            return True

        # Check if last word (team nickname) matches
        espn_parts = espn_lower.split()
        our_parts = our_lower.split()
        if espn_parts and our_parts and espn_parts[-1] == our_parts[-1]:
            return True

        # Handle common abbreviations
        abbreviations = {
            "la": "los angeles",
            "ny": "new york",
            "sf": "san francisco",
            "gb": "green bay",
            "kc": "kansas city",
            "tb": "tampa bay",
            "ne": "new england",
            "no": "new orleans",
            "man": "manchester",
        }
        expanded_our = our_lower
        for abbr, full in abbreviations.items():
            if expanded_our.startswith(abbr + " "):
                expanded_our = full + expanded_our[len(abbr):]
                break

        if espn_lower == expanded_our or espn_lower in expanded_our or expanded_our in espn_lower:
            return True

        return False


# Module-level singleton
espn_provider = ESPNScoreProvider()
