from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
import urllib.parse
import time
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
)


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


def _rollup_game_from_play_tree(play_tree: object, team_abbr: str | None, opp_abbr: str | None) -> dict:
    explosive_passes = 0
    explosive_rushes = 0
    negative_plays = 0
    negative_plays_forced = 0
    turnovers_lost = 0
    turnovers_gained = 0

    team = (team_abbr or "").upper()
    opp = (opp_abbr or "").upper()
    for play in _iter_play_tree_plays(play_tree):
        if play.get("is_no_play"):
            continue
        offense = (play.get("offense") or "").upper()
        yards = play.get("yards")
        desc = (play.get("description") or "").upper()

        if offense == team:
            if isinstance(yards, (int, float)) and yards < 0:
                negative_plays += 1
            if isinstance(yards, (int, float)) and yards >= 20 and "PASS" in desc:
                explosive_passes += 1
            if isinstance(yards, (int, float)) and yards >= 15 and "RUSH" in desc:
                explosive_rushes += 1
            if play.get("is_turnover"):
                turnovers_lost += 1
        elif offense == opp:
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


def _estimate_total_yards_from_play_tree(play_tree: object, team_abbr: str | None) -> int | None:
    team = (team_abbr or "").upper()
    if not team:
        return None
    total = 0
    seen = False
    for play in _iter_play_tree_plays(play_tree):
        if play.get("is_no_play"):
            continue
        if str(play.get("offense") or "").upper() != team:
            continue
        yards = play.get("yards")
        if isinstance(yards, (int, float)):
            total += int(yards)
            seen = True
    return total if seen else None


def _estimate_points_from_play_tree(play_tree: object, team_abbr: str | None, opp_abbr: str | None) -> tuple[int | None, int | None]:
    team = (team_abbr or "").upper()
    opp = (opp_abbr or "").upper()
    if not team or not opp:
        return None, None

    points = {team: 0, opp: 0}
    pending_td_for: str | None = None

    for play in _iter_play_tree_plays(play_tree):
        offense = (play.get("offense") or "").upper()
        desc = (play.get("description") or "").upper()
        if offense not in points:
            continue

        if "TOUCHDOWN" in desc:
            points[offense] += 6
            pending_td_for = offense
            continue
        if "FIELD GOAL" in desc and "GOOD" in desc:
            points[offense] += 3
            pending_td_for = None
            continue
        if "SAFETY" in desc:
            defense = opp if offense == team else team
            points[defense] += 2
            pending_td_for = None
            continue

        if pending_td_for:
            if "2-POINT" in desc and ("GOOD" in desc or "SUCCESS" in desc):
                points[pending_td_for] += 2
                pending_td_for = None
                continue
            if ("PAT" in desc or "KICK ATTEMPT" in desc) and "GOOD" in desc:
                points[pending_td_for] += 1
                pending_td_for = None
                continue
            if "NO GOOD" in desc or "FAILED" in desc:
                pending_td_for = None

    return points[team], points[opp]


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


def _yards_to_goal_from_spot(spot: object, offense_abbr: str, opp_abbr: str) -> int | None:
    text = str(spot or "").strip().upper()
    if not text:
        return None
    if text == "50":
        return 50
    m = re.search(r"(\d{1,2})$", text)
    if not m:
        return None
    yard = int(m.group(1))
    offense_abbr = (offense_abbr or "").upper()
    opp_abbr = (opp_abbr or "").upper()
    if opp_abbr and opp_abbr in text:
        return yard
    if offense_abbr and offense_abbr in text:
        return 100 - yard
    return yard if yard <= 50 else 100 - yard


