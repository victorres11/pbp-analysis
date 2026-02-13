#!/usr/bin/env python3
"""
cfbstats.com leaderboard scraper with simple file caching.

Supports conference context badges for red zone, third down, explosives, and scoring.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://cfbstats.com"

CONFERENCE_IDS = {
    "American": "823",
    "ACC": "821",
    "Big 12": "25354",
    "Big Ten": "827",
    "C-USA": "24312",
    "FBS Independents": "99001",
    "MAC": "875",
    "Mountain West": "5486",
    "Pac-12": "905",
    "SEC": "911",
    "Sun Belt": "818",
}

CATEGORY_IDS = {
    "RED_ZONE": 27,
    "THIRD_DOWN": 25,
    "LONG_PLAYS": 30,
    "SCORING": 9,
}

DEFAULT_TEAM_ALIASES = {
    "georgia": "georgia",
    "uga": "georgia",
    "arizona st": "asu",
    "arizona state": "asu",
    "ariz st": "asu",
    "asu": "asu",
}


def normalize_header(value: str) -> str:
    if value is None:
        return ""
    # Preserve % to distinguish "TD" from "TD %"
    return re.sub(r"[^a-z0-9%]+", "", value.lower())


def normalize_team_name(name: str) -> str:
    if not name:
        return ""
    cleaned = name.lower().replace("&", "and")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def format_ppg(value: str) -> str:
    if value is None:
        return ""
    cleaned = str(value).strip()
    if not cleaned:
        return ""
    if re.search(r"(ppg|/g|pts/g)", cleaned, re.IGNORECASE):
        return cleaned
    try:
        num = float(cleaned)
        return f"{num:.1f} PPG"
    except ValueError:
        return cleaned


class LeaderboardTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[str]] = []
        self._table_depth = 0
        self._in_row = False
        self._in_cell = False
        self._cell_parts: List[str] = []
        self._row_cells: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self._table_depth == 0:
                self.rows = []
            self._table_depth += 1
        if self._table_depth == 0:
            return
        if tag == "tr":
            self._in_row = True
            self._row_cells = []
        if self._in_row and tag in ("td", "th"):
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag):
        if tag == "table" and self._table_depth > 0:
            self._table_depth -= 1
        if self._table_depth == 0:
            return
        if tag in ("td", "th") and self._in_cell:
            cell = " ".join("".join(self._cell_parts).split()).strip()
            self._row_cells.append(cell)
            self._in_cell = False
        if tag == "tr" and self._in_row:
            if any(c for c in self._row_cells):
                self.rows.append(self._row_cells)
            self._row_cells = []
            self._in_row = False

    def handle_data(self, data):
        if self._in_cell:
            self._cell_parts.append(data)


def parse_leaderboard_table(html: str) -> Optional[Dict[str, List[Dict[str, str]]]]:
    parser = LeaderboardTableParser()
    parser.feed(html)
    rows = parser.rows
    if not rows:
        return None

    header_index = None
    for idx, row in enumerate(rows):
        normalized = [normalize_header(c) for c in row]
        if "name" in normalized or "team" in normalized:
            header_index = idx
            break
    if header_index is None:
        header_index = 0

    headers = rows[header_index]
    data_rows = rows[header_index + 1 :]
    parsed_rows: List[Dict[str, str]] = []
    for row in data_rows:
        if len(row) < 2:
            continue
        padded = row[: len(headers)] + [""] * max(0, len(headers) - len(row))
        parsed_rows.append({headers[i]: padded[i] for i in range(len(headers))})

    return {"headers": headers, "rows": parsed_rows}


def find_column(headers: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    header_list = list(headers)
    normalized_headers = [normalize_header(h) for h in header_list]
    normalized_candidates = [normalize_header(candidate) for candidate in candidates]
    normalized_candidate_set = set(normalized_candidates)

    # Prefer exact matches (after normalization), choosing the longest match.
    exact_matches = [
        (len(header_norm), idx)
        for idx, header_norm in enumerate(normalized_headers)
        if header_norm in normalized_candidate_set
    ]
    if exact_matches:
        _, best_idx = max(exact_matches, key=lambda item: (item[0], -item[1]))
        return header_list[best_idx]

    # Fall back to substring matches, preferring longer candidates over shorter ones.
    substring_matches = []
    for idx, header_norm in enumerate(normalized_headers):
        for candidate_norm in normalized_candidates:
            if candidate_norm and candidate_norm in header_norm:
                substring_matches.append((len(candidate_norm), len(header_norm), idx))
    if substring_matches:
        _, _, best_idx = max(substring_matches, key=lambda item: (item[0], item[1], -item[2]))
        return header_list[best_idx]

    normalized_candidates = set(normalized_candidates)
    if {"rank", "rk", "#"} & normalized_candidates and header_list:
        if normalized_headers[0] == "":
            return header_list[0]
    return None


def parse_percent(value: str) -> Optional[float]:
    if value is None:
        return None
    cleaned = str(value).strip().replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def build_team_lookup(teams: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for team_id, info in teams.items():
        for value in (info.get("name"), info.get("abbr")):
            if value:
                lookup[normalize_team_name(value)] = team_id
    for alias, team_id in DEFAULT_TEAM_ALIASES.items():
        lookup.setdefault(normalize_team_name(alias), team_id)
    return lookup


@dataclass
class LeaderboardResult:
    headers: List[str]
    rows: List[Dict[str, str]]
    fetched_at: str


class CfbstatsScraper:
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        base_url: str = BASE_URL,
        user_agent: str = "Mozilla/5.0 (compatible; cfbstats-scraper/0.1)",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir or Path(__file__).parent / "cfbstats_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent

    def build_leaderboard_url(
        self,
        year: int,
        scope: str,
        category: int,
        split: str = "split01",
        sort: str = "sort01",
        offense: str = "offense",
    ) -> str:
        return (
            f"{self.base_url}/{year}/leader/{scope}/team/{offense}/"
            f"{split}/category{int(category):02d}/{sort}.html"
        )

    def cache_path(self, year: int, scope: str, category: int, split: str, sort: str) -> Path:
        filename = f"{year}_{scope}_category{int(category):02d}_{split}_{sort}.json"
        return self.cache_dir / filename

    def load_cache(self, path: Path) -> Optional[LeaderboardResult]:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return LeaderboardResult(
                headers=payload.get("headers", []),
                rows=payload.get("rows", []),
                fetched_at=payload.get("fetched_at", ""),
            )
        except (OSError, json.JSONDecodeError):
            return None

    def save_cache(self, path: Path, result: LeaderboardResult) -> None:
        payload = {
            "headers": result.headers,
            "rows": result.rows,
            "fetched_at": result.fetched_at,
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def fetch_html(self, url: str) -> Optional[str]:
        try:
            request = Request(url, headers={"User-Agent": self.user_agent})
            with urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError):
            return None

    def get_leaderboard(
        self,
        year: int,
        scope: str,
        category: int,
        split: str = "split01",
        sort: str = "sort01",
        offense: str = "offense",
        force_refresh: bool = False,
    ) -> Optional[LeaderboardResult]:
        cache_path = self.cache_path(year, scope, category, split, sort)
        if not force_refresh:
            cached = self.load_cache(cache_path)
            if cached:
                return cached

        url = self.build_leaderboard_url(year, scope, category, split, sort, offense)
        html = self.fetch_html(url)
        if not html:
            return self.load_cache(cache_path)

        parsed = parse_leaderboard_table(html)
        if not parsed:
            return self.load_cache(cache_path)

        result = LeaderboardResult(
            headers=parsed["headers"],
            rows=parsed["rows"],
            fetched_at=datetime.utcnow().isoformat() + "Z",
        )
        self.save_cache(cache_path, result)
        return result

    def get_red_zone_badges(
        self,
        year: int,
        teams: Dict[str, Dict[str, str]],
        split: str = "split01",
    ) -> Dict[str, List[str]]:
        badges: Dict[str, List[str]] = {team_id: [] for team_id in teams}
        team_lookup = build_team_lookup(teams)

        by_conference: Dict[str, List[str]] = {}
        for team_id, info in teams.items():
            conf = info.get("conference")
            if not conf:
                continue
            by_conference.setdefault(conf, []).append(team_id)

        for conf, team_ids in by_conference.items():
            scope = CONFERENCE_IDS.get(conf)
            if not scope:
                continue
            leaderboard = self.get_leaderboard(year, scope, 27, split=split)
            if not leaderboard:
                continue
            team_col = find_column(leaderboard.headers, ["Team", "Name"])
            rank_col = find_column(leaderboard.headers, ["Rank", "Rk", "#"])
            td_col = find_column(leaderboard.headers, ["TD %", "TD%", "TD Pct", "TD%"]) or ""
            if not team_col or not rank_col or not td_col:
                continue
            for row in leaderboard.rows:
                team_name = row.get(team_col, "")
                team_id = team_lookup.get(normalize_team_name(team_name))
                if not team_id or team_id not in team_ids:
                    continue
                try:
                    rank = int(re.sub(r"[^0-9]", "", row.get(rank_col, "")))
                except ValueError:
                    continue
                td_value = row.get(td_col, "")
                td_pct = parse_percent(td_value)
                if td_pct is not None:
                    td_display = f"{td_pct:.2f}%"
                else:
                    td_display = f"{td_value}%" if td_value else ""
                if not td_display:
                    continue
                badges[team_id].append(
                    f"Ranks {ordinal(rank)} in {conf} in red zone TD% ({td_display})"
                )

        return badges

    def get_context_badges(
        self,
        year: int,
        teams: Dict[str, Dict[str, str]],
        split: str = "split01",
    ) -> Dict[str, Dict[str, List[str]]]:
        configs = [
            {
                "key": "red_zone",
                "label": "red zone TD%",
                "category": CATEGORY_IDS["RED_ZONE"],
                "stat_candidates": ["TD %", "TD%", "TD Pct", "TD%"],
                "formatter": lambda v: f"{parse_percent(v):.2f}%" if parse_percent(v) is not None else v,
                "offense": "offense",
            },
            {
                "key": "third_down",
                "label": "third down %",
                "category": CATEGORY_IDS["THIRD_DOWN"],
                "stat_candidates": ["Conversion %", "Pct", "Pct.", "Conv %", "Conv%", "Pct%"],
                "formatter": lambda v: f"{parse_percent(v):.2f}%" if parse_percent(v) is not None else v,
                "offense": "offense",
            },
            {
                "key": "explosives",
                "label": "explosive plays (20+)",
                "category": CATEGORY_IDS["LONG_PLAYS"],
                "stat_candidates": ["20+", "20", "20+ Plays", "20+ Yds", "20+Yds"],
                "formatter": lambda v: str(v).strip() if v is not None else "",
                "offense": "offense",
            },
            {
                "key": "scoring_offense",
                "label": "scoring offense",
                "category": CATEGORY_IDS["SCORING"],
                "stat_candidates": ["Points/G", "Pts/G", "Pts/Gm", "Pts/G.", "PPG", "Pts"],
                "formatter": format_ppg,
                "offense": "offense",
            },
            {
                "key": "scoring_defense",
                "label": "scoring defense",
                "category": CATEGORY_IDS["SCORING"],
                "stat_candidates": ["Points/G", "Pts/G", "Pts/Gm", "Pts/G.", "PPG", "Pts"],
                "formatter": format_ppg,
                "offense": "defense",
            },
        ]

        badges: Dict[str, Dict[str, List[str]]] = {
            team_id: {cfg["key"]: [] for cfg in configs} for team_id in teams
        }
        team_lookup = build_team_lookup(teams)

        by_conference: Dict[str, List[str]] = {}
        for team_id, info in teams.items():
            conf = info.get("conference")
            if not conf:
                continue
            by_conference.setdefault(conf, []).append(team_id)

        for conf, team_ids in by_conference.items():
            scope = CONFERENCE_IDS.get(conf)
            if not scope:
                continue
            for cfg in configs:
                leaderboard = self.get_leaderboard(
                    year,
                    scope,
                    cfg["category"],
                    split=split,
                    offense=cfg["offense"],
                )
                if not leaderboard:
                    continue
                team_col = find_column(leaderboard.headers, ["Team", "Name"])
                rank_col = find_column(leaderboard.headers, ["Rank", "Rk", "#"])
                stat_col = find_column(leaderboard.headers, cfg["stat_candidates"])
                # Check 'is None' because rank_col can be empty string ""
                if team_col is None or rank_col is None or stat_col is None:
                    continue
                for row in leaderboard.rows:
                    team_name = row.get(team_col, "")
                    team_id = team_lookup.get(normalize_team_name(team_name))
                    if not team_id or team_id not in team_ids:
                        continue
                    try:
                        rank = int(re.sub(r"[^0-9]", "", row.get(rank_col, "")))
                    except ValueError:
                        continue
                    stat_value = row.get(stat_col, "")
                    display_value = cfg["formatter"](stat_value)
                    if not display_value:
                        continue
                    badges[team_id][cfg["key"]].append(
                        f"Ranks {ordinal(rank)} in {conf} in {cfg['label']} ({display_value})"
                    )

        return badges
