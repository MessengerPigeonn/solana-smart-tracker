from __future__ import annotations

import logging
import re
import time
import unicodedata
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

ESPN_SUMMARY_URLS: dict[str, str] = {
    "NBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary",
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary",
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/summary",
}

# ESPN box score stat label -> index mapping
# NBA Labels: ['MIN', 'PTS', 'FG', '3PT', 'FT', 'REB', 'AST', 'TO', 'STL', 'BLK', ...]
PROP_STAT_INDEX: dict[str, int] = {
    "player_points": 1,
    "player_rebounds": 5,
    "player_assists": 6,
    "player_threes": 3,  # format "X-Y", parse X (made)
}

# NFL stats are split across categories — map prop_market -> (category_name, index)
# Passing:   [C/ATT, YDS, AVG, TD, INT, SACKS, QBR, RTG]
# Rushing:   [CAR, YDS, AVG, TD, LONG]
# Receiving: [REC, YDS, AVG, TD, LONG, TGTS]
NFL_PROP_STAT_MAP: dict[str, tuple[str, int]] = {
    "player_pass_yds": ("passing", 1),
    "player_pass_tds": ("passing", 3),
    "player_rush_yds": ("rushing", 1),
    "player_rush_tds": ("rushing", 3),
    "player_reception_yds": ("receiving", 1),
    "player_receptions": ("receiving", 0),
}

# Sports that use multi-category box score format
MULTI_CATEGORY_SPORTS = {"NFL"}

