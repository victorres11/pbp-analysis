from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
PBP_JSON = ROOT_DIR / "data.json"
MATCHUPS_DIR = ROOT_DIR / "matchups"
OUTPUT_DIR = ROOT_DIR / "outputs" / "game_prep_brief"

NCAA_SCOREBOARD = (
    "https://data.ncaa.com/casablanca/scoreboard/football/fbs/{year}/{week:02d}/scoreboard.json"
)

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


def slugify(name: str) -> str:
    lower = name.strip().lower()
    if lower in SLUG_ALIASES:
        return SLUG_ALIASES[lower]
    return re.sub(r"[^a-z0-9]+", "-", lower).strip("-")


def _deep_merge(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, val in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def load_pbp_data(matchup_slug: str | None = None) -> dict:
    base: dict = {}
    if PBP_JSON.exists():
        with open(PBP_JSON) as f:
            raw = json.load(f)
        base = raw.get("teams", {})

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

    def defensive_plays_allowed(game: dict, team_abbr: str) -> int:
        direct = game.get("defensive_plays_allowed")
        if isinstance(direct, (int, float)):
            return int(direct)

        play_tree = game.get("play_tree") or []
        if not isinstance(play_tree, list):
            return 0

        total = 0
        for quarter in play_tree:
            for drive in ((quarter or {}).get("drives") or []):
                for play in ((drive or {}).get("plays") or []):
                    if not isinstance(play, dict):
                        continue
                    offense = str(play.get("offense") or "")
                    if not offense or offense == team_abbr:
                        continue
                    if play.get("is_no_play"):
                        continue
                    total += 1
        return total

    games_count = len(games)
    offensive_plays_total = sum(int(g.get("total_plays") or 0) for g in games)
    team_abbr = str(team_data.get("abbr") or "")
    defensive_plays_allowed_total = sum(defensive_plays_allowed(g, team_abbr) for g in games)
    offensive_plays_per_game = round(offensive_plays_total / games_count, 1) if games_count else 0.0
    defensive_plays_allowed_per_game = round(defensive_plays_allowed_total / games_count, 1) if games_count else 0.0

    return {
        "record": agg.get("record", "N/A"),
        "conf_record": agg.get("conf_record", "N/A"),
        "ppg": agg.get("ppg", "N/A"),
        "opp_ppg": agg.get("opp_ppg", "N/A"),
        "explosives_per_game": agg.get("explosives_per_game", "N/A"),
        "turnover_margin": agg.get("turnover_margin", "N/A"),
        "red_zone_td_pct": agg.get("red_zone_td_pct", "N/A"),
        "penalties_per_game": agg.get("penalties_per_game", "N/A"),
        "offensive_plays_per_game": offensive_plays_per_game,
        "defensive_plays_allowed_per_game": defensive_plays_allowed_per_game,
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
        "red_zone_rank": rank("red_zone"),
        "turnover_rank": rank("turnover_margin"),
        "recent_results": recent,
        "color": team_data.get("color", "#888888"),
        "conference": team_data.get("conference", ""),
        "abbr": team_data.get("abbr", ""),
    }


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

    explosives_total = 0
    explosive_passes_total = 0
    explosive_rushes_total = 0
    penalties_total = 0
    penalties_offense = 0
    penalties_defense = 0
    penalties_special_teams = 0

    def defensive_plays_allowed(game: dict, team_abbr: str) -> int:
        direct = game.get("defensive_plays_allowed")
        if isinstance(direct, (int, float)):
            return int(direct)

        play_tree = game.get("play_tree") or []
        if not isinstance(play_tree, list):
            return 0

        total = 0
        for quarter in play_tree:
            drives = (quarter or {}).get("drives") or []
            for drive in drives:
                for play in (drive or {}).get("plays") or []:
                    if not isinstance(play, dict):
                        continue
                    offense = str(play.get("offense") or "")
                    if not offense or offense == team_abbr:
                        continue
                    if play.get("is_no_play"):
                        continue
                    total += 1
        return total

    offensive_plays_total = 0
    defensive_plays_allowed_total = 0

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

        offensive_plays_total += int(g.get("total_plays") or 0)
        team_abbr = str(g.get("team") or g.get("abbr") or "")
        if not team_abbr:
            # Try to infer from offense in first valid play if team marker isn't present.
            for quarter in (g.get("play_tree") or []):
                for drive in ((quarter or {}).get("drives") or []):
                    for play in ((drive or {}).get("plays") or []):
                        offense = str((play or {}).get("offense") or "")
                        if offense:
                            team_abbr = offense
                            break
                    if team_abbr:
                        break
                if team_abbr:
                    break
        defensive_plays_allowed_total += defensive_plays_allowed(g, team_abbr)

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
    tight_rz_trips = sum_stat("tight_red_zone_trips")
    tight_rz_tds = sum_stat("tight_red_zone_tds")

    if actual_n == 0:
        explosives_per_game = 0
        explosive_passes_per_game = 0
        explosive_rushes_per_game = 0
        penalties_per_game = 0
        offensive_plays_per_game = 0
        defensive_plays_allowed_per_game = 0
        ppg = 0
        opp_ppg = 0
    else:
        explosives_per_game = explosives_total / actual_n
        explosive_passes_per_game = explosive_passes_total / actual_n
        explosive_rushes_per_game = explosive_rushes_total / actual_n
        penalties_per_game = penalties_total / actual_n
        offensive_plays_per_game = offensive_plays_total / actual_n
        defensive_plays_allowed_per_game = defensive_plays_allowed_total / actual_n
        ppg = avg_stat("points_for")
        opp_ppg = avg_stat("points_against")

    return {
        "actual_n": actual_n,
        "required_n": n,
        "ppg": round(ppg, 1),
        "opp_ppg": round(opp_ppg, 1),
        "explosives_per_game": round(explosives_per_game, 1),
        "explosive_passes_per_game": round(explosive_passes_per_game, 1),
        "explosive_rushes_per_game": round(explosive_rushes_per_game, 1),
        "rz_trips": rz_trips,
        "rz_tds": rz_tds,
        "rz_td_pct": round((rz_tds / rz_trips * 100), 1) if rz_trips else 0,
        "tight_rz_trips": tight_rz_trips,
        "tight_rz_tds": tight_rz_tds,
        "tight_rz_td_pct": round((tight_rz_tds / tight_rz_trips * 100), 1)
        if tight_rz_trips
        else 0,
        "green_zone_trips": sum_stat("green_zone_trips"),
        "green_zone_tds": sum_stat("green_zone_tds"),
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
        "offensive_plays_per_game": round(offensive_plays_per_game, 1),
        "defensive_plays_allowed_per_game": round(defensive_plays_allowed_per_game, 1),
    }


def gather_team_data(
    pbp_teams: dict,
    team_name: str,
    season: int,
    last_n: int = 3,
) -> dict:
    school_slug = slugify(team_name)
    pbp_entry = get_team_pbp(pbp_teams, team_name, school_slug)
    pbp_stats = _extract_pbp_stats(pbp_entry) if pbp_entry else {}
    games = pbp_entry.get("games", []) if pbp_entry else []
    last_n_stats = compute_last_n_stats(games, last_n)

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
        "pbp_entry": pbp_entry,
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
