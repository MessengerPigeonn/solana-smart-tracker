from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
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

# ESPN Core Plays API sport/league mapping: (sport_path, league_slug)
ESPN_SPORT_LEAGUE: dict[str, tuple[str, str]] = {
    "NBA": ("basketball", "nba"),
    "NFL": ("football", "nfl"),
    "MLB": ("baseball", "mlb"),
    "NHL": ("hockey", "nhl"),
    "Soccer": ("soccer", "eng.1"),
}

CACHE_TTL_SECONDS = 30
PLAYS_CACHE_TTL_SECONDS = 30


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
    event_id: Optional[str] = None


@dataclass
class PlayByPlayEntry:
    id: str
    sequence_number: int
    text: str
    short_text: Optional[str]
    clock: Optional[str]
    period: Optional[str]
    period_number: int
    home_score: int
    away_score: int
    scoring_play: bool
    score_value: int
    play_type: Optional[str]
    team_id: Optional[str]
    wallclock: Optional[str]
    extras: dict = field(default_factory=dict)


@dataclass
class _CacheEntry:
    data: list[LiveGameScore]
    timestamp: float


@dataclass
class _PlaysCacheEntry:
    plays: list[PlayByPlayEntry]
    timestamp: float


class ESPNScoreProvider:
    """Fetches live game scores from ESPN's public scoreboard API."""

    def __init__(self) -> None:
        self._cache: dict[str, _CacheEntry] = {}
        self._plays_cache: dict[str, _PlaysCacheEntry] = {}

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
            event_id = event.get("id")
            for comp in event.get("competitions", []):
                parsed = self._parse_competition(comp, sport, event_id=event_id)
                if parsed:
                    scores.append(parsed)

        self._cache[sport] = _CacheEntry(data=scores, timestamp=now)
        return scores

    def _parse_competition(
        self, comp: dict, sport: str, event_id: Optional[str] = None
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
            event_id=event_id,
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

    async def get_play_by_play(
        self,
        event_id: str,
        sport: str,
        home_team: str,
        away_team: str,
    ) -> tuple[list[PlayByPlayEntry], int]:
        """Fetch recent play-by-play data for an event.

        Uses a 2-request strategy: probe for page count, then fetch last page.
        Returns (plays, total_plays) where plays are most recent 25, reverse-sorted.
        """
        now = time.time()
        cached = self._plays_cache.get(event_id)
        if cached and (now - cached.timestamp) < PLAYS_CACHE_TTL_SECONDS:
            return cached.plays, len(cached.plays)

        sport_league = ESPN_SPORT_LEAGUE.get(sport)
        if not sport_league:
            return [], 0

        sport_path, league_slug = sport_league
        base_url = (
            f"https://sports.core.api.espn.com/v2/sports/{sport_path}"
            f"/leagues/{league_slug}/events/{event_id}/competitions/{event_id}/plays"
        )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # ESPN Core API caps page size at 50 (returns 404 for limit>50)
                page_size = 50

                # Step 1: Probe to get page count at our page size
                probe_resp = await client.get(base_url, params={"limit": page_size, "page": 1})
                probe_resp.raise_for_status()
                probe_data = probe_resp.json()
                page_count = probe_data.get("pageCount", 1)
                total_plays = probe_data.get("count", 0)

                # Step 2: Fetch last page (if only 1 page, reuse probe data)
                if page_count <= 1:
                    last_data = probe_data
                else:
                    last_resp = await client.get(base_url, params={"limit": page_size, "page": page_count})
                    last_resp.raise_for_status()
                    last_data = last_resp.json()
        except Exception as e:
            logger.warning("ESPN plays fetch failed for event %s: %s", event_id, e)
            return cached.plays if cached else [], 0

        items = last_data.get("items", [])
        plays = []
        for item in items:
            parsed = self._parse_play(item, sport)
            if parsed:
                plays.append(parsed)

        # Sort most recent first: use sequence_number if available, else play id (numeric)
        plays.sort(key=lambda p: p.sequence_number or int(p.id or 0), reverse=True)
        plays = plays[:25]

        self._plays_cache[event_id] = _PlaysCacheEntry(plays=plays, timestamp=now)
        return plays, total_plays

    def _parse_play(self, item: dict, sport: str) -> Optional[PlayByPlayEntry]:
        """Parse a single play item from the ESPN Core Plays API."""
        play_id = str(item.get("id", ""))
        text = item.get("text") or item.get("shortText") or ""
        # Fall back to type description if no text (common for soccer kickoffs etc.)
        if not text:
            type_obj = item.get("type", {})
            text = type_obj.get("text", "") if isinstance(type_obj, dict) else ""
        if not text:
            return None

        # Extract team_id from team.$ref URL
        team_id = None
        team_ref = item.get("team", {}).get("$ref", "") if isinstance(item.get("team"), dict) else ""
        if team_ref:
            match = re.search(r"/teams/(\d+)", team_ref)
            if match:
                team_id = match.group(1)

        # Period info
        period_obj = item.get("period", {})
        period_number = period_obj.get("number", 0) if isinstance(period_obj, dict) else 0
        period_text = period_obj.get("displayValue") if isinstance(period_obj, dict) else None
        # Soccer periods only have number, no displayValue
        if not period_text and period_number:
            if sport == "Soccer":
                period_text = "1st Half" if period_number == 1 else "2nd Half"
            else:
                period_text = f"Period {period_number}"

        clock_obj = item.get("clock", {})
        clock = clock_obj.get("displayValue") if isinstance(clock_obj, dict) else None

        # Score
        home_score = int(item.get("homeScore", 0) or 0)
        away_score = int(item.get("awayScore", 0) or 0)

        # Type
        play_type_obj = item.get("type", {})
        play_type = play_type_obj.get("text") if isinstance(play_type_obj, dict) else None

        # Sport-specific extras
        extras: dict = {}
        if sport == "NFL":
            end = item.get("end", {})
            if isinstance(end, dict):
                if end.get("down"):
                    extras["down"] = end["down"]
                if end.get("distance"):
                    extras["distance"] = end["distance"]
            if item.get("statYardage") is not None:
                extras["yards"] = item["statYardage"]
        elif sport == "MLB":
            if item.get("pitchCount") is not None:
                extras["pitchCount"] = item["pitchCount"]
            if item.get("outs") is not None:
                extras["outs"] = item["outs"]
        elif sport == "NHL":
            strength = item.get("strength", {})
            if isinstance(strength, dict) and strength.get("text"):
                extras["strength"] = strength["text"]

        return PlayByPlayEntry(
            id=play_id,
            sequence_number=int(item.get("sequenceNumber", 0) or 0),
            text=text,
            short_text=item.get("shortText"),
            clock=clock,
            period=period_text,
            period_number=period_number,
            home_score=home_score,
            away_score=away_score,
            scoring_play=bool(item.get("scoringPlay", False)),
            score_value=int(item.get("scoreValue", 0) or 0),
            play_type=play_type,
            team_id=team_id,
            wallclock=item.get("wallclock"),
            extras=extras,
        )

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
