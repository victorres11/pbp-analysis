from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .published_artifacts import (
    fetch_published_artifact_json,
    published_artifact_download_url,
    published_artifact_release_url,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
PBP_JSON = ROOT_DIR / "data.json"
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

ENRICHMENT_PROVIDER_KEYS = {
    "blitz": (
        "blitz_pct",
        "blitz_pct_last3",
    ),
    "negative_plays": (
        "negative_plays_pg_api",
        "negative_plays_forced_pg_api",
        "negative_plays_pg_last3_api",
        "negative_plays_forced_pg_last3_api",
    ),
    "pff": (
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
    ),
}


def _has_enrichment_signal(value: object) -> bool:
    if value in ("N/A", None, ""):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _provider_status_for_values(values: dict, keys: tuple[str, ...]) -> str:
    present = [key for key in keys if _has_enrichment_signal(values.get(key))]
    if not present:
        return "unavailable"
    if len(present) == len(keys):
        return "ok"
    return "partial"


def _overall_enrichment_status(payload: dict, providers: dict | None = None) -> str:
    if isinstance(providers, dict) and providers:
        for provider_name, keys in ENRICHMENT_PROVIDER_KEYS.items():
            provider = providers.get(provider_name)
            if not isinstance(provider, dict):
                continue
            fields = provider.get("fields")
            if isinstance(fields, dict) and any(_has_enrichment_signal(fields.get(key)) for key in keys):
                return "ok"
    return "ok" if _enrichment_has_signal(payload) else "unavailable"


def _normalize_provider_payload(values: dict, provider_payload: dict | None = None) -> dict:
    normalized_providers: dict = {}
    for provider_name, keys in ENRICHMENT_PROVIDER_KEYS.items():
        raw_provider = provider_payload.get(provider_name) if isinstance(provider_payload, dict) else None
        normalized_provider = dict(raw_provider) if isinstance(raw_provider, dict) else {}

        raw_fields = normalized_provider.get("fields")
        provider_fields = dict(raw_fields) if isinstance(raw_fields, dict) else {}
        normalized_provider["fields"] = {
            key: values.get(key, provider_fields.get(key, "N/A"))
            for key in keys
        }

        status = str(normalized_provider.get("status") or "").strip().lower()
        if status not in {"ok", "partial", "unavailable"}:
            status = _provider_status_for_values(normalized_provider["fields"], keys)
        normalized_provider["status"] = status

        raw_reasons = normalized_provider.get("reasons")
        if isinstance(raw_reasons, list):
            normalized_provider["reasons"] = [str(reason).strip() for reason in raw_reasons if str(reason).strip()]
        else:
            normalized_provider["reasons"] = []

        normalized_providers[provider_name] = normalized_provider
    return normalized_providers


def _norm_team_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.lower().replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def _team_name_variants(team_name: str, team_slug: str) -> set[str]:
    base = _norm_team_name(team_name)
    variants = {base, _norm_team_name(team_slug)}
    if " state" in base:
        variants.add(base.replace(" state", " st"))
    if " st" in base:
        variants.add(base.replace(" st", " state"))
    return {v for v in variants if v}

def _is_url_source(value: str | Path | None) -> bool:
    if isinstance(value, Path):
        return False
    if not isinstance(value, str):
        return False
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"}


def _coerce_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value).expanduser()


