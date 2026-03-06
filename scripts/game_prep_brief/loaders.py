from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import urllib.parse
import time
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
PBP_JSON = ROOT_DIR / "data.json"
XML_BUNDLE_JSON = Path(
    os.getenv(
        "GAME_PREP_XML_BUNDLE_PATH",
        str(ROOT_DIR.parent / "yr-data-api" / "data" / "pbp_stats_bundle.json"),
    )
)
GAME_PREP_DATA_SOURCE = (os.getenv("GAME_PREP_DATA_SOURCE") or "xml").strip().lower()
MATCHUPS_DIR = ROOT_DIR / "matchups"
OUTPUT_DIR = ROOT_DIR / "outputs" / "game_prep_brief"

NCAA_SCOREBOARD = (
    "https://data.ncaa.com/casablanca/scoreboard/football/fbs/{year}/{week:02d}/scoreboard.json"
)
YR_DATA_API_BASE = os.getenv("YR_DATA_API_BASE", "https://yr-data-api.fly.dev").rstrip("/")

SLUG_ALIASES = {
    "ole miss": "mississippi",
    "miami fl": "miami",
    "miami (fl)": "miami",
    "miami florida": "miami",
    "lsu": "lsu",
    "usc": "usc",
    "tcu": "tcu",
    "smu": "smu",
    "ucf": "ucf",
    "uab": "uab",
    "utsa": "utsa",
    "byu": "byu",
    "arizona state": "asu",
}

TEAM_API_ALIASES = {
    "ohio-state": ["ohio-state"],
    "washington": ["washington", "wash"],
}

ENRICHMENT_KEYS = (
    "blitz_pct",
    "blitz_pct_last3",
    "negative_plays_pg_api",
    "negative_plays_forced_pg_api",
    "negative_plays_pg_last3_api",
    "negative_plays_forced_pg_last3_api",
    "pff_plays_offense_pg",
    "pff_plays_defense_pg",
    "pff_missed_tackles_pg",
    "pff_tfl_pg",
    "pff_sacks_pg",
    "pff_sacks_allowed_pg",
    "pff_fmt_total",
    "pff_fmt_pg",
    "pff_avg_play_clock",
    "pff_hurry_up_pct",
    "pff_tempo_label",
)

_PBP_PARSER_SRC = ROOT_DIR.parent / "pbp-parser" / "src"
if str(_PBP_PARSER_SRC) not in sys.path:
    sys.path.insert(0, str(_PBP_PARSER_SRC))

_UPSTREAM_IMPORT_ERRORS: dict[str, str] = {}
_UPSTREAM_IMPORT_WARNED = False

try:
    from pbp_parser.cfbstats.scraper_v2 import CfbstatsScraper
except Exception as exc:
    CfbstatsScraper = None  # type: ignore[assignment]
    _UPSTREAM_IMPORT_ERRORS["cfbstats_scraper"] = f"{type(exc).__name__}: {exc}"

try:
    from pbp_parser.cfbstats import verify_bundle_against_cfbstats as _upstream_verify_bundle_against_cfbstats
except Exception as exc:
    _upstream_verify_bundle_against_cfbstats = None  # type: ignore[assignment]
    _UPSTREAM_IMPORT_ERRORS["cfbstats_bundle_verifier"] = f"{type(exc).__name__}: {exc}"

try:
    from pbp_parser.rate_limit import RateLimitConfig
except Exception as exc:
    RateLimitConfig = None  # type: ignore[assignment]
    _UPSTREAM_IMPORT_ERRORS["rate_limit"] = f"{type(exc).__name__}: {exc}"

try:
    from pbp_parser.reference.teams import get_team_conference
except Exception as exc:
    get_team_conference = None  # type: ignore[assignment]
    _UPSTREAM_IMPORT_ERRORS["reference_teams"] = f"{type(exc).__name__}: {exc}"

try:
    from pbp_parser.fourth_down import compute_fourth_down_stats as _upstream_fourth_down_stats
except Exception as exc:
    _upstream_fourth_down_stats = None  # type: ignore[assignment]
    _UPSTREAM_IMPORT_ERRORS["fourth_down"] = f"{type(exc).__name__}: {exc}"

try:
    from pbp_parser.points_off_turnovers import (
        compute_team_points_off_turnover_splits as _upstream_points_off_turnovers_splits,
    )
except Exception as exc:
    _upstream_points_off_turnovers_splits = None  # type: ignore[assignment]
    _UPSTREAM_IMPORT_ERRORS["points_off_turnovers"] = f"{type(exc).__name__}: {exc}"

try:
    from pbp_parser.red_zone import compute_team_red_zone_splits as _upstream_red_zone_splits
except Exception as exc:
    _upstream_red_zone_splits = None  # type: ignore[assignment]
    _UPSTREAM_IMPORT_ERRORS["red_zone"] = f"{type(exc).__name__}: {exc}"

try:
    from pbp_parser.models import ParsedGame as ParserParsedGame, Play as ParserPlay
except Exception as exc:
    ParserParsedGame = None  # type: ignore[assignment]
    ParserPlay = None  # type: ignore[assignment]
    _UPSTREAM_IMPORT_ERRORS["models"] = f"{type(exc).__name__}: {exc}"

_CONFERENCE_NAME_MAP = {
    "AAC": "American",
    "Conference USA": "C-USA",
    "Independents": "FBS Independents",
}

_FALLBACK_CONFERENCE_IDS = {
    "American": 823,
    "ACC": 821,
    "Big 12": 25354,
    "Big Ten": 827,
    "C-USA": 24312,
    "FBS Independents": 99001,
    "MAC": 875,
    "Mountain West": 5486,
    "Pac-12": 905,
    "SEC": 911,
    "Sun Belt": 818,
}

_FALLBACK_CONFERENCE_MEMBERS = {
    "SEC": (
        "Alabama", "Arkansas", "Auburn", "Florida", "Georgia", "Kentucky", "LSU",
        "Mississippi", "Mississippi State", "Missouri", "Oklahoma", "South Carolina",
        "Tennessee", "Texas", "Texas A&M", "Vanderbilt",
    ),
    "Big Ten": (
        "Illinois", "Indiana", "Iowa", "Maryland", "Michigan", "Michigan State",
        "Minnesota", "Nebraska", "Northwestern", "Ohio State", "Oregon", "Penn State",
        "Purdue", "Rutgers", "UCLA", "USC", "Washington", "Wisconsin",
    ),
    "Big 12": (
        "Arizona", "Arizona State", "Baylor", "BYU", "Cincinnati", "Colorado",
        "Houston", "Iowa State", "Kansas", "Kansas State", "Oklahoma State", "TCU",
        "Texas Tech", "UCF", "Utah", "West Virginia",
    ),
    "ACC": (
        "Boston College", "California", "Clemson", "Duke", "Florida State",
        "Georgia Tech", "Louisville", "Miami", "North Carolina", "NC State",
        "Pittsburgh", "SMU", "Stanford", "Syracuse", "Virginia", "Virginia Tech",
        "Wake Forest",
    ),
    "American": (
        "Army", "Charlotte", "East Carolina", "Florida Atlantic", "Memphis", "Navy",
        "North Texas", "Rice", "South Florida", "Temple", "Tulane", "Tulsa", "UAB",
        "UTSA",
    ),
    "Mountain West": (
        "Air Force", "Boise State", "Colorado State", "Fresno State", "Hawaii",
        "Nevada", "New Mexico", "San Diego State", "San Jose State", "UNLV",
        "Utah State", "Wyoming",
    ),
    "Sun Belt": (
        "Appalachian State", "Arkansas State", "Coastal Carolina", "Georgia Southern",
        "Georgia State", "James Madison", "Louisiana", "Marshall", "Old Dominion",
        "South Alabama", "Southern Miss", "Texas State", "Troy", "UL Monroe",
    ),
    "MAC": (
        "Akron", "Ball State", "Bowling Green", "Buffalo", "Central Michigan",
        "Eastern Michigan", "Kent State", "Miami (OH)", "Northern Illinois", "Ohio",
        "Toledo", "UMass", "Western Michigan",
    ),
    "C-USA": (
        "Delaware", "FIU", "Jacksonville State", "Kennesaw State", "Liberty",
        "Louisiana Tech", "Middle Tennessee State", "New Mexico State", "Sam Houston State",
        "UTEP", "Western Kentucky",
    ),
    "Pac-12": ("Oregon State", "Washington State"),
    "FBS Independents": ("Connecticut", "Notre Dame"),
}

_FALLBACK_TEAM_ALIASES = {
    "ole miss": "mississippi",
    "southern california": "usc",
    "miami fl": "miami",
    "miami florida": "miami",
    "miami (fl)": "miami",
    "texas am": "texas a&m",
    "texas a and m": "texas a&m",
}


def _norm_team_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.lower().replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


_FALLBACK_TEAM_TO_CONFERENCE: dict[str, str] = {}
for _conf, _members in _FALLBACK_CONFERENCE_MEMBERS.items():
    for _member in _members:
        _FALLBACK_TEAM_TO_CONFERENCE[_norm_team_name(_member)] = _conf
for _alias, _target in _FALLBACK_TEAM_ALIASES.items():
    _FALLBACK_TEAM_TO_CONFERENCE[_norm_team_name(_alias)] = _FALLBACK_TEAM_TO_CONFERENCE.get(
        _norm_team_name(_target), ""
    )

_LIVE_TURNOVER_SPLIT_CACHE: dict[tuple[int, str], dict] = {}


def _warn_upstream_import_fallback_once() -> None:
    global _UPSTREAM_IMPORT_WARNED
    if _UPSTREAM_IMPORT_WARNED or not _UPSTREAM_IMPORT_ERRORS:
        return
    keys = ", ".join(sorted(_UPSTREAM_IMPORT_ERRORS.keys()))
    print(
        f"[warn] pbp_parser imports unavailable ({keys}); using local fallback logic in game brief loader.",
        file=sys.stderr,
    )
    first_key = next(iter(_UPSTREAM_IMPORT_ERRORS))
    print(
        f"[warn] Example import error: {first_key} -> {_UPSTREAM_IMPORT_ERRORS[first_key]}",
        file=sys.stderr,
    )
    if sys.version_info < (3, 10):
        print(
            "[warn] Python < 3.10 detected; run with a 3.10+ interpreter to enable upstream pbp_parser helpers.",
            file=sys.stderr,
        )
    _UPSTREAM_IMPORT_WARNED = True


class _LeaderboardTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._table_depth = 0
        self._in_row = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._row_cells: list[str] = []

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


def _norm_header(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9%]+", "", value.lower())


def _find_col(headers: list[str], candidates: list[str]) -> str | None:
    normalized_headers = [_norm_header(h) for h in headers]
    normalized_candidates = [_norm_header(c) for c in candidates]
    candidate_set = set(normalized_candidates)
    for idx, h in enumerate(normalized_headers):
        if h in candidate_set:
            return headers[idx]
    for idx, h in enumerate(normalized_headers):
        for c in normalized_candidates:
            if c and c in h:
                return headers[idx]
    if {"rank", "rk", "#"} & set(normalized_candidates):
        if headers and (_norm_header(headers[0]) in {"", "col0"} or headers[0] == ""):
            return headers[0]
    return None