def _derive_game_detail_stats(play_tree: object, team_abbr: str | None, opp_abbr: str | None) -> dict:
    team = (team_abbr or "").upper()
    opp = (opp_abbr or "").upper()
    if not team or not opp:
        return {}

    third_att = third_conv = 0
    fourth_att = fourth_conv = 0
    penalty_count = penalty_yards = 0
    penalties_off = penalties_def = penalties_st = 0
    punts = punt_yards = punts_inside_20 = punt_touchbacks = punt_long = 0
    punt_returns = punt_return_yards = punt_return_long = punt_return_20_plus = 0
    kick_returns = kick_return_yards = kick_return_long = kick_return_30_plus = 0
    rz_trips = rz_tds = rz_fgs = 0
    trz_trips = trz_tds = trz_fgs = 0
    gz_trips = gz_tds = gz_fgs = gz_failed = 0
    for quarter in play_tree or []:
        if not isinstance(quarter, dict):
            continue
        for drive in quarter.get("drives") or []:
            if not isinstance(drive, dict):
                continue
            drive_rz = drive_trz = drive_gz = False
            drive_td = drive_fg = False
            for play in drive.get("plays") or []:
                if not isinstance(play, dict) or play.get("is_no_play"):
                    continue
                desc = str(play.get("description") or "")
                desc_up = desc.upper()
                offense = str(play.get("offense") or "").upper()
                down = _parse_down(play.get("down_distance"))

                if offense == team and play.get("is_scrimmage_play"):
                    ytg = _yards_to_goal_from_spot(play.get("spot"), team, opp)
                    if isinstance(ytg, int):
                        if ytg <= 40:
                            drive_gz = True
                        if ytg <= 20:
                            drive_rz = True
                        if ytg <= 10:
                            drive_trz = True
                    if "TOUCHDOWN" in desc_up:
                        drive_td = True
                    if "FIELD GOAL" in desc_up and "GOOD" in desc_up:
                        drive_fg = True

                if offense == team and down in (3, 4):
                    if down == 3:
                        third_att += 1
                    else:
                        fourth_att += 1
                    if "1ST DOWN" in desc_up or "TOUCHDOWN" in desc_up:
                        if down == 3:
                            third_conv += 1
                        else:
                            fourth_conv += 1

                if "PENALTY" in desc_up:
                    penalty_count += 1
                    y = _parse_int(r"(\d+)\s*yards?", desc) or 0
                    penalty_yards += y
                    if offense == team:
                        penalties_off += 1
                    elif offense == opp:
                        penalties_def += 1
                    else:
                        penalties_st += 1

                if offense == team and " PUNT " in f" {desc_up} ":
                    py = _parse_int(r"punt\s+(\d+)\s+yards?", desc) or 0
                    punts += 1
                    punt_yards += py
                    punt_long = max(punt_long, py)
                    if "TOUCHBACK" in desc_up:
                        punt_touchbacks += 1
                    dest = _parse_int(r"to the [A-Z]{2,4}(\d{1,2})", desc)
                    if dest is not None and 0 <= dest <= 20:
                        punts_inside_20 += 1
                    ret = _parse_int(r"return(?:ed)?\s+(\d+)\s+yards?", desc) or 0
                    if ret > 0:
                        punt_returns += 1
                        punt_return_yards += ret
                        punt_return_long = max(punt_return_long, ret)
                        if ret >= 20:
                            punt_return_20_plus += 1

                if offense == opp and " KICKOFF " in f" {desc_up} " and "RETURN" in desc_up:
                    kret = _parse_int(r"return(?:ed)?\s+(\d+)\s+yards?", desc) or 0
                    if kret > 0:
                        kick_returns += 1
                        kick_return_yards += kret
                        kick_return_long = max(kick_return_long, kret)
                        if kret >= 30:
                            kick_return_30_plus += 1

            if drive_gz:
                gz_trips += 1
                if drive_td:
                    gz_tds += 1
                elif drive_fg:
                    gz_fgs += 1
                else:
                    gz_failed += 1
            if drive_rz:
                rz_trips += 1
                if drive_td:
                    rz_tds += 1
                elif drive_fg:
                    rz_fgs += 1
            if drive_trz:
                trz_trips += 1
                if drive_td:
                    trz_tds += 1
                elif drive_fg:
                    trz_fgs += 1

    special_teams = {
        "punts": punts,
        "punt_yards": punt_yards,
        "punt_long": punt_long,
        "punts_inside_20": punts_inside_20,
        "punt_touchbacks": punt_touchbacks,
        "punt_returns": punt_returns,
        "punt_return_yards": punt_return_yards,
        "punt_return_long": punt_return_long,
        "punt_return_20_plus": punt_return_20_plus,
        "kickoff_returns": kick_returns,
        "kickoff_return_yards": kick_return_yards,
        "kickoff_return_long": kick_return_long,
        "kick_return_30_plus": kick_return_30_plus,
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
        "special_teams": special_teams,
    }