def _read_json_url(url: str) -> dict:
    headers = {"User-Agent": "pbp-analysis-game-prep-brief"}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to read JSON url {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid JSON payload at {url}: expected top-level object")
    return payload


def _load_json_from_source(
    source: str | Path | None,
    *,
    expected_artifact: str | None = None,
    published_logical_name: str,
    season: int,
    env_var_name: str,
) -> dict:
    resolved_source = source if source is not None else (os.getenv(env_var_name) or "").strip() or None
    source_label = None
    try:
        if resolved_source is None:
            source_label = published_artifact_download_url(published_logical_name, season)
            data = fetch_published_artifact_json(published_logical_name, season)
        elif _is_url_source(resolved_source):
            source_label = str(resolved_source)
            data = _read_json_url(str(resolved_source))
        else:
            path = _coerce_path(resolved_source)
            source_label = str(path)
            if not path.exists():
                print(f"[warn] Missing {published_logical_name} artifact at {path}", file=sys.stderr)
                return {}
            with open(path) as handle:
                data = json.load(handle)
    except Exception as exc:
        fallback_release_url = published_artifact_release_url(season)
        print(
            f"[warn] Failed to load {published_logical_name} artifact from "
            f"{source_label or fallback_release_url}: {exc}",
            file=sys.stderr,
        )
        return {}

    if not isinstance(data, dict):
        print(
            f"[warn] Invalid {published_logical_name} artifact at {source_label}: expected top-level object",
            file=sys.stderr,
        )
        return {}
    if expected_artifact is not None:
        actual_artifact = ((data.get("meta") or {}).get("artifact") or "").strip()
        if actual_artifact != expected_artifact:
            print(
                f"[warn] Invalid {published_logical_name} artifact at {source_label}: "
                f"found '{actual_artifact or 'unknown'}'",
                file=sys.stderr,
            )
            return {}
    return data


def load_cfbstats_snapshot(season: int, source: str | Path | None = None) -> dict:
    return _load_json_from_source(
        source,
        expected_artifact="cfbstats_snapshot",
        published_logical_name="cfbstats_snapshot",
        season=season,
        env_var_name="GAME_PREP_CFBSTATS_SNAPSHOT_PATH",
    )


def load_cfbstats_verification_report(season: int, source: str | Path | None = None) -> dict:
    return _load_json_from_source(
        source,
        expected_artifact="cfbstats_bundle_verification_report",
        published_logical_name="cfbstats_verification_report",
        season=season,
        env_var_name="GAME_PREP_CFBSTATS_VERIFICATION_PATH",
    )


def _artifact_team_entry(artifact: dict | None, team_slug: str, team_name: str) -> dict:
    teams = artifact.get("teams") if isinstance(artifact, dict) else None
    if not isinstance(teams, dict):
        return {}

    for candidate in (team_slug, slugify(team_name)):
        entry = teams.get(candidate)
        if isinstance(entry, dict):
            return entry

    name_variants = _team_name_variants(team_name, team_slug)
    for slug, payload in teams.items():
        if not isinstance(payload, dict):
            continue
        payload_names = {
            _norm_team_name(slug),
            _norm_team_name(payload.get("team_slug")),
            _norm_team_name(payload.get("team_name")),
            _norm_team_name(payload.get("name")),
        }
        if name_variants & payload_names:
            return payload
    return {}


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
    result = _fetch_text_result_from_candidates(
        candidates,
        suffix,
        timeout=timeout,
        attempts=attempts,
    )
    return result.get("text")


def _fetch_text_result_from_candidates(
    candidates: list[str],
    suffix: str,
    timeout: int = 8,
    attempts: int = 3,
) -> dict[str, object]:
    if not candidates:
        return {"text": None, "status": "unavailable", "reason": "no_team_candidates", "url": None}
    last_reason = "empty_response"
    last_url: str | None = None
    for candidate in candidates:
        encoded = urllib.parse.quote(candidate)
        url = f"{YR_DATA_API_BASE}/yr/{encoded}/{suffix}"
        last_url = url
        for attempt in range(1, attempts + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    text = (resp.read().decode("utf-8", errors="ignore") or "").strip()
                if text:
                    return {"text": text, "status": "ok", "reason": None, "url": url}
                last_reason = f"empty_response via {candidate}"
            except Exception as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
                if attempt < attempts:
                    time.sleep(0.2 * attempt)
                continue
    print(
        f"[warn] yr-data-api fetch failed for {suffix}: {last_reason}",
        file=sys.stderr,
    )
    return {"text": None, "status": "unavailable", "reason": last_reason, "url": last_url}


def _fetch_json_result_from_candidates(
    candidates: list[str],
    suffix: str,
    timeout: int = 8,
    attempts: int = 3,
) -> dict[str, object]:
    if not candidates:
        return {"json": None, "status": "unavailable", "reason": "no_team_candidates", "url": None}
    last_reason = "empty_response"
    last_url: str | None = None
    for candidate in candidates:
        encoded = urllib.parse.quote(candidate)
        url = f"{YR_DATA_API_BASE}/yr/{encoded}/{suffix}"
        last_url = url
        for attempt in range(1, attempts + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
                if isinstance(payload, dict):
                    return {"json": payload, "status": "ok", "reason": None, "url": url}
                last_reason = f"invalid_json_type via {candidate}"
            except Exception as exc:
                last_reason = f"{type(exc).__name__}: {exc}"
                if attempt < attempts:
                    time.sleep(0.2 * attempt)
                continue
    print(
        f"[warn] yr-data-api fetch failed for {suffix}: {last_reason}",
        file=sys.stderr,
    )
    return {"json": None, "status": "unavailable", "reason": last_reason, "url": last_url}


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


def _game_stat_row(stats: dict, category: str, opponent_abbr: object) -> dict:
    cat = stats.get(category) or {}
    if not isinstance(cat, dict):
        return {}
    opp = str(opponent_abbr or "").strip().upper()
    if opp and isinstance(cat.get(opp), dict):
        return cat.get(opp) or {}
    return {}


def _pick_present(*values: object) -> object | None:
    for value in values:
        if value is not None:
            return value
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _list_or_empty(value: object) -> list:
    return value if isinstance(value, list) else []


def _converted_bundle_game(
    raw_game: dict,
    *,
    game_number: int,
    normalized_week: int,
    stats: dict,
) -> dict:
    opponent_abbr = raw_game.get("opponent_abbr") or raw_game.get("opponent")
    play_tree = raw_game.get("play_tree") if isinstance(raw_game.get("play_tree"), list) else []
    scoring = _game_stat_row(stats, "scoring", opponent_abbr)
    total_yardage = _game_stat_row(stats, "total_yardage", opponent_abbr)
    explosives = _game_stat_row(stats, "explosives", opponent_abbr)
    negative_plays = _game_stat_row(stats, "negative_plays", opponent_abbr)
    turnovers = _game_stat_row(stats, "turnovers", opponent_abbr)
    points_off_turnovers = _game_stat_row(stats, "points_off_turnovers", opponent_abbr)
    red_zone = _game_stat_row(stats, "red_zone", opponent_abbr)
    third_down = _game_stat_row(stats, "third_down", opponent_abbr)
    fourth_down = _game_stat_row(stats, "fourth_down", opponent_abbr)
    penalties = _game_stat_row(stats, "penalties", opponent_abbr)
    two_point = _game_stat_row(stats, "two_point", opponent_abbr)

    return {
        "game_number": game_number,
        "week": normalized_week,
        "date": _pick_present(raw_game.get("date"), raw_game.get("game_date")),
        "is_home": raw_game.get("is_home") if isinstance(raw_game.get("is_home"), bool) else None,
        "opponent_abbr": opponent_abbr,
        "opponent": raw_game.get("opponent") or opponent_abbr or "OPP",
        "points_for": _pick_present(raw_game.get("points_for"), scoring.get("points_for")),
        "points_against": _pick_present(raw_game.get("points_against"), scoring.get("points_against")),
        "total_plays": _int_or_none(raw_game.get("total_plays")),
        "total_yards": _pick_present(
            _int_or_none(raw_game.get("total_yards")),
            _int_or_none(raw_game.get("total_yardage")),
            _int_or_none(total_yardage.get("total_offense_yards")),
            _int_or_none(total_yardage.get("play_derived_total_offense_yards")),
        ),
        "explosive_passes": _pick_present(
            _int_or_none(raw_game.get("explosive_passes")),
            _int_or_none(explosives.get("explosive_pass")),
        ),
        "explosive_rushes": _pick_present(
            _int_or_none(raw_game.get("explosive_rushes")),
            _int_or_none(explosives.get("explosive_run")),
        ),
        "explosives": _pick_present(
            _int_or_none(raw_game.get("explosives")),
            _int_or_none(explosives.get("explosives")),
        ),
        "negative_plays": _pick_present(
            _int_or_none(raw_game.get("negative_plays")),
            _int_or_none(negative_plays.get("negative_plays")),
        ),
        "negative_plays_forced": _pick_present(
            _int_or_none(raw_game.get("negative_plays_forced")),
            _int_or_none(negative_plays.get("negative_plays_forced")),
        ),
        "third_down_attempts": _pick_present(
            _int_or_none(raw_game.get("third_down_attempts")),
            _int_or_none(third_down.get("third_down_attempts")),
        ),
        "third_down_conversions": _pick_present(
            _int_or_none(raw_game.get("third_down_conversions")),
            _int_or_none(third_down.get("third_down_conversions")),
        ),
        "4th_down_attempts": _pick_present(
            _int_or_none(raw_game.get("4th_down_attempts")),
            _int_or_none(raw_game.get("fourth_down_attempts")),
            _int_or_none(fourth_down.get("attempts")),
        ),
        "4th_down_conversions": _pick_present(
            _int_or_none(raw_game.get("4th_down_conversions")),
            _int_or_none(raw_game.get("fourth_down_conversions")),
            _int_or_none(fourth_down.get("conversions")),
        ),
        "turnovers_lost": _pick_present(
            _int_or_none(raw_game.get("turnovers_lost")),
            _int_or_none(turnovers.get("turnovers")),
        ),
        "turnovers_gained": _pick_present(
            _int_or_none(raw_game.get("turnovers_gained")),
            _int_or_none(turnovers.get("turnovers_forced")),
        ),
        "interceptions_lost": _pick_present(
            _int_or_none(raw_game.get("interceptions_lost")),
            _int_or_none(turnovers.get("interceptions")),
        ),
        "interceptions_gained": _pick_present(
            _int_or_none(raw_game.get("interceptions_gained")),
            _int_or_none(turnovers.get("interceptions_forced")),
        ),
        "fumbles_lost": _pick_present(
            _int_or_none(raw_game.get("fumbles_lost")),
            _int_or_none(turnovers.get("fumbles_lost")),
        ),
        "fumbles_gained": _pick_present(
            _int_or_none(raw_game.get("fumbles_gained")),
            _int_or_none(turnovers.get("fumbles_recovered")),
        ),
        "points_off_turnovers_for": _pick_present(
            _int_or_none(raw_game.get("points_off_turnovers_for")),
            _int_or_none(raw_game.get("points_off_turnovers")),
            _int_or_none(points_off_turnovers.get("points_off_turnovers")),
        ),
        "points_off_turnovers_against": _pick_present(
            _int_or_none(raw_game.get("points_off_turnovers_against")),
            _int_or_none(raw_game.get("points_off_turnovers_allowed")),
            _int_or_none(points_off_turnovers.get("points_off_turnovers_allowed")),
        ),
        "post_turnover_drives": _enrich_post_turnover_drives(
            raw_game,
            _list_or_empty(raw_game.get("post_turnover_drives")),
            team_aliases=_abbr_set(raw_game.get("team")),
            opp_aliases=_abbr_set(opponent_abbr),
        ),
        "red_zone_trips": _pick_present(
            _int_or_none(raw_game.get("red_zone_trips")),
            _int_or_none(red_zone.get("rz_trips")),
        ),
        "red_zone_tds": _pick_present(
            _int_or_none(raw_game.get("red_zone_tds")),
            _int_or_none(red_zone.get("rz_tds")),
        ),
        "red_zone_fgs": _pick_present(
            _int_or_none(raw_game.get("red_zone_fgs")),
            _int_or_none(red_zone.get("rz_fgs")),
        ),
        "tight_red_zone_trips": _int_or_none(raw_game.get("tight_red_zone_trips")),
        "tight_red_zone_tds": _int_or_none(raw_game.get("tight_red_zone_tds")),
        "tight_red_zone_fgs": _int_or_none(raw_game.get("tight_red_zone_fgs")),
        "green_zone_trips": _int_or_none(raw_game.get("green_zone_trips")),
        "green_zone_tds": _int_or_none(raw_game.get("green_zone_tds")),
        "green_zone_fgs": _int_or_none(raw_game.get("green_zone_fgs")),
        "green_zone_failed": _int_or_none(raw_game.get("green_zone_failed")),
        "penalties": _pick_present(
            _int_or_none(raw_game.get("penalties")),
            _int_or_none(penalties.get("total_penalties")),
        ),
        "penalty_yards": _pick_present(
            _int_or_none(raw_game.get("penalty_yards")),
            _int_or_none(penalties.get("total_penalty_yards")),
        ),
        "penalties_offense": _pick_present(
            _int_or_none(raw_game.get("penalties_offense")),
            _int_or_none(penalties.get("offensive_penalties")),
        ),
        "penalties_defense": _pick_present(
            _int_or_none(raw_game.get("penalties_defense")),
            _int_or_none(penalties.get("defensive_penalties")),
        ),
        "penalties_special_teams": _pick_present(
            _int_or_none(raw_game.get("penalties_special_teams")),
            _int_or_none(penalties.get("special_teams_penalties")),
        ),
        "two_pt_attempts": _pick_present(
            _int_or_none(raw_game.get("two_pt_attempts")),
            _int_or_none(raw_game.get("two_point_attempts")),
            _int_or_none(two_point.get("two_point_attempts")),
        ),
        "two_pt_conversions": _pick_present(
            _int_or_none(raw_game.get("two_pt_conversions")),
            _int_or_none(raw_game.get("two_point_conversions")),
            _int_or_none(two_point.get("two_point_conversions")),
        ),
        "opp_two_pt_attempts": _pick_present(
            _int_or_none(raw_game.get("opp_two_pt_attempts")),
            _int_or_none(raw_game.get("two_point_allowed_attempts")),
            _int_or_none(two_point.get("two_point_allowed_attempts")),
        ),
        "opp_two_pt_conversions": _pick_present(
            _int_or_none(raw_game.get("opp_two_pt_conversions")),
            _int_or_none(raw_game.get("two_point_allowed_conversions")),
            _int_or_none(two_point.get("two_point_allowed_conversions")),
        ),
        "play_tree": play_tree,
    }


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


def _scrimmage_play_count(plays: list[dict]) -> int:
    return sum(1 for play in plays if not play.get("is_no_play") and play.get("is_scrimmage_play"))


def _clock_remaining_seconds(clock: object) -> int | None:
    if not isinstance(clock, str):
        return None
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", clock)
    if not match:
        return None
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    if seconds >= 60:
        return None
    return minutes * 60 + seconds


def _clock_elapsed_seconds(quarter: object, clock: object) -> int | None:
    if not isinstance(quarter, int) or quarter <= 0:
        return None
    remaining = _clock_remaining_seconds(clock)
    if remaining is None:
        return None
    if quarter <= 4:
        return ((quarter - 1) * 15 * 60) + ((15 * 60) - remaining)
    return None


def _format_drive_top(seconds: int | None) -> str | None:
    if seconds is None or seconds < 0:
        return None
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes}:{remainder:02d}"


def _drive_side(plays: list[dict], resolver: "_PlaySideResolver") -> str | None:
    for play in plays:
        if play.get("is_no_play") or not play.get("is_scrimmage_play"):
            continue
        side = resolver.resolve(play.get("offense"))
        if side in {"team", "opp"}:
            return side
    return None


def _find_turnover_drive_index(
    flat_drives: list[tuple[int | None, list[dict]]],
    entry: dict,
) -> int | None:
    target_desc = str(entry.get("turnover_description") or "").strip()
    target_clock = str(entry.get("clock") or "").strip()
    target_quarter = entry.get("quarter")
    for idx, (quarter, plays) in enumerate(flat_drives):
        for play in plays:
            if play.get("is_no_play"):
                continue
            desc = str(play.get("description") or "").strip()
            clock = str(play.get("clock") or "").strip()
            if target_desc and desc != target_desc:
                continue
            if target_clock and clock != target_clock:
                continue
            play_quarter = play.get("quarter")
            quarter_value = play_quarter if isinstance(play_quarter, int) else quarter
            if isinstance(target_quarter, int) and quarter_value != target_quarter:
                continue
            return idx
    return None


def _matched_post_turnover_drive_segments(
    flat_drives: list[tuple[int | None, list[dict]]],
    entry: dict,
    resolver: "_PlaySideResolver",
) -> list[tuple[int | None, list[dict]]]:
    turnover_drive_idx = _find_turnover_drive_index(flat_drives, entry)
    if turnover_drive_idx is None:
        return []

    expected_side = "team" if entry.get("side") == "team_gained" else "opp"
    expected_plays = entry.get("num_plays") if isinstance(entry.get("num_plays"), int) else None
    collected: list[tuple[int | None, list[dict]]] = []
    total_scrimmage_plays = 0

    for drive_idx in range(turnover_drive_idx + 1, len(flat_drives)):
        quarter, plays = flat_drives[drive_idx]
        drive_side = _drive_side(plays, resolver)
        if drive_side != expected_side:
            if collected:
                break
            continue
        if not _scrimmage_play_count(plays):
            continue
        collected.append((quarter, plays))
        total_scrimmage_plays += _scrimmage_play_count(plays)
        if expected_plays is not None and total_scrimmage_plays >= expected_plays:
            break

    return collected


def _drive_top_seconds(drive_segments: list[tuple[int | None, list[dict]]]) -> int | None:
    first_elapsed: int | None = None
    last_elapsed: int | None = None

    for quarter, plays in drive_segments:
        valid_plays = [play for play in plays if not play.get("is_no_play") and play.get("clock")]
        if not valid_plays:
            continue
        first_play = valid_plays[0]
        last_play = valid_plays[-1]
        start_elapsed = _clock_elapsed_seconds(
            first_play.get("quarter") if isinstance(first_play.get("quarter"), int) else quarter,
            first_play.get("clock"),
        )
        end_elapsed = _clock_elapsed_seconds(
            last_play.get("quarter") if isinstance(last_play.get("quarter"), int) else quarter,
            last_play.get("clock"),
        )
        if first_elapsed is None and start_elapsed is not None:
            first_elapsed = start_elapsed
        if end_elapsed is not None:
            last_elapsed = end_elapsed

    if first_elapsed is None or last_elapsed is None or last_elapsed < first_elapsed:
        return None
    return last_elapsed - first_elapsed


def _first_drive_segment_elapsed(drive_segments: list[tuple[int | None, list[dict]]]) -> int | None:
    for quarter, plays in drive_segments:
        valid_plays = [play for play in plays if not play.get("is_no_play") and play.get("clock")]
        if not valid_plays:
            continue
        first_play = valid_plays[0]
        return _clock_elapsed_seconds(
            first_play.get("quarter") if isinstance(first_play.get("quarter"), int) else quarter,
            first_play.get("clock"),
        )
    return None


def _is_reasonable_post_turnover_match(entry: dict, drive_segments: list[tuple[int | None, list[dict]]]) -> bool:
    if not drive_segments:
        return False
    turnover_elapsed = _clock_elapsed_seconds(entry.get("quarter"), entry.get("clock"))
    first_segment_elapsed = _first_drive_segment_elapsed(drive_segments)
    if turnover_elapsed is None or first_segment_elapsed is None:
        return True
    gap = first_segment_elapsed - turnover_elapsed
    return 0 <= gap <= 75


def _enrich_post_turnover_drives(
    raw_game: dict,
    entries: list[dict],
    *,
    team_aliases: set[str],
    opp_aliases: set[str],
) -> list[dict]:
    if not entries:
        return []
    play_tree = raw_game.get("play_tree")
    if not isinstance(play_tree, list) or not play_tree:
        return entries

    resolver = _build_play_side_resolver(raw_game, team_aliases=team_aliases, opp_aliases=opp_aliases)
    flat_drives = list(_iter_play_tree_drives(play_tree))
    if not flat_drives:
        return entries

    enriched: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        out = dict(entry)
        if str(out.get("drive_result") or "").upper() == "DEF TD":
            top_seconds = 0
        else:
            segments = _matched_post_turnover_drive_segments(flat_drives, out, resolver)
            if not _is_reasonable_post_turnover_match(out, segments):
                segments = []
            top_seconds = _drive_top_seconds(segments)
        if top_seconds is not None:
            out["drive_top_seconds"] = top_seconds
            out["drive_top"] = _format_drive_top(top_seconds)
        enriched.append(out)
    return enriched


def _desc_contains_alias(desc_up: str, aliases: set[str]) -> bool:
    return any(alias and alias in desc_up for alias in aliases)


def _is_fg_attempt_desc(desc: str) -> bool:
    return "FIELD GOAL" in desc or bool(re.search(r"\bFG\b", desc))


def _is_fg_made_desc(desc: str) -> bool:
    if any(bad in desc for bad in ("NO GOOD", "MISSED", "WIDE", "BLOCKED")):
        return False
    return any(good in desc for good in ("GOOD", "IS GOOD", "MADE"))


def _extract_field_goal_yards(desc: str) -> int | None:
    if not _is_fg_attempt_desc(desc):
        return None
    patterns = (
        r"(\d{1,3})\s*-\s*YARD\s+FIELD GOAL",
        r"(\d{1,3})\s+YARD\s+FIELD GOAL",
        r"FIELD GOAL(?:\s+ATTEMPT)?(?:\s+FROM|\s+AT)?\s*(\d{1,3})\s*YARD",
        r"FG(?:\s+ATTEMPT)?(?:\s+FROM|\s+AT)?\s*(\d{1,3})\s*YARD",
        r"(\d{1,3})\s*YDS?\s+FIELD GOAL",
        r"(\d{1,3})\s*YD\S*\s+FIELD GOAL",
    )
    for pattern in patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    match = re.search(r"FROM\s+(\d{1,3})\s*YARD", desc)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _extract_punt_yards(desc: str) -> int | None:
    if "PUNT" not in desc:
        return None
    for pattern in (r"PUNT(?:ED|S)?\s+(-?\d{1,3})\s+YARD", r"PUNT(?:ED|S)?\s+(-?\d{1,3})\s+YDS?"):
        match = re.search(pattern, desc)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _extract_return_yards(desc: str) -> int | None:
    if "RETURN" not in desc:
        return None
    patterns: tuple[tuple[str, bool], ...] = (
        (r"RETURN(?:ED)?\s+(-?\d{1,3})\s+YARD", False),
        (r"RETURN(?:ED)?\s+(-?\d{1,3})\s+YDS?", False),
        (r"RETURN\s+FOR\s+LOSS\s+OF\s+(\d{1,3})\s+YARD", True),
        (r"RETURN\s+FOR\s+LOSS\s+OF\s+(\d{1,3})\s+YDS?", True),
    )
    for pattern, is_loss in patterns:
        match = re.search(pattern, desc)
        if not match:
            continue
        try:
            yards = int(match.group(1))
        except ValueError:
            return None
        return -yards if is_loss else yards
    return None


def _is_dead_ball_uns_kickoff_enforcement(desc: str) -> bool:
    if "NO PLAY" not in desc or "PENALTY" not in desc:
        return False
    if "UNS" not in desc and "UNSPORTSMANLIKE" not in desc:
        return False
    if "ATTEMPT" not in desc or "SUCCESSFUL" not in desc:
        return False
    return re.search(r"\bFROM\s+([A-Z]{2,6})\s*35\s+TO\s+\1\s*50\b", desc) is not None


def _special_teams_kick_side(
    *,
    desc_up: str,
    offense_side: str | None,
    is_kickoff: bool,
    team_aliases: set[str],
    opp_aliases: set[str],
) -> str | None:
    if offense_side in {"team", "opp"}:
        return offense_side
    if not is_kickoff:
        return None
    team_in_desc = _desc_contains_alias(desc_up, team_aliases)
    opp_in_desc = _desc_contains_alias(desc_up, opp_aliases)
    if team_in_desc and not opp_in_desc:
        return "opp"
    if opp_in_desc and not team_in_desc:
        return "team"
    return None


def _derive_two_point_stats_from_play_tree(
    game: dict,
    *,
    team_aliases: set[str],
    opp_aliases: set[str],
) -> dict | None:
    play_tree = game.get("play_tree")
    if not isinstance(play_tree, list):
        return None

    plays = list(_iter_play_tree_plays(play_tree))
    if not plays:
        return None

    resolver = _build_play_side_resolver(game, team_aliases=team_aliases, opp_aliases=opp_aliases)
    stats = {
        "two_pt_attempts": 0,
        "two_pt_conversions": 0,
        "two_pt_rush_attempts": 0,
        "two_pt_rush_conversions": 0,
        "two_pt_pass_attempts": 0,
        "two_pt_pass_conversions": 0,
        "opp_two_pt_attempts": 0,
        "opp_two_pt_conversions": 0,
    }
    two_pt_keywords = ("TWO-POINT", "TWO POINT", "2-POINT", "2 POINT", "2PT")
    success_keywords = ("SUCCESSFUL", "CONVERTED", "GOOD", "CONVERSION", "SUCCESS")
    failure_keywords = ("FAILED", "FAIL", "NO GOOD", "UNSUCCESSFUL")
    pass_keywords = ("PASS", "COMPLETE", "INCOMPLETE", "THROWN")
    rush_keywords = (
        "RUSH",
        "RUN",
        "SCRAMBLE",
        "UP THE MIDDLE",
        "LEFT END",
        "RIGHT END",
        "LEFT TACKLE",
        "RIGHT TACKLE",
        "LEFT GUARD",
        "RIGHT GUARD",
    )

    for play in plays:
        desc_up = str(play.get("description") or "").upper()
        has_two_pt_keyword = any(keyword in desc_up for keyword in two_pt_keywords)
        has_attempt_phrase = (
            ("PASS ATTEMPT" in desc_up or "RUSH ATTEMPT" in desc_up)
            and any(keyword in desc_up for keyword in ("SUCCESSFUL", "FAILED"))
        )
        if not has_two_pt_keyword and not has_attempt_phrase:
            continue
        if "EXTRA POINT" in desc_up or "POINT AFTER" in desc_up or " PAT " in f" {desc_up} ":
            continue

        side = resolver.resolve(play.get("offense"))
        if side not in {"team", "opp"}:
            continue
        if play.get("is_no_play") and not _is_dead_ball_uns_kickoff_enforcement(desc_up):
            continue

        has_failure = any(keyword in desc_up for keyword in failure_keywords)
        if bool(play.get("is_scoring")):
            successful = True
        elif has_failure:
            successful = False
        else:
            successful = any(keyword in desc_up for keyword in success_keywords)

        is_pass = any(keyword in desc_up for keyword in pass_keywords)
        is_rush = any(keyword in desc_up for keyword in rush_keywords)
        play_type = "pass" if is_pass else ("rush" if is_rush else "unknown")

        if side == "team":
            stats["two_pt_attempts"] += 1
            if successful:
                stats["two_pt_conversions"] += 1
            if play_type == "pass":
                stats["two_pt_pass_attempts"] += 1
                if successful:
                    stats["two_pt_pass_conversions"] += 1
            elif play_type == "rush":
                stats["two_pt_rush_attempts"] += 1
                if successful:
                    stats["two_pt_rush_conversions"] += 1
        else:
            stats["opp_two_pt_attempts"] += 1
            if successful:
                stats["opp_two_pt_conversions"] += 1

    return stats


def _derive_special_teams_stats_from_play_tree(
    game: dict,
    *,
    team_aliases: set[str],
    opp_aliases: set[str],
) -> dict | None:
    play_tree = game.get("play_tree")
    if not isinstance(play_tree, list):
        return None

    plays = list(_iter_play_tree_plays(play_tree))
    if not plays:
        return None

    resolver = _build_play_side_resolver(game, team_aliases=team_aliases, opp_aliases=opp_aliases)
    stats = {
        "kickoff_returns": 0,
        "kickoff_return_yards": 0,
        "kickoff_return_long": 0,
        "kick_return_30_plus": 0,
        "punt_returns": 0,
        "punt_return_yards": 0,
        "punt_return_long": 0,
        "punt_return_20_plus": 0,
        "punt_returns_allowed": 0,
        "punt_return_yards_allowed": 0,
        "punt_return_long_allowed": 0,
        "punt_return_20_plus_allowed": 0,
        "special_teams_tds": 0,
        "fg_blocks": 0,
        "punt_blocks": 0,
        "punts": 0,
        "punt_yards": 0,
        "punt_net_yards": 0,
        "punt_long": 0,
        "punts_inside_20": 0,
        "punt_touchbacks": 0,
        "field_goals_made": 0,
        "field_goals_attempts": 0,
        "field_goal_long": 0,
        "pat_made": 0,
        "pat_attempts": 0,
        "onside_kicks_attempted": 0,
        "onside_kicks_recovered": 0,
    }
    has_signal = False

    for play in plays:
        if play.get("is_no_play"):
            continue
        desc_up = str(play.get("description") or "").upper()
        offense_side = resolver.resolve(play.get("offense"))
        if offense_side not in {"team", "opp"}:
            offense_side = None
        is_kickoff = "KICKOFF" in desc_up
        is_punt = "PUNT" in desc_up
        is_fg = _is_fg_attempt_desc(desc_up)
        is_pat = "PAT" in desc_up or "EXTRA POINT" in desc_up or "POINT AFTER" in desc_up
        is_onside = "ONSIDE" in desc_up
        has_signal = has_signal or is_kickoff or is_punt or is_fg or is_pat
        kick_side = _special_teams_kick_side(
            desc_up=desc_up,
            offense_side=offense_side,
            is_kickoff=is_kickoff,
            team_aliases=team_aliases,
            opp_aliases=opp_aliases,
        )

        if "BLOCKED" in desc_up:
            if is_fg and (
                offense_side == "opp"
                or (offense_side is None and _desc_contains_alias(desc_up, team_aliases) and not _desc_contains_alias(desc_up, opp_aliases))
            ):
                stats["fg_blocks"] += 1
            if is_punt and (
                offense_side == "opp"
                or (offense_side is None and _desc_contains_alias(desc_up, team_aliases) and not _desc_contains_alias(desc_up, opp_aliases))
            ):
                stats["punt_blocks"] += 1

        if kick_side == "team":
            if is_punt:
                stats["punts"] += 1
                gross = _extract_punt_yards(desc_up)
                if gross is None and isinstance(play.get("yards"), (int, float)):
                    gross = int(play.get("yards") or 0)
                if gross is None:
                    gross = 0
                stats["punt_yards"] += gross
                stats["punt_long"] = max(stats["punt_long"], gross)
                touchback = "TOUCHBACK" in desc_up
                if touchback:
                    stats["punt_touchbacks"] += 1
                return_yards = _extract_return_yards(desc_up) if "RETURN" in desc_up else 0
                net = gross
                if return_yards is not None:
                    net -= return_yards
                    stats["punt_returns_allowed"] += 1
                    stats["punt_return_yards_allowed"] += return_yards
                    stats["punt_return_long_allowed"] = max(stats["punt_return_long_allowed"], return_yards)
                    if return_yards >= 20:
                        stats["punt_return_20_plus_allowed"] += 1
                if touchback:
                    net = max(net - 20, 0)
                stats["punt_net_yards"] += net
                if not touchback and ("INSIDE 20" in desc_up or re.search(r"(OUT OF BOUNDS|DOWNED|FAIR CATCH).*?(\d+)", desc_up)):
                    spot_match = re.search(r"AT\s+[A-Z]*(\d+)", desc_up)
                    if spot_match and int(spot_match.group(1)) <= 20:
                        stats["punts_inside_20"] += 1

            if is_fg:
                stats["field_goals_attempts"] += 1
                fg_made = _is_fg_made_desc(desc_up)
                if fg_made:
                    stats["field_goals_made"] += 1
                fg_yards = _extract_field_goal_yards(desc_up)
                if fg_yards is not None and fg_made:
                    stats["field_goal_long"] = max(stats["field_goal_long"], fg_yards)

            if is_pat:
                stats["pat_attempts"] += 1
                if "GOOD" in desc_up or "MADE" in desc_up:
                    stats["pat_made"] += 1

            if is_kickoff and is_onside:
                stats["onside_kicks_attempted"] += 1
                if "RECOVER" in desc_up and _desc_contains_alias(desc_up, team_aliases):
                    stats["onside_kicks_recovered"] += 1

        if kick_side == "opp":
            if is_kickoff and "RETURN" in desc_up:
                ret_yards = play.get("yards") if isinstance(play.get("yards"), (int, float)) else _extract_return_yards(desc_up)
                if isinstance(ret_yards, (int, float)):
                    ret_yards_int = int(ret_yards)
                    stats["kickoff_returns"] += 1
                    stats["kickoff_return_yards"] += ret_yards_int
                    stats["kickoff_return_long"] = max(stats["kickoff_return_long"], ret_yards_int)
                    if ret_yards_int >= 30:
                        stats["kick_return_30_plus"] += 1

            if is_punt and "RETURN" in desc_up and kick_side == "opp":
                ret_yards = play.get("yards") if isinstance(play.get("yards"), (int, float)) else _extract_return_yards(desc_up)
                if isinstance(ret_yards, (int, float)):
                    ret_yards_int = int(ret_yards)
                    stats["punt_returns"] += 1
                    stats["punt_return_yards"] += ret_yards_int
                    stats["punt_return_long"] = max(stats["punt_return_long"], ret_yards_int)
                    if ret_yards_int >= 20:
                        stats["punt_return_20_plus"] += 1

        if "TOUCHDOWN" in desc_up and (is_kickoff or is_punt or is_fg or is_pat or "RETURN" in desc_up or "BLOCKED" in desc_up):
            credited = False
            if _desc_contains_alias(desc_up, team_aliases) and not _desc_contains_alias(desc_up, opp_aliases):
                credited = True
            elif kick_side == "opp":
                credited = True
            elif (is_fg or is_punt) and kick_side == "team" and "FAKE" in desc_up:
                credited = True
            if credited:
                stats["special_teams_tds"] += 1

    stats["kickoff_return_avg"] = (
        round(stats["kickoff_return_yards"] / stats["kickoff_returns"], 1) if stats["kickoff_returns"] else 0.0
    )
    stats["punt_return_avg"] = (
        round(stats["punt_return_yards"] / stats["punt_returns"], 1) if stats["punt_returns"] else 0.0
    )
    stats["punt_return_allowed_avg"] = (
        round(stats["punt_return_yards_allowed"] / stats["punt_returns_allowed"], 1)
        if stats["punt_returns_allowed"]
        else 0.0
    )
    stats["punt_avg"] = round(stats["punt_yards"] / stats["punts"], 1) if stats["punts"] else 0.0
    stats["punt_net_avg"] = round(stats["punt_net_yards"] / stats["punts"], 1) if stats["punts"] else 0.0
    return stats if has_signal else None


@dataclass(frozen=True)
class _PlaySideResolver:
    team_aliases: frozenset[str]
    opp_aliases: frozenset[str]
    offense_tokens: frozenset[str]
    warnings: tuple[str, ...]

    def resolve(self, offense: object) -> str:
        token = str(offense or "").upper().strip()
        if not token:
            return "unknown"
        if token in self.team_aliases:
            return "team"
        if token in self.opp_aliases:
            return "opp"
        return "unknown"


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


def _extract_penalty_team_token(desc: str) -> str:
    upper = desc.upper()
    patterns = (
        r"\bPENALTY\s+BEFORE\s+THE\s+SNAP,\s*([A-Z0-9]{2,8})\b",
        r"\bPENALTY\s+ON\s+([A-Z0-9]{2,8})\b",
        r"\bPENALTY\s+([A-Z0-9]{2,8})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, upper)
        if match:
            token = re.sub(r"[^A-Z0-9]", "", match.group(1))
            if token != "BEFORE":
                return token
    return ""


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


def _play_tree_offense_tokens(play_tree: object) -> set[str]:
    tokens: set[str] = set()
    for play in _iter_play_tree_plays(play_tree):
        token = str(play.get("offense") or "").upper().strip()
        if token:
            tokens.add(token)
    return tokens


def _play_tree_description_tokens(play_tree: object) -> set[str]:
    tokens: set[str] = set()
    for play in _iter_play_tree_plays(play_tree):
        if play.get("is_no_play"):
            continue
        desc_up = str(play.get("description") or "").upper()
        for pattern in (
            r"RECOVERED BY ([A-Z]{2,6})\b",
            r"TOUCHDOWN ([A-Z]{2,6})\b",
        ):
            for match in re.finditer(pattern, desc_up):
                tokens.add(match.group(1))
        match = re.match(r"([A-Z]{2,6}) BALL ON\b", desc_up)
        if match:
            tokens.add(match.group(1))
    return tokens


def _build_play_side_resolver(
    game: dict,
    *,
    team_aliases: set[str],
    opp_aliases: set[str],
) -> _PlaySideResolver:
    play_tree = game.get("play_tree") if isinstance(game, dict) else None
    team_tokens = set(team_aliases)
    opp_tokens = set(opp_aliases)
    offense_tokens = _play_tree_offense_tokens(play_tree)

    inferred_team_aliases = _infer_team_alias_from_play_tree(
        play_tree,
        team_aliases=team_tokens,
        opponent_abbr=opp_tokens,
    )
    team_tokens.update(inferred_team_aliases)

    known_team = offense_tokens & team_tokens
    known_opp = offense_tokens & opp_tokens
    unknown = offense_tokens - known_team - known_opp

    # If the game only uses two offense tokens, assign the unresolved token by
    # elimination when one side is already known.
    if len(offense_tokens) == 2 and len(unknown) == 1:
        token = next(iter(unknown))
        if known_opp and not known_team:
            team_tokens.add(token)
        elif known_team and not known_opp:
            opp_tokens.add(token)

    known_team = offense_tokens & team_tokens
    known_opp = offense_tokens & opp_tokens

    # Turnover recovery and possession text can introduce a single team token
    # even when the offense field only uses the other side's abbreviation.
    desc_unknown = _play_tree_description_tokens(play_tree) - team_tokens - opp_tokens
    if len(desc_unknown) == 1:
        token = next(iter(desc_unknown))
        if known_opp and not known_team:
            team_tokens.add(token)
        elif known_team and not known_opp:
            opp_tokens.add(token)

    warnings: list[str] = []
    unresolved = offense_tokens - team_tokens - opp_tokens
    if len(offense_tokens) > 2:
        warnings.append(f"multiple offense tokens detected: {', '.join(sorted(offense_tokens))}")
    if unresolved:
        warnings.append(f"unresolved offense tokens: {', '.join(sorted(unresolved))}")
    if offense_tokens and not (offense_tokens & team_tokens):
        warnings.append("team offense token unresolved after alias resolution")

    return _PlaySideResolver(
        team_aliases=frozenset(team_tokens),
        opp_aliases=frozenset(opp_tokens),
        offense_tokens=frozenset(offense_tokens),
        warnings=tuple(warnings),
    )


def _collect_play_tree_alias_warnings(team_name: str, pbp_entry: dict | None) -> list[str]:
    if not isinstance(pbp_entry, dict):
        return []
    warnings: list[str] = []
    team_aliases = _abbr_set(pbp_entry.get("abbr_aliases") or pbp_entry.get("abbr"))
    for game in pbp_entry.get("games") or []:
        if not isinstance(game, dict):
            continue
        opp_aliases = _abbr_set(game.get("opponent_abbr"))
        resolver = _build_play_side_resolver(game, team_aliases=team_aliases, opp_aliases=opp_aliases)
        if not resolver.warnings:
            continue
        label = f"{team_name}: G{game.get('game_number') or '?'} {game.get('opponent_abbr') or game.get('opponent') or 'OPP'}"
        for warning in resolver.warnings:
            warnings.append(f"{label}: {warning}")
    return warnings


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

    # Sort games by date before assigning week numbers so the monotonic
    # guard doesn't misfire when the bundle stores games in file-load order.
    raw_games = [g for g in (payload.get("games") or []) if isinstance(g, dict)]
    raw_games.sort(key=lambda g: str(g.get("game_date") or g.get("date") or ""))

    normalized_games: list[tuple[int, int, dict]] = []
    last_week = 0
    for idx, g in enumerate(raw_games, start=1):
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
        games_out.append(
            _converted_bundle_game(
                g,
                game_number=game_number,
                normalized_week=normalized_week,
                stats=stats,
            )
        )

    turnover_margin = "N/A"
    if games_out and all(
        isinstance(game.get("turnovers_gained"), int) and isinstance(game.get("turnovers_lost"), int)
        for game in games_out
    ):
        turnover_margin = sum(int(game.get("turnovers_gained") or 0) for game in games_out) - sum(
            int(game.get("turnovers_lost") or 0) for game in games_out
        )
    elif isinstance(turnovers_forced, (int, float)) and isinstance(turnovers, (int, float)):
        turnover_margin = turnovers_forced - turnovers

    return {
        "name": payload.get("team_name") or slug.replace("-", " ").title(),
        "abbr": home_abbr or slug[:4].upper(),
        "abbr_aliases": sorted(team_aliases),
        "conference": "",
        "color": "#888888",
        "cfbstats": {"rankings": {"all": {}, "conf": {}, "nonconf": {}}, "two_point_totals": {}},
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
            "turnover_margin": turnover_margin,
            "red_zone_td_pct": rz_pct,
            "penalties_per_game": pen.get("total_penalties_pg", "N/A"),
        },
        "bye_weeks": sched.get("bye_weeks", []),
        "schedule": {"games": schedule_games_out},
        "games": games_out,
        "xml_stats": stats,
        "xml_source": True,
        "bundle_metadata": payload.get("bundle_metadata"),
    }


def _load_xml_bundle_data(season: int, source: str | Path | None = None) -> dict:
    raw = _load_json_from_source(
        source,
        expected_artifact=None,
        published_logical_name="bundle",
        season=season,
        env_var_name="GAME_PREP_XML_BUNDLE_PATH",
    )
    if not raw:
        return {}
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


def load_pbp_data(
    matchup_slug: str | None = None,
    *,
    season: int = 2025,
    bundle_source: str | Path | None = None,
) -> dict:
    base: dict = {}
    if GAME_PREP_DATA_SOURCE != "xml":
        print(
            f"[warn] Non-XML source '{GAME_PREP_DATA_SOURCE}' is disabled; forcing XML bundle mode",
            file=sys.stderr,
        )
    base = _load_xml_bundle_data(season, bundle_source)
    if not base:
        print(
            "[warn] XML bundle source unavailable; returning empty team set",
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


def _apply_special_teams_play_tree_derivations(team_name: str, pbp_entry: dict | None) -> list[str]:
    if not isinstance(pbp_entry, dict):
        return []
    games = [g for g in (pbp_entry.get("games") or []) if isinstance(g, dict)]
    if not games:
        return []

    team_aliases = _abbr_set(pbp_entry.get("abbr_aliases") or pbp_entry.get("abbr"))
    if not team_aliases:
        return []

    for game in games:
        opp_aliases = _abbr_set(game.get("opponent_abbr"))
        derived_st = _derive_special_teams_stats_from_play_tree(
            game,
            team_aliases=team_aliases,
            opp_aliases=opp_aliases,
        )
        if isinstance(derived_st, dict):
            existing = game.get("special_teams") if isinstance(game.get("special_teams"), dict) else {}
            merged = dict(existing)
            for key, value in derived_st.items():
                if key not in merged or merged.get(key) in (None, "", "N/A"):
                    merged[key] = value
            if not existing:
                merged = derived_st
            game["special_teams"] = merged

        derived_two_pt = _derive_two_point_stats_from_play_tree(
            game,
            team_aliases=team_aliases,
            opp_aliases=opp_aliases,
        )
        if isinstance(derived_two_pt, dict):
            game.update(derived_two_pt)

    warnings: list[str] = []
    xml_stats = pbp_entry.get("xml_stats") if isinstance(pbp_entry.get("xml_stats"), dict) else {}
    xml_st = _best_xml_row(xml_stats, "special_teams")
    if xml_st:
        derived_fg_att = sum(
            int((g.get("special_teams") or {}).get("field_goals_attempts") or 0)
            for g in games
            if isinstance(g.get("special_teams"), dict)
        )
        derived_fg_made = sum(
            int((g.get("special_teams") or {}).get("field_goals_made") or 0)
            for g in games
            if isinstance(g.get("special_teams"), dict)
        )
        xml_fg_att = int(xml_st.get("fg_attempts") or 0)
        xml_fg_made = int(xml_st.get("fg_made") or 0)
        if derived_fg_att != xml_fg_att or derived_fg_made != xml_fg_made:
            warnings.append(
                f"{team_name}: special-teams FG parity delta "
                f"(derived {derived_fg_made}/{derived_fg_att} vs XML {xml_fg_made}/{xml_fg_att})"
            )

    xml_tp = _best_xml_row(xml_stats, "two_point")
    if xml_tp:
        derived_totals = {
            "two_point_attempts": sum(int(g.get("two_pt_attempts") or 0) for g in games if isinstance(g.get("two_pt_attempts"), int)),
            "two_point_conversions": sum(int(g.get("two_pt_conversions") or 0) for g in games if isinstance(g.get("two_pt_conversions"), int)),
            "two_point_allowed_attempts": sum(
                int(g.get("opp_two_pt_attempts") or 0) for g in games if isinstance(g.get("opp_two_pt_attempts"), int)
            ),
            "two_point_allowed_conversions": sum(
                int(g.get("opp_two_pt_conversions") or 0)
                for g in games
                if isinstance(g.get("opp_two_pt_conversions"), int)
            ),
        }
        xml_totals = {
            "two_point_attempts": int(xml_tp.get("two_point_attempts") or 0),
            "two_point_conversions": int(xml_tp.get("two_point_conversions") or 0),
            "two_point_allowed_attempts": int(xml_tp.get("two_point_allowed_attempts") or 0),
            "two_point_allowed_conversions": int(xml_tp.get("two_point_allowed_conversions") or 0),
        }
        if derived_totals != xml_totals:
            warnings.append(
                f"{team_name}: derived two-point totals differ from XML "
                f"(derived O {derived_totals['two_point_conversions']}/{derived_totals['two_point_attempts']}, "
                f"D {derived_totals['two_point_allowed_conversions']}/{derived_totals['two_point_allowed_attempts']} "
                f"vs XML O {xml_totals['two_point_conversions']}/{xml_totals['two_point_attempts']}, "
                f"D {xml_totals['two_point_allowed_conversions']}/{xml_totals['two_point_allowed_attempts']})"
            )
    return warnings


def _apply_turnover_xml_game_overrides(pbp_entry: dict | None) -> None:
    if not isinstance(pbp_entry, dict):
        return
    games = [g for g in (pbp_entry.get("games") or []) if isinstance(g, dict)]
    if not games:
        return

    xml_stats = pbp_entry.get("xml_stats") if isinstance(pbp_entry.get("xml_stats"), dict) else {}
    tov_cat = xml_stats.get("turnovers") if isinstance(xml_stats.get("turnovers"), dict) else {}
    pot_cat = (
        xml_stats.get("points_off_turnovers")
        if isinstance(xml_stats.get("points_off_turnovers"), dict)
        else {}
    )
    opponent_counts: dict[str, int] = {}
    for game in games:
        opp = str(game.get("opponent_abbr") or "").upper().strip()
        if opp:
            opponent_counts[opp] = opponent_counts.get(opp, 0) + 1

    def _set_if_numeric(game: dict, key: str, value: object) -> None:
        if isinstance(value, (int, float)):
            game[key] = int(value)

    def _single_game_row(row: dict, opp: str) -> bool:
        if not isinstance(row, dict):
            return False
        if opponent_counts.get(opp, 0) > 1:
            return False
        games_value = row.get("games")
        return not isinstance(games_value, (int, float)) or int(games_value) <= 1

    for game in games:
        opp = str(game.get("opponent_abbr") or "").upper().strip()
        if not opp:
            continue
        tov_row = tov_cat.get(opp) if isinstance(tov_cat.get(opp), dict) else {}
        pot_row = pot_cat.get(opp) if isinstance(pot_cat.get(opp), dict) else {}
        if _single_game_row(tov_row, opp):
            _set_if_numeric(game, "turnovers_gained", tov_row.get("turnovers"))
            _set_if_numeric(game, "turnovers_lost", tov_row.get("turnovers_forced"))
            _set_if_numeric(game, "interceptions_gained", tov_row.get("interceptions"))
            _set_if_numeric(game, "interceptions_lost", tov_row.get("interceptions_forced"))
            _set_if_numeric(game, "fumbles_gained", tov_row.get("fumbles_lost"))
            _set_if_numeric(game, "fumbles_lost", tov_row.get("fumbles_recovered"))
        if _single_game_row(pot_row, opp):
            _set_if_numeric(game, "points_off_turnovers_for", pot_row.get("points_off_turnovers_allowed"))
            _set_if_numeric(game, "points_off_turnovers_against", pot_row.get("points_off_turnovers"))

    if all(
        isinstance(game.get("turnovers_gained"), int) and isinstance(game.get("turnovers_lost"), int)
        for game in games
    ):
        aggregates = pbp_entry.get("aggregates") if isinstance(pbp_entry.get("aggregates"), dict) else {}
        aggregates["turnover_margin"] = sum(int(game.get("turnovers_gained") or 0) for game in games) - sum(
            int(game.get("turnovers_lost") or 0) for game in games
        )
        pbp_entry["aggregates"] = aggregates


def _normalize_team_name_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _normalize_game_date_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _raw_game_briefs_root() -> Path | None:
    candidates = [
        ROOT_DIR.parent / "pbp-parser" / "data" / "statbroadcast_game_briefs",
        ROOT_DIR / "data" / "statbroadcast_game_briefs",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=None)
def _load_raw_game_fourth_down_totals(team_slug: str, team_name: str) -> dict[str, dict]:
    root = _raw_game_briefs_root()
    if root is None:
        return {}
    team_dir = root / team_slug
    if not team_dir.exists():
        return {}

    team_name_key = _normalize_team_name_key(team_name)
    totals_by_date: dict[str, dict] = {}
    for path in sorted(team_dir.glob("game_*.json")):
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        team_names = payload.get("team_names") or []
        teams = payload.get("teams") or []
        if not isinstance(team_names, list) or not isinstance(teams, list) or len(team_names) != len(teams):
            continue
        team_idx = next(
            (
                idx
                for idx, candidate_name in enumerate(team_names)
                if _normalize_team_name_key(candidate_name) == team_name_key
            ),
            None,
        )
        if team_idx is None:
            continue
        team_token = str(teams[team_idx] or "").upper().strip()
        team_stats = (payload.get("team_stats") or {}).get(team_token) or {}
        if not team_stats:
            continue
        date_key = _normalize_game_date_key((payload.get("meta") or {}).get("game_date"))
        if not date_key:
            continue
        totals_by_date[date_key] = {
            "attempts": int(team_stats.get("fourth_down_attempts") or 0),
            "conversions": int(team_stats.get("fourth_down_conversions") or 0),
            "source_path": str(path),
        }
    return totals_by_date


@lru_cache(maxsize=None)
def _load_raw_game_third_down_totals(team_slug: str, team_name: str) -> dict[str, dict]:
    root = _raw_game_briefs_root()
    if root is None:
        return {}
    team_dir = root / team_slug
    if not team_dir.exists():
        return {}

    team_name_key = _normalize_team_name_key(team_name)
    totals_by_date: dict[str, dict] = {}
    for path in sorted(team_dir.glob("game_*.json")):
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        team_names = payload.get("team_names") or []
        teams = payload.get("teams") or []
        if not isinstance(team_names, list) or not isinstance(teams, list) or len(team_names) != len(teams):
            continue
        team_idx = next(
            (
                idx
                for idx, candidate_name in enumerate(team_names)
                if _normalize_team_name_key(candidate_name) == team_name_key
            ),
            None,
        )
        if team_idx is None:
            continue
        team_token = str(teams[team_idx] or "").upper().strip()
        team_stats = (payload.get("team_stats") or {}).get(team_token) or {}
        if not team_stats:
            continue
        date_key = _normalize_game_date_key((payload.get("meta") or {}).get("game_date"))
        if not date_key:
            continue
        totals_by_date[date_key] = {
            "attempts": int(team_stats.get("third_down_attempts") or 0),
            "conversions": int(team_stats.get("third_down_conversions") or 0),
            "source_path": str(path),
        }
    return totals_by_date


def _apply_raw_game_fourth_down_overrides(
    pbp_entry: dict | None,
    *,
    team_slug: str,
    team_name: str,
) -> None:
    if not isinstance(pbp_entry, dict):
        return
    games = [g for g in (pbp_entry.get("games") or []) if isinstance(g, dict)]
    if not games:
        return
    totals_by_date = _load_raw_game_fourth_down_totals(team_slug, team_name)
    if not totals_by_date:
        return
    for game in games:
        date_key = _normalize_game_date_key(game.get("date") or game.get("game_date"))
        row = totals_by_date.get(date_key)
        if not isinstance(row, dict):
            continue
        game["4th_down_attempts"] = int(row.get("attempts") or 0)
        game["4th_down_conversions"] = int(row.get("conversions") or 0)


def _apply_raw_game_third_down_overrides(
    pbp_entry: dict | None,
    *,
    team_slug: str,
    team_name: str,
) -> None:
    if not isinstance(pbp_entry, dict):
        return
    games = [g for g in (pbp_entry.get("games") or []) if isinstance(g, dict)]
    if not games:
        return
    totals_by_date = _load_raw_game_third_down_totals(team_slug, team_name)
    if not totals_by_date:
        return
    for game in games:
        date_key = _normalize_game_date_key(game.get("date") or game.get("game_date"))
        row = totals_by_date.get(date_key)
        if not isinstance(row, dict):
            continue
        game["third_down_attempts"] = int(row.get("attempts") or 0)
        game["third_down_conversions"] = int(row.get("conversions") or 0)


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


_VERIFICATION_METRIC_KEY_MAP = {
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


def _attach_cfbstats_snapshot(
    team_name: str,
    team_slug: str,
    pbp_entry: dict | None,
    snapshot_artifact: dict | None,
) -> None:
    if not isinstance(pbp_entry, dict):
        return
    pbp_entry.setdefault("cfbstats", {})
    pbp_entry["cfbstats"]["rankings"] = {"all": {}, "conf": {}, "nonconf": {}}
    pbp_entry["cfbstats"]["two_point_totals"] = {}

    team_snapshot = _artifact_team_entry(snapshot_artifact, team_slug, team_name)
    if not team_snapshot:
        return

    rankings = team_snapshot.get("rankings")
    if isinstance(rankings, dict):
        pbp_entry["cfbstats"]["rankings"] = rankings

    two_point_totals = team_snapshot.get("two_point_totals")
    if isinstance(two_point_totals, dict):
        pbp_entry["cfbstats"]["two_point_totals"] = two_point_totals

    conference = team_snapshot.get("conference")
    if isinstance(conference, str) and conference.strip():
        pbp_entry["conference"] = conference.strip()


def _verification_metric_note(metric: dict, known_gaps: dict) -> str | None:
    note = metric.get("note")
    reason_id = metric.get("reason_id")
    gap = known_gaps.get(reason_id) if isinstance(reason_id, str) and isinstance(known_gaps, dict) else None
    title = gap.get("title") if isinstance(gap, dict) else None
    description = gap.get("description") if isinstance(gap, dict) else None
    if note and title:
        return f"{note} [{title}]"
    if note:
        return note
    if title and description:
        return f"{title}: {description}"
    if title:
        return str(title)
    return None


def _verification_from_artifact(
    team_name: str,
    team_slug: str,
    verification_artifact: dict | None,
) -> dict:
    team_report = _artifact_team_entry(verification_artifact, team_slug, team_name)
    known_gaps = verification_artifact.get("known_gaps") if isinstance(verification_artifact, dict) else {}
    if not isinstance(known_gaps, dict):
        known_gaps = {}
    if not isinstance(team_report, dict):
        return {"summary": {}, "metrics": [], "known_gaps": known_gaps}

    raw_metrics = team_report.get("metrics")
    if not isinstance(raw_metrics, dict):
        raw_metrics = {}

    metrics: list[dict] = []
    summary = {"match": 0, "mismatch": 0, "missing_source": 0, "missing_derived": 0, "special_case": 0}
    for raw_key, metric in raw_metrics.items():
        if not isinstance(metric, dict):
            continue
        raw_status = str(metric.get("status") or "")
        if raw_status in {"missing_cfbstats_team", "invalid_cfbstats_value"}:
            status = "missing_source"
        elif raw_status in {"missing_bundle_category", "missing_bundle_value", "invalid_bundle_row"}:
            status = "missing_derived"
        else:
            status = raw_status
        if status in summary:
            summary[status] += 1
        comparison = metric.get("comparison") if isinstance(metric.get("comparison"), dict) else {}
        metrics.append(
            {
                "key": _VERIFICATION_METRIC_KEY_MAP.get(raw_key, raw_key),
                "artifact_key": raw_key,
                "label": metric.get("label") or raw_key,
                "status": status,
                "result": metric.get("result"),
                "derived": comparison.get("parser_value"),
                "source": comparison.get("cfbstats_value"),
                "delta": comparison.get("delta"),
                "tolerance": comparison.get("tolerance"),
                "reason_id": metric.get("reason_id"),
                "note": _verification_metric_note(metric, known_gaps),
            }
        )

    summary["total"] = len(metrics)
    metric_results = team_report.get("summary", {}).get("metric_results") if isinstance(team_report.get("summary"), dict) else {}
    if isinstance(metric_results, dict):
        summary["pass"] = int(metric_results.get("pass") or 0)
        summary["warning"] = int(metric_results.get("warning") or 0)
        summary["fail"] = int(metric_results.get("fail") or 0)

    return {
        "summary": summary,
        "metrics": metrics,
        "known_gaps": known_gaps,
        "result": team_report.get("result"),
        "team_slug": team_report.get("team_slug") or team_slug,
    }


def _down_rate_parity_gap(
    team_name: str,
    pbp_entry: dict | None,
    *,
    attempts_key: str,
    conversions_key: str,
    ranking_key: str,
    label: str,
    threshold: float,
) -> str | None:
    if not isinstance(pbp_entry, dict):
        return None
    games = [g for g in (pbp_entry.get("games") or []) if isinstance(g, dict)]
    attempts = sum(int(g.get(attempts_key) or 0) for g in games)
    conversions = sum(int(g.get(conversions_key) or 0) for g in games)
    if attempts <= 0:
        return None
    pbp_pct = round((conversions / attempts) * 100.0, 1)

    rankings = ((pbp_entry.get("cfbstats") or {}).get("rankings") or {}).get("all") or {}
    cfb_row = rankings.get(ranking_key) if isinstance(rankings, dict) else {}
    cfb_value = _to_float_number((cfb_row or {}).get("value"))
    if cfb_value is None:
        return None
    cfb_pct = round(float(cfb_value), 1)
    delta = round(pbp_pct - cfb_pct, 1)
    if abs(delta) < threshold:
        return None
    return (
        f"{team_name}: {label} parity delta {delta:+.1f} pts "
        f"(PBP {conversions}/{attempts}={pbp_pct}% vs CFBStats {cfb_pct}%)"
    )


def _third_down_parity_gap(team_name: str, pbp_entry: dict | None, threshold: float = 0.25) -> str | None:
    return _down_rate_parity_gap(
        team_name,
        pbp_entry,
        attempts_key="third_down_attempts",
        conversions_key="third_down_conversions",
        ranking_key="third_down",
        label="3rd-down",
        threshold=threshold,
    )


def _fourth_down_parity_gap(team_name: str, pbp_entry: dict | None, threshold: float = 1.0) -> str | None:
    return _down_rate_parity_gap(
        team_name,
        pbp_entry,
        attempts_key="4th_down_attempts",
        conversions_key="4th_down_conversions",
        ranking_key="fourth_down",
        label="4th-down",
        threshold=threshold,
    )


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
        resolver = _build_play_side_resolver(g, team_aliases=team_aliases, opp_aliases=_abbr_set(opp_abbr))
        for play in _iter_play_tree_plays(g.get("play_tree") or []):
            if play.get("is_no_play"):
                continue
            offense_side = resolver.resolve(play.get("offense"))
            desc = str(play.get("description") or "").upper()
            yards = play.get("yards")
            if "SACK" in desc:
                if offense_side == "team":
                    sacks_allowed += 1
                elif offense_side == "opp":
                    sacks_forced += 1
            if isinstance(yards, (int, float)) and yards < 0 and "RUSH" in desc:
                if offense_side == "team":
                    tfl_allowed += 1
                elif offense_side == "opp":
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
        "source_points_off_turnovers_for": xml_pot.get("points_off_turnovers", "N/A"),
        "source_points_off_turnovers_against": xml_pot.get("points_off_turnovers_allowed", "N/A"),
        "source_post_turnover_drives_for": xml_pot.get("pot_drives", "N/A"),
        "source_post_turnover_drives_against": xml_pot.get("pot_drives_allowed", "N/A"),
        "last3_turnovers_gained": xml_tov.get("last_n_turnovers_forced", "N/A"),
        "last3_turnovers_lost": xml_tov.get("last_n_turnovers", "N/A"),
        "last3_points_off_turnovers_for": xml_pot.get("last_3_points_off_turnovers", "N/A"),
        "last3_points_off_turnovers_against": xml_pot.get("last_3_points_off_turnovers_allowed", "N/A"),
        "last3_post_turnover_drives_for": xml_pot.get("last_3_pot_drives", "N/A"),
        "last3_post_turnover_drives_against": xml_pot.get("last_3_pot_drives_allowed", "N/A"),
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


def _build_provider_entry(
    provider_name: str,
    values: dict,
    *,
    reasons: list[str] | None = None,
) -> dict:
    keys = ENRICHMENT_PROVIDER_KEYS[provider_name]
    return {
        "status": _provider_status_for_values(values, keys),
        "fields": {key: values.get(key, "N/A") for key in keys},
        "reasons": [reason for reason in (reasons or []) if reason],
    }


def _fetch_blitz_stats(team_slug: str, team_name: str | None = None) -> tuple[dict, dict]:
    """Fetch blitz season/last3 values from yr-data-api. Returns N/A on failure."""
    if not team_slug and not team_name:
        out = {"blitz_pct": "N/A", "blitz_pct_last3": "N/A"}
        return out, _build_provider_entry("blitz", out, reasons=["no_team_identifier"])

    candidates = _candidate_team_ids(team_slug, team_name)

    out = {"blitz_pct": "N/A", "blitz_pct_last3": "N/A"}
    reasons: list[str] = []

    for scope_key, scope in (("blitz_pct", "season"), ("blitz_pct_last3", "last3")):
        result = _fetch_text_result_from_candidates(candidates, f"pff/blitz?scope={scope}&format=text")
        text = result.get("text")
        if text:
            out[scope_key] = text
        else:
            reasons.append(f"{scope_key}:{result.get('reason') or 'unavailable'}")

    return out, _build_provider_entry("blitz", out, reasons=reasons)


def _fetch_negative_play_stats(team_slug: str, team_name: str | None = None) -> tuple[dict, dict]:
    """Fetch offensive/defensive negative plays (season + last3) from yr-data-api."""
    if not team_slug and not team_name:
        out = {
            "negative_plays_pg_api": "N/A",
            "negative_plays_forced_pg_api": "N/A",
            "negative_plays_pg_last3_api": "N/A",
            "negative_plays_forced_pg_last3_api": "N/A",
        }
        return out, _build_provider_entry("negative_plays", out, reasons=["no_team_identifier"])

    candidates = _candidate_team_ids(team_slug, team_name)

    out = {
        "negative_plays_pg_api": "N/A",
        "negative_plays_forced_pg_api": "N/A",
        "negative_plays_pg_last3_api": "N/A",
        "negative_plays_forced_pg_last3_api": "N/A",
    }
    reasons: list[str] = []

    endpoint_specs = [
        ("negative_plays_pg_api", "pbp/negative-plays?side=off&scope=season&format=text"),
        ("negative_plays_forced_pg_api", "pbp/negative-plays?side=def&scope=season&format=text"),
        ("negative_plays_pg_last3_api", "pbp/negative-plays?side=off&scope=last3&format=text"),
        ("negative_plays_forced_pg_last3_api", "pbp/negative-plays?side=def&scope=last3&format=text"),
    ]

    for key, suffix in endpoint_specs:
        result = _fetch_text_result_from_candidates(candidates, suffix)
        text = result.get("text")
        if text:
            out[key] = text
        else:
            reasons.append(f"{key}:{result.get('reason') or 'unavailable'}")

    return out, _build_provider_entry("negative_plays", out, reasons=reasons)


def _fetch_pff_snapshot(team_slug: str, team_name: str | None = None) -> tuple[dict, dict]:
    """Fetch compact PFF metrics used in callout blocks."""
    if not team_slug and not team_name:
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
        return out, _build_provider_entry("pff", out, reasons=["no_team_identifier"])

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
    reasons: list[str] = []

    def _try_fetch(suffix: str) -> dict[str, object]:
        return _fetch_text_result_from_candidates(candidates, suffix)

    def _try_fetch_json(suffix: str) -> dict[str, object]:
        return _fetch_json_result_from_candidates(candidates, suffix)

    def _parse_float(value: object) -> float | None:
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _parse_games_played() -> int | None:
        games_result = _try_fetch("games-played?format=text")
        text = games_result.get("text")
        try:
            games = int(float(str(text).strip()))
        except (TypeError, ValueError, AttributeError):
            if games_result.get("reason"):
                reasons.append(f"pff_games_played:{games_result.get('reason')}")
            return None
        return games if games > 0 else None

    def _per_game_value(
        total_value: object,
        per_game_value: object,
        *,
        games: int | None,
    ) -> str:
        per_game = _parse_float(per_game_value)
        total = _parse_float(total_value)
        if per_game is not None and per_game > 0:
            return f"{per_game:.1f}"
        if total is not None and games:
            return f"{round(total / games, 1):.1f}"
        return "N/A"

    games_played = _parse_games_played()

    plays_off_result = _try_fetch("pff/plays?side=off&format=text")
    plays_off = plays_off_result.get("text")
    if plays_off:
        out["pff_plays_offense_pg"] = str(plays_off).strip() or "N/A"
    else:
        reasons.append(f"pff_plays_off:{plays_off_result.get('reason') or 'unavailable'}")

    plays_def_result = _try_fetch("pff/plays?side=def&format=text")
    plays_def = plays_def_result.get("text")
    if plays_def:
        out["pff_plays_defense_pg"] = str(plays_def).strip() or "N/A"
    else:
        reasons.append(f"pff_plays_def:{plays_def_result.get('reason') or 'unavailable'}")

    tackling_json_result = _try_fetch_json("pff/tackling-per-game")
    tackling_payload = tackling_json_result.get("json")
    tackling_data = tackling_payload.get("data") if isinstance(tackling_payload, dict) else None
    if isinstance(tackling_data, dict):
        effective_games = int(_parse_float(tackling_data.get("games")) or 0) or games_played
        out["pff_missed_tackles_pg"] = _per_game_value(
            tackling_data.get("missed_tackles"),
            tackling_data.get("missed_tackles_per_game"),
            games=effective_games,
        )
        out["pff_tfl_pg"] = _per_game_value(
            tackling_data.get("tfl"),
            tackling_data.get("tfl_per_game"),
            games=effective_games,
        )
        out["pff_sacks_pg"] = _per_game_value(
            tackling_data.get("sacks"),
            tackling_data.get("sacks_per_game"),
            games=effective_games,
        )
        if all(out[key] == "N/A" for key in ("pff_missed_tackles_pg", "pff_tfl_pg", "pff_sacks_pg")):
            reasons.append("pff_tackling:zero_placeholder_response")
    else:
        tackling_result = _try_fetch("pff/tackling-per-game?format=text")
        tackling_pg = tackling_result.get("text")
        if tackling_pg:
            parts = [p.strip() for p in str(tackling_pg).split("\t")]
            if len(parts) >= 4 and games_played:
                out["pff_missed_tackles_pg"] = _per_game_value(parts[0], None, games=games_played)
                out["pff_tfl_pg"] = _per_game_value(parts[1], None, games=games_played)
                out["pff_sacks_pg"] = _per_game_value(parts[2], None, games=games_played)
            elif len(parts) >= 3:
                first_three = parts[:3]
                if all(part in {"0", "0.0", "0.00"} for part in first_three):
                    reasons.append("pff_tackling:zero_placeholder_response")
                else:
                    out["pff_missed_tackles_pg"] = first_three[0] or "N/A"
                    out["pff_tfl_pg"] = first_three[1] or "N/A"
                    out["pff_sacks_pg"] = first_three[2] or "N/A"
            else:
                reasons.append("pff_tackling:malformed_payload")
        else:
            reasons.append(f"pff_tackling:{tackling_result.get('reason') or 'unavailable'}")

    sacks_allowed_json_result = _try_fetch_json("pff/sacks-allowed")
    sacks_allowed_payload = sacks_allowed_json_result.get("json")
    sacks_allowed_data = sacks_allowed_payload.get("data") if isinstance(sacks_allowed_payload, dict) else None
    if isinstance(sacks_allowed_data, dict):
        effective_games = int(_parse_float(sacks_allowed_data.get("games")) or 0) or games_played
        out["pff_sacks_allowed_pg"] = _per_game_value(
            sacks_allowed_data.get("sacks_allowed"),
            sacks_allowed_data.get("sacks_allowed_per_game"),
            games=effective_games,
        )
    else:
        sacks_allowed_result = _try_fetch("pff/sacks-allowed?format=text")
        sacks_allowed = sacks_allowed_result.get("text")
        if sacks_allowed:
            total_or_pg = _parse_float(sacks_allowed)
            if total_or_pg is not None and total_or_pg > 5 and games_played:
                out["pff_sacks_allowed_pg"] = _per_game_value(total_or_pg, None, games=games_played)
            else:
                out["pff_sacks_allowed_pg"] = str(sacks_allowed).strip()
        else:
            reasons.append(f"pff_sacks_allowed:{sacks_allowed_result.get('reason') or 'unavailable'}")

    fmt_json_result = _try_fetch_json("pff/fmt")
    fmt_payload = fmt_json_result.get("json")
    fmt_data = fmt_payload.get("data") if isinstance(fmt_payload, dict) else None
    if isinstance(fmt_data, dict):
        total = _parse_float(fmt_data.get("fmt"))
        effective_games = int(_parse_float(fmt_data.get("games")) or 0) or games_played
        out["pff_fmt_total"] = str(int(total)) if total is not None else "N/A"
        out["pff_fmt_pg"] = _per_game_value(
            fmt_data.get("fmt"),
            fmt_data.get("fmt_per_game"),
            games=effective_games,
        )
    else:
        fmt_result = _try_fetch("pff/fmt?format=text")
        fmt = fmt_result.get("text")
        if fmt:
            parts = [p.strip() for p in str(fmt).split("\t")]
            if len(parts) >= 2:
                out["pff_fmt_total"] = parts[0] or "N/A"
                out["pff_fmt_pg"] = parts[1] or "N/A"
            elif len(parts) == 1:
                total = _parse_float(parts[0])
                out["pff_fmt_total"] = parts[0] or "N/A"
                out["pff_fmt_pg"] = _per_game_value(total, None, games=games_played)
            else:
                reasons.append("pff_fmt:malformed_payload")
        else:
            reasons.append(f"pff_fmt:{fmt_result.get('reason') or 'unavailable'}")

    play_clock_result = _try_fetch("pff/play-clock?format=text")
    play_clock = play_clock_result.get("text")
    if play_clock:
        parts = [p.strip() for p in str(play_clock).split("\t")]
        if len(parts) >= 1:
            out["pff_avg_play_clock"] = parts[0] or "N/A"
        if len(parts) >= 2:
            try:
                hurry_pct = round(float(parts[1]) * 100, 1)
                out["pff_hurry_up_pct"] = f"{hurry_pct}%"
            except (ValueError, TypeError):
                out["pff_hurry_up_pct"] = "N/A"
                reasons.append("pff_play_clock:invalid_hurry_up_pct")
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
            reasons.append("pff_play_clock:invalid_avg_play_clock")
    else:
        reasons.append(f"pff_play_clock:{play_clock_result.get('reason') or 'unavailable'}")

    return out, _build_provider_entry("pff", out, reasons=reasons)


def _fetch_live_enrichment(team_slug: str, team_name: str | None = None) -> tuple[dict, dict]:
    payload: dict = {}
    providers: dict = {}

    blitz_values, blitz_provider = _fetch_blitz_stats(team_slug, team_name=team_name)
    payload.update(blitz_values)
    providers["blitz"] = blitz_provider

    negative_values, negative_provider = _fetch_negative_play_stats(team_slug, team_name=team_name)
    payload.update(negative_values)
    providers["negative_plays"] = negative_provider

    pff_values, pff_provider = _fetch_pff_snapshot(team_slug, team_name=team_name)
    payload.update(pff_values)
    providers["pff"] = pff_provider

    return payload, providers


def _enrichment_has_signal(payload: dict) -> bool:
    return any(_has_enrichment_signal(payload.get(k)) for k in ENRICHMENT_KEYS)


def normalize_enrichment_payload(payload: dict) -> dict:
    normalized: dict = {}
    if not isinstance(payload, dict):
        return normalized
    for slug, raw in payload.items():
        if not isinstance(slug, str) or not isinstance(raw, dict):
            continue
        out = dict(raw)
        provider_payload = _normalize_provider_payload(out, out.get("_providers"))
        out["_providers"] = provider_payload
        status = str(out.get("_status") or "").strip().lower()
        if status not in {"ok", "unavailable"}:
            out["_status"] = _overall_enrichment_status(out, provider_payload)
        if "_source" not in out:
            out["_source"] = "artifact"
        normalized[slug] = out
    return normalized


def validate_enrichment_payload(payload: dict, required_team_slugs: list[str]) -> dict:
    normalized = normalize_enrichment_payload(payload)
    missing = [slug for slug in required_team_slugs if slug not in normalized]
    if missing:
        raise ValueError(f"missing teams: {', '.join(missing)}")
    return normalized


def build_team_enrichment(team_slug: str, team_name: str | None = None) -> dict:
    data, providers = _fetch_live_enrichment(team_slug, team_name=team_name)
    return {
        **data,
        "_providers": providers,
        "_fetched_at": datetime.now(timezone.utc).isoformat(),
        "_source": "yr-data-api",
        "_status": _overall_enrichment_status(data, providers),
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
        return normalize_enrichment_payload(data)
    except Exception:
        return {}


def write_enrichment_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def merge_enrichment_payload(existing: dict, refreshed: dict) -> dict:
    """Preserve prior non-empty enrichment values when live refresh is unavailable."""
    merged: dict = normalize_enrichment_payload(existing or {})
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
        out["_providers"] = _normalize_provider_payload(out, incoming.get("_providers"))
        out["_status"] = _overall_enrichment_status(out, out.get("_providers"))
        merged[slug] = out
    return merged


def compute_last_n_stats(games: list[dict], n: int = 3, team_aliases: object = None) -> dict:
    sorted_games = sorted(games, key=lambda g: g.get("game_number", 0), reverse=True)
    last_games = sorted_games[:n]
    actual_n = len(last_games)
    resolved_team_aliases = _abbr_set(team_aliases)

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
            resolver = _build_play_side_resolver(
                g,
                team_aliases=resolved_team_aliases,
                opp_aliases=_abbr_set(g.get("opponent_abbr")),
            )
            for q in g.get("play_tree") or []:
                for drive in q.get("drives") or []:
                    for p in drive.get("plays") or []:
                        if p.get("is_no_play"):
                            continue
                        # Opponent offense snaps are our defense snaps faced.
                        if resolver.resolve(p.get("offense")) == "opp":
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
            token = re.sub(
                r"[^A-Z0-9]",
                "",
                str(p.get("team") or p.get("penalized_team") or "").upper(),
            )
            if not token:
                token = _extract_penalty_team_token(str(p.get("description") or ""))
            if token and resolved_team_aliases and token not in resolved_team_aliases:
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
        "gained": _pick_int(xml_tov.get("turnovers_forced"), None),
        "lost": _pick_int(xml_tov.get("turnovers"), None),
        "int_lost": _pick_int(xml_tov.get("interceptions"), None),
        "fum_lost": _pick_int(xml_tov.get("fumbles_lost"), None),
        "pot_for": _pick_int(xml_pot.get("points_off_turnovers"), None),
        "pot_against": _pick_int(xml_pot.get("points_off_turnovers_allowed"), None),
    }
    if isinstance(game_recon, list) and game_recon and len(game_recon) == len(games):
        cfb_from_games = {
            "gained": 0,
            "lost": 0,
            "int_gained": 0,
            "int_lost": 0,
            "fum_gained": 0,
            "fum_lost": 0,
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
        cfb_totals["int_lost"] = int(cfb_from_games["int_lost"])
        cfb_totals["fum_lost"] = int(cfb_from_games["fum_lost"])
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
    opponent_counts: dict[str, int] = {}
    for game in games:
        opp = str(game.get("opponent_abbr") or "").upper().strip()
        if opp:
            opponent_counts[opp] = opponent_counts.get(opp, 0) + 1

    report: list[dict] = []
    for game in games:
        opp = str(game.get("opponent_abbr") or "").upper()
        if not opp:
            continue
        tov_row = tov_cat.get(opp) if isinstance(tov_cat.get(opp), dict) else {}
        pot_row = pot_cat.get(opp) if isinstance(pot_cat.get(opp), dict) else {}
        if opponent_counts.get(opp, 0) > 1:
            if isinstance(tov_row, dict) and isinstance(tov_row.get("games"), (int, float)) and int(tov_row.get("games") or 0) > 1:
                continue
            if isinstance(pot_row, dict) and isinstance(pot_row.get("games"), (int, float)) and int(pot_row.get("games") or 0) > 1:
                continue
        if not tov_row and not pot_row:
            continue

        pbp = {
            "gained": int(game.get("turnovers_gained") or 0),
            "lost": int(game.get("turnovers_lost") or 0),
            "int_gained": int(game.get("interceptions_gained") or 0),
            "int_lost": int(game.get("interceptions_lost") or 0),
            "fum_gained": int(game.get("fumbles_gained") or 0),
            "fum_lost": int(game.get("fumbles_lost") or 0),
            "pot_for": int(game.get("points_off_turnovers_for") or 0),
            "pot_against": int(game.get("points_off_turnovers_against") or 0),
        }
        # Opponent-keyed XML game rows are stored in opponent perspective.
        # Convert to team perspective for apples-to-apples reconciliation.
        cfb = {
            "gained": int(tov_row.get("turnovers") or 0),
            "lost": int(tov_row.get("turnovers_forced") or 0),
            "int_gained": int(tov_row.get("interceptions") or 0),
            "int_lost": int(tov_row.get("interceptions_forced") or 0),
            "fum_gained": int(tov_row.get("fumbles_lost") or 0),
            "fum_lost": int(tov_row.get("fumbles_recovered") or 0),
            "pot_for": int(pot_row.get("points_off_turnovers_allowed") or 0),
            "pot_against": int(pot_row.get("points_off_turnovers") or 0),
        }
        delta = {k: pbp[k] - cfb[k] for k in pbp.keys()}
        count_keys = {"gained", "lost", "int_gained", "int_lost", "fum_gained", "fum_lost"}
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
    resolver = _build_play_side_resolver(game, team_aliases=team_aliases, opp_aliases=opp_aliases)
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
                resolved_side = resolver.resolve(offense)
                offense_side = resolved_side if resolved_side in {"team", "opp"} else None
                recovery_side = _turnover_recovery_side(
                    desc_up,
                    offense_side,
                    turnover_type,
                    set(resolver.team_aliases),
                    set(resolver.opp_aliases),
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
    allow_live_enrichment: bool | None = None,
    cfbstats_snapshot: dict | None = None,
    cfbstats_verification_report: dict | None = None,
) -> dict:
    school_slug = slugify(team_name)
    if allow_live_enrichment:
        print(
            "[warn] allow_live_enrichment is deprecated and ignored; use an enrichment artifact or --refresh-enrichment.",
            file=sys.stderr,
        )
    pbp_entry = get_team_pbp(pbp_teams, team_name, school_slug)
    if pbp_entry:
        _attach_cfbstats_snapshot(team_name, school_slug, pbp_entry, cfbstats_snapshot)
        parity_gaps = _apply_special_teams_play_tree_derivations(team_name, pbp_entry)
        _apply_turnover_xml_game_overrides(pbp_entry)
        _apply_raw_game_third_down_overrides(
            pbp_entry,
            team_slug=school_slug,
            team_name=team_name,
        )
        _apply_raw_game_fourth_down_overrides(
            pbp_entry,
            team_slug=school_slug,
            team_name=team_name,
        )
    else:
        parity_gaps = []
    parity_gaps.extend(_collect_parity_gaps(team_name, pbp_entry))
    alias_warnings = _collect_play_tree_alias_warnings(team_name, pbp_entry)
    parity_gaps.extend(alias_warnings)
    third_down_gap = _third_down_parity_gap(team_name, pbp_entry)
    if third_down_gap:
        parity_gaps.append(third_down_gap)
    fourth_down_gap = _fourth_down_parity_gap(team_name, pbp_entry)
    if fourth_down_gap:
        parity_gaps.append(fourth_down_gap)
    pbp_stats = _extract_pbp_stats(pbp_entry) if pbp_entry else {}
    raw_seeded = (enrichment_by_slug or {}).get(school_slug)
    seeded = (
        normalize_enrichment_payload({school_slug: raw_seeded}).get(school_slug, {})
        if isinstance(raw_seeded, dict)
        else {}
    )
    if isinstance(seeded, dict):
        for key in ENRICHMENT_KEYS:
            value = seeded.get(key)
            if value not in (None, ""):
                pbp_stats[key] = value
    games = pbp_entry.get("games", []) if pbp_entry else []
    cfbstats_verification = (
        _verification_from_artifact(team_name, school_slug, cfbstats_verification_report)
        if pbp_entry
        else {"summary": {}, "metrics": [], "known_gaps": {}}
    )
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
        if third_down_gap:
            print(f"[warn] {third_down_gap}", file=sys.stderr)
        if fourth_down_gap:
            print(f"[warn] {fourth_down_gap}", file=sys.stderr)
        for warning in alias_warnings:
            print(f"[warn] {warning}", file=sys.stderr)
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
    last_n_stats = compute_last_n_stats(
        games,
        last_n,
        team_aliases=(
            pbp_entry.get("abbr_aliases") or pbp_entry.get("abbr")
            if isinstance(pbp_entry, dict)
            else None
        ),
    )
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
    if isinstance(pbp_stats.get("last3_points_off_turnovers_for"), (int, float)):
        last_n_stats["points_off_turnovers_for"] = int(pbp_stats["last3_points_off_turnovers_for"])
    if isinstance(pbp_stats.get("last3_points_off_turnovers_against"), (int, float)):
        last_n_stats["points_off_turnovers_against"] = int(pbp_stats["last3_points_off_turnovers_against"])
    if isinstance(pbp_stats.get("last3_post_turnover_drives_for"), (int, float)):
        last_n_stats["post_turnover_drives_for"] = int(pbp_stats["last3_post_turnover_drives_for"])
    if isinstance(pbp_stats.get("last3_post_turnover_drives_against"), (int, float)):
        last_n_stats["post_turnover_drives_against"] = int(pbp_stats["last3_post_turnover_drives_against"])
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
        "enrichment": seeded,
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