def _parse_cfbstats_table(html: str) -> tuple[list[str], list[dict]]:
    parser = _LeaderboardTableParser()
    parser.feed(html)
    rows = parser.rows
    if not rows:
        return [], []
    header_idx = 0
    for idx, row in enumerate(rows):
        norm = [_norm_header(c) for c in row]
        if "team" in norm or "name" in norm:
            header_idx = idx
            break
    raw_headers = rows[header_idx]
    headers: list[str] = []
    seen: dict[str, int] = {}
    for i, header in enumerate(raw_headers):
        base = header if header else ("" if i == 0 else f"col_{i}")
        count = seen.get(base, 0)
        seen[base] = count + 1
        headers.append(base if count == 0 else f"{base}__{count}")
    out_rows: list[dict] = []
    for row in rows[header_idx + 1 :]:
        if len(row) < 2:
            continue
        padded = row[: len(headers)] + [""] * max(0, len(headers) - len(row))
        out_rows.append({headers[i]: padded[i] for i in range(len(headers))})
    return headers, out_rows


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^0-9.+-]", "", str(value))
    if not cleaned or cleaned in {"+", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fetch_cfbstats_rows(
    year: int,
    conference_id: int,
    split: str,
    category: int,
    offense: str,
    timeout: int = 8,
) -> tuple[list[str], list[dict]]:
    def _req(use_split: str) -> tuple[list[str], list[dict]]:
        url = (
            f"https://cfbstats.com/{year}/leader/{conference_id}/team/{offense}/"
            f"{use_split}/category{int(category):02d}/sort01.html"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        return _parse_cfbstats_table(html)

    try:
        return _req(split)
    except urllib.error.HTTPError as exc:
        # CFBStats currently 404s for split05/split06 leaderboards.
        # Fall back to split01 so conference/nonconf tables are still live-populated.
        if exc.code == 404 and split != "split01":
            return _req("split01")
        raise


def _team_name_variants(team_name: str, team_slug: str) -> set[str]:
    base = _norm_team_name(team_name)
    variants = {base, _norm_team_name(team_slug)}
    if " state" in base:
        variants.add(base.replace(" state", " st"))
    if " st" in base:
        variants.add(base.replace(" st", " state"))
    return {v for v in variants if v}


def _match_row_for_team(rows: list[dict], team_col: str, team_names: set[str]) -> dict | None:
    for row in rows:
        row_team = _norm_team_name(row.get(team_col))
        if row_team in team_names:
            return row
    return None


def _fallback_team_conference(team_name: str) -> str:
    return _FALLBACK_TEAM_TO_CONFERENCE.get(_norm_team_name(team_name), "")


def _fetch_live_rankings_fallback(team_name: str, team_slug: str, season: int) -> tuple[str, dict]:
    conference = _normalize_cfbstats_conference(_fallback_team_conference(team_name))
    conference_id = _FALLBACK_CONFERENCE_IDS.get(conference)
    if not conference or not conference_id:
        return "", {"all": {}, "conf": {}, "nonconf": {}}

    configs = [
        ("red_zone", "red zone TD%", 27, "offense", ["TD %", "TD%", "TD Pct"]),
        ("third_down", "third down %", 25, "offense", ["Conversion %", "Pct", "Conv %", "Conv%"]),
        ("explosives", "explosive plays (20+)", 30, "offense", ["20+", "20+ Plays", "20+ Yds", "20"]),
        ("fourth_down", "4th down conversion %", 26, "offense", ["Conversion %", "Conv %", "Conv%", "Pct"]),
        ("penalties", "penalty yards/game", 14, "offense", ["Yards/G", "Yds/G", "Yards/Gm", "Yds/Gm"]),
        ("time_of_possession", "time of possession", 15, "offense", ["TOP", "Time", "Time of Possession"]),
        ("sacks_defense", "sacks", 20, "offense", ["Sacks", "Sack", "Sk"]),
        ("sacks_offense", "sacks allowed", 20, "defense", ["Sacks", "Sack", "Sk"]),
        ("tfl_defense", "TFL", 21, "offense", ["TFL", "TFL/G", "TFLA"]),
        ("tfl_offense", "TFL allowed", 21, "defense", ["TFL", "TFL/G"]),
        ("total_offense", "total offense", 10, "offense", ["Yards/G", "Yds/G", "Total", "Yds"]),
        ("total_defense", "total defense", 10, "defense", ["Yards/G", "Yds/G", "Total", "Yds"]),
        ("rushing_offense", "rushing offense", 1, "offense", ["Rush Yds/G", "Rush Yards/G", "Yards/G", "Yds/G"]),
        ("rushing_defense", "rushing defense", 1, "defense", ["Rush Yds/G", "Rush Yards/G", "Yards/G", "Yds/G"]),
        ("passing_offense", "passing offense", 2, "offense", ["Pass Yds/G", "Pass Yards/G", "Yards/G", "Yds/G"]),
        ("passing_defense", "passing defense", 2, "defense", ["Pass Yds/G", "Pass Yards/G", "Yards/G", "Yds/G"]),
        ("scoring_offense", "scoring offense", 9, "offense", ["Points/G", "Pts/G", "Pts/Gm", "PPG"]),
        ("scoring_defense", "scoring defense", 9, "defense", ["Points/G", "Pts/G", "Pts/Gm", "PPG"]),
        ("turnover_margin", "turnover margin", 12, "offense", ["Margin", "TO Margin", "Margin/G", "+/-"]),
    ]

    split_map = {"all": "split01", "conf": "split05", "nonconf": "split06"}
    team_names = _team_name_variants(team_name, team_slug)
    rankings = {"all": {}, "conf": {}, "nonconf": {}}

    for scope, split in split_map.items():
        cached_tables: dict[tuple[int, str], tuple[list[str], list[dict]]] = {}
        for key, label, category, offense, stat_candidates in configs:
            try:
                headers, rows = cached_tables.get((category, offense), ([], []))
                if not rows:
                    headers, rows = _fetch_cfbstats_rows(season, conference_id, split, category, offense)
                    cached_tables[(category, offense)] = (headers, rows)
                if not rows:
                    continue
                team_col = _find_col(headers, ["Team", "Name"])
                rank_col = _find_col(headers, ["Rank", "Rk", "#"])
                stat_col = _find_col(headers, stat_candidates)
                if stat_col is None and key == "explosives" and len(headers) > 4:
                    # category30 table uses duplicate "Yards" headers by threshold.
                    # index 4 is the 20+ column after ['', Name, G, 10+, 20+, ...].
                    stat_col = headers[4]
                if team_col is None or rank_col is None or stat_col is None:
                    continue
                row = _match_row_for_team(rows, team_col, team_names)
                if not row:
                    continue
                rank = _to_float(row.get(rank_col))
                if rank is None:
                    continue
                value_raw = (row.get(stat_col) or "").strip()
                if "%" in value_raw:
                    value_raw = value_raw.replace("%", "").strip()
                value_num = _to_float(value_raw)
                value = value_raw
                if value_num is not None and ":" not in value_raw:
                    value = f"{value_num:.1f}" if not value_num.is_integer() else str(int(value_num))
                rankings[scope][key] = {
                    "rank": int(rank),
                    "conference": conference,
                    "value": value or "N/A",
                    "label": label,
                    "total": sum(1 for r in rows if r.get(team_col)),
                }
            except Exception:
                continue

        # Derive scoring margin from scoring offense/defense leaderboards.
        try:
            off_headers, off_rows = cached_tables.get((9, "offense"), ([], []))
            def_headers, def_rows = cached_tables.get((9, "defense"), ([], []))
            off_team_col = _find_col(off_headers, ["Team", "Name"]) if off_headers else None
            def_team_col = _find_col(def_headers, ["Team", "Name"]) if def_headers else None
            off_stat_col = _find_col(off_headers, ["Points/G", "Pts/G", "Pts/Gm", "PPG"]) if off_headers else None
            def_stat_col = _find_col(def_headers, ["Points/G", "Pts/G", "Pts/Gm", "PPG"]) if def_headers else None
            if off_team_col and def_team_col and off_stat_col and def_stat_col:
                off_map = {
                    _norm_team_name(r.get(off_team_col)): _to_float(r.get(off_stat_col))
                    for r in off_rows
                    if r.get(off_team_col)
                }
                def_map = {
                    _norm_team_name(r.get(def_team_col)): _to_float(r.get(def_stat_col))
                    for r in def_rows
                    if r.get(def_team_col)
                }
                margin_map = {}
                for k, off in off_map.items():
                    deff = def_map.get(k)
                    if off is None or deff is None:
                        continue
                    margin_map[k] = off - deff
                if margin_map:
                    ranked = sorted(margin_map.items(), key=lambda item: item[1], reverse=True)
                    rank_lookup = {name: idx + 1 for idx, (name, _) in enumerate(ranked)}
                    team_key = next((name for name in team_names if name in margin_map), None)
                    if team_key:
                        margin_value = margin_map[team_key]
                        rankings[scope]["scoring_margin"] = {
                            "rank": rank_lookup[team_key],
                            "conference": conference,
                            "value": f"{margin_value:+.1f}",
                            "label": "scoring margin",
                            "total": len(ranked),
                        }
        except Exception:
            pass

    return conference, rankings


def _normalize_cfbstats_conference(conference: str | None) -> str:
    if not conference:
        return ""
    return _CONFERENCE_NAME_MAP.get(conference, conference)


def _is_missing_rankings(team_entry: dict | None) -> bool:
    if not isinstance(team_entry, dict):
        return True
    rankings = team_entry.get("cfbstats", {}).get("rankings", {})
    all_rankings = rankings.get("all")
    return not isinstance(all_rankings, dict) or not all_rankings


def _flatten_badges(payload: dict, slug: str) -> dict:
    split_rows = payload.get(slug, {}) if isinstance(payload, dict) else {}
    if not isinstance(split_rows, dict):
        return {}

    out: dict = {}
    for key, rows in split_rows.items():
        if not isinstance(rows, list) or not rows:
            continue
        row = rows[0] if isinstance(rows[0], dict) else None
        if not row:
            continue
        rank = row.get("rank")
        total = row.get("total")
        value = row.get("value")
        conference = row.get("conference")
        label = row.get("label")
        if rank is None or value in (None, ""):
            continue
        out[key] = {
            "rank": rank,
            "total": total if isinstance(total, int) else None,
            "value": value,
            "conference": conference or "",
            "label": label or key.replace("_", " "),
        }
    return out


def _fetch_live_rankings(team_name: str, team_slug: str, season: int) -> tuple[str, dict]:
    if CfbstatsScraper is None or RateLimitConfig is None or get_team_conference is None:
        return _fetch_live_rankings_fallback(team_name, team_slug, season)

    conference = _normalize_cfbstats_conference(get_team_conference(team_name))
    if not conference:
        # Input team names may be lowercase/hyphenated (e.g., "ohio-state"),
        # which can miss in upstream conference lookup. Fall back instead of N/A.
        return _fetch_live_rankings_fallback(team_name, team_slug, season)

    team_payload = {
        team_slug: {
            "name": team_name,
            "abbr": team_slug[:4].upper(),
            "conference": conference,
        }
    }

    # Use an ephemeral cache directory per generation run to avoid stale rankings.
    cache_dir = Path(tempfile.gettempdir()) / f"cfbstats_live_{os.getpid()}_{time.time_ns()}"
    rate_cfg = RateLimitConfig(  # type: ignore[misc]
        min_delay=0.0,
        max_delay=0.05,
        max_retries=0,
        backoff_base=0.0,
        backoff_factor=1.0,
        max_backoff=0.0,
        jitter=0.0,
    )
    scraper = CfbstatsScraper(cache_dir=cache_dir, timeout=6, rate_config=rate_cfg)
    split_map = {"all": "split01", "conf": "split05", "nonconf": "split06"}

    rankings = {"all": {}, "conf": {}, "nonconf": {}}
    try:
        for scope, split in split_map.items():
            badges = scraper.get_context_badges(season, team_payload, split=split)
            rankings[scope] = _flatten_badges(badges, team_slug)
    except Exception:
        return _fetch_live_rankings_fallback(team_name, team_slug, season)
    fb_conf, fb_rankings = _fetch_live_rankings_fallback(team_name, team_slug, season)
    for scope in ("all", "conf", "nonconf"):
        primary_scope = rankings.get(scope) if isinstance(rankings.get(scope), dict) else {}
        fallback_scope = fb_rankings.get(scope) if isinstance(fb_rankings.get(scope), dict) else {}
        if not primary_scope:
            rankings[scope] = fallback_scope
            continue
        if fallback_scope:
            for key, value in fallback_scope.items():
                if key not in primary_scope or not isinstance(primary_scope.get(key), dict):
                    primary_scope[key] = value
            rankings[scope] = primary_scope
    if not rankings.get("all"):
        return fb_conf or conference, fb_rankings
    return fb_conf or conference, rankings


def _parse_turnover_split_all_games(html: str) -> dict:
    m = re.search(
        r'<td class="split-name">All Games</td>\s*'
        r"<td>(\d+)</td>\s*"
        r"<td>(\d+)</td>\s*"
        r"<td>(\d+)</td>\s*"
        r"<td>(\d+)</td>\s*"
        r"<td>(\d+)</td>\s*"
        r"<td>(\d+)</td>\s*"
        r"<td>(\d+)</td>\s*"
        r"<td>([-+]?\d+)</td>\s*"
        r"<td>([-+]?\d*\.?\d+)</td>",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return {}
    g, fum_gain, int_gain, total_gain, fum_lost, int_lost, total_lost, margin, margin_pg = m.groups()
    return {
        "games": int(g),
        "fumbles_gained": int(fum_gain),
        "interceptions_gained": int(int_gain),
        "turnovers_gained": int(total_gain),
        "fumbles_lost": int(fum_lost),
        "interceptions_lost": int(int_lost),
        "turnovers_lost": int(total_lost),
        "margin": int(margin),
        "margin_per_game": float(margin_pg),
    }


def _fetch_live_turnover_split(team_name: str, team_slug: str, season: int, timeout: int = 8) -> dict:
    key = (season, team_slug)
    cached = _LIVE_TURNOVER_SPLIT_CACHE.get(key)
    if isinstance(cached, dict) and cached:
        return cached

    team_variants = _team_name_variants(team_name, team_slug)
    index_url = f"https://cfbstats.com/{season}/team/index.html"
    try:
        req = urllib.request.Request(index_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            index_html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return {}

    team_id: str | None = None
    for match in re.finditer(
        rf'/{season}/team/(\d+)/index\.html"[^>]*>([^<]+)<',
        index_html,
        re.IGNORECASE,
    ):
        cand_id = match.group(1)
        cand_name = _norm_team_name(match.group(2))
        if cand_name in team_variants:
            team_id = cand_id
            break
    if not team_id:
        return {}

    split_url = f"https://cfbstats.com/{season}/team/{team_id}/turnovermargin/split.html"
    try:
        req = urllib.request.Request(split_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            split_html = resp.read().decode("utf-8", errors="ignore")
        parsed = _parse_turnover_split_all_games(split_html)
    except Exception:
        parsed = {}
    if parsed:
        _LIVE_TURNOVER_SPLIT_CACHE[key] = parsed
    return parsed


def slugify(name: str) -> str:
    lower = name.strip().lower()
    if lower in SLUG_ALIASES:
        return SLUG_ALIASES[lower]
    return re.sub(r"[^a-z0-9]+", "-", lower).strip("-")


def _candidate_team_ids(team_slug: str, team_name: str | None = None) -> list[str]:
    candidates: list[str] = []
    slug = (team_slug or "").strip().lower()
    if slug:
        candidates.append(slug)
    for alias in TEAM_API_ALIASES.get(slug, []):
        if alias not in candidates:
            candidates.append(alias)
    if team_name:
        normalized_name = re.sub(r"[^a-z0-9]+", "-", team_name.strip().lower()).strip("-")
        if normalized_name and normalized_name not in candidates:
            candidates.append(normalized_name)
    return candidates


def _fetch_text_from_candidates(candidates: list[str], suffix: str, timeout: int = 8, attempts: int = 3) -> str | None:
    if not candidates:
        return None
    for candidate in candidates:
        encoded = urllib.parse.quote(candidate)
        url = f"{YR_DATA_API_BASE}/yr/{encoded}/{suffix}"
        for attempt in range(1, attempts + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    text = (resp.read().decode("utf-8", errors="ignore") or "").strip()
                if text:
                    return text
            except Exception:
                if attempt < attempts:
                    time.sleep(0.2 * attempt)
                continue
    return None


def _deep_merge(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, val in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _bundle_home_abbr(stats: dict) -> str | None:
    best_abbr: str | None = None
    best_games = -1
    for cat_payload in stats.values():
        if not isinstance(cat_payload, dict):
            continue
        for abbr, row in cat_payload.items():
            if not isinstance(row, dict):
                continue
            games = row.get("games")
            if not isinstance(games, int):
                games = len(row.get("games") or []) if isinstance(row.get("games"), list) else 0
            if games > best_games:
                best_games = games
                best_abbr = abbr
    return best_abbr


def _bundle_row(stats: dict, category: str, home_abbr: str | None) -> dict:
    cat = stats.get(category) or {}
    if not isinstance(cat, dict):
        return {}
    if home_abbr and isinstance(cat.get(home_abbr), dict):
        return cat.get(home_abbr) or {}
    if cat:
        key, row = max(
            cat.items(),
            key=lambda item: (
                item[1].get("games")
                if isinstance(item[1], dict) and isinstance(item[1].get("games"), int)
                else (
                    len(item[1].get("games") or [])
                    if isinstance(item[1], dict) and isinstance(item[1].get("games"), list)
                    else 0
                )
            ),
        )
        if isinstance(row, dict):
            return row
    return {}


def _iter_play_tree_plays(play_tree: object):
    for quarter in play_tree or []:
        if not isinstance(quarter, dict):
            continue
        for drive in quarter.get("drives") or []:
            if not isinstance(drive, dict):
                continue
            for play in drive.get("plays") or []:
                if isinstance(play, dict):
                    yield play


def _iter_play_tree_drives(play_tree: object):
    for quarter in play_tree or []:
        if not isinstance(quarter, dict):
            continue
        quarter_num = quarter.get("quarter")
        for drive in quarter.get("drives") or []:
            if not isinstance(drive, dict):
                continue
            plays = [p for p in (drive.get("plays") or []) if isinstance(p, dict)]
            if plays:
                yield quarter_num, plays


def _abbr_set(value: object) -> set[str]:
    if isinstance(value, str):
        cleaned = value.strip().upper()
        return {cleaned} if cleaned else set()
    if isinstance(value, (list, tuple, set)):
        out: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                continue
            cleaned = item.strip().upper()
            if cleaned:
                out.add(cleaned)
        return out
    return set()


def _team_aliases_from_bundle(home_abbr: str | None, stats: object, games: object) -> set[str]:
    aliases = _abbr_set(home_abbr)
    opponent_abbrs = {
        str(g.get("opponent_abbr") or "").strip().upper()
        for g in (games or [])
        if isinstance(g, dict) and g.get("opponent_abbr")
    }
    if isinstance(stats, dict):
        for category in stats.values():
            if not isinstance(category, dict):
                continue
            for abbr, row in category.items():
                if not isinstance(abbr, str):
                    continue
                cleaned = abbr.strip().upper()
                if not cleaned or cleaned in opponent_abbrs:
                    continue
                if isinstance(row, dict):
                    games_count = row.get("games")
                    if isinstance(games_count, int) and games_count <= 0:
                        continue
                aliases.add(cleaned)
    return aliases


def _infer_team_alias_from_play_tree(
    play_tree: object,
    *,
    team_aliases: set[str],
    opponent_abbr: object,
) -> set[str]:
    opp_aliases = _abbr_set(opponent_abbr)
    if not team_aliases or not opp_aliases:
        return set()

    offense_counts: dict[str, int] = {}
    desc_tokens: dict[str, int] = {}
    for play in _iter_play_tree_plays(play_tree):
        if play.get("is_no_play"):
            continue
        token = str(play.get("offense") or "").upper().strip()
        if token:
            offense_counts[token] = offense_counts.get(token, 0) + 1
        # Also scan descriptions for team abbreviations in key patterns:
        # "RECOVERED BY [TEAM]", "TOUCHDOWN [TEAM]", "[TEAM] ball on"
        desc_up = str(play.get("description") or "").upper()
        for m in re.finditer(r"RECOVERED BY ([A-Z]{2,6})\b", desc_up):
            t = m.group(1)
            if t not in opp_aliases:
                desc_tokens[t] = desc_tokens.get(t, 0) + 1
        for m in re.finditer(r"TOUCHDOWN ([A-Z]{2,6})\b", desc_up):
            t = m.group(1)
            if t not in opp_aliases:
                desc_tokens[t] = desc_tokens.get(t, 0) + 1
        m = re.match(r"([A-Z]{2,6}) BALL ON\b", desc_up)
        if m:
            t = m.group(1)
            if t not in opp_aliases:
                desc_tokens[t] = desc_tokens.get(t, 0) + 1
    if not offense_counts:
        return set()

    has_opp = any(token in opp_aliases for token in offense_counts)
    if not has_opp:
        return set()

    inferred: set[str] = set()

    # Infer from offense field — conservative, one dominant token.
    unknown = {
        token: count
        for token, count in offense_counts.items()
        if token not in team_aliases and token not in opp_aliases
    }
    if unknown:
        sorted_unknown = sorted(unknown.items(), key=lambda kv: kv[1], reverse=True)
        best_token, best_count = sorted_unknown[0]
        if best_count >= 3 and (len(sorted_unknown) == 1 or best_count > sorted_unknown[1][1]):
            inferred.add(best_token)

    # Infer from description patterns — tokens appearing 2+ times
    # that aren't already known.
    for token, count in desc_tokens.items():
        if count >= 2 and token not in team_aliases and token not in opp_aliases and token not in inferred:
            inferred.add(token)

    return inferred


def _aggregate_xml_alias_rows(stats: object, category: str, team_aliases: set[str]) -> dict:
    if not isinstance(stats, dict):
        return {}
    cat = stats.get(category) or {}
    if not isinstance(cat, dict):
        return {}
    rows = [
        row
        for abbr, row in cat.items()
        if isinstance(abbr, str) and abbr.strip().upper() in team_aliases and isinstance(row, dict)
    ]
    if not rows:
        return {}
    out: dict[str, object] = {}
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (int, float)):
                out[key] = (out.get(key) or 0) + value
            elif key not in out and value not in (None, ""):
                out[key] = value
    return out


def _drive_offense_abbr(plays: list[dict]) -> str:
    for play in plays:
        offense = str(play.get("offense") or "").strip().upper()
        if offense:
            return offense
    return ""


def _touchdown_extra_points(plays: list[dict], td_index: int) -> int:
    # Prefer explicit conversion/PAT result if present; fallback assumes PAT good.
    for play in plays[td_index + 1 : td_index + 6]:
        desc_up = str(play.get("description") or "").upper()
        if not desc_up:
            continue
        if "2-POINT" in desc_up:
            if "GOOD" in desc_up or "SUCCESS" in desc_up:
                return 2
            if "NO GOOD" in desc_up or "FAILED" in desc_up:
                return 0
        if "PAT" in desc_up or "EXTRA POINT" in desc_up or "KICK ATTEMPT" in desc_up:
            if "GOOD" in desc_up:
                return 1
            if "NO GOOD" in desc_up or "FAILED" in desc_up or "BLOCKED" in desc_up:
                return 0
    return 1


def _drive_points_result(plays: list[dict]) -> tuple[str, int]:
    for idx, play in enumerate(plays):
        if not play.get("is_scoring"):
            continue
        # Skip defensive TDs (e.g. another turnover returned for a score during the
        # post-TO drive) — those aren't "points off turnovers" for the offense.
        if play.get("is_turnover"):
            desc_chk = str(play.get("description") or "").upper()
            if "TOUCHDOWN" in desc_chk or re.search(r"\bTD\b", desc_chk):
                continue
        desc_up = str(play.get("description") or "").upper()
        if "TOUCHDOWN" in desc_up or re.search(r"\bTD\b", desc_up):
            return "TD", 6 + _touchdown_extra_points(plays, idx)
        if "FIELD GOAL" in desc_up or re.search(r"\bFG\b", desc_up):
            return "FG", 3
        if "SAFETY" in desc_up:
            return "SAFETY", 2
    # Classify non-scoring ending from last play description
    if plays:
        last = plays[-1]
        last_desc = str(last.get("description") or "").upper()
        if "PUNT" in last_desc:
            return "PUNT", 0
        if "FUMBLE" in last_desc or "INTERCEPTED" in last_desc or "INTERCEPTION" in last_desc:
            return "TURNOVER", 0
        if "FIELD GOAL" in last_desc and ("MISSED" in last_desc or "NO GOOD" in last_desc or "BLOCKED" in last_desc):
            return "MISSED FG", 0
        if "END OF" in last_desc or "KNEEL" in last_desc or "KNEE" in last_desc:
            return "END OF PERIOD", 0
        # Check explicit down==4 first, then scan all plays for 4th-down indicator
        if last.get("down") == 4:
            return "DOWNS", 0
        # When down numbers aren't populated, a non-scoring drive that doesn't
        # end in a punt/turnover/kick was most likely a failed 4th-down attempt.
        return "DOWNS", 0
    return "NO SCORE", 0


def _is_transition_play(play: dict) -> bool:
    """Return True for non-action plays (spot indicators, timeouts, kickoffs)
    that should be skipped when searching for the next offensive possession."""
    desc = str(play.get("description") or "").upper()
    if re.search(r"\bBALL ON\b", desc):
        return True
    if not play.get("offense"):
        return True
    # Standalone timeout lines — no rush/pass/kick action
    if re.match(r"^TIMEOUT\b", desc):
        return True
    return False


def _turnover_return_points(play: dict) -> tuple[str, int]:
    desc_up = str(play.get("description") or "").upper()
    if "TOUCHDOWN" in desc_up or re.search(r"\bTD\b", desc_up):
        # PAT often omitted in reduced play trees; default to 7 for scoreboard-equivalent points.
        return "DEF TD", 7
    if "SAFETY" in desc_up:
        return "SAFETY", 2
    return "NO SCORE", 0


def _turnover_recovery_side(
    desc_up: str,
    offense_side: str | None,
    turnover_type: str,
    team_aliases: set[str],
    opp_aliases: set[str],
) -> str | None:
    if turnover_type == "INT":
        if offense_side == "team":
            return "opp"
        if offense_side == "opp":
            return "team"
        return None

    recovered = ""
    match = re.search(r"RECOVERED BY ([A-Z0-9.'\\-]+)", desc_up)
    if match:
        recovered = re.sub(r"[^A-Z0-9]", "", match.group(1))

    if recovered in team_aliases:
        return "team"
    if recovered in opp_aliases:
        return "opp"
    return None


def _turnover_possessing_side(desc_up: str, offense_side: str | None, turnover_type: str) -> str | None:
    if turnover_type != "FUM":
        return offense_side
    if offense_side is None:
        return None
    # On kick/punt returns, the return team (opposite listed offense) possesses the ball.
    if ("PUNT" in desc_up or "KICKOFF" in desc_up) and "RETURN" in desc_up:
        return "opp" if offense_side == "team" else "team"
    return offense_side


def _is_overturned_turnover_text(desc_up: str) -> bool:
    return (
        "PLAY OVERTURNED" in desc_up
        or "CALL OVERTURNED" in desc_up
        or "RULING ON THE FIELD WAS OVERTURNED" in desc_up
    )


def _is_turnover_on_downs_text(desc_up: str) -> bool:
    return "TURNOVER ON DOWNS" in desc_up or ("ON DOWNS" in desc_up and "4TH" in desc_up)


def _drive_takeaway_event(
    plays: list[dict], team_aliases: set[str], opp_aliases: set[str]
) -> tuple[str, str, dict] | None:
    last_event: tuple[str, str, dict] | None = None
    for play in plays:
        if play.get("is_no_play"):
            continue
        offense = str(play.get("offense") or "").upper()
        desc_up = str(play.get("description") or "").upper()
        turnover_looking = play.get("is_turnover") or "INTERCEPT" in desc_up or "FUMBLE" in desc_up
        if not turnover_looking:
            continue
        if _is_overturned_turnover_text(desc_up):
            continue
        if _is_turnover_on_downs_text(desc_up):
            continue
        if "INTERCEPT" in desc_up:
            turnover_type = "INT"
        elif "FUMBLE" in desc_up:
            turnover_type = "FUM"
        else:
            # Exclude turnover-on-downs and other possession flips from takeaway stats.
            continue
        offense_side = "team" if offense in team_aliases else ("opp" if offense in opp_aliases else None)
        possessing_side = _turnover_possessing_side(desc_up, offense_side, turnover_type)
        recovery_side = _turnover_recovery_side(
            desc_up, offense_side, turnover_type, team_aliases, opp_aliases
        )
        if recovery_side is None or possessing_side is None or recovery_side == possessing_side:
            continue
        if recovery_side == "team":
            last_event = ("team_gained", turnover_type, play)
        elif recovery_side == "opp":
            last_event = ("team_lost", turnover_type, play)
    return last_event


def _derive_turnover_drive_stats(play_tree: object, team_abbr: object, opp_abbr: object) -> dict:
    team_aliases = _abbr_set(team_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    if not team_aliases or not opp_aliases:
        return {}

    post_turnover_drives: list[dict] = []
    points_off_turnovers_for = 0
    points_off_turnovers_against = 0
    ints_lost = ints_gained = fum_lost = fum_gained = 0
    turnovers_lost = turnovers_gained = 0

    indexed_plays: list[tuple[int | None, dict]] = []
    for quarter in play_tree or []:
        if not isinstance(quarter, dict):
            continue
        quarter_num = quarter.get("quarter")
        for drive in quarter.get("drives") or []:
            if not isinstance(drive, dict):
                continue
            for play in drive.get("plays") or []:
                if isinstance(play, dict):
                    indexed_plays.append((quarter_num if isinstance(quarter_num, int) else None, play))

    def _next_possession_side(start_idx: int) -> str | None:
        for j in range(start_idx + 1, len(indexed_plays)):
            nxt = indexed_plays[j][1]
            if nxt.get("is_no_play") or _is_transition_play(nxt):
                continue
            nxt_off = str(nxt.get("offense") or "").upper()
            if nxt_off in team_aliases:
                return "team"
            if nxt_off in opp_aliases:
                return "opp"
        return None

    for idx, (quarter_num, play) in enumerate(indexed_plays):
        if play.get("is_no_play"):
            continue
        if not play.get("is_turnover"):
            continue
        offense = str(play.get("offense") or "").upper()
        desc_up = str(play.get("description") or "").upper()
        if _is_overturned_turnover_text(desc_up):
            continue
        # Turnover-on-downs should not be counted as a takeaway, even when play text
        # also contains a fumble phrase (e.g., out-of-bounds + turnover on downs).
        if _is_turnover_on_downs_text(desc_up):
            continue
        if "INTERCEPT" in desc_up:
            turnover_type = "INT"
        elif "FUMBLE" in desc_up:
            turnover_type = "FUM"
        else:
            continue

        # Detect special-teams turnovers (punt/kickoff return fumbles).
        # StatBroadcast excludes these from POT — no ensuing drive is counted.
        is_special_teams_turnover = bool(
            turnover_type == "FUM"
            and ("PUNT" in desc_up or "KICKOFF" in desc_up)
            and "RETURN" in desc_up
        )

        offense_side = "team" if offense in team_aliases else ("opp" if offense in opp_aliases else None)
        if offense_side is None:
            continue
        recovery_side = _turnover_recovery_side(
            desc_up, offense_side, turnover_type, team_aliases, opp_aliases
        )
        possessing_side = _turnover_possessing_side(desc_up, offense_side, turnover_type)
        next_side = _next_possession_side(idx)
        possession_changed = (
            recovery_side is not None and possessing_side is not None and recovery_side != possessing_side
        )
        if not possession_changed and possessing_side and next_side and next_side != possessing_side:
            possession_changed = True
            recovery_side = next_side
        if not possession_changed:
            continue

        if recovery_side == "opp":
            turnover_side = "team_lost"
            recovered_aliases = opp_aliases
            losing_aliases = team_aliases
            recovered_by_default = sorted(opp_aliases)[0]
            turnovers_lost += 1
            if turnover_type == "INT":
                ints_lost += 1
            else:
                fum_lost += 1
        elif recovery_side == "team":
            turnover_side = "team_gained"
            recovered_aliases = team_aliases
            losing_aliases = opp_aliases
            recovered_by_default = sorted(team_aliases)[0]
            turnovers_gained += 1
            if turnover_type == "INT":
                ints_gained += 1
            else:
                fum_gained += 1
        else:
            continue

        # Turnover return score (e.g., pick-six/fumble return TD) counts immediately.
        if play.get("is_scoring"):
            drive_result, points_scored = _turnover_return_points(play)
            if not is_special_teams_turnover:
                if turnover_side == "team_gained":
                    points_off_turnovers_for += points_scored
                else:
                    points_off_turnovers_against += points_scored
            post_turnover_drives.append(
                {
                    "quarter": quarter_num,
                    "clock": play.get("clock") or "",
                    "turnover_type": turnover_type,
                    "lost_by": offense or "?",
                    "recovered_by": recovered_by_default or "?",
                    "drive_result": drive_result,
                    "points_scored": points_scored,
                    "side": turnover_side,
                    "turnover_description": play.get("description") or "",
                }
            )
            continue

        # Find ensuing possession by the recovering side.
        start_idx: int | None = None
        for j in range(idx + 1, len(indexed_plays)):
            nxt = indexed_plays[j][1]
            if nxt.get("is_no_play") or _is_transition_play(nxt):
                continue
            nxt_off = str(nxt.get("offense") or "").upper()
            if nxt_off in recovered_aliases:
                start_idx = j
                break
            if nxt_off in losing_aliases:
                # Possession returned to the losing side before a recovery-side drive started.
                # Do not attribute later drives to this turnover.
                break
        if start_idx is None:
            continue

        # Skip turnovers at end of Q2 when next drive starts in Q3 (halftime reset).
        start_quarter = indexed_plays[start_idx][0]
        if quarter_num == 2 and start_quarter == 3:
            continue

        drive_plays: list[dict] = []
        recovered_by = ""
        for j in range(start_idx, len(indexed_plays)):
            nxt = indexed_plays[j][1]
            if _is_transition_play(nxt):
                continue
            nxt_off = str(nxt.get("offense") or "").upper()
            if not recovered_by and nxt_off in recovered_aliases:
                recovered_by = nxt_off
            if drive_plays and nxt_off and nxt_off not in recovered_aliases:
                break
            drive_plays.append(nxt)

        drive_result, points_scored = _drive_points_result(drive_plays)
        if not is_special_teams_turnover:
            if turnover_side == "team_gained":
                points_off_turnovers_for += points_scored
            else:
                points_off_turnovers_against += points_scored
        total_yards = sum(p.get("yards", 0) or 0 for p in drive_plays if isinstance(p.get("yards"), (int, float)))
        post_turnover_drives.append(
            {
                "quarter": start_quarter if isinstance(start_quarter, int) else quarter_num,
                "clock": play.get("clock") or "",
                "turnover_type": turnover_type,
                "lost_by": offense or "?",
                "recovered_by": recovered_by or recovered_by_default or "?",
                "drive_result": drive_result,
                "points_scored": points_scored,
                "side": turnover_side,
                "num_plays": len(drive_plays),
                "total_yards": total_yards,
                "turnover_description": play.get("description") or "",
            }
        )

    return {
        "post_turnover_drives": post_turnover_drives,
        "points_off_turnovers_for": points_off_turnovers_for,
        "points_off_turnovers_against": points_off_turnovers_against,
        "interceptions_lost": ints_lost,
        "interceptions_gained": ints_gained,
        "fumbles_lost": fum_lost,
        "fumbles_gained": fum_gained,
        "turnovers_lost": turnovers_lost,
        "turnovers_gained": turnovers_gained,
    }


def _rollup_game_from_play_tree(play_tree: object, team_abbr: object, opp_abbr: object) -> dict:
    explosive_passes = 0
    explosive_rushes = 0
    negative_plays = 0
    negative_plays_forced = 0
    turnovers_lost = 0
    turnovers_gained = 0

    team_aliases = _abbr_set(team_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    for play in _iter_play_tree_plays(play_tree):
        if play.get("is_no_play"):
            continue
        offense = (play.get("offense") or "").upper()
        yards = play.get("yards")
        desc = (play.get("description") or "").upper()
        is_interception = "INTERCEPT" in desc

        if offense in team_aliases:
            if isinstance(yards, (int, float)) and yards < 0:
                negative_plays += 1
            # Treat interception-return records as non-explosive for offense.
            if isinstance(yards, (int, float)) and yards >= 20 and "PASS" in desc and not is_interception:
                explosive_passes += 1
            if isinstance(yards, (int, float)) and yards >= 15 and "RUSH" in desc:
                explosive_rushes += 1
            if play.get("is_turnover"):
                turnovers_lost += 1
        elif offense in opp_aliases:
            if isinstance(yards, (int, float)) and yards < 0:
                negative_plays_forced += 1
            if play.get("is_turnover"):
                turnovers_gained += 1

    return {
        "explosive_passes": explosive_passes,
        "explosive_rushes": explosive_rushes,
        "explosives": explosive_passes + explosive_rushes,
        "negative_plays": negative_plays,
        "negative_plays_forced": negative_plays_forced,
        "turnovers_lost": turnovers_lost,
        "turnovers_gained": turnovers_gained,
    }


def _estimate_total_yards_from_play_tree(play_tree: object, team_abbr: object) -> int | None:
    team_aliases = _abbr_set(team_abbr)
    if not team_aliases:
        return None
    total = 0
    seen = False
    for play in _iter_play_tree_plays(play_tree):
        if play.get("is_no_play"):
            continue
        if str(play.get("offense") or "").upper() not in team_aliases:
            continue
        if not _counts_toward_total_offense(play):
            continue
        yards = play.get("yards")
        if isinstance(yards, (int, float)):
            total += int(yards)
            seen = True
    return total if seen else None


def _estimate_points_from_play_tree(play_tree: object, team_abbr: object, opp_abbr: object) -> tuple[int | None, int | None]:
    team_aliases = _abbr_set(team_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    if not team_aliases or not opp_aliases:
        return None, None

    team_points = 0
    opp_points = 0
    pending_td_for_team: bool | None = None

    for play in _iter_play_tree_plays(play_tree):
        offense = (play.get("offense") or "").upper()
        desc = (play.get("description") or "").upper()
        offense_is_team = offense in team_aliases
        offense_is_opp = offense in opp_aliases
        if not offense_is_team and not offense_is_opp:
            continue

        if "TOUCHDOWN" in desc:
            if offense_is_team:
                team_points += 6
                pending_td_for_team = True
            else:
                opp_points += 6
                pending_td_for_team = False
            continue
        if "FIELD GOAL" in desc and "GOOD" in desc:
            if offense_is_team:
                team_points += 3
            else:
                opp_points += 3
            pending_td_for_team = None
            continue
        if "SAFETY" in desc:
            if offense_is_team:
                opp_points += 2
            else:
                team_points += 2
            pending_td_for_team = None
            continue

        if pending_td_for_team is not None:
            if "2-POINT" in desc and ("GOOD" in desc or "SUCCESS" in desc):
                if pending_td_for_team:
                    team_points += 2
                else:
                    opp_points += 2
                pending_td_for_team = None
                continue
            if ("PAT" in desc or "KICK ATTEMPT" in desc) and "GOOD" in desc:
                if pending_td_for_team:
                    team_points += 1
                else:
                    opp_points += 1
                pending_td_for_team = None
                continue
            if "NO GOOD" in desc or "FAILED" in desc:
                pending_td_for_team = None

    return team_points, opp_points


def _parse_down(down_distance: object) -> int | None:
    text = str(down_distance or "").strip()
    if not text:
        return None
    head = text.split("-", 1)[0].strip()
    if head.isdigit():
        value = int(head)
        return value if 1 <= value <= 4 else None
    return None


def _parse_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _parser_plays_from_play_tree(play_tree: object) -> list[ParserPlay]:
    if ParserPlay is None:
        return []
    parser_plays: list[ParserPlay] = []
    for quarter in play_tree or []:
        if not isinstance(quarter, dict):
            continue
        quarter_num = quarter.get("quarter")
        qnum = quarter_num if isinstance(quarter_num, int) and quarter_num > 0 else 1
        for drive in quarter.get("drives") or []:
            if not isinstance(drive, dict):
                continue
            for play in drive.get("plays") or []:
                if not isinstance(play, dict):
                    continue
                desc = str(play.get("description") or "")
                if not desc:
                    continue
                desc_up = desc.upper()
                raw_is_turnover = bool(play.get("is_turnover"))
                # Normalize the known false-positive pattern where a fumble goes out
                # of bounds and the play is ultimately turnover on downs.
                is_tod_out_of_bounds = _is_turnover_on_downs_text(desc_up) and "OUT OF BOUNDS" in desc_up
                is_turnover = raw_is_turnover and not is_tod_out_of_bounds
                parser_plays.append(
                    ParserPlay(
                        quarter=qnum,
                        offense=(str(play.get("offense") or "").upper().strip() or None),
                        clock=(str(play.get("clock") or "").strip() or None),
                        down_distance=(str(play.get("down_distance") or "").strip() or None),
                        spot=(str(play.get("spot") or "").strip() or None),
                        description=desc,
                        yards=play.get("yards") if isinstance(play.get("yards"), int) else None,
                        is_no_play=bool(play.get("is_no_play")),
                        is_scrimmage_play=bool(play.get("is_scrimmage_play")),
                        is_turnover=is_turnover,
                        is_scoring=bool(play.get("is_scoring")),
                    )
                )
    return parser_plays


def _compute_fourth_down_stats_from_play_tree(play_tree: object, team_abbr: object) -> tuple[int, int] | None:
    team_aliases = _abbr_set(team_abbr)
    if not team_aliases or _upstream_fourth_down_stats is None or ParserPlay is None:
        return None
    team = sorted(team_aliases)[0]
    parser_plays = _parser_plays_from_play_tree(play_tree)
    if not parser_plays:
        return None
    try:
        stats = _upstream_fourth_down_stats(parser_plays, team)
        return int(stats.attempts or 0), int(stats.conversions or 0)
    except Exception:
        return None


def _compute_red_zone_20_stats_from_play_tree(
    play_tree: object, team_abbr: object, opp_abbr: object
) -> tuple[int, int, int] | None:
    """
    Reuse upstream red-zone helper for canonical RZ (inside-20) totals only.

    Note: upstream parser defines Green Zone/Tight Red Zone differently than this
    brief, so we intentionally keep local derivation for those metrics.
    """
    team_aliases = _abbr_set(team_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    if (
        not team_aliases
        or not opp_aliases
        or _upstream_red_zone_splits is None
        or ParserPlay is None
        or ParserParsedGame is None
    ):
        return None

    parser_plays = _parser_plays_from_play_tree(play_tree)
    if not parser_plays:
        return None

    team_tokens: dict[str, int] = {}
    opp_tokens: dict[str, int] = {}
    for play in parser_plays:
        offense = (play.offense or "").upper()
        if offense in team_aliases:
            team_tokens[offense] = team_tokens.get(offense, 0) + 1
        if offense in opp_aliases:
            opp_tokens[offense] = opp_tokens.get(offense, 0) + 1

    team = max(team_tokens, key=team_tokens.get) if team_tokens else sorted(team_aliases)[0]
    opp = max(opp_tokens, key=opp_tokens.get) if opp_tokens else sorted(opp_aliases)[0]
    if team == opp:
        return None

    try:
        parsed_game = ParserParsedGame(pdf_path=Path("play_tree.json"), teams=[team, opp], plays=parser_plays)
        splits = _upstream_red_zone_splits([parsed_game], last_n=3)
        team_splits = splits.get(team)
        if team_splits is None:
            return None
        season = team_splits.season
        return int(season.rz_trips or 0), int(season.rz_tds or 0), int(season.rz_fgs or 0)
    except Exception:
        return None


def _compute_points_off_turnovers_from_play_tree(
    play_tree: object, team_abbr: object, opp_abbr: object
) -> tuple[int, int] | None:
    team_aliases = _abbr_set(team_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    if (
        not team_aliases
        or not opp_aliases
        or _upstream_points_off_turnovers_splits is None
        or ParserParsedGame is None
    ):
        return None

    parser_plays = _parser_plays_from_play_tree(play_tree)
    if not parser_plays:
        return None

    team_tokens: dict[str, int] = {}
    opp_tokens: dict[str, int] = {}
    for play in parser_plays:
        offense = (play.offense or "").upper()
        if offense in team_aliases:
            team_tokens[offense] = team_tokens.get(offense, 0) + 1
        if offense in opp_aliases:
            opp_tokens[offense] = opp_tokens.get(offense, 0) + 1

    team = max(team_tokens, key=team_tokens.get) if team_tokens else sorted(team_aliases)[0]
    opp = max(opp_tokens, key=opp_tokens.get) if opp_tokens else sorted(opp_aliases)[0]
    if team == opp:
        return None

    try:
        parsed_game = ParserParsedGame(pdf_path=Path("play_tree.json"), teams=[team, opp], plays=parser_plays)
        splits = _upstream_points_off_turnovers_splits([parsed_game], last_n=3)
        team_splits = splits.get(team)
        if team_splits is None:
            return None
        season = team_splits.season
        return int(season.points_for or 0), int(season.points_allowed or 0)
    except Exception:
        return None


def _is_scrimmage_play(play: dict, down: int | None) -> bool:
    explicit = play.get("is_scrimmage_play")
    if isinstance(explicit, bool):
        return explicit
    if down in (1, 2, 3, 4):
        return True
    desc = str(play.get("description") or "").upper()
    if " PASS " in f" {desc} " or " RUSH " in f" {desc} " or " SACK " in f" {desc} ":
        return True
    return False


def _counts_toward_total_offense(play: dict) -> bool:
    down = _parse_down(play.get("down_distance"))
    if not _is_scrimmage_play(play, down):
        return False
    desc = str(play.get("description") or "").upper()
    if " PUNT " in f" {desc} ":
        return False
    if "FIELD GOAL" in desc or "KICK ATTEMPT" in desc:
        return False
    if "PAT" in desc or "EXTRA POINT" in desc:
        return False
    return any(token in desc for token in (" PASS ", " RUSH ", "SACK", "SCRAMBLE", "KNEEL"))


def _yards_to_goal_from_spot(spot: object, offense_abbr: object, opp_abbr: object) -> int | None:
    text = str(spot or "").strip().upper()
    if not text:
        return None
    if text == "50":
        return 50
    m = re.search(r"(\d{1,2})$", text)
    if not m:
        return None
    yard = int(m.group(1))
    offense_aliases = _abbr_set(offense_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    if any(alias in text for alias in opp_aliases):
        return yard
    if any(alias in text for alias in offense_aliases):
        return 100 - yard
    return yard if yard <= 50 else 100 - yard


def _yards_to_goal_reached_on_play(play: dict, offense_abbr: object, opp_abbr: object) -> int | None:
    """
    Best-effort estimate of the closest point to the goal line reached during a play.

    Use the minimum of:
    - the recorded pre-play spot
    - the explicit end spot in the play description (`to the XYZ12`)
    - 0 for offensive touchdowns
    """
    offense_aliases = _abbr_set(offense_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    best = _yards_to_goal_from_spot(play.get("spot"), offense_abbr, opp_abbr)

    desc = str(play.get("description") or "")
    desc_up = desc.upper()
    if "TOUCHDOWN" in desc_up:
        best = 0 if best is None else min(best, 0)

    matches = list(re.finditer(r"to the\s+([A-Z]{2,4})(\d{1,2})", desc, re.IGNORECASE))
    for match in matches:
        side = re.sub(r"[^A-Z0-9]", "", match.group(1).upper())
        yard = int(match.group(2))
        reached = None
        if side in opp_aliases:
            reached = yard
        elif side in offense_aliases:
            reached = 100 - yard
        if reached is not None:
            best = reached if best is None else min(best, reached)

    return best


def _iter_flat_play_tree_plays(play_tree: object) -> list[tuple[int | None, dict]]:
    indexed_plays: list[tuple[int | None, dict]] = []
    for quarter in play_tree or []:
        if not isinstance(quarter, dict):
            continue
        quarter_num = quarter.get("quarter")
        for drive in quarter.get("drives") or []:
            if not isinstance(drive, dict):
                continue
            for play in drive.get("plays") or []:
                if isinstance(play, dict):
                    indexed_plays.append((quarter_num if isinstance(quarter_num, int) else None, play))
    return indexed_plays


def _iter_possession_drives(play_tree: object, team_abbr: object, opp_abbr: object) -> list[tuple[str, list[dict]]]:
    team_aliases = _abbr_set(team_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    drives: list[tuple[str, list[dict]]] = []
    current_side: str | None = None
    current_plays: list[dict] = []
    last_quarter: int | None = None

    def flush() -> None:
        nonlocal current_side, current_plays
        if current_side and current_plays:
            drives.append((current_side, current_plays))
        current_side = None
        current_plays = []

    for quarter_num, play in _iter_flat_play_tree_plays(play_tree):
        if not isinstance(play, dict) or play.get("is_no_play"):
            continue
        offense = str(play.get("offense") or "").upper()
        if offense in team_aliases:
            side = "team"
        elif offense in opp_aliases:
            side = "opp"
        else:
            side = None

        if last_quarter == 2 and quarter_num == 3:
            flush()
        last_quarter = quarter_num

        desc_up = str(play.get("description") or "").upper()
        if "DRIVE STARTS AT" in desc_up:
            flush()
            current_side = side
            continue

        if side is None:
            continue

        if current_side is None:
            current_side = side
            current_plays = [play]
            continue

        if side != current_side:
            flush()
            current_side = side
            current_plays = [play]
        else:
            current_plays.append(play)

    if current_side and current_plays:
        drives.append((current_side, current_plays))
    return drives


def _is_conversion_attempt_text(desc_up: str) -> bool:
    return any(
        token in desc_up
        for token in (
            "KICK ATTEMPT",
            "EXTRA POINT",
            "PAT",
            "2PT",
            "2-POINT",
            "2 POINT",
            "TWO-POINT",
            "TWO POINT",
            "CONVERSION",
        )
    )


def _zone_drive_result(plays: list[dict], team_aliases: set[str]) -> tuple[int, int]:
    for play in reversed(plays):
        offense = str(play.get("offense") or "").upper()
        if offense not in team_aliases:
            continue
        desc_up = str(play.get("description") or "").upper()
        if "TOUCHDOWN" in desc_up:
            if play.get("is_turnover") and not _is_overturned_turnover_text(desc_up):
                continue
            return 1, 0
        if (
            "FIELD GOAL" in desc_up
            and "GOOD" in desc_up
            and "NO GOOD" not in desc_up
            and "BLOCKED" not in desc_up
            and "MISSED" not in desc_up
        ):
            return 0, 1
    return 0, 0


def _derive_zone_trip_stats(play_tree: object, team_abbr: object, opp_abbr: object) -> dict[str, int]:
    team_aliases = _abbr_set(team_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    rz_trips = rz_tds = rz_fgs = 0
    trz_trips = trz_tds = trz_fgs = 0
    gz_trips = gz_tds = gz_fgs = gz_failed = 0

    for drive_side, drive_plays in _iter_possession_drives(play_tree, team_aliases, opp_aliases):
        if drive_side != "team":
            continue

        scrimmage_plays = []
        entered_rz = entered_trz = entered_gz = False

        for play in drive_plays:
            desc_up = str(play.get("description") or "").upper()
            if "TIMEOUT" in desc_up or _is_conversion_attempt_text(desc_up):
                continue
            if " PUNT " in f" {desc_up} " or "KICKOFF" in desc_up or "KICK OFF" in desc_up:
                continue

            down = _parse_down(play.get("down_distance"))
            is_fg_attempt = "FIELD GOAL" in desc_up
            if not (_is_scrimmage_play(play, down) or is_fg_attempt):
                continue
            if not play.get("down_distance") and not is_fg_attempt:
                continue

            if _is_scrimmage_play(play, down) and not play.get("is_no_play"):
                scrimmage_plays.append(play)

            ytg = _yards_to_goal_from_spot(play.get("spot"), team_aliases, opp_aliases)
            if not isinstance(ytg, int):
                continue
            if 0 < ytg <= 30:
                entered_gz = True
            if 0 < ytg <= 20:
                entered_rz = True
            if 0 < ytg <= 10:
                entered_trz = True

        if scrimmage_plays and all("KNEEL" in str(play.get("description") or "").upper() for play in scrimmage_plays):
            continue

        if not (entered_gz or entered_rz or entered_trz):
            continue

        td, fg = _zone_drive_result(drive_plays, team_aliases)
        if entered_gz:
            gz_trips += 1
            gz_tds += td
            gz_fgs += fg
            if not td and not fg:
                gz_failed += 1
        if entered_rz:
            rz_trips += 1
            rz_tds += td
            rz_fgs += fg
        if entered_trz:
            trz_trips += 1
            trz_tds += td
            trz_fgs += fg

    return {
        "red_zone_trips": rz_trips,
        "red_zone_tds": rz_tds,
        "red_zone_fgs": rz_fgs,
        "tight_red_zone_trips": trz_trips,
        "tight_red_zone_tds": trz_tds,
        "tight_red_zone_fgs": trz_fgs,
        "green_zone_trips": gz_trips,
        "green_zone_tds": gz_tds,
        "green_zone_fgs": gz_fgs,
        "green_zone_failed": gz_failed,
    }


def _derive_game_detail_stats(play_tree: object, team_abbr: object, opp_abbr: object) -> dict:
    team_aliases = _abbr_set(team_abbr)
    opp_aliases = _abbr_set(opp_abbr)
    team = sorted(team_aliases)[0] if team_aliases else ""
    opp = sorted(opp_aliases)[0] if opp_aliases else ""
    if not team_aliases or not opp_aliases:
        return {}

    third_att = third_conv = 0
    fourth_att = fourth_conv = 0
    penalty_count = penalty_yards = 0
    penalties_off = penalties_def = penalties_st = 0
    punts = punt_yards = punt_net_yards = punts_inside_20 = punt_touchbacks = punt_long = 0
    punt_returns_for = punt_return_yards_for = punt_return_long_for = punt_return_20_plus_for = 0
    punt_returns_allowed = punt_return_yards_allowed = punt_return_long_allowed = punt_return_20_plus_allowed = 0
    kick_returns = kick_return_yards = kick_return_long = kick_return_30_plus = 0
    special_teams_tds = fg_blocks = punt_blocks = 0
    onside_kicks_attempted = onside_kicks_recovered = 0
    two_pt_attempts = two_pt_conversions = 0
    opp_two_pt_attempts = opp_two_pt_conversions = 0
    rz_trips = rz_tds = rz_fgs = 0
    trz_trips = trz_tds = trz_fgs = 0
    gz_trips = gz_tds = gz_fgs = gz_failed = 0
    for quarter in play_tree or []:
        if not isinstance(quarter, dict):
            continue
        for drive in quarter.get("drives") or []:
            if not isinstance(drive, dict):
                continue
            for play in drive.get("plays") or []:
                if not isinstance(play, dict) or play.get("is_no_play"):
                    continue
                desc = str(play.get("description") or "")
                desc_up = desc.upper()
                offense = str(play.get("offense") or "").upper()
                offense_is_team = offense in team_aliases
                offense_is_opp = offense in opp_aliases
                down = _parse_down(play.get("down_distance"))
                is_scrimmage = _is_scrimmage_play(play, down)

                if offense_is_team and down in (3, 4):
                    if down == 3:
                        third_att += 1
                        if "1ST DOWN" in desc_up or "TOUCHDOWN" in desc_up:
                            third_conv += 1
                    else:
                        is_punt = "PUNT" in desc_up
                        is_field_goal_try = (
                            "FIELD GOAL" in desc_up
                            or (
                                "KICK ATTEMPT" in desc_up
                                and "PAT" not in desc_up
                                and "EXTRA POINT" not in desc_up
                            )
                        )
                        has_go_for_it_action = any(
                            token in desc_up
                            for token in ("RUSH", " RUN ", "PASS", "COMPLETE", "INCOMPLETE", "SACK", "SCRAMBLE")
                        )
                        # Penalty-only 4th downs are not "go for it" attempts unless
                        # an actual rush/pass action occurred in the same play text.
                        if "PENALTY" in desc_up and not has_go_for_it_action:
                            has_go_for_it_action = False

                        # 4th-down attempts are go-for-it snaps only:
                        # exclude punts/FG tries/special teams and non-action penalties.
                        if not is_punt and not is_field_goal_try and has_go_for_it_action:
                            fourth_att += 1
                            is_td = "TOUCHDOWN" in desc_up
                            is_first_down = "1ST DOWN" in desc_up
                            # CFBStats conversion behavior aligns with:
                            # - TD on 4th down counts as conversion even if the text also
                            #   references a turnover-on-downs original ruling.
                            # - First-down text paired with turnover-on-downs does not.
                            if is_td or (is_first_down and "TURNOVER ON DOWNS" not in desc_up):
                                fourth_conv += 1

                if "PENALTY" in desc_up:
                    penalty_count += 1
                    y = _parse_int(r"(\d+)\s*yards?", desc) or 0
                    penalty_yards += y
                    if offense_is_team:
                        penalties_off += 1
                    elif offense_is_opp:
                        penalties_def += 1
                    else:
                        penalties_st += 1

                if offense_is_team and " PUNT " in f" {desc_up} ":
                    py = _parse_int(r"punt\s+(\d+)\s+yards?", desc) or 0
                    punts += 1
                    punt_yards += py
                    punt_long = max(punt_long, py)
                    punt_net = py
                    if "TOUCHBACK" in desc_up:
                        punt_touchbacks += 1
                        punt_net -= 20
                    dest = _parse_int(r"to the [A-Z]{2,4}(\d{1,2})", desc)
                    if dest is not None and 0 <= dest <= 20:
                        punts_inside_20 += 1
                    ret = _parse_int(r"return(?:ed)?\s+(\d+)\s+yards?", desc) or 0
                    if ret > 0:
                        punt_returns_allowed += 1
                        punt_return_yards_allowed += ret
                        punt_return_long_allowed = max(punt_return_long_allowed, ret)
                        if ret >= 20:
                            punt_return_20_plus_allowed += 1
                    punt_net -= ret
                    punt_net_yards += max(0, punt_net)

                if offense_is_opp and " PUNT " in f" {desc_up} " and "RETURN" in desc_up:
                    pret = _parse_int(r"return(?:ed)?\s+(\d+)\s+yards?", desc) or 0
                    if pret > 0:
                        punt_returns_for += 1
                        punt_return_yards_for += pret
                        punt_return_long_for = max(punt_return_long_for, pret)
                        if pret >= 20:
                            punt_return_20_plus_for += 1
                        if "TOUCHDOWN" in desc_up:
                            special_teams_tds += 1

                if offense_is_opp and " PUNT " in f" {desc_up} " and "BLOCKED" in desc_up:
                    punt_blocks += 1
                    if "TOUCHDOWN" in desc_up:
                        special_teams_tds += 1

                if offense_is_opp and ("FIELD GOAL" in desc_up or " KICK ATTEMPT " in f" {desc_up} ") and "BLOCKED" in desc_up:
                    fg_blocks += 1
                    if "TOUCHDOWN" in desc_up:
                        special_teams_tds += 1

                if offense_is_opp and " KICKOFF " in f" {desc_up} " and "RETURN" in desc_up:
                    kret = _parse_int(r"return(?:ed)?\s+(\d+)\s+yards?", desc) or 0
                    if kret > 0:
                        kick_returns += 1
                        kick_return_yards += kret
                        kick_return_long = max(kick_return_long, kret)
                        if kret >= 30:
                            kick_return_30_plus += 1
                        if "TOUCHDOWN" in desc_up:
                            special_teams_tds += 1

                if offense_is_team and "ONSIDE" in desc_up and "KICKOFF" in desc_up:
                    onside_kicks_attempted += 1
                    if any(f"RECOVERED BY {alias}" in desc_up for alias in team_aliases):
                        onside_kicks_recovered += 1

                if "TWO-POINT" in desc_up or "TWO POINT" in desc_up or "2-POINT" in desc_up or "2 POINT" in desc_up or "2PT" in desc_up:
                    is_good = any(
                        token in desc_up
                        for token in ("GOOD", "SUCCESSFUL", "SUCCEEDS", "CONVERSION IS GOOD")
                    ) and not any(token in desc_up for token in ("NO GOOD", "FAILED", "FAILS"))
                    if offense_is_team:
                        two_pt_attempts += 1
                        if is_good:
                            two_pt_conversions += 1
                    elif offense_is_opp:
                        opp_two_pt_attempts += 1
                        if is_good:
                            opp_two_pt_conversions += 1

    zone_stats = _derive_zone_trip_stats(play_tree, team_aliases, opp_aliases)
    rz_trips = int(zone_stats.get("red_zone_trips") or 0)
    rz_tds = int(zone_stats.get("red_zone_tds") or 0)
    rz_fgs = int(zone_stats.get("red_zone_fgs") or 0)
    trz_trips = int(zone_stats.get("tight_red_zone_trips") or 0)
    trz_tds = int(zone_stats.get("tight_red_zone_tds") or 0)
    trz_fgs = int(zone_stats.get("tight_red_zone_fgs") or 0)
    gz_trips = int(zone_stats.get("green_zone_trips") or 0)
    gz_tds = int(zone_stats.get("green_zone_tds") or 0)
    gz_fgs = int(zone_stats.get("green_zone_fgs") or 0)
    gz_failed = int(zone_stats.get("green_zone_failed") or 0)

    if rz_trips > gz_trips:
        print(
            f"[warn] Zone invariant violated for {team} vs {opp}: rz_trips ({rz_trips}) > gz_trips ({gz_trips})",
            file=sys.stderr,
        )
    if trz_trips > rz_trips:
        print(
            f"[warn] Zone invariant violated for {team} vs {opp}: trz_trips ({trz_trips}) > rz_trips ({rz_trips})",
            file=sys.stderr,
        )
    if rz_tds > rz_trips:
        print(
            f"[warn] Zone invariant violated for {team} vs {opp}: rz_tds ({rz_tds}) > rz_trips ({rz_trips})",
            file=sys.stderr,
        )
    if trz_tds > trz_trips:
        print(
            f"[warn] Zone invariant violated for {team} vs {opp}: trz_tds ({trz_tds}) > trz_trips ({trz_trips})",
            file=sys.stderr,
        )

    special_teams = {
        "punts": punts,
        "punt_yards": punt_yards,
        "punt_net_yards": punt_net_yards,
        "punt_long": punt_long,
        "punts_inside_20": punts_inside_20,
        "punt_touchbacks": punt_touchbacks,
        "punt_returns": punt_returns_for,
        "punt_return_yards": punt_return_yards_for,
        "punt_return_long": punt_return_long_for,
        "punt_return_20_plus": punt_return_20_plus_for,
        "punt_returns_allowed": punt_returns_allowed,
        "punt_return_yards_allowed": punt_return_yards_allowed,
        "punt_return_long_allowed": punt_return_long_allowed,
        "punt_return_20_plus_allowed": punt_return_20_plus_allowed,
        "kickoff_returns": kick_returns,
        "kickoff_return_yards": kick_return_yards,
        "kickoff_return_long": kick_return_long,
        "kick_return_30_plus": kick_return_30_plus,
        "special_teams_tds": special_teams_tds,
        "fg_blocks": fg_blocks,
        "punt_blocks": punt_blocks,
        "onside_kicks_attempted": onside_kicks_attempted,
        "onside_kicks_recovered": onside_kicks_recovered,
    }

    return {
        "third_down_attempts": third_att,
        "third_down_conversions": third_conv,
        "4th_down_attempts": fourth_att,
        "4th_down_conversions": fourth_conv,
        "penalties": penalty_count,
        "penalty_yards": penalty_yards,
        "penalties_offense": penalties_off,
        "penalties_defense": penalties_def,
        "penalties_special_teams": penalties_st,
        "red_zone_trips": rz_trips,
        "red_zone_tds": rz_tds,
        "red_zone_fgs": rz_fgs,
        "tight_red_zone_trips": trz_trips,
        "tight_red_zone_tds": trz_tds,
        "tight_red_zone_fgs": trz_fgs,
        "green_zone_trips": gz_trips,
        "green_zone_tds": gz_tds,
        "green_zone_fgs": gz_fgs,
        "green_zone_failed": gz_failed,
        "two_pt_attempts": two_pt_attempts,
        "two_pt_conversions": two_pt_conversions,
        "opp_two_pt_attempts": opp_two_pt_attempts,
        "opp_two_pt_conversions": opp_two_pt_conversions,
        "special_teams": special_teams,
    }


def _convert_xml_bundle_team(slug: str, payload: dict) -> dict:
    stats = payload.get("stats") or {}
    home_abbr = _bundle_home_abbr(stats)
    team_aliases = _team_aliases_from_bundle(home_abbr, stats, payload.get("games"))
    tov_rollup = _aggregate_xml_alias_rows(stats, "turnovers", team_aliases)
    pot_rollup = _aggregate_xml_alias_rows(stats, "points_off_turnovers", team_aliases)

    expl = _bundle_row(stats, "explosives", home_abbr)
    neg = _bundle_row(stats, "negative_plays", home_abbr)
    rz = _bundle_row(stats, "red_zone", home_abbr)
    pen = _bundle_row(stats, "penalties", home_abbr)
    tov = _bundle_row(stats, "turnovers", home_abbr)
    sched = _bundle_row(stats, "schedule", home_abbr)

    rz_rate = rz.get("rz_td_rate")
    if isinstance(rz_rate, (int, float)) and rz_rate <= 1:
        rz_pct = round(rz_rate * 100, 1)
    elif isinstance(rz_rate, (int, float)):
        rz_pct = round(float(rz_rate), 1)
    else:
        rz_pct = "N/A"

    normalized_games: list[tuple[int, int, dict]] = []
    last_week = 0
    for idx, g in enumerate(payload.get("games") or [], start=1):
        if not isinstance(g, dict):
            continue
        game_number = g.get("game_number") if isinstance(g.get("game_number"), int) else idx
        raw_week = g.get("week")
        if isinstance(raw_week, int) and raw_week > 0:
            week = raw_week
        else:
            week = last_week + 1 if last_week > 0 else game_number
        # Ensure monotonic ordering even when source week labels are sparse/missing.
        if week <= last_week:
            week = last_week + 1
        last_week = week
        normalized_games.append((game_number, week, g))

    week_to_is_home: dict[int, bool | None] = {}
    for _, week, g in normalized_games:
        raw_home = g.get("is_home")
        week_to_is_home[week] = raw_home if isinstance(raw_home, bool) else None

    schedule_games_out: list[dict] = []
    # Build schedule from played games first. Alias-split XML schedule rows can contain
    # synthetic BYE placeholders when one alias only covers part of a season.
    for _, week, g in normalized_games:
        schedule_games_out.append(
            {
                "week": week,
                "game_date": g.get("date") or g.get("game_date"),
                "is_home": g.get("is_home") if isinstance(g.get("is_home"), bool) else None,
                "is_bye": False,
                "opponent": g.get("opponent_abbr") or g.get("opponent") or "OPP",
            }
        )

    # Fallback to XML schedule row only when no played games were present.
    if not schedule_games_out:
        for g in sched.get("games") or []:
            if not isinstance(g, dict):
                continue
            is_bye = bool(g.get("is_bye_week"))
            opp = g.get("opponent")
            week = g.get("week_number")
            game_date = g.get("game_date")
            inferred_is_home = week_to_is_home.get(week) if isinstance(week, int) else None
            schedule_games_out.append(
                {
                    "week": week,
                    "game_date": game_date,
                    "is_home": inferred_is_home,
                    "is_bye": is_bye,
                    "opponent": None if is_bye else (opp or "OPP"),
                }
            )

    games_parsed = payload.get("games_parsed")
    turnovers = tov_rollup.get("turnovers", tov.get("turnovers"))
    turnovers_forced = tov_rollup.get("turnovers_forced", tov.get("turnovers_forced"))
    games_out: list[dict] = []
    for game_number, normalized_week, g in normalized_games:
        opp_abbr = g.get("opponent_abbr") or g.get("opponent")
        play_tree = g.get("play_tree") if isinstance(g.get("play_tree"), list) else []
        inferred_aliases = _infer_team_alias_from_play_tree(
            play_tree, team_aliases=team_aliases, opponent_abbr=opp_abbr
        )
        if inferred_aliases:
            team_aliases.update(inferred_aliases)
        game_rollup = _rollup_game_from_play_tree(play_tree, team_aliases, opp_abbr)
        game_detail = _derive_game_detail_stats(play_tree, team_aliases, opp_abbr)
        game_turnover_detail = _derive_turnover_drive_stats(play_tree, team_aliases, opp_abbr)
        raw_pf = g.get("points_for")
        raw_pa = g.get("points_against")
        estimated_pf, estimated_pa = _estimate_points_from_play_tree(play_tree, team_aliases, opp_abbr)
        points_for = raw_pf if isinstance(raw_pf, (int, float)) else estimated_pf
        points_against = raw_pa if isinstance(raw_pa, (int, float)) else estimated_pa
        total_plays = g.get("total_plays")
        if not isinstance(total_plays, int):
            total_plays = sum(
                1
                for play in _iter_play_tree_plays(play_tree)
                if not play.get("is_no_play") and play.get("is_scrimmage_play")
            )
        total_yards = _estimate_total_yards_from_play_tree(play_tree, team_aliases)

        game = {
            "game_number": game_number,
            "week": normalized_week,
            "date": g.get("date") or g.get("game_date"),
            "is_home": g.get("is_home"),
            "opponent_abbr": opp_abbr,
            "opponent": g.get("opponent") or opp_abbr or "OPP",
            "points_for": points_for,
            "points_against": points_against,
            "total_plays": total_plays,
            "total_yards": total_yards,
            "play_tree": play_tree,
        }
        game.update(game_rollup)
        game.update(game_detail)
        game.update(game_turnover_detail)
        games_out.append(game)

    return {
        "name": payload.get("team_name") or slug.replace("-", " ").title(),
        "abbr": home_abbr or slug[:4].upper(),
        "abbr_aliases": sorted(team_aliases),
        "conference": "",
        "color": "#888888",
        "cfbstats": {"rankings": {"all": {}, "conf": {}, "nonconf": {}}},
        "xml_rollups": {
            "turnovers": tov_rollup or tov,
            "points_off_turnovers": pot_rollup,
        },
        "aggregates": {
            "games": games_parsed if isinstance(games_parsed, int) else "N/A",
            "record": "N/A",
            "conf_record": "N/A",
            "ppg": "N/A",
            "opp_ppg": "N/A",
            "explosives_per_game": expl.get("explosives_pg", "N/A"),
            "negative_plays_per_game": neg.get("negative_plays_pg", "N/A"),
            "negative_plays_forced_per_game": neg.get("negative_plays_forced_pg", "N/A"),
            "turnover_margin": (turnovers_forced - turnovers) if isinstance(turnovers_forced, (int, float)) and isinstance(turnovers, (int, float)) else "N/A",
            "red_zone_td_pct": rz_pct,
            "penalties_per_game": pen.get("total_penalties_pg", "N/A"),
        },
        "bye_weeks": sched.get("bye_weeks", []),
        "schedule": {"games": schedule_games_out},
        "games": games_out,
        "xml_stats": stats,
        "xml_source": True,
    }


def _load_xml_bundle_data() -> dict:
    if not XML_BUNDLE_JSON.exists():
        return {}
    with open(XML_BUNDLE_JSON) as f:
        raw = json.load(f)
    out: dict = {}
    # Support wrapper shape {"teams": {...}, "_meta": {...}} and legacy flat shape.
    meta = raw.get("_meta")
    if isinstance(meta, dict):
        out["_meta"] = meta
    teams = raw.get("teams", raw) if "teams" in raw else raw
    for slug, payload in teams.items():
        if slug.startswith("_"):
            continue
        if isinstance(payload, dict):
            converted = _convert_xml_bundle_team(slug, payload)
            converted["_parser_bundle_payload"] = payload
            out[slug] = converted
    return out


def load_pbp_data(matchup_slug: str | None = None) -> dict:
    base: dict = {}
    if GAME_PREP_DATA_SOURCE != "xml":
        print(
            f"[warn] Non-XML source '{GAME_PREP_DATA_SOURCE}' is disabled; forcing XML bundle mode",
            file=sys.stderr,
        )
    base = _load_xml_bundle_data()
    if not base:
        print(
            f"[warn] XML bundle source unavailable at {XML_BUNDLE_JSON}; returning empty team set",
            file=sys.stderr,
        )

    if matchup_slug:
        matchup_path = MATCHUPS_DIR / matchup_slug / "data.json"
        if matchup_path.exists():
            with open(matchup_path) as f:
                overlay_raw = json.load(f)
            overlay = overlay_raw.get("teams", {})
            if overlay:
                merged = dict(base)
                for slug, data in overlay.items():
                    if slug in merged and isinstance(merged[slug], dict):
                        merged[slug] = _deep_merge(merged[slug], data)
                    else:
                        merged[slug] = data
                base = merged
        else:
            print(f"[warn] Matchup data not found at {matchup_path}", file=sys.stderr)

    return base


CORE_XML_FIELDS = {
    "explosives": ("explosives", "explosive_pass", "explosive_run"),
    "red_zone": ("rz_trips", "rz_tds"),
    "turnovers": ("turnovers", "turnovers_forced"),
    "points_off_turnovers": ("points_off_turnovers", "points_off_turnovers_allowed"),
    "middle_eight": ("middle_eight_points", "middle_eight_points_allowed"),
    "special_teams": ("fg_attempts", "fg_made"),
    "two_point": (
        "two_point_attempts",
        "two_point_conversions",
        "two_point_allowed_attempts",
        "two_point_allowed_conversions",
    ),
    "penalties": ("total_penalties", "total_penalty_yards"),
}


def _is_numeric_zero(value: object) -> bool:
    return isinstance(value, (int, float)) and value == 0


def _best_xml_row(xml_stats: dict, category: str) -> dict:
    cat = xml_stats.get(category) or {}
    if not isinstance(cat, dict) or not cat:
        return {}
    _, row = max(
        cat.items(),
        key=lambda item: (item[1].get("games", 0) if isinstance(item[1], dict) else 0),
    )
    return row if isinstance(row, dict) else {}


def _collect_parity_gaps(team_name: str, pbp_entry: dict | None) -> list[str]:
    if not pbp_entry:
        return [f"{team_name}: missing team payload in XML bundle"]
    if not pbp_entry.get("xml_source"):
        return [f"{team_name}: non-XML source detected (unsupported)"]

    xml_stats = pbp_entry.get("xml_stats") or {}
    if not isinstance(xml_stats, dict) or not xml_stats:
        return [f"{team_name}: missing xml_stats payload"]

    games_payload = pbp_entry.get("games") or []
    team_games = len(games_payload) if isinstance(games_payload, list) else 0
    opponent_abbrs = {
        str(g.get("opponent_abbr") or "").upper()
        for g in games_payload
        if isinstance(g, dict) and g.get("opponent_abbr")
    }
    gaps: list[str] = []
    for category, required_fields in CORE_XML_FIELDS.items():
        row = _best_xml_row(xml_stats, category)
        if not row:
            gaps.append(f"{team_name}: missing '{category}' category row")
            continue

        games = row.get("games")
        if not isinstance(games, int) or games <= 0:
            gaps.append(f"{team_name}: '{category}' row has invalid games count ({games})")
            continue

        missing = [field for field in required_fields if row.get(field) is None]
        if missing:
            gaps.append(f"{team_name}: '{category}' missing fields: {', '.join(missing)}")
            continue

        values = [row.get(field) for field in required_fields]
        if values and all(_is_numeric_zero(v) for v in values):
            if team_games and isinstance(games, int) and games < team_games:
                # Some feeds split one team across aliases (e.g., UW/WASH/WAS).
                # If non-opponent alias rows collectively cover the full season
                # and remain all-zero, treat as valid instead of a parity gap.
                category_rows = xml_stats.get(category) or {}
                if isinstance(category_rows, dict):
                    alias_rows = []
                    for abbr, alias_row in category_rows.items():
                        if not isinstance(alias_row, dict):
                            continue
                        if str(abbr).upper() in opponent_abbrs:
                            continue
                        alias_rows.append(alias_row)
                    alias_games = sum(
                        int(r.get("games") or 0) for r in alias_rows if isinstance(r.get("games"), int)
                    )
                    alias_all_zero = bool(alias_rows) and all(
                        all(_is_numeric_zero(r.get(field)) for field in required_fields) for r in alias_rows
                    )
                    if alias_all_zero and alias_games >= team_games:
                        continue
            if team_games and isinstance(games, int) and games >= team_games:
                # A full-season all-zero row can be a legitimate outcome.
                continue
            gaps.append(
                f"{team_name}: '{category}' has all-zero core fields across {games} games (parity risk)"
            )

    return gaps


def _to_float_number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        if match:
            try:
                return float(match.group(0))
            except Exception:
                return None
    return None


def _fourth_down_parity_gap(team_name: str, pbp_entry: dict | None, threshold: float = 1.0) -> str | None:
    if not isinstance(pbp_entry, dict):
        return None
    games = [g for g in (pbp_entry.get("games") or []) if isinstance(g, dict)]
    attempts = sum(int(g.get("4th_down_attempts") or 0) for g in games)
    conversions = sum(int(g.get("4th_down_conversions") or 0) for g in games)
    if attempts <= 0:
        return None
    pbp_pct = round((conversions / attempts) * 100.0, 1)

    rankings = ((pbp_entry.get("cfbstats") or {}).get("rankings") or {}).get("all") or {}
    cfb_row = rankings.get("fourth_down") if isinstance(rankings, dict) else {}
    cfb_value = _to_float_number((cfb_row or {}).get("value"))
    if cfb_value is None:
        return None
    cfb_pct = round(float(cfb_value), 1)
    delta = round(pbp_pct - cfb_pct, 1)
    if abs(delta) < threshold:
        return None
    return (
        f"{team_name}: 4th-down parity delta {delta:+.1f} pts "
        f"(PBP {conversions}/{attempts}={pbp_pct}% vs CFBStats {cfb_pct}%)"
    )


_CFBSTATS_VERIFY_RULES = {
    "scoring_offense": {"label": "Scoring Offense", "tolerance": 0.2},
    "scoring_defense": {"label": "Scoring Defense", "tolerance": 0.2},
    "total_offense": {"label": "Total Offense", "tolerance": 0.5},
    "total_defense": {"label": "Total Defense", "tolerance": 0.5},
    "rushing_offense": {"label": "Rushing Offense", "tolerance": 0.5},
    "rushing_defense": {"label": "Rushing Defense", "tolerance": 0.5},
    "passing_offense": {"label": "Passing Offense", "tolerance": 0.5},
    "passing_defense": {"label": "Passing Defense", "tolerance": 0.5},
    "scoring_margin": {"label": "Scoring Margin", "tolerance": 0.2},
    "turnover_margin": {"label": "Turnover Margin", "tolerance": 0.2},
    "red_zone": {"label": "Red Zone TD%", "tolerance": 0.2},
    "third_down": {"label": "3rd Down %", "tolerance": 0.2},
    "fourth_down": {"label": "4th Down %", "tolerance": 0.2},
    "penalties": {"label": "Penalty Yards/Game", "tolerance": 0.5},
    "sacks_offense": {"label": "Sacks Allowed", "tolerance": 0.0},
    "sacks_defense": {"label": "Sacks", "tolerance": 0.0},
    "tfl_offense": {"label": "TFL Allowed", "tolerance": 0.0},
    "tfl_defense": {"label": "TFL", "tolerance": 0.0},
    "explosives": {
        "label": "Explosive Plays",
        "status": "special_case",
        "note": "Definition mismatch: brief uses 15+ rush / 20+ pass, CFBStats uses 20+ for both.",
    },
    "time_of_possession": {
        "label": "Time of Possession",
        "status": "special_case",
        "note": "No canonical parser-derived season TOP is computed in this brief path yet.",
    },
}


def _derive_yard_splits_from_play_tree(play_tree: object, offense_abbr: object) -> dict[str, int | None]:
    offense_aliases = _abbr_set(offense_abbr)
    if not offense_aliases:
        return {"total": None, "rush": None, "pass": None}

    total = 0
    rush = 0
    pas = 0
    seen_total = seen_rush = seen_pass = False
    for play in _iter_play_tree_plays(play_tree):
        if play.get("is_no_play"):
            continue
        if str(play.get("offense") or "").upper() not in offense_aliases:
            continue
        if not _counts_toward_total_offense(play):
            continue
        yards = play.get("yards")
        if not isinstance(yards, (int, float)):
            continue
        desc_up = str(play.get("description") or "").upper()
        yards_i = int(yards)
        total += yards_i
        seen_total = True
        if "SACK" in desc_up:
            rush += yards_i
            seen_rush = True
        elif " PASS " in f" {desc_up} ":
            pas += yards_i
            seen_pass = True
        elif any(token in desc_up for token in (" RUSH ", "SCRAMBLE", "KNEEL")):
            rush += yards_i
            seen_rush = True

    return {
        "total": total if seen_total else None,
        "rush": rush if seen_rush else None,
        "pass": pas if seen_pass else None,
    }


def _derive_cfbstats_reference_metrics(pbp_entry: dict | None) -> dict[str, float | None]:
    if not isinstance(pbp_entry, dict):
        return {}
    games = [g for g in (pbp_entry.get("games") or []) if isinstance(g, dict)]
    if not games:
        return {}

    team_aliases = _abbr_set(pbp_entry.get("abbr_aliases") or pbp_entry.get("abbr"))
    game_count = len(games)
    pf_total = pa_total = 0.0
    total_off = total_def = 0.0
    rush_off = rush_def = 0.0
    pass_off = pass_def = 0.0
    total_off_games = total_def_games = 0
    rush_off_games = rush_def_games = 0
    pass_off_games = pass_def_games = 0
    third_att = third_conv = 0
    fourth_att = fourth_conv = 0
    penalty_yards = 0
    turnovers_gained = turnovers_lost = 0
    rz_trips = rz_tds = 0
    sacks_allowed = sacks_forced = 0
    tfl_allowed = tfl_forced = 0

    for g in games:
        pf = g.get("points_for")
        pa = g.get("points_against")
        if isinstance(pf, (int, float)):
            pf_total += float(pf)
        if isinstance(pa, (int, float)):
            pa_total += float(pa)

        own_total = g.get("total_yards")
        if not isinstance(own_total, (int, float)):
            own_total = _estimate_total_yards_from_play_tree(g.get("play_tree") or [], team_aliases)
        if isinstance(own_total, (int, float)):
            total_off += float(own_total)
            total_off_games += 1

        opp_abbr = g.get("opponent_abbr")
        opp_total = _estimate_total_yards_from_play_tree(g.get("play_tree") or [], opp_abbr)
        if isinstance(opp_total, (int, float)):
            total_def += float(opp_total)
            total_def_games += 1

        own_splits = _derive_yard_splits_from_play_tree(g.get("play_tree") or [], team_aliases)
        opp_splits = _derive_yard_splits_from_play_tree(g.get("play_tree") or [], opp_abbr)
        if isinstance(own_splits.get("rush"), (int, float)):
            rush_off += float(own_splits["rush"])
            rush_off_games += 1
        if isinstance(own_splits.get("pass"), (int, float)):
            pass_off += float(own_splits["pass"])
            pass_off_games += 1
        if isinstance(opp_splits.get("rush"), (int, float)):
            rush_def += float(opp_splits["rush"])
            rush_def_games += 1
        if isinstance(opp_splits.get("pass"), (int, float)):
            pass_def += float(opp_splits["pass"])
            pass_def_games += 1

        third_att += int(g.get("third_down_attempts") or 0)
        third_conv += int(g.get("third_down_conversions") or 0)
        fourth_att += int(g.get("4th_down_attempts") or 0)
        fourth_conv += int(g.get("4th_down_conversions") or 0)
        penalty_yards += int(g.get("penalty_yards") or 0)
        turnovers_gained += int(g.get("turnovers_gained") or 0)
        turnovers_lost += int(g.get("turnovers_lost") or 0)
        rz_trips += int(g.get("red_zone_trips") or 0)
        rz_tds += int(g.get("red_zone_tds") or 0)

        opp_aliases = _abbr_set(opp_abbr)
        for play in _iter_play_tree_plays(g.get("play_tree") or []):
            if play.get("is_no_play"):
                continue
            offense = str(play.get("offense") or "").upper()
            desc = str(play.get("description") or "").upper()
            yards = play.get("yards")
            if "SACK" in desc:
                if offense in team_aliases:
                    sacks_allowed += 1
                    tfl_allowed += 1
                elif offense in opp_aliases:
                    sacks_forced += 1
                    tfl_forced += 1
            elif isinstance(yards, (int, float)) and yards < 0 and "RUSH" in desc:
                if offense in team_aliases:
                    tfl_allowed += 1
                elif offense in opp_aliases:
                    tfl_forced += 1

    def _avg(total: float, n: int) -> float | None:
        return round(total / n, 1) if n else None

    def _pct(num: int, den: int) -> float | None:
        return round((num / den) * 100.0, 1) if den else None

    scoring_offense = _avg(pf_total, game_count)
    scoring_defense = _avg(pa_total, game_count)
    scoring_margin = round(scoring_offense - scoring_defense, 1) if scoring_offense is not None and scoring_defense is not None else None

    return {
        "scoring_offense": scoring_offense,
        "scoring_defense": scoring_defense,
        "total_offense": _avg(total_off, total_off_games),
        "total_defense": _avg(total_def, total_def_games),
        "rushing_offense": _avg(rush_off, rush_off_games),
        "rushing_defense": _avg(rush_def, rush_def_games),
        "passing_offense": _avg(pass_off, pass_off_games),
        "passing_defense": _avg(pass_def, pass_def_games),
        "scoring_margin": scoring_margin,
        "turnover_margin": float(turnovers_gained - turnovers_lost),
        "red_zone": _pct(rz_tds, rz_trips),
        "third_down": _pct(third_conv, third_att),
        "fourth_down": _pct(fourth_conv, fourth_att),
        "penalties": _avg(float(penalty_yards), game_count),
        "sacks_offense": float(sacks_allowed),
        "sacks_defense": float(sacks_forced),
        "tfl_offense": float(tfl_allowed),
        "tfl_defense": float(tfl_forced),
        "explosives": None,
        "time_of_possession": None,
    }


def _infer_verification_year(pbp_entry: dict | None) -> int | None:
    if not isinstance(pbp_entry, dict):
        return None
    for game in pbp_entry.get("games") or []:
        if not isinstance(game, dict):
            continue
        raw_date = str(game.get("date") or game.get("game_date") or "").strip()
        if not raw_date:
            continue
        try:
            return datetime.fromisoformat(raw_date).year
        except ValueError:
            continue
    return None


def _verify_cfbstats_metrics(team_name: str, pbp_entry: dict | None) -> dict:
    def _local_report() -> dict:
        rankings = (((pbp_entry or {}).get("cfbstats") or {}).get("rankings") or {}).get("all") or {}
        turnover_split = (((pbp_entry or {}).get("cfbstats") or {}).get("turnover_split") or {})
        xml_rollups = ((pbp_entry or {}).get("xml_rollups") or {})
        xml_tov = xml_rollups.get("turnovers") if isinstance(xml_rollups.get("turnovers"), dict) else {}
        derived = _derive_cfbstats_reference_metrics(pbp_entry)
        metrics = []
        summary = {"match": 0, "mismatch": 0, "missing_source": 0, "missing_derived": 0, "special_case": 0}

        for key, rule in _CFBSTATS_VERIFY_RULES.items():
            label = rule["label"]
            if key == "turnover_margin" and isinstance(xml_tov, dict) and xml_tov:
                gained = _to_float_number(xml_tov.get("turnovers_forced"))
                lost = _to_float_number(xml_tov.get("turnovers"))
                source_value = None if gained is None or lost is None else round(gained - lost, 1)
            elif key == "turnover_margin" and isinstance(turnover_split, dict):
                source_value = _to_float_number(turnover_split.get("margin"))
            else:
                source_value = _to_float_number((rankings.get(key) or {}).get("value")) if isinstance(rankings, dict) else None
            derived_value = derived.get(key)
            if rule.get("status") == "special_case":
                status = "special_case"
                delta = None
                summary[status] += 1
            elif source_value is None:
                status = "missing_source"
                delta = None
                summary[status] += 1
            elif derived_value is None:
                status = "missing_derived"
                delta = None
                summary[status] += 1
            else:
                delta = round(float(derived_value) - float(source_value), 1)
                status = "match" if abs(delta) <= float(rule.get("tolerance", 0.0)) else "mismatch"
                summary[status] += 1
            metrics.append(
                {
                    "key": key,
                    "label": label,
                    "status": status,
                    "derived": derived_value,
                    "source": source_value,
                    "delta": delta,
                    "tolerance": rule.get("tolerance"),
                    "note": rule.get("note"),
                }
            )

        summary["total"] = len(metrics)
        return {"summary": summary, "metrics": metrics}

    parser_payload = (pbp_entry or {}).get("_parser_bundle_payload")
    if isinstance(parser_payload, dict) and _upstream_verify_bundle_against_cfbstats is not None:
        parser_team_name = str(parser_payload.get("team_name") or team_name).strip()
        team_slug = slugify(parser_team_name)
        report = _upstream_verify_bundle_against_cfbstats(
            {team_slug: parser_payload},
            year=_infer_verification_year(pbp_entry) or datetime.now(timezone.utc).year,
        )
        teams = report.get("teams") or []
        team_report = teams[0] if teams else {}
        raw_metrics = team_report.get("metrics") or []
        key_map = {
            "red_zone_td_pct": "red_zone",
            "third_down_pct": "third_down",
            "fourth_down_pct": "fourth_down",
            "penalty_yards_pg": "penalties",
            "turnover_margin": "turnover_margin",
            "total_offense_ypg": "total_offense",
            "total_defense_ypg": "total_defense",
            "scoring_offense_ppg": "scoring_offense",
            "scoring_defense_ppg": "scoring_defense",
            "scoring_margin_pg": "scoring_margin",
            "rushing_offense_ypg": "rushing_offense",
            "rushing_defense_ypg": "rushing_defense",
            "passing_offense_ypg": "passing_offense",
            "passing_defense_ypg": "passing_defense",
            "sacks_allowed_pg": "sacks_offense",
            "sacks_defense_pg": "sacks_defense",
        }
        label_map = {
            "red_zone_td_pct": "Red Zone TD%",
            "third_down_pct": "3rd Down %",
            "fourth_down_pct": "4th Down %",
            "penalty_yards_pg": "Penalties",
            "turnover_margin": "Turnover Margin",
            "total_offense_ypg": "Total Offense",
            "total_defense_ypg": "Total Defense",
            "scoring_offense_ppg": "Scoring Offense",
            "scoring_defense_ppg": "Scoring Defense",
            "scoring_margin_pg": "Scoring Margin",
            "rushing_offense_ypg": "Rushing Offense",
            "rushing_defense_ypg": "Rushing Defense",
            "passing_offense_ypg": "Passing Offense",
            "passing_defense_ypg": "Passing Defense",
            "sacks_allowed_pg": "Sacks Allowed",
            "sacks_defense_pg": "Sacks",
        }
        metrics = []
        for metric in raw_metrics:
            raw_key = metric.get("metric")
            status = str(metric.get("status") or "")
            if status in {"missing_cfbstats_team", "invalid_cfbstats_value"}:
                status = "missing_source"
            elif status not in {"match", "mismatch", "special_case", "missing_source"}:
                status = "missing_derived"
            metrics.append(
                {
                    "key": key_map.get(raw_key, raw_key),
                    "label": label_map.get(raw_key, raw_key),
                    "status": status,
                    "derived": metric.get("bundle_value"),
                    "source": metric.get("cfbstats_value"),
                    "delta": metric.get("delta"),
                    "note": metric.get("note"),
                }
            )
        summary = {"match": 0, "mismatch": 0, "missing_source": 0, "missing_derived": 0, "special_case": 0}
        for metric in metrics:
            status = metric.get("status")
            if status in summary:
                summary[status] += 1
        summary["total"] = len(metrics)
        if summary["mismatch"]:
            mismatch_preview = ", ".join(
                f"{m['label']} ({m['delta']:+.1f})" for m in metrics if m["status"] == "mismatch"
            )
            print(f"[warn] CFBStats verification mismatches for {team_name}: {mismatch_preview}", file=sys.stderr)
        return {"summary": summary, "metrics": metrics}

    local_report = _local_report()
    metrics = local_report["metrics"]
    summary = local_report["summary"]

    if summary["mismatch"]:
        mismatch_preview = ", ".join(
            f"{m['label']} ({m['delta']:+.1f})" for m in metrics if m["status"] == "mismatch"
        )
        print(f"[warn] CFBStats verification mismatches for {team_name}: {mismatch_preview}", file=sys.stderr)

    return {"summary": summary, "metrics": metrics}


def get_team_pbp(pbp_teams: dict, team_name: str, school_slug: str) -> dict | None:
    if school_slug in pbp_teams:
        return pbp_teams[school_slug]

    slug = slugify(team_name)
    if slug in pbp_teams:
        return pbp_teams[slug]

    name_lower = team_name.lower()
    for _, val in pbp_teams.items():
        stored = (val.get("name") or "").lower()
        if name_lower in stored or stored in name_lower:
            return val

    return None


def _extract_pbp_stats(team_data: dict) -> dict:
    agg = team_data.get("aggregates", {})
    rankings = team_data.get("cfbstats", {}).get("rankings", {}).get("all", {})
    games = team_data.get("games", [])
    xml_stats = team_data.get("xml_stats") or {}
    xml_rollups = team_data.get("xml_rollups") or {}

    def rank(key: str) -> str:
        r = rankings.get(key, {})
        val = r.get("value", "")
        rnk = r.get("rank", "")
        if val != "" and rnk != "":
            return f"{val} (#{rnk})"
        return val or "N/A"

    last_games = sorted(games, key=lambda g: g.get("game_number", 0))[-5:]
    recent = []
    for g in last_games:
        pf = g.get("points_for")
        pa = g.get("points_against")
        opp = g.get("opponent", "?")
        date = g.get("date", "")
        if pf is not None and pa is not None:
            result = "W" if pf > pa else ("L" if pf < pa else "T")
            loc = "vs" if g.get("is_home", True) else "@"
            recent.append(f"{result} {pf}-{pa} {loc} {opp} ({date})")

    wins = losses = ties = 0
    pf_total = pa_total = 0.0
    decided_games = 0
    third_att = third_conv = 0
    fourth_att = fourth_conv = 0
    sacks_allowed = sacks_forced = 0
    tfl_allowed = tfl_forced = 0
    team_aliases = _abbr_set(team_data.get("abbr_aliases") or team_data.get("abbr"))
    for g in games:
        pf = g.get("points_for")
        pa = g.get("points_against")
        if isinstance(pf, (int, float)) and isinstance(pa, (int, float)):
            decided_games += 1
            pf_total += float(pf)
            pa_total += float(pa)
            if pf > pa:
                wins += 1
            elif pf < pa:
                losses += 1
            else:
                ties += 1
        third_att += int(g.get("third_down_attempts") or 0)
        third_conv += int(g.get("third_down_conversions") or 0)
        fourth_att += int(g.get("4th_down_attempts") or 0)
        fourth_conv += int(g.get("4th_down_conversions") or 0)
        opp_abbr = str(g.get("opponent_abbr") or "").upper()
        for play in _iter_play_tree_plays(g.get("play_tree") or []):
            if play.get("is_no_play"):
                continue
            offense = str(play.get("offense") or "").upper()
            desc = str(play.get("description") or "").upper()
            yards = play.get("yards")
            if "SACK" in desc:
                if offense in team_aliases:
                    sacks_allowed += 1
                elif offense == opp_abbr:
                    sacks_forced += 1
            if isinstance(yards, (int, float)) and yards < 0 and "RUSH" in desc:
                if offense in team_aliases:
                    tfl_allowed += 1
                elif offense == opp_abbr:
                    tfl_forced += 1

    record_fallback = f"{wins}-{losses}" + (f"-{ties}" if ties else "") if decided_games else "N/A"
    ppg_fallback = round(pf_total / decided_games, 1) if decided_games else "N/A"
    opp_ppg_fallback = round(pa_total / decided_games, 1) if decided_games else "N/A"

    record_val = agg.get("record", "N/A")
    ppg_val = agg.get("ppg", "N/A")
    opp_ppg_val = agg.get("opp_ppg", "N/A")
    if record_val in ("N/A", None, ""):
        record_val = record_fallback
    if ppg_val in ("N/A", None, ""):
        ppg_val = ppg_fallback
    if opp_ppg_val in ("N/A", None, ""):
        opp_ppg_val = opp_ppg_fallback

    third_down_text = "N/A"
    if third_att > 0:
        third_down_text = f"{third_conv}/{third_att} ({round((third_conv / third_att) * 100, 1)}%)"
    fourth_down_text = "N/A"
    if fourth_att > 0:
        fourth_down_text = f"{fourth_conv}/{fourth_att} ({round((fourth_conv / fourth_att) * 100, 1)}%)"

    def _best_xml_row(category: str) -> dict:
        cat = xml_stats.get(category) or {}
        if not isinstance(cat, dict) or not cat:
            return {}
        key = team_data.get("abbr")
        if key and isinstance(cat.get(key), dict):
            return cat.get(key) or {}
        _, row = max(
            cat.items(),
            key=lambda item: (
                item[1].get("games")
                if isinstance(item[1], dict) and isinstance(item[1].get("games"), int)
                else 0
            ),
        )
        return row if isinstance(row, dict) else {}

    xml_tov = (
        xml_rollups.get("turnovers")
        if isinstance(xml_rollups.get("turnovers"), dict) and xml_rollups.get("turnovers")
        else _best_xml_row("turnovers")
    )
    xml_pot = (
        xml_rollups.get("points_off_turnovers")
        if isinstance(xml_rollups.get("points_off_turnovers"), dict) and xml_rollups.get("points_off_turnovers")
        else _best_xml_row("points_off_turnovers")
    )
    xml_m8 = _best_xml_row("middle_eight")

    return {
        "record": record_val,
        "conf_record": agg.get("conf_record", "N/A"),
        "ppg": ppg_val,
        "opp_ppg": opp_ppg_val,
        "explosives_per_game": agg.get("explosives_per_game", "N/A"),
        "negative_plays_per_game": agg.get("negative_plays_per_game", "N/A"),
        "negative_plays_forced_per_game": agg.get("negative_plays_forced_per_game", "N/A"),
        "turnover_margin": agg.get("turnover_margin", "N/A"),
        "red_zone_td_pct": agg.get("red_zone_td_pct", "N/A"),
        "penalties_per_game": agg.get("penalties_per_game", "N/A"),
        "scoring_offense": rank("scoring_offense"),
        "scoring_defense": rank("scoring_defense"),
        "total_offense": rank("total_offense"),
        "total_defense": rank("total_defense"),
        "rushing_offense": rank("rushing_offense"),
        "rushing_defense": rank("rushing_defense"),
        "passing_offense": rank("passing_offense"),
        "passing_defense": rank("passing_defense"),
        "explosives_rank": rank("explosives"),
        "third_down": rank("third_down"),
        "third_down_derived": third_down_text,
        "fourth_down_derived": fourth_down_text,
        "red_zone_rank": rank("red_zone"),
        "turnover_rank": rank("turnover_margin"),
        "recent_results": recent,
        "color": team_data.get("color", "#888888"),
        "conference": team_data.get("conference", ""),
        "abbr": team_data.get("abbr", ""),
        "last3_turnovers_gained": xml_tov.get("last_n_turnovers_forced", "N/A"),
        "last3_turnovers_lost": xml_tov.get("last_n_turnovers", "N/A"),
        "last3_points_off_turnovers_for": xml_pot.get("last_3_points_off_turnovers", "N/A"),
        "last3_points_off_turnovers_against": xml_pot.get("last_3_points_off_turnovers_allowed", "N/A"),
        "last3_middle8_points_for": xml_m8.get("last_3_middle_eight_points", "N/A"),
        "last3_middle8_points_against": xml_m8.get("last_3_middle_eight_points_allowed", "N/A"),
        "last3_middle8_points_for_pg": xml_m8.get("last_3_middle_eight_points_pg", "N/A"),
        "last3_middle8_points_against_pg": xml_m8.get("last_3_middle_eight_points_allowed_pg", "N/A"),
        "last3_middle8_games": xml_m8.get("last_n_games", "N/A"),
        "last3_penalties_pg": _best_xml_row("penalties").get("last_3_total_penalties_pg", "N/A"),
        "sacks_allowed_derived_pg": round(sacks_allowed / decided_games, 1) if decided_games else "N/A",
        "sacks_forced_derived_pg": round(sacks_forced / decided_games, 1) if decided_games else "N/A",
        "tfl_allowed_derived_pg": round(tfl_allowed / decided_games, 1) if decided_games else "N/A",
        "tfl_forced_derived_pg": round(tfl_forced / decided_games, 1) if decided_games else "N/A",
    }


def _fetch_blitz_stats(team_slug: str, team_name: str | None = None) -> dict:
    """Fetch blitz season/last3 values from yr-data-api. Returns N/A on failure."""
    if not team_slug and not team_name:
        return {"blitz_pct": "N/A", "blitz_pct_last3": "N/A"}

    candidates = _candidate_team_ids(team_slug, team_name)

    out = {"blitz_pct": "N/A", "blitz_pct_last3": "N/A"}

    for scope_key, scope in (("blitz_pct", "season"), ("blitz_pct_last3", "last3")):
        text = _fetch_text_from_candidates(candidates, f"pff/blitz?scope={scope}&format=text")
        if text:
            out[scope_key] = text

    return out


def _fetch_negative_play_stats(team_slug: str, team_name: str | None = None) -> dict:
    """Fetch offensive/defensive negative plays (season + last3) from yr-data-api."""
    if not team_slug and not team_name:
        return {
            "negative_plays_pg_api": "N/A",
            "negative_plays_forced_pg_api": "N/A",
            "negative_plays_pg_last3_api": "N/A",
            "negative_plays_forced_pg_last3_api": "N/A",
        }

    candidates = _candidate_team_ids(team_slug, team_name)

    out = {
        "negative_plays_pg_api": "N/A",
        "negative_plays_forced_pg_api": "N/A",
        "negative_plays_pg_last3_api": "N/A",
        "negative_plays_forced_pg_last3_api": "N/A",
    }

    endpoint_specs = [
        ("negative_plays_pg_api", "pbp/negative-plays?scope=season&format=text"),
        ("negative_plays_forced_pg_api", "pbp/negative-plays-forced?scope=season&format=text"),
        ("negative_plays_pg_last3_api", "pbp/negative-plays?scope=last3&format=text"),
        ("negative_plays_forced_pg_last3_api", "pbp/negative-plays-forced?scope=last3&format=text"),
    ]

    for key, suffix in endpoint_specs:
        text = _fetch_text_from_candidates(candidates, suffix)
        if text:
            out[key] = text

    return out


def _fetch_pff_snapshot(team_slug: str, team_name: str | None = None) -> dict:
    """Fetch compact PFF metrics used in callout blocks."""
    if not team_slug and not team_name:
        return {
            "pff_plays_offense_pg": "N/A",
            "pff_plays_defense_pg": "N/A",
            "pff_missed_tackles_pg": "N/A",
            "pff_tfl_pg": "N/A",
            "pff_sacks_pg": "N/A",
            "pff_sacks_allowed_pg": "N/A",
            "pff_fmt_total": "N/A",
            "pff_fmt_pg": "N/A",
            "pff_avg_play_clock": "N/A",
            "pff_hurry_up_pct": "N/A",
            "pff_tempo_label": "N/A",
        }

    candidates = _candidate_team_ids(team_slug, team_name)

    out = {
        "pff_plays_offense_pg": "N/A",
        "pff_plays_defense_pg": "N/A",
        "pff_missed_tackles_pg": "N/A",
        "pff_tfl_pg": "N/A",
        "pff_sacks_pg": "N/A",
        "pff_sacks_allowed_pg": "N/A",
        "pff_fmt_total": "N/A",
        "pff_fmt_pg": "N/A",
        "pff_avg_play_clock": "N/A",
        "pff_hurry_up_pct": "N/A",
        "pff_tempo_label": "N/A",
    }

    def _try_fetch(suffix: str) -> str | None:
        return _fetch_text_from_candidates(candidates, suffix)

    plays = _try_fetch("pff/plays?side=both&format=text")
    if plays and "," in plays:
        off, deff = plays.split(",", 1)
        out["pff_plays_offense_pg"] = off.strip() or "N/A"
        out["pff_plays_defense_pg"] = deff.strip() or "N/A"

    tackling_pg = _try_fetch("pff/tackling-per-game?format=text")
    if tackling_pg:
        parts = [p.strip() for p in tackling_pg.split("\t")]
        if len(parts) >= 3:
            out["pff_missed_tackles_pg"] = parts[0] or "N/A"
            out["pff_tfl_pg"] = parts[1] or "N/A"
            out["pff_sacks_pg"] = parts[2] or "N/A"

    sacks_allowed = _try_fetch("pff/sacks-allowed?format=text")
    if sacks_allowed:
        out["pff_sacks_allowed_pg"] = sacks_allowed.strip()

    fmt = _try_fetch("pff/fmt?format=text")
    if fmt:
        parts = [p.strip() for p in fmt.split("\t")]
        if len(parts) >= 2:
            out["pff_fmt_total"] = parts[0] or "N/A"
            out["pff_fmt_pg"] = parts[1] or "N/A"

    play_clock = _try_fetch("pff/play-clock?format=text")
    if play_clock:
        parts = [p.strip() for p in play_clock.split("\t")]
        if len(parts) >= 1:
            out["pff_avg_play_clock"] = parts[0] or "N/A"
        if len(parts) >= 2:
            try:
                hurry_pct = round(float(parts[1]) * 100, 1)
                out["pff_hurry_up_pct"] = f"{hurry_pct}%"
            except (ValueError, TypeError):
                out["pff_hurry_up_pct"] = "N/A"
        try:
            avg = float(out["pff_avg_play_clock"])
            if avg >= 18:
                out["pff_tempo_label"] = "Deliberate"
            elif avg >= 14:
                out["pff_tempo_label"] = "Moderate"
            else:
                out["pff_tempo_label"] = "Fast"
        except (ValueError, TypeError):
            out["pff_tempo_label"] = "N/A"

    return out


def _fetch_live_enrichment(team_slug: str, team_name: str | None = None) -> dict:
    payload = {}
    payload.update(_fetch_blitz_stats(team_slug, team_name=team_name))
    payload.update(_fetch_negative_play_stats(team_slug, team_name=team_name))
    payload.update(_fetch_pff_snapshot(team_slug, team_name=team_name))
    return payload


def build_team_enrichment(team_slug: str, team_name: str | None = None) -> dict:
    data = _fetch_live_enrichment(team_slug, team_name=team_name)
    has_signal = any(v not in ("N/A", None, "") for k, v in data.items() if k in ENRICHMENT_KEYS)
    return {
        **data,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_source": "yr-data-api",
        "_status": "ok" if has_signal else "unavailable",
    }


def build_enrichment_payload(team_specs: list[dict]) -> dict:
    payload: dict = {}
    for spec in team_specs:
        slug = (spec.get("slug") or "").strip().lower()
        if not slug:
            continue
        payload[slug] = build_team_enrichment(slug, team_name=spec.get("display_name"))
    return payload


def load_enrichment_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_enrichment_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def merge_enrichment_payload(existing: dict, refreshed: dict) -> dict:
    """Preserve prior non-empty enrichment values when live refresh is unavailable."""
    merged: dict = dict(existing or {})
    for slug, incoming in (refreshed or {}).items():
        if not isinstance(incoming, dict):
            continue
        prior = merged.get(slug) if isinstance(merged.get(slug), dict) else {}
        out = dict(prior)
        for key, value in incoming.items():
            if key in ENRICHMENT_KEYS and value in ("N/A", None, ""):
                prior_value = prior.get(key)
                if prior_value not in ("N/A", None, ""):
                    out[key] = prior_value
                    continue
            out[key] = value
        has_signal = any(out.get(k) not in ("N/A", None, "") for k in ENRICHMENT_KEYS)
        out["_status"] = "ok" if has_signal else "unavailable"
        merged[slug] = out
    return merged


def compute_last_n_stats(games: list[dict], n: int = 3) -> dict:
    sorted_games = sorted(games, key=lambda g: g.get("game_number", 0), reverse=True)
    last_games = sorted_games[:n]
    actual_n = len(last_games)

    def sum_stat(key: str) -> int:
        return sum(g.get(key) or 0 for g in last_games)

    def avg_stat(key: str) -> float:
        if actual_n == 0:
            return 0
        return sum_stat(key) / actual_n

    def _def_plays_allowed_per_game() -> float:
        if actual_n == 0:
            return 0.0
        totals = []
        for g in last_games:
            count = 0
            for q in g.get("play_tree") or []:
                for drive in q.get("drives") or []:
                    for p in drive.get("plays") or []:
                        if p.get("is_no_play"):
                            continue
                        offense = (p.get("offense") or "").upper()
                        team_abbr = (g.get("opponent_abbr") or "").upper()
                        # Opponent offense snaps are our defense snaps faced.
                        if team_abbr and offense == team_abbr:
                            count += 1
            totals.append(count)
        return round(sum(totals) / actual_n, 1)

    explosives_total = 0
    explosive_passes_total = 0
    explosive_rushes_total = 0
    penalties_total = 0
    penalties_offense = 0
    penalties_defense = 0
    penalties_special_teams = 0

    for g in last_games:
        explosive_passes = g.get("explosive_passes") or 0
        explosive_rushes = g.get("explosive_rushes") or 0
        explosive_passes_total += explosive_passes
        explosive_rushes_total += explosive_rushes
        explosives = g.get("explosives")
        if explosives is None:
            explosives_total += explosive_passes + explosive_rushes
        else:
            explosives_total += explosives

        for p in g.get("penalty_details") or []:
            if not p.get("accepted"):
                continue
            penalties_total += 1
            side = (p.get("offense_or_defense") or "").lower()
            if side == "offense":
                penalties_offense += 1
            elif side == "defense":
                penalties_defense += 1
            elif side in {"special_teams", "special"}:
                penalties_special_teams += 1

    rz_trips = sum_stat("red_zone_trips")
    rz_tds = sum_stat("red_zone_tds")
    rz_fgs = sum_stat("red_zone_fgs")
    tight_rz_trips = sum_stat("tight_red_zone_trips")
    tight_rz_tds = sum_stat("tight_red_zone_tds")
    tight_rz_fgs = sum_stat("tight_red_zone_fgs")
    green_zone_trips = sum_stat("green_zone_trips")
    green_zone_tds = sum_stat("green_zone_tds")
    green_zone_fgs = sum_stat("green_zone_fgs")

    if actual_n == 0:
        return {
            "actual_n": 0,
            "required_n": n,
            "ppg": "N/A",
            "opp_ppg": "N/A",
            "explosives_per_game": "N/A",
            "negative_plays_per_game": "N/A",
            "negative_plays_forced_per_game": "N/A",
            "offense_plays_per_game": "N/A",
            "defense_plays_allowed_per_game": "N/A",
            "explosive_passes_per_game": "N/A",
            "explosive_rushes_per_game": "N/A",
            "rz_trips": "N/A",
            "rz_tds": "N/A",
            "rz_fgs": "N/A",
            "rz_td_pct": "N/A",
            "tight_rz_trips": "N/A",
            "tight_rz_tds": "N/A",
            "tight_rz_fgs": "N/A",
            "tight_rz_td_pct": "N/A",
            "green_zone_trips": "N/A",
            "green_zone_tds": "N/A",
            "green_zone_fgs": "N/A",
            "green_zone_success": "N/A",
            "turnover_margin": "N/A",
            "turnovers_gained": "N/A",
            "turnovers_lost": "N/A",
            "points_off_turnovers_for": "N/A",
            "points_off_turnovers_against": "N/A",
            "middle8_margin": "N/A",
            "middle8_points_for": "N/A",
            "middle8_points_against": "N/A",
            "fourth_down_attempts": "N/A",
            "fourth_down_conversions": "N/A",
            "penalties_per_game": "N/A",
            "penalties_offense": "N/A",
            "penalties_defense": "N/A",
            "penalties_special_teams": "N/A",
        }
    else:
        explosives_per_game = explosives_total / actual_n
        explosive_passes_per_game = explosive_passes_total / actual_n
        explosive_rushes_per_game = explosive_rushes_total / actual_n
        penalties_per_game = penalties_total / actual_n
        ppg = avg_stat("points_for")
        opp_ppg = avg_stat("points_against")

    green_zone_trips = sum_stat("green_zone_trips")
    green_zone_tds = sum_stat("green_zone_tds")
    green_zone_fgs = sum_stat("green_zone_fgs")

    return {
        "actual_n": actual_n,
        "required_n": n,
        "ppg": round(ppg, 1),
        "opp_ppg": round(opp_ppg, 1),
        "explosives_per_game": round(explosives_per_game, 1),
        "negative_plays_per_game": round(avg_stat("negative_plays"), 1),
        "negative_plays_forced_per_game": round(avg_stat("negative_plays_forced"), 1),
        "offense_plays_per_game": round(avg_stat("total_plays"), 1),
        "defense_plays_allowed_per_game": _def_plays_allowed_per_game(),
        "explosive_passes_per_game": round(explosive_passes_per_game, 1),
        "explosive_rushes_per_game": round(explosive_rushes_per_game, 1),
        "rz_trips": rz_trips,
        "rz_tds": rz_tds,
        "rz_fgs": rz_fgs,
        "rz_td_pct": round((rz_tds / rz_trips * 100), 1) if rz_trips else "N/A",
        "tight_rz_trips": tight_rz_trips,
        "tight_rz_tds": tight_rz_tds,
        "tight_rz_fgs": tight_rz_fgs,
        "tight_rz_td_pct": round((tight_rz_tds / tight_rz_trips * 100), 1)
        if tight_rz_trips
        else "N/A",
        "green_zone_trips": green_zone_trips,
        "green_zone_tds": green_zone_tds,
        "green_zone_fgs": green_zone_fgs,
        "green_zone_success": round(((green_zone_tds + green_zone_fgs) / green_zone_trips * 100), 1)
        if green_zone_trips
        else "N/A",
        "turnover_margin": sum_stat("turnovers_gained") - sum_stat("turnovers_lost"),
        "turnovers_gained": sum_stat("turnovers_gained"),
        "turnovers_lost": sum_stat("turnovers_lost"),
        "points_off_turnovers_for": sum_stat("points_off_turnovers_for"),
        "points_off_turnovers_against": sum_stat("points_off_turnovers_against"),
        "middle8_margin": sum_stat("middle8_points_for") - sum_stat("middle8_points_against"),
        "middle8_points_for": sum_stat("middle8_points_for"),
        "middle8_points_against": sum_stat("middle8_points_against"),
        "fourth_down_attempts": sum_stat("4th_down_attempts"),
        "fourth_down_conversions": sum_stat("4th_down_conversions"),
        "penalties_per_game": penalties_per_game,
        "penalties_offense": penalties_offense,
        "penalties_defense": penalties_defense,
        "penalties_special_teams": penalties_special_teams,
    }


def _turnover_reconciliation(pbp_entry: dict, game_recon: list[dict] | None = None) -> dict:
    games = pbp_entry.get("games") or []
    xml_rollups = pbp_entry.get("xml_rollups") or {}
    cfb_live = (pbp_entry.get("cfbstats") or {}).get("turnover_split")
    xml_tov = xml_rollups.get("turnovers") if isinstance(xml_rollups.get("turnovers"), dict) else {}
    xml_pot = (
        xml_rollups.get("points_off_turnovers")
        if isinstance(xml_rollups.get("points_off_turnovers"), dict)
        else {}
    )

    pbp_totals = {
        "gained": sum(int(g.get("turnovers_gained") or 0) for g in games if isinstance(g, dict)),
        "lost": sum(int(g.get("turnovers_lost") or 0) for g in games if isinstance(g, dict)),
        "int_gained": sum(int(g.get("interceptions_gained") or 0) for g in games if isinstance(g, dict)),
        "int_lost": sum(int(g.get("interceptions_lost") or 0) for g in games if isinstance(g, dict)),
        "fum_gained": sum(int(g.get("fumbles_gained") or 0) for g in games if isinstance(g, dict)),
        "fum_lost": sum(int(g.get("fumbles_lost") or 0) for g in games if isinstance(g, dict)),
        "pot_for": sum(int(g.get("points_off_turnovers_for") or 0) for g in games if isinstance(g, dict)),
        "pot_against": sum(int(g.get("points_off_turnovers_against") or 0) for g in games if isinstance(g, dict)),
        "post_to_drives": sum(len(g.get("post_turnover_drives") or []) for g in games if isinstance(g, dict)),
    }

    def _pick_int(primary: object, fallback: object) -> int:
        if isinstance(primary, (int, float)):
            return int(primary)
        if isinstance(fallback, (int, float)):
            return int(fallback)
        return 0

    # Use XML bundle totals as canonical reconciliation baseline; they are sourced
    # from per-game CFBStats rows and avoid live split drift.
    cfb_totals = {
        "gained": _pick_int(
            xml_tov.get("turnovers_forced"),
            cfb_live.get("turnovers_gained") if isinstance(cfb_live, dict) else None,
        ),
        "lost": _pick_int(
            xml_tov.get("turnovers"),
            cfb_live.get("turnovers_lost") if isinstance(cfb_live, dict) else None,
        ),
        "int_lost": _pick_int(
            xml_tov.get("interceptions"),
            cfb_live.get("interceptions_lost") if isinstance(cfb_live, dict) else None,
        ),
        "fum_lost": _pick_int(
            xml_tov.get("fumbles_lost"),
            cfb_live.get("fumbles_lost") if isinstance(cfb_live, dict) else None,
        ),
        "pot_for": _pick_int(xml_pot.get("points_off_turnovers"), None),
        "pot_against": _pick_int(xml_pot.get("points_off_turnovers_allowed"), None),
    }
    if isinstance(game_recon, list) and game_recon:
        cfb_from_games = {
            "gained": 0,
            "lost": 0,
            "int_gained": 0,
            "fum_gained": 0,
            "pot_for": 0,
            "pot_against": 0,
        }
        for row in game_recon:
            if not isinstance(row, dict):
                continue
            cfb = row.get("cfbstats")
            if not isinstance(cfb, dict):
                continue
            for key in cfb_from_games.keys():
                cfb_from_games[key] += int(cfb.get(key) or 0)
        cfb_totals["gained"] = int(cfb_from_games["gained"])
        cfb_totals["lost"] = int(cfb_from_games["lost"])
        cfb_totals["pot_for"] = int(cfb_from_games["pot_for"])
        cfb_totals["pot_against"] = int(cfb_from_games["pot_against"])

    deltas = {
        "gained": pbp_totals["gained"] - cfb_totals["gained"],
        "lost": pbp_totals["lost"] - cfb_totals["lost"],
        "int_lost": pbp_totals["int_lost"] - cfb_totals["int_lost"],
        "fum_lost": pbp_totals["fum_lost"] - cfb_totals["fum_lost"],
        "pot_for": pbp_totals["pot_for"] - cfb_totals["pot_for"],
        "pot_against": pbp_totals["pot_against"] - cfb_totals["pot_against"],
    }
    # Only turnover counts determine sync — POT deltas are expected because we
    # derive POT from the play tree while StatBroadcast pre-bakes values that
    # are internally inconsistent with their own play data.
    # Season-level cfb_totals uses int_lost/fum_lost (from XML rollups which
    # only provide the "lost" perspective); game-level uses int_gained/fum_gained
    # (from opponent-keyed XML rows inverted to team perspective).
    count_keys = {"gained", "lost", "int_lost", "fum_lost"}
    in_sync = all(deltas[k] == 0 for k in count_keys)
    return {"pbp": pbp_totals, "cfbstats": cfb_totals, "delta": deltas, "in_sync": in_sync}


def _turnover_game_reconciliation(pbp_entry: dict) -> list[dict]:
    games = [g for g in (pbp_entry.get("games") or []) if isinstance(g, dict)]
    xml_stats = pbp_entry.get("xml_stats") or {}
    tov_cat = xml_stats.get("turnovers") or {}
    pot_cat = xml_stats.get("points_off_turnovers") or {}
    if not isinstance(tov_cat, dict):
        tov_cat = {}
    if not isinstance(pot_cat, dict):
        pot_cat = {}

    report: list[dict] = []
    for game in games:
        opp = str(game.get("opponent_abbr") or "").upper()
        if not opp:
            continue
        tov_row = tov_cat.get(opp) if isinstance(tov_cat.get(opp), dict) else {}
        pot_row = pot_cat.get(opp) if isinstance(pot_cat.get(opp), dict) else {}
        if not tov_row and not pot_row:
            continue

        pbp = {
            "gained": int(game.get("turnovers_gained") or 0),
            "lost": int(game.get("turnovers_lost") or 0),
            "int_gained": int(game.get("interceptions_gained") or 0),
            "fum_gained": int(game.get("fumbles_gained") or 0),
            "pot_for": int(game.get("points_off_turnovers_for") or 0),
            "pot_against": int(game.get("points_off_turnovers_against") or 0),
        }
        # Opponent-keyed XML game rows are stored in opponent perspective.
        # Convert to team perspective for apples-to-apples reconciliation.
        cfb = {
            "gained": int(tov_row.get("turnovers") or 0),
            "lost": int(tov_row.get("turnovers_forced") or 0),
            "int_gained": int(tov_row.get("interceptions") or 0),
            "fum_gained": int(tov_row.get("fumbles_lost") or 0),
            "pot_for": int(pot_row.get("points_off_turnovers_allowed") or 0),
            "pot_against": int(pot_row.get("points_off_turnovers") or 0),
        }
        delta = {k: pbp[k] - cfb[k] for k in pbp.keys()}
        count_keys = {"gained", "lost", "int_gained", "fum_gained"}
        in_sync = all(delta[k] == 0 for k in count_keys)
        report.append(
            {
                "game_number": game.get("game_number"),
                "opponent_abbr": opp,
                "opponent": game.get("opponent"),
                "date": game.get("date"),
                "pbp": pbp,
                "cfbstats": cfb,
                "delta": delta,
                "in_sync": in_sync,
            }
        )
    return report


def _turnover_events_for_game(game: dict, team_aliases: set[str], opp_aliases: set[str]) -> list[dict]:
    events: list[dict] = []
    play_tree = game.get("play_tree")
    if not isinstance(play_tree, list):
        return events
    for quarter in play_tree:
        if not isinstance(quarter, dict):
            continue
        qnum = quarter.get("quarter")
        quarter_num = qnum if isinstance(qnum, int) else None
        for drive in quarter.get("drives") or []:
            if not isinstance(drive, dict):
                continue
            for play in drive.get("plays") or []:
                if not isinstance(play, dict) or play.get("is_no_play"):
                    continue
                if not play.get("is_turnover"):
                    continue
                desc = str(play.get("description") or "")
                desc_up = desc.upper()
                turnover_type = "INT" if "INTERCEPT" in desc_up else ("FUM" if "FUMBLE" in desc_up else "OTHER")
                offense = str(play.get("offense") or "").upper()
                offense_side = "team" if offense in team_aliases else ("opp" if offense in opp_aliases else None)
                recovery_side = _turnover_recovery_side(
                    desc_up, offense_side, turnover_type, team_aliases, opp_aliases
                )
                events.append(
                    {
                        "quarter": quarter_num,
                        "clock": play.get("clock") or "",
                        "offense": offense,
                        "description": desc,
                        "turnover_type": turnover_type,
                        "recovery_side": recovery_side or "?",
                    }
                )
    return events


def _print_turnover_debug(team_name: str, pbp_entry: dict, mismatch_games: list[dict], limit: int = 3) -> None:
    team_aliases = _abbr_set(pbp_entry.get("abbr_aliases") or pbp_entry.get("abbr"))
    for mismatch in mismatch_games[:limit]:
        game_num = mismatch.get("game_number")
        game = next(
            (
                g
                for g in (pbp_entry.get("games") or [])
                if isinstance(g, dict) and g.get("game_number") == game_num
            ),
            None,
        )
        if not isinstance(game, dict):
            continue
        opp = str(game.get("opponent_abbr") or "").upper()
        opp_aliases = _abbr_set([opp])
        if not opp_aliases:
            continue
        events = _turnover_events_for_game(game, team_aliases, opp_aliases)
        drives = [d for d in (game.get("post_turnover_drives") or []) if isinstance(d, dict)]
        print(
            f"[debug] TO recon {team_name} G{game_num} vs {opp} delta={mismatch.get('delta')}",
            file=sys.stderr,
        )
        if not events:
            print("[debug]   turnover_events: none", file=sys.stderr)
        else:
            for e in events[:8]:
                print(
                    "[debug]   turnover_event "
                    f"q={e.get('quarter')} t={e.get('clock')} off={e.get('offense')} "
                    f"type={e.get('turnover_type')} rec={e.get('recovery_side')} desc={e.get('description')}",
                    file=sys.stderr,
                )
        if not drives:
            print("[debug]   post_turnover_drives: none", file=sys.stderr)
        else:
            for d in drives[:8]:
                print(
                    "[debug]   post_turnover_drive "
                    f"q={d.get('quarter')} t={d.get('clock')} type={d.get('turnover_type')} "
                    f"rec={d.get('recovered_by')} result={d.get('drive_result')} pts={d.get('points_scored')} "
                    f"desc={d.get('turnover_description')}",
                    file=sys.stderr,
                )


def gather_team_data(
    pbp_teams: dict,
    team_name: str,
    season: int,
    last_n: int = 3,
    enrichment_by_slug: dict | None = None,
    allow_live_enrichment: bool = False,
) -> dict:
    _warn_upstream_import_fallback_once()
    school_slug = slugify(team_name)
    pbp_entry = get_team_pbp(pbp_teams, team_name, school_slug)
    if pbp_entry:
        conf, rankings = _fetch_live_rankings(team_name, school_slug, season)
        if conf:
            pbp_entry["conference"] = conf
        pbp_entry.setdefault("cfbstats", {})
        pbp_entry["cfbstats"]["rankings"] = {"all": {}, "conf": {}, "nonconf": {}}
        if rankings.get("all"):
            pbp_entry["cfbstats"]["rankings"] = rankings
        else:
            print(
                f"[warn] Live CFBStats rankings unavailable for {team_name} ({season}); rankings may render N/A",
                file=sys.stderr,
            )
        live_turnover_split = _fetch_live_turnover_split(team_name, school_slug, season)
        if live_turnover_split:
            pbp_entry["cfbstats"]["turnover_split"] = live_turnover_split
            pbp_entry.setdefault("aggregates", {})
            pbp_entry["aggregates"]["turnover_margin"] = live_turnover_split.get(
                "margin", pbp_entry["aggregates"].get("turnover_margin")
            )
    parity_gaps = _collect_parity_gaps(team_name, pbp_entry)
    fourth_down_gap = _fourth_down_parity_gap(team_name, pbp_entry)
    if fourth_down_gap:
        parity_gaps.append(fourth_down_gap)
    pbp_stats = _extract_pbp_stats(pbp_entry) if pbp_entry else {}
    seeded = (enrichment_by_slug or {}).get(school_slug) or {}
    if isinstance(seeded, dict):
        for key in ENRICHMENT_KEYS:
            value = seeded.get(key)
            if value not in (None, ""):
                pbp_stats[key] = value
    if allow_live_enrichment:
        live = _fetch_live_enrichment(school_slug, team_name=team_name)
        for key in ENRICHMENT_KEYS:
            value = live.get(key)
            if value not in (None, ""):
                pbp_stats[key] = value
    games = pbp_entry.get("games", []) if pbp_entry else []
    cfbstats_verification = _verify_cfbstats_metrics(team_name, pbp_entry) if pbp_entry else {"summary": {}, "metrics": []}
    turnover_game_recon = _turnover_game_reconciliation(pbp_entry) if pbp_entry else []
    turnover_recon = _turnover_reconciliation(pbp_entry, turnover_game_recon) if pbp_entry else {}
    if pbp_entry:
        pbp_entry["cfbstats_verification"] = cfbstats_verification
        pbp_entry["turnover_reconciliation"] = turnover_recon
        pbp_entry["turnover_game_reconciliation"] = turnover_game_recon
        if turnover_recon and not turnover_recon.get("in_sync", True):
            print(
                f"[warn] Turnover reconciliation mismatch for {team_name}: "
                f"{turnover_recon.get('delta')}",
                file=sys.stderr,
            )
        mismatch_games = [g for g in turnover_game_recon if not g.get("in_sync")]
        if mismatch_games:
            sample = mismatch_games[:3]
            sample_text = ", ".join(
                f"G{g.get('game_number')} {g.get('opponent_abbr')} {g.get('delta')}" for g in sample
            )
            print(
                f"[warn] Turnover game mismatches for {team_name}: {sample_text}",
                file=sys.stderr,
            )
            debug_flag = str(os.getenv("GAME_PREP_TURNOVER_DEBUG") or "").strip().lower()
            if debug_flag in {"1", "true", "yes", "on"}:
                _print_turnover_debug(team_name, pbp_entry, mismatch_games, limit=3)
        if fourth_down_gap:
            print(f"[warn] {fourth_down_gap}", file=sys.stderr)
    if games:
        offense_plays_pg = round(sum((g.get("total_plays") or 0) for g in games) / len(games), 1)
        defense_counts = []
        for g in games:
            count = 0
            opp_abbr = (g.get("opponent_abbr") or "").upper()
            for q in g.get("play_tree") or []:
                for drive in q.get("drives") or []:
                    for p in drive.get("plays") or []:
                        if p.get("is_no_play"):
                            continue
                        if opp_abbr and (p.get("offense") or "").upper() == opp_abbr:
                            count += 1
            defense_counts.append(count)
        pbp_stats["offense_plays_per_game"] = offense_plays_pg
        pbp_stats["defense_plays_allowed_per_game"] = round(sum(defense_counts) / len(defense_counts), 1) if defense_counts else "N/A"
    last_n_stats = compute_last_n_stats(games, last_n)
    # Keep turnover/points-off-turnover L3 metrics parser-derived from game-level rollups.
    # XML alias rows can overstate last-3 aggregates when multiple abbreviations are present.
    if isinstance(pbp_stats.get("last3_middle8_points_for"), (int, float)):
        last_n_stats["middle8_points_for"] = int(pbp_stats["last3_middle8_points_for"])
    if isinstance(pbp_stats.get("last3_middle8_points_against"), (int, float)):
        last_n_stats["middle8_points_against"] = int(pbp_stats["last3_middle8_points_against"])
    needs_m8_for = (
        not isinstance(last_n_stats.get("middle8_points_for"), (int, float))
        or last_n_stats.get("middle8_points_for") == 0
    )
    if needs_m8_for and isinstance(pbp_stats.get("last3_middle8_points_for_pg"), (int, float)):
        n_games = (
            int(pbp_stats["last3_middle8_games"])
            if isinstance(pbp_stats.get("last3_middle8_games"), (int, float))
            else int(last_n_stats.get("actual_n", 3) or 3)
        )
        last_n_stats["middle8_points_for"] = int(round(float(pbp_stats["last3_middle8_points_for_pg"]) * n_games))
    needs_m8_against = (
        not isinstance(last_n_stats.get("middle8_points_against"), (int, float))
        or last_n_stats.get("middle8_points_against") == 0
    )
    if needs_m8_against and isinstance(pbp_stats.get("last3_middle8_points_against_pg"), (int, float)):
        n_games = (
            int(pbp_stats["last3_middle8_games"])
            if isinstance(pbp_stats.get("last3_middle8_games"), (int, float))
            else int(last_n_stats.get("actual_n", 3) or 3)
        )
        last_n_stats["middle8_points_against"] = int(
            round(float(pbp_stats["last3_middle8_points_against_pg"]) * n_games)
        )
    if isinstance(last_n_stats.get("middle8_points_for"), (int, float)) and isinstance(
        last_n_stats.get("middle8_points_against"), (int, float)
    ):
        last_n_stats["middle8_margin"] = int(last_n_stats["middle8_points_for"]) - int(
            last_n_stats["middle8_points_against"]
        )
    if isinstance(pbp_stats.get("last3_penalties_pg"), (int, float)):
        last_n_stats["penalties_per_game"] = float(pbp_stats["last3_penalties_pg"])

    conference = pbp_stats.get("conference", "")

    return {
        "display_name": team_name,
        "school_name": team_name,
        "slug": school_slug,
        "conference": conference,
        "coaches": {
            "head_coach": "N/A",
            "oc": "N/A",
            "oc_title": "",
            "dc": "N/A",
            "dc_title": "",
            "play_caller": None,
            "play_caller_title": None,
        },
        "full_staff": [],
        "stats": pbp_stats,
        "last_n": last_n_stats,
        "turnover_reconciliation": turnover_recon,
        "turnover_game_reconciliation": turnover_game_recon,
        "cfbstats_verification": cfbstats_verification,
        "pbp_entry": pbp_entry,
        "parity_gaps": parity_gaps,
        "has_pbp": pbp_entry is not None,
        "has_coaches": False,
    }


def fetch_ncaa_scoreboard(year: int, week: int) -> list[dict]:
    url = NCAA_SCOREBOARD.format(year=year, week=week)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return [g["game"] for g in data.get("games", []) if "game" in g]
    except Exception as e:
        print(f"[warn] NCAA scoreboard unavailable: {e}", file=sys.stderr)
        return []


def find_ncaa_game(games: list[dict], slug1: str, slug2: str) -> dict | None:
    s1, s2 = slug1.lower(), slug2.lower()
    for g in games:
        away_seo = (g.get("away") or {}).get("names", {}).get("seo", "")
        home_seo = (g.get("home") or {}).get("names", {}).get("seo", "")
        if {away_seo, home_seo} & {s1, s2}:
            return g
    return None