def _convert_xml_bundle_team(slug: str, payload: dict) -> dict:
    stats = payload.get("stats") or {}
    home_abbr = _bundle_home_abbr(stats)

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

    week_to_is_home: dict[int, bool | None] = {}
    for g in payload.get("games") or []:
        if not isinstance(g, dict):
            continue
        week = g.get("week")
        if isinstance(week, int):
            raw_home = g.get("is_home")
            week_to_is_home[week] = raw_home if isinstance(raw_home, bool) else None

    schedule_games_out: list[dict] = []
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
    turnovers = tov.get("turnovers")
    turnovers_forced = tov.get("turnovers_forced")
    games_out: list[dict] = []
    for idx, g in enumerate(payload.get("games") or [], start=1):
        if not isinstance(g, dict):
            continue
        opp_abbr = g.get("opponent_abbr") or g.get("opponent")
        play_tree = g.get("play_tree") if isinstance(g.get("play_tree"), list) else []
        game_rollup = _rollup_game_from_play_tree(play_tree, home_abbr, opp_abbr)
        game_detail = _derive_game_detail_stats(play_tree, home_abbr, opp_abbr)
        estimated_pf, estimated_pa = _estimate_points_from_play_tree(play_tree, home_abbr, opp_abbr)
        raw_pf = g.get("points_for")
        raw_pa = g.get("points_against")
        points_for = estimated_pf if isinstance(estimated_pf, int) else raw_pf
        points_against = estimated_pa if isinstance(estimated_pa, int) else raw_pa
        total_plays = g.get("total_plays")
        if not isinstance(total_plays, int):
            total_plays = sum(
                1
                for play in _iter_play_tree_plays(play_tree)
                if not play.get("is_no_play") and play.get("is_scrimmage_play")
            )
        total_yards = _estimate_total_yards_from_play_tree(play_tree, home_abbr)

        game = {
            "game_number": g.get("game_number") if isinstance(g.get("game_number"), int) else idx,
            "week": g.get("week"),
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
        games_out.append(game)

    return {
        "name": payload.get("team_name") or slug.replace("-", " ").title(),
        "abbr": home_abbr or slug[:4].upper(),
        "conference": "",
        "color": "#888888",
        "cfbstats": {"rankings": {"all": {}, "conf": {}, "nonconf": {}}},
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
    for slug, payload in raw.items():
        if isinstance(payload, dict):
            out[slug] = _convert_xml_bundle_team(slug, payload)
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
            gaps.append(
                f"{team_name}: '{category}' has all-zero core fields across {games} games (parity risk)"
            )

    return gaps


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
        team_abbr = str(team_data.get("abbr") or "").upper()
        opp_abbr = str(g.get("opponent_abbr") or "").upper()
        for play in _iter_play_tree_plays(g.get("play_tree") or []):
            if play.get("is_no_play"):
                continue
            offense = str(play.get("offense") or "").upper()
            desc = str(play.get("description") or "").upper()
            yards = play.get("yards")
            if "SACK" in desc:
                if offense == team_abbr:
                    sacks_allowed += 1
                elif offense == opp_abbr:
                    sacks_forced += 1
            if isinstance(yards, (int, float)) and yards < 0 and "RUSH" in desc:
                if offense == team_abbr:
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

    xml_tov = _best_xml_row("turnovers")
    xml_pot = _best_xml_row("points_off_turnovers")
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
    tight_rz_trips = sum_stat("tight_red_zone_trips")
    tight_rz_tds = sum_stat("tight_red_zone_tds")

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
            "rz_td_pct": "N/A",
            "tight_rz_trips": "N/A",
            "tight_rz_tds": "N/A",
            "tight_rz_td_pct": "N/A",
            "green_zone_trips": "N/A",
            "green_zone_tds": "N/A",
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
        "rz_td_pct": round((rz_tds / rz_trips * 100), 1) if rz_trips else "N/A",
        "tight_rz_trips": tight_rz_trips,
        "tight_rz_tds": tight_rz_tds,
        "tight_rz_td_pct": round((tight_rz_tds / tight_rz_trips * 100), 1)
        if tight_rz_trips
        else "N/A",
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
    }


def gather_team_data(
    pbp_teams: dict,
    team_name: str,
    season: int,
    last_n: int = 3,
    enrichment_by_slug: dict | None = None,
    allow_live_enrichment: bool = False,
) -> dict:
    school_slug = slugify(team_name)
    pbp_entry = get_team_pbp(pbp_teams, team_name, school_slug)
    parity_gaps = _collect_parity_gaps(team_name, pbp_entry)
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
    # Prefer XML bundle last-3 aggregates when available; per-game mirrors can be incomplete.
    if isinstance(pbp_stats.get("last3_turnovers_gained"), (int, float)) and isinstance(
        pbp_stats.get("last3_turnovers_lost"), (int, float)
    ):
        last_n_stats["turnovers_gained"] = int(pbp_stats["last3_turnovers_gained"])
        last_n_stats["turnovers_lost"] = int(pbp_stats["last3_turnovers_lost"])
        last_n_stats["turnover_margin"] = int(pbp_stats["last3_turnovers_gained"]) - int(
            pbp_stats["last3_turnovers_lost"]
        )
    if isinstance(pbp_stats.get("last3_points_off_turnovers_for"), (int, float)):
        last_n_stats["points_off_turnovers_for"] = int(pbp_stats["last3_points_off_turnovers_for"])
    if isinstance(pbp_stats.get("last3_points_off_turnovers_against"), (int, float)):
        last_n_stats["points_off_turnovers_against"] = int(
            pbp_stats["last3_points_off_turnovers_against"]
        )
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