CACHE_TTL_SECONDS = 8
PLAYS_CACHE_TTL_SECONDS = 8


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
class PlayerBoxScore:
    """A player's stats from an ESPN box score."""
    name: str
    stats: list[str]  # raw stat values from ESPN (NBA flat array)
    dnp: bool  # True if player was on roster but didn't play
    category_stats: dict = field(default_factory=dict)  # NFL: {category_name: [stats]}


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
        self._plays_page_count: dict[str, int] = {}  # event_id -> last known page count

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
            async with httpx.AsyncClient(timeout=10) as client:
                # ESPN Core API caps page size at 50 (returns 404 for limit>50)
                page_size = 50
                known_page_count = self._plays_page_count.get(event_id)

                if known_page_count and known_page_count > 1:
                    # Fast path: skip probe, fetch last known page directly
                    last_resp = await client.get(base_url, params={"limit": page_size, "page": known_page_count})
                    last_resp.raise_for_status()
                    last_data = last_resp.json()
                    total_plays = last_data.get("count", 0)
                    new_page_count = last_data.get("pageCount", known_page_count)
                    # If page count grew, fetch the actual last page
                    if new_page_count > known_page_count:
                        last_resp = await client.get(base_url, params={"limit": page_size, "page": new_page_count})
                        last_resp.raise_for_status()
                        last_data = last_resp.json()
                    self._plays_page_count[event_id] = new_page_count
                else:
                    # First fetch: probe page 1 to learn page count
                    probe_resp = await client.get(base_url, params={"limit": page_size, "page": 1})
                    probe_resp.raise_for_status()
                    probe_data = probe_resp.json()
                    page_count = probe_data.get("pageCount", 1)
                    total_plays = probe_data.get("count", 0)
                    self._plays_page_count[event_id] = page_count

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
        elif sport == "Soccer":
            # Field position data for pitch visualization (0-1 normalized)
            fx = item.get("fieldPositionX", 0) or 0
            fy = item.get("fieldPositionY", 0) or 0
            fx2 = item.get("fieldPosition2X", 0) or 0
            fy2 = item.get("fieldPosition2Y", 0) or 0
            if fx or fy:
                extras["fieldX"] = fx
                extras["fieldY"] = fy
            if fx2 or fy2:
                extras["fieldX2"] = fx2
                extras["fieldY2"] = fy2
            # Soccer event subtype for icons
            type_obj_soccer = item.get("type", {})
            if isinstance(type_obj_soccer, dict) and type_obj_soccer.get("type"):
                extras["eventType"] = type_obj_soccer["type"]
            if item.get("redCard"):
                extras["redCard"] = True
            if item.get("yellowCard"):
                extras["yellowCard"] = True

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

    async def get_box_score(
        self, sport: str, espn_event_id: str
    ) -> dict[str, PlayerBoxScore]:
        """Fetch player box scores for a completed game from ESPN summary API.

        Returns a dict mapping normalized player name -> PlayerBoxScore.
        """
        summary_url = ESPN_SUMMARY_URLS.get(sport)
        if not summary_url:
            return {}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(summary_url, params={"event": espn_event_id})
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("ESPN box score fetch failed for %s event %s: %s", sport, espn_event_id, e)
            return {}

        players: dict[str, PlayerBoxScore] = {}
        is_multi_category = sport in MULTI_CATEGORY_SPORTS

        for team_data in data.get("boxscore", {}).get("players", []):
            for stat_group in team_data.get("statistics", []):
                category_name = stat_group.get("name", "")
                for athlete in stat_group.get("athletes", []):
                    name = athlete.get("athlete", {}).get("displayName", "")
                    if not name:
                        continue
                    stats = athlete.get("stats", [])
                    key = self._normalize_name(name)

                    if key in players:
                        # Player already seen in another category — merge
                        if is_multi_category and category_name:
                            players[key].category_stats[category_name] = stats
                        if not players[key].stats and stats:
                            players[key].stats = stats
                            players[key].dnp = False
                    else:
                        cat_stats = {}
                        if is_multi_category and category_name:
                            cat_stats[category_name] = stats
                        players[key] = PlayerBoxScore(
                            name=name,
                            stats=stats,
                            dnp=not bool(stats),
                            category_stats=cat_stats,
                        )
        return players

    async def find_espn_event_id(
        self, sport: str, home_team: str, away_team: str, game_date: str
    ) -> Optional[str]:
        """Find an ESPN event ID by team names and date (YYYYMMDD format)."""
        url = ESPN_ENDPOINTS.get(sport)
        if not url:
            return None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params={"dates": game_date})
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("ESPN event lookup failed for %s on %s: %s", sport, game_date, e)
            return None

        for event in data.get("events", []):
            for comp in event.get("competitions", []):
                competitors = comp.get("competitors", [])
                if len(competitors) < 2:
                    continue
                espn_home = espn_away = ""
                for c in competitors:
                    team_name = c.get("team", {}).get("displayName", "")
                    if c.get("homeAway") == "home":
                        espn_home = team_name
                    else:
                        espn_away = team_name
                if (self.match_team(espn_home, home_team) and self.match_team(espn_away, away_team)) or \
                   (self.match_team(espn_home, away_team) and self.match_team(espn_away, home_team)):
                    status = comp.get("status", {}).get("type", {}).get("name", "")
                    if status == "STATUS_FINAL":
                        return event.get("id")
        return None

    @staticmethod
    def get_player_stat(player: PlayerBoxScore, prop_market: str) -> Optional[float]:
        """Extract a stat value for a prop market from a player's box score."""
        if player.dnp:
            return 0.0

        # Anytime TD: check rushing, receiving, kick/punt return TDs
        if prop_market == "player_anytime_td":
            total_tds = 0
            for cat, td_idx in [("rushing", 3), ("receiving", 3), ("kickReturns", 4), ("puntReturns", 4)]:
                cat_stats = player.category_stats.get(cat, [])
                if td_idx < len(cat_stats):
                    try:
                        total_tds += int(float(cat_stats[td_idx]))
                    except (ValueError, TypeError):
                        pass
            return float(total_tds)

        # NFL category-based stats (passing, rushing, receiving)
        nfl_map = NFL_PROP_STAT_MAP.get(prop_market)
        if nfl_map and player.category_stats:
            category, idx = nfl_map
            cat_stats = player.category_stats.get(category, [])
            if idx < len(cat_stats):
                try:
                    return float(cat_stats[idx])
                except (ValueError, TypeError):
                    return None
            # Player exists but has no stats in this category (e.g. QB with 0 rush yards)
            return 0.0 if player.category_stats else None

        # NBA flat-array stats
        idx = PROP_STAT_INDEX.get(prop_market)
        if idx is None or idx >= len(player.stats):
            return None
        val = player.stats[idx]
        if prop_market == "player_threes":
            try:
                return float(val.split("-")[0])
            except (ValueError, IndexError):
                return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def match_player(name1: str, name2: str) -> bool:
        """Fuzzy player name matching."""
        def _norm(s: str) -> str:
            s = "".join(
                c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn"
            ).lower().strip()
            return s.replace(".", "").replace(" jr", "").replace(" sr", "").replace(" iii", "").replace(" ii", "")

        n1, n2 = _norm(name1), _norm(name2)
        if n1 == n2:
            return True
        p1, p2 = n1.split(), n2.split()
        if len(p1) >= 2 and len(p2) >= 2:
            if p1[-1] == p2[-1] and p1[0][0] == p2[0][0]:
                return True
        if n1 in n2 or n2 in n1:
            return True
        return False

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a player name for lookup."""
        return "".join(
            c for c in unicodedata.normalize("NFD", name)
            if unicodedata.category(c) != "Mn"
        ).lower().strip()

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
