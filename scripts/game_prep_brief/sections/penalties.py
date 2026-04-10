from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from ..loaders import _build_play_side_resolver, slugify
from ._sources import SRC_PBP, SRC_CFB

PROCEDURAL_TERMS = (
    "false start",
    "offside",
    "offsides",
    "encroachment",
    "neutral zone infraction",
    "delay of game",
    "illegal formation",
    "illegal procedure",
    "illegal motion",
    "illegal shift",
    "too many men",
    "illegal substitution",
)

_PENALTY_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("False Start", re.compile(r"\bFALSE\s+START\b", re.IGNORECASE)),
    ("Delay of Game", re.compile(r"\bDELAY\s+OF\s+GAME\b", re.IGNORECASE)),
    ("Illegal Formation", re.compile(r"\bILLEGAL\s+FORMATION\b", re.IGNORECASE)),
    ("Encroachment", re.compile(r"\bENCROACH(?:MENT)?\b", re.IGNORECASE)),
    ("Offsides", re.compile(r"\bOFFSIDE(?:S)?\b", re.IGNORECASE)),
    ("Neutral Zone Infraction", re.compile(r"\bNEUTRAL\s+ZONE\s+INFRACTION\b", re.IGNORECASE)),
    ("Holding", re.compile(r"\bHOLDING\b", re.IGNORECASE)),
    ("Face Mask", re.compile(r"\bFACE\s*MASK(?:ING)?\b|\bFACEMASK(?:ING)?\b", re.IGNORECASE)),
    (
        "Illegal Block in the Back",
        re.compile(r"\bILLEGAL\s+BLOCK\s+IN\s+THE\s+BACK\b|\bBLOCK\s+IN\s+THE\s+BACK\b", re.IGNORECASE),
    ),
    ("Illegal Block", re.compile(r"\bILLEGAL\s+(?:BLOCK|BLOCKING)\b", re.IGNORECASE)),
    (
        "Ineligible Downfield",
        re.compile(r"\bINELIGIBLE\s+(?:MAN\s+)?DOWNFIELD\b|\bINELIGIBLE\s+RECEIVER\s+DOWNFIELD\b", re.IGNORECASE),
    ),
    ("Pass Interference", re.compile(r"\b(?:DEFENSIVE\s+|OFFENSIVE\s+)?PASS\s+INTERFERENCE\b", re.IGNORECASE)),
    (
        "Roughing Passer",
        re.compile(r"\bROUGHING\s+(?:THE\s+)?PASSER\b|\bROUGHING\s+(?:THE\s+)?QB\b", re.IGNORECASE),
    ),
    (
        "Unsportsmanlike Conduct",
        re.compile(r"\bUNSPORTSMANLIKE\s+CONDUCT\b|\bUNSPORTSMANLIKE\b|\bUNS\b", re.IGNORECASE),
    ),
    ("Targeting", re.compile(r"\bTARGETING\b", re.IGNORECASE)),
    ("Personal Foul", re.compile(r"\bPERSONAL\s+FOUL\b", re.IGNORECASE)),
]

_PENALTY_CLAUSE_START_RE = re.compile(
    r"(?:(?P<penalty_prefix>\bPENALTY\s+BEFORE\s+THE\s+SNAP,\s*|\bPENALTY\s+ON\s+|\bPENALTY\s+)"
    r"|(?P<continuation>\b(?:DECLINED|OFFSETTING|ACCEPTED)\s+))(?P<team>[A-Z0-9-]{2,8})\b",
    re.IGNORECASE,
)


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", [])


def _normalize_name_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _normalize_game_date(value: object) -> str:
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
    base = Path(__file__).resolve()
    candidates = [
        base.parents[4] / "pbp-parser" / "data" / "statbroadcast_game_briefs",
        base.parents[3] / "data" / "statbroadcast_game_briefs",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=None)
def _load_raw_game_penalty_totals(team_slug: str, team_name: str) -> dict[str, dict]:
    root = _raw_game_briefs_root()
    if root is None:
        return {}

    team_dir = root / team_slug
    if not team_dir.exists():
        return {}

    team_name_norm = _normalize_name_token(team_name)
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
                for idx, name in enumerate(team_names)
                if _normalize_name_token(name) == team_name_norm
            ),
            None,
        )
        if team_idx is None:
            continue

        team_token = str(teams[team_idx] or "").upper().strip()
        if not team_token:
            continue

        team_stats = (payload.get("team_stats") or {}).get(team_token) or {}
        penalty_summary = (payload.get("penalty_summary") or {}).get(team_token) or {}
        total_count = penalty_summary.get("total_penalties")
        total_yards = penalty_summary.get("total_penalty_yards")
        if total_count is None:
            total_count = team_stats.get("penalties")
        if total_yards is None:
            total_yards = team_stats.get("penalty_yards")
        if total_count is None and total_yards is None:
            continue

        date_key = _normalize_game_date((payload.get("meta") or {}).get("game_date"))
        if not date_key:
            continue
        totals_by_date[date_key] = {
            "total_count": int(total_count or 0),
            "total_yards": int(total_yards or 0),
            "source_path": str(path),
        }
    return totals_by_date


def _game_penalty_totals_source(team: dict) -> dict[str, dict]:
    injected = team.get("penalty_totals_by_game")
    if isinstance(injected, dict):
        return injected

    pbp = team.get("pbp_entry") or {}
    injected = pbp.get("penalty_totals_by_game")
    if isinstance(injected, dict):
        return injected

    team_name = str(team.get("display_name") or pbp.get("name") or "").strip()
    team_slug = str(team.get("slug") or slugify(team_name)).strip()
    if not team_name or not team_slug:
        return {}
    return _load_raw_game_penalty_totals(team_slug, team_name)


def _official_penalty_totals_for_game(team: dict, game: dict) -> dict | None:
    sources = _game_penalty_totals_source(team)
    if not sources:
        return None

    date_key = _normalize_game_date(game.get("date") or game.get("game_date"))
    opponent = str(game.get("opponent") or game.get("opponent_abbr") or "").strip()
    game_number = game.get("game_number")
    candidates = [
        f"date:{date_key}",
        date_key,
        f"opp:{opponent}",
        opponent,
    ]
    if isinstance(game_number, int):
        candidates.extend([f"game:{game_number}", game_number])
    for key in candidates:
        row = sources.get(key)
        if isinstance(row, dict):
            return row
    return None


def _abbr_set(value: object) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        cleaned = re.sub(r"[^A-Z0-9]", "", value.upper())
        return {cleaned} if cleaned else set()
    if isinstance(value, (list, tuple, set)):
        out: set[str] = set()
        for item in value:
            out.update(_abbr_set(item))
        return out
    return set()


def _extract_penalized_team_token(desc: str) -> str:
    upper = desc.upper()
    patterns = [
        r"\bPENALTY\s+BEFORE\s+THE\s+SNAP,\s*([A-Z0-9]{2,8})\b",
        r"\bPENALTY\s+ON\s+([A-Z0-9]{2,6})\b",
        r"\bPENALTY\s+([A-Z0-9]{2,6})\b",
    ]
    for pat in patterns:
        m = re.search(pat, upper)
        if m:
            return re.sub(r"[^A-Z0-9]", "", m.group(1))
    return ""


def _penalty_team_token(pen: dict) -> str:
    token = pen.get("team") or pen.get("penalized_team") or ""
    normalized = re.sub(r"[^A-Z0-9]", "", str(token).upper())
    if normalized:
        return normalized
    return _extract_penalized_team_token(str(pen.get("description") or ""))


def _penalty_yards_from_text(desc: str) -> int:
    enforced = re.search(
        r"\bENFORCED(?:\s+AT\s+THE\s+SPOT\s+OF\s+THE\s+FOUL\s+FOR)?\s+(\d+)\s+YARDS?\b",
        desc,
        re.IGNORECASE,
    )
    if enforced:
        return int(enforced.group(1))
    tail = re.split(r"\bPENALTY\b", desc, flags=re.IGNORECASE)[-1]
    match = re.search(r"(\d+)\s+YARDS?", tail, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _split_penalty_clauses(desc: str) -> list[str]:
    review_marker = desc.upper().find("ORIGINAL PLAY:")
    if review_marker != -1 and desc.upper().find("PENALTY", review_marker) != -1:
        desc = desc[:review_marker].rstrip(" (")

    upper = desc.upper()
    if "PENALTY" not in upper:
        return []

    matches = list(_PENALTY_CLAUSE_START_RE.finditer(desc))
    if not matches:
        return [desc]

    clauses: list[str] = []
    for idx, match in enumerate(matches):
        end = len(desc)
        if idx + 1 < len(matches):
            next_match = matches[idx + 1]
            end = (
                next_match.start("team")
                if next_match.group("continuation")
                else next_match.start("penalty_prefix")
            )
        if match.group("penalty_prefix"):
            clause = desc[match.start("penalty_prefix"):end]
        else:
            clause = f"PENALTY {desc[match.start('team'):end]}"
        clause = clause.strip(" ,;.")
        if clause:
            clauses.append(clause)
    return clauses


def _skip_non_enforced_penalty(desc: str, yards: int) -> bool:
    upper = desc.upper()
    if "DECLINED" in upper:
        return True
    return "OFFSETTING" in upper and yards == 0


def _penalty_side_from_text(desc: str, default: str = "unknown") -> str:
    normalized = default.lower().strip()
    if normalized in {"offense", "defense", "special_teams", "special"}:
        return "special_teams" if normalized == "special" else normalized

    upper = desc.upper()
    offense_terms = (
        "FALSE START",
        "DELAY OF GAME",
        "ILLEGAL FORMATION",
        "ILLEGAL SHIFT",
        "ILLEGAL MOTION",
        "ILLEGAL PROCEDURE",
        "ILLEGAL SUBSTITUTION",
        "INELIGIBLE",
        "INTENTIONAL GROUNDING",
        "OFFENSIVE HOLDING",
        "OFFENSIVE PASS INTERFERENCE",
    )
    defense_terms = (
        "DEFENSIVE HOLDING",
        "DEFENSIVE PASS INTERFERENCE",
        "OFFSIDE",
        "OFFSIDES",
        "ENCROACHMENT",
        "NEUTRAL ZONE INFRACTION",
    )
    if any(term in upper for term in offense_terms):
        return "offense"
    if any(term in upper for term in defense_terms):
        return "defense"
    if "PASS INTERFERENCE" in upper:
        return "defense"
    return normalized or "unknown"


def _resolve_penalty_owner(
    token: str,
    penalty_side: str,
    offense_side: str | None,
    *,
    team_aliases: set[str],
    opp_aliases: set[str],
) -> str | None:
    if token and not team_aliases and token not in opp_aliases:
        return "team"
    if token in team_aliases:
        return "team"
    if token in opp_aliases:
        return "opp"
    if penalty_side == "offense" and offense_side in {"team", "opp"}:
        return offense_side
    if penalty_side == "defense" and offense_side in {"team", "opp"}:
        return "opp" if offense_side == "team" else "team"
    return None


def _game_penalty_aliases(base_team_aliases: set[str], game: dict) -> tuple[object, set[str], set[str]]:
    opp_aliases = _abbr_set(game.get("opponent_abbr") or game.get("opponent"))
    resolver = _build_play_side_resolver(game, team_aliases=base_team_aliases, opp_aliases=opp_aliases)
    team_tokens = set(base_team_aliases)
    team_tokens.update(
        token
        for token in resolver.team_aliases
        if token in base_team_aliases or token in resolver.offense_tokens
    )
    opp_tokens = set(opp_aliases)
    opp_tokens.update(token for token in resolver.opp_aliases if token in resolver.offense_tokens)
    return resolver, team_tokens, opp_tokens


def _penalty_stats_row(team: dict) -> dict | None:
    """Best available team penalty row from bundled stats payload."""
    pbp = team.get("pbp_entry") or {}
    stats = pbp.get("stats") or pbp.get("xml_stats") or {}
    penalties = stats.get("penalties") or {}
    if not isinstance(penalties, dict) or not penalties:
        return None
    rows = [v for v in penalties.values() if isinstance(v, dict)]
    if not rows:
        return None
    return max(rows, key=lambda r: int(r.get("games", 0) or 0))


def _simplify_penalty(pen: dict) -> str:
    desc = " ".join(
        str(v or "")
        for v in (
            pen.get("penalty_type"),
            pen.get("type"),
            pen.get("description"),
        )
        if v
    )
    for canonical, pattern in _PENALTY_TYPE_PATTERNS:
        if pattern.search(desc):
            return canonical

    m = re.search(r"PENALTY\s+\w+\s+([^\d\.]+)", desc, re.IGNORECASE)
    if m:
        text = m.group(1)
    else:
        text = pen.get("penalty_type") or pen.get("type") or desc
    text = re.sub(r"Penalty\s+", "", text, flags=re.IGNORECASE)
    # Remove player annotations and trailing notes that pollute infraction labels,
    # e.g. "Pass Interference (Prysock,Ephesians): ..."
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"\b(?:DECLINED|ACCEPTED|ENFORCED|NO PLAY)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAT THE DEADBALL SPOT\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bFOR\b\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*UNS\s*:\s*", "Unsportsmanlike Conduct ", text, flags=re.IGNORECASE)
    text = text.split(":", 1)[0]
    text = re.split(r"\s+\d", text)[0]
    text = text.replace("yards", "").replace("yard", "").strip()
    text = re.sub(r"[-–]+$", "", text).strip(" -,:;.")
    text = re.sub(r"\s{2,}", " ", text).strip()
    lower = text.lower()
    if "pass interference" in lower:
        return "Pass Interference"
    return text.title() if text else "Unknown"


def _penalty_group(pen: dict) -> str:
    category = str(pen.get("penalty_category") or "").lower()
    if category.startswith("pre_snap"):
        return "procedural"
    if category.startswith("post_snap") or category in {"special_teams", "conduct"}:
        return "live_ball"

    text = f"{pen.get('type') or ''} {pen.get('description') or ''}".lower()
    if any(term in text for term in PROCEDURAL_TERMS):
        return "procedural"
    return "live_ball"


def _aggregate(team: dict) -> dict:
    stats_row = _penalty_stats_row(team)
    games = _games(team)
    pbp = team.get("pbp_entry") or {}
    team_aliases = _abbr_set(pbp.get("abbr_aliases") or pbp.get("abbr"))
    total = 0
    yards = 0
    by_side = defaultdict(lambda: {"count": 0, "yards": 0})
    by_group = defaultdict(lambda: {"count": 0, "yards": 0})
    by_type_count = Counter()
    by_type_yards = Counter()
    by_quarter = Counter()
    per_game = []
    pi_drawn = 0
    pi_allowed = 0
    off_holding = 0
    off_holding_yards = 0
    def_holding = 0
    def_holding_yards = 0

    alias_votes_team = Counter()
    alias_votes_opp = Counter()
    game_penalty_payloads: list[tuple[dict, dict, list[dict], set[str], set[str]]] = []

    for g in games:
        resolver, known_team_aliases, known_opp_aliases = _game_penalty_aliases(team_aliases, g)
        game_row = {
            "game_number": g.get("game_number") or 0,
            "opponent": g.get("opponent") or "?",
            "date": g.get("date") or g.get("game_date") or "",
            "count": 0,
            "yards": 0,
            "procedural_count": 0,
            "procedural_yards": 0,
            "live_ball_count": 0,
            "live_ball_yards": 0,
            "official_count": None,
            "official_yards": None,
            "delta_count": 0,
            "delta_yards": 0,
            "official_source_path": "",
        }
        penalty_events: list[dict] = []
        details = g.get("penalty_details", []) or []
        for p in details:
            if not p.get("accepted", False):
                continue
            desc = str(p.get("description") or "")
            token = _penalty_team_token(p)
            y = int(p.get("yards", 0) or 0)
            if _skip_non_enforced_penalty(desc, y):
                continue
            penalty_side = _penalty_side_from_text(desc, default=str(p.get("offense_or_defense", "unknown") or "unknown"))
            ptype = _simplify_penalty(p)
            if ptype == "Holding":
                if penalty_side == "offense":
                    ptype = "Offensive Holding"
                elif penalty_side == "defense":
                    ptype = "Defensive Holding"
            group = _penalty_group(p)
            penalty_events.append(
                {
                    "token": token,
                    "yards": y,
                    "penalty_side": penalty_side,
                    "offense_side": None,
                    "ptype": ptype,
                    "group": group,
                    "quarter": p.get("quarter"),
                }
            )

        # Fallback: derive penalty type/count from play descriptions when detail rows are absent.
        if not details and isinstance(g.get("play_tree"), list):
            for q in g.get("play_tree") or []:
                for drive in q.get("drives") or []:
                    for play in drive.get("plays") or []:
                        desc = str(play.get("description") or "")
                        if "PENALTY" not in desc.upper():
                            continue
                        offense_side = resolver.resolve(play.get("offense"))
                        for clause in _split_penalty_clauses(desc):
                            token = _extract_penalized_team_token(clause.upper())
                            penalty_side = _penalty_side_from_text(clause)
                            yards_value = _penalty_yards_from_text(clause)
                            if _skip_non_enforced_penalty(clause, yards_value):
                                continue
                            if (
                                token
                                and token not in known_team_aliases
                                and token not in known_opp_aliases
                                and penalty_side in {"offense", "defense"}
                                and offense_side in {"team", "opp"}
                            ):
                                predicted = offense_side if penalty_side == "offense" else ("opp" if offense_side == "team" else "team")
                                if predicted == "team":
                                    alias_votes_team[token] += 1
                                else:
                                    alias_votes_opp[token] += 1

                            pen_obj = {"description": clause}
                            ptype = _simplify_penalty(pen_obj)
                            if ptype == "Holding":
                                if penalty_side == "offense":
                                    ptype = "Offensive Holding"
                                elif penalty_side == "defense":
                                    ptype = "Defensive Holding"
                            penalty_events.append(
                                {
                                    "token": token,
                                    "yards": yards_value,
                                    "penalty_side": penalty_side,
                                    "offense_side": offense_side if offense_side in {"team", "opp"} else None,
                                    "ptype": ptype,
                                    "group": _penalty_group(pen_obj),
                                    "quarter": play.get("quarter") if play.get("quarter") is not None else q.get("quarter"),
                                }
                            )

        game_penalty_payloads.append((g, game_row, penalty_events, known_team_aliases, known_opp_aliases))

    inferred_team_aliases = {
        token
        for token, votes in alias_votes_team.items()
        if votes >= 2 and votes > alias_votes_opp.get(token, 0)
    }
    inferred_opp_aliases = {
        token
        for token, votes in alias_votes_opp.items()
        if votes >= 2 and votes > alias_votes_team.get(token, 0)
    }

    for g, game_row, penalty_events, known_team_aliases, known_opp_aliases in game_penalty_payloads:
        game_team_aliases = set(known_team_aliases) | inferred_team_aliases
        game_opp_aliases = set(known_opp_aliases) | inferred_opp_aliases
        for event in penalty_events:
            owner = _resolve_penalty_owner(
                event["token"],
                event["penalty_side"],
                event["offense_side"],
                team_aliases=game_team_aliases,
                opp_aliases=game_opp_aliases,
            )
            if event["ptype"] == "Pass Interference" and (
                event["token"] in game_team_aliases or event["token"] in game_opp_aliases
            ):
                if owner == "team":
                    pi_allowed += 1
                elif owner == "opp":
                    pi_drawn += 1
            if owner != "team":
                continue

            y = int(event["yards"] or 0)
            penalty_side = event["penalty_side"]
            ptype = event["ptype"]
            group = event["group"]
            total += 1
            yards += y
            by_side[penalty_side]["count"] += 1
            by_side[penalty_side]["yards"] += y
            by_group[group]["count"] += 1
            by_group[group]["yards"] += y
            by_type_count[ptype] += 1
            by_type_yards[ptype] += y
            game_row["count"] += 1
            game_row["yards"] += y
            if group == "procedural":
                game_row["procedural_count"] += 1
                game_row["procedural_yards"] += y
            else:
                game_row["live_ball_count"] += 1
                game_row["live_ball_yards"] += y
            q = event.get("quarter")
            if q is not None:
                by_quarter[q] += 1
            if ptype == "Offensive Holding":
                off_holding += 1
                off_holding_yards += y
            elif ptype == "Defensive Holding":
                def_holding += 1
                def_holding_yards += y
        per_game.append(game_row)

    parsed_total_count = sum(r["count"] for r in per_game)
    parsed_total_yards = sum(r["yards"] for r in per_game)
    official_candidates: list[tuple[dict, int, int, str]] = []
    for game_row, game in zip(per_game, games):
        official = _official_penalty_totals_for_game(team, game)
        if not official:
            continue
        official_candidates.append(
            (
                game_row,
                int(official.get("total_count", game_row["count"]) or 0),
                int(official.get("total_yards", game_row["yards"]) or 0),
                str(official.get("source_path") or ""),
            )
        )

    apply_official_game_totals = bool(official_candidates)
    if stats_row and official_candidates:
        target_count = int(stats_row.get("total_penalties", parsed_total_count) or 0)
        target_yards = int(stats_row.get("total_penalty_yards", parsed_total_yards) or 0)
        adjusted_count = parsed_total_count + sum(official_count - row["count"] for row, official_count, _, _ in official_candidates)
        adjusted_yards = parsed_total_yards + sum(official_yards - row["yards"] for row, _, official_yards, _ in official_candidates)
        before_score = abs(target_count - parsed_total_count) + abs(target_yards - parsed_total_yards)
        after_score = abs(target_count - adjusted_count) + abs(target_yards - adjusted_yards)
        apply_official_game_totals = after_score < before_score

    season_unattributed_count = 0
    season_unattributed_yards = 0
    if apply_official_game_totals:
        for game_row, official_count, official_yards, source_path in official_candidates:
            game_row["official_count"] = official_count
            game_row["official_yards"] = official_yards
            game_row["delta_count"] = official_count - game_row["count"]
            game_row["delta_yards"] = official_yards - game_row["yards"]
            game_row["official_source_path"] = source_path
            if game_row["delta_count"] > 0:
                season_unattributed_count += game_row["delta_count"]
            if game_row["delta_yards"] > 0:
                season_unattributed_yards += game_row["delta_yards"]

    # Prefer bundle-level penalty rollups when available (source of truth).
    has_group_breakdown = False
    has_pi_breakdown = False
    derived_procedural = dict(by_group["procedural"])
    derived_live_ball = dict(by_group["live_ball"])
    derived_pi_drawn = pi_drawn
    derived_pi_allowed = pi_allowed
    if stats_row:
        total = int(stats_row.get("total_penalties", total) or total)
        yards = int(stats_row.get("total_penalty_yards", yards) or yards)
        by_side["offense"] = {
            "count": int(stats_row.get("offensive_penalties", by_side["offense"]["count"]) or 0),
            "yards": int(stats_row.get("offensive_penalty_yards", by_side["offense"]["yards"]) or 0),
        }
        by_side["defense"] = {
            "count": int(stats_row.get("defensive_penalties", by_side["defense"]["count"]) or 0),
            "yards": int(stats_row.get("defensive_penalty_yards", by_side["defense"]["yards"]) or 0),
        }
        by_group["procedural"] = {
            "count": int(stats_row.get("procedural_penalties", by_group["procedural"]["count"]) or 0),
            "yards": int(stats_row.get("procedural_penalty_yards", by_group["procedural"]["yards"]) or 0),
        }
        by_group["live_ball"] = {
            "count": int(stats_row.get("live_ball_penalties", by_group["live_ball"]["count"]) or 0),
            "yards": int(stats_row.get("live_ball_penalty_yards", by_group["live_ball"]["yards"]) or 0),
        }
        pi_drawn = int(stats_row.get("pass_interference_drawn", pi_drawn) or 0)
        pi_allowed = int(stats_row.get("pass_interference_allowed", pi_allowed) or 0)
        off_holding = int(stats_row.get("offensive_holding", off_holding) or 0)
        off_holding_yards = int(stats_row.get("offensive_holding_yards", off_holding_yards) or 0)
        def_holding = int(stats_row.get("defensive_holding", def_holding) or 0)
        def_holding_yards = int(stats_row.get("defensive_holding_yards", def_holding_yards) or 0)
        has_group_breakdown = any(
            stats_row.get(k) is not None
            for k in (
                "procedural_penalties",
                "procedural_penalty_yards",
                "live_ball_penalties",
                "live_ball_penalty_yards",
            )
        ) and not (
            total > 0
            and by_group["procedural"]["count"] == 0
            and by_group["live_ball"]["count"] == 0
        )
        has_pi_breakdown = any(
            stats_row.get(k) is not None
            for k in (
                "pass_interference_drawn",
                "pass_interference_drawn_yards",
                "pass_interference_allowed",
                "pass_interference_allowed_yards",
            )
        ) and not (total > 0 and pi_drawn == 0 and pi_allowed == 0)
        has_holding_breakdown = any(
            stats_row.get(k) is not None
            for k in (
                "offensive_holding",
                "defensive_holding",
            )
        ) and not (total > 0 and off_holding == 0 and def_holding == 0)
        derived_group_count = derived_procedural["count"] + derived_live_ball["count"]
        derived_group_yards = derived_procedural["yards"] + derived_live_ball["yards"]
        structured_group_count = by_group["procedural"]["count"] + by_group["live_ball"]["count"]
        structured_group_yards = by_group["procedural"]["yards"] + by_group["live_ball"]["yards"]
        # XML feeds can publish zeroed advanced splits while per-play details are present.
        if (
            total > 0
            and (derived_procedural["count"] > 0 or derived_live_ball["count"] > 0)
            and (
                structured_group_count == 0
                or structured_group_count != total
                or structured_group_yards != yards
            )
        ):
            by_group["procedural"] = derived_procedural
            by_group["live_ball"] = derived_live_ball
            has_group_breakdown = True
        if total > 0 and pi_drawn == 0 and pi_allowed == 0 and (
            derived_pi_drawn > 0 or derived_pi_allowed > 0
        ):
            pi_drawn = derived_pi_drawn
            pi_allowed = derived_pi_allowed
            has_pi_breakdown = True
        if not has_group_breakdown and (
            by_group["procedural"]["count"] > 0 or by_group["live_ball"]["count"] > 0
        ):
            has_group_breakdown = True
        if not has_pi_breakdown and (pi_drawn > 0 or pi_allowed > 0):
            has_pi_breakdown = True
        if not has_holding_breakdown and (off_holding > 0 or def_holding > 0):
            has_holding_breakdown = True
    else:
        has_group_breakdown = bool(by_group["procedural"]["count"] or by_group["live_ball"]["count"])
        has_pi_breakdown = bool(pi_drawn or pi_allowed)
        has_holding_breakdown = bool(off_holding or def_holding)

    season_residual_count = 0
    season_residual_yards = 0
    if stats_row:
        season_resolved_count = sum(
            int(r["official_count"]) if isinstance(r.get("official_count"), int) else int(r["count"])
            for r in per_game
        )
        season_resolved_yards = sum(
            int(r["official_yards"]) if isinstance(r.get("official_yards"), int) else int(r["yards"])
            for r in per_game
        )
        season_residual_count = int(stats_row.get("total_penalties", total) or 0) - season_resolved_count
        season_residual_yards = int(stats_row.get("total_penalty_yards", yards) or 0) - season_resolved_yards

    return {
        "total": total,
        "yards": yards,
        "by_side": by_side,
        "by_group": by_group,
        "by_type_count": by_type_count,
        "by_type_yards": by_type_yards,
        "by_quarter": by_quarter,
        "per_game": sorted(per_game, key=lambda r: r["game_number"]),
        "pi_drawn": pi_drawn,
        "pi_allowed": pi_allowed,
        "off_holding": off_holding,
        "off_holding_yards": off_holding_yards,
        "def_holding": def_holding,
        "def_holding_yards": def_holding_yards,
        "has_group_breakdown": has_group_breakdown,
        "has_pi_breakdown": has_pi_breakdown,
        "has_holding_breakdown": has_holding_breakdown,
        "season_unattributed_count": season_unattributed_count,
        "season_unattributed_yards": season_unattributed_yards,
        "season_residual_count": season_residual_count,
        "season_residual_yards": season_residual_yards,
    }


def _penalties_rank(team: dict) -> str:
    pbp = team.get("pbp_entry") or {}
    rankings = pbp.get("cfbstats", {}).get("rankings", {}).get("all", {})
    r = rankings.get("penalties", {})
    val = r.get("value", "")
    rnk = r.get("rank", "")
    if val != "" and rnk != "":
        return f"{val} (#{rnk})"
    return val or "N/A"


def _should_show_last_n(team: dict) -> bool:
    last_n = team.get("last_n", {}) or {}
    return last_n.get("actual_n", 0) >= last_n.get("required_n", 3)


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No PBP data.</em></p></div>"

    games = _games(team)
    game_count = max(len(games), 1)
    agg = _aggregate(team)
    stats_row = _penalty_stats_row(team) or {}
    has_source_data = bool(games) or bool(stats_row)
    top_common = agg["by_type_count"].most_common(3)
    top_yards = agg["by_type_yards"].most_common(3)
    per_game_rows = agg["per_game"]

    common_html = "".join(f"<li>{k}: {v}</li>" for k, v in top_common) or "<li>N/A</li>"
    yards_html = "".join(f"<li>{k}: {v} yds</li>" for k, v in top_yards) or "<li>N/A</li>"

    offense = agg["by_side"].get("offense", {"count": 0, "yards": 0})
    defense = agg["by_side"].get("defense", {"count": 0, "yards": 0})
    procedural = agg["by_group"].get("procedural", {"count": 0, "yards": 0})
    live_ball = agg["by_group"].get("live_ball", {"count": 0, "yards": 0})
    unattributed_count = agg.get("season_unattributed_count", 0)
    unattributed_yards = agg.get("season_unattributed_yards", 0)
    show_group = bool(agg.get("has_group_breakdown"))
    show_pi = bool(agg.get("has_pi_breakdown"))
    show_holding = bool(agg.get("has_holding_breakdown"))
    if stats_row:
        pen_per_game = stats_row.get("total_penalties_pg")
        yds_per_game = stats_row.get("total_penalty_yards_pg")
    else:
        pen_per_game = (agg["total"] / game_count) if has_source_data else None
        yds_per_game = (agg["yards"] / game_count) if has_source_data else None

    per_game_table = "".join(
        f"<tr>"
        f"<td>G{r['game_number']}</td>"
        f"<td>{r['opponent']}</td>"
        f"<td>{r['official_count'] if isinstance(r.get('official_count'), int) else r['count']}{'*' if r.get('delta_count') else ''}</td>"
        f"<td>{r['official_yards'] if isinstance(r.get('official_yards'), int) else r['yards']}{'*' if r.get('delta_yards') else ''}</td>"
        f"<td>{r['procedural_count']} ({r['procedural_yards']})</td>"
        f"<td>{r['live_ball_count']} ({r['live_ball_yards']})</td>"
        f"</tr>"
        for r in per_game_rows
    ) or "<tr><td colspan='6'>N/A</td></tr>"
    delta_rows = [
        r
        for r in per_game_rows
        if (r.get("delta_count") or 0) != 0 or (r.get("delta_yards") or 0) != 0
    ]
    delta_html = ""
    if delta_rows:
        delta_items = "".join(
            "<li>"
            f"G{r['game_number']} {r['opponent']}: "
            f"{r.get('delta_count', 0):+d} penalties, {r.get('delta_yards', 0):+d} yards "
            "between official game totals and play-attributed breakdown."
            "</li>"
            for r in delta_rows
        )
        delta_html = (
            "<p class=\"section-note\">* Totals use official game summaries when available. "
            "Procedural/live-ball splits remain play-attributed.</p>"
            f"<ul class=\"section-note\">{delta_items}</ul>"
        )
    residual_html = ""
    if agg.get("season_residual_count") or agg.get("season_residual_yards"):
        residual_html = (
            "<p class=\"section-note\">"
            f"Season-source residual: {agg.get('season_residual_count', 0):+d} penalties, "
            f"{agg.get('season_residual_yards', 0):+d} yards not attributable to a single game from available PBP detail."
            "</p>"
        )

    last_n_html = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_ppg = last_n.get("penalties_per_game")
        season_ppg = pen_per_game
        ppg_arrow = ""
        if isinstance(l3_ppg, (int, float)) and isinstance(season_ppg, (int, float)) and l3_ppg < season_ppg:
            ppg_arrow = " <span style=\"color: #1b7f3a;\">↓</span>"
        elif isinstance(l3_ppg, (int, float)) and isinstance(season_ppg, (int, float)) and l3_ppg > season_ppg:
            ppg_arrow = " <span style=\"color: #b3261e;\">↑</span>"

        l3_off_pg = float(
            stats_row.get("last_3_offensive_penalties_pg", last_n.get("penalties_offense", 0)) or 0
        )
        l3_def_pg = float(
            stats_row.get("last_3_defensive_penalties_pg", last_n.get("penalties_defense", 0)) or 0
        )
        l3_st_total = int(last_n.get("penalties_special_teams", 0) or 0)
        l3_st_avg = l3_st_total / actual_n if actual_n else 0
        l3_proc = stats_row.get("last_3_procedural_penalties_pg") if stats_row else None
        l3_live = stats_row.get("last_3_live_ball_penalties_pg") if stats_row else None
        l3_pi_drawn = stats_row.get("last_3_pass_interference_drawn_pg") if stats_row else None
        l3_pi_allowed = stats_row.get("last_3_pass_interference_allowed_pg") if stats_row else None
        l3_off_holding = stats_row.get("last_3_offensive_holding_pg") if stats_row else None
        l3_def_holding = stats_row.get("last_3_defensive_holding_pg") if stats_row else None

        # When bundle stats_row has zeroed L3 breakdowns but season play-tree
        # data has non-zero values, derive L3 from the last N per-game rows.
        last_n_games = per_game_rows[-actual_n:] if per_game_rows else []
        if (
            show_group
            and actual_n
            and last_n_games
            and (l3_proc == 0 or l3_proc is None)
            and (l3_live == 0 or l3_live is None)
            and (procedural["count"] > 0 or live_ball["count"] > 0)
        ):
            l3_proc = round(sum(r["procedural_count"] for r in last_n_games) / actual_n, 1)
            l3_live = round(sum(r["live_ball_count"] for r in last_n_games) / actual_n, 1)
        if (
            not show_holding
            and actual_n
            and (agg["off_holding"] > 0 or agg["def_holding"] > 0)
        ):
            # Season holding data exists from play-tree derivation; enable the
            # breakdown even though the bundle didn't provide these fields.
            show_holding = True

        def _l3(pg: float | None) -> str:
            if pg is None or not actual_n:
                return "N/A"
            total = round(pg * actual_n)
            return f"{total} ({pg:.1f}/g)"

        l3_pen_total = round(l3_ppg * actual_n) if isinstance(l3_ppg, (int, float)) and actual_n else None
        pen_total_str = f"{l3_pen_total}" if l3_pen_total is not None else "N/A"
        pen_avg_str = f"{l3_ppg:.1f}/g" if isinstance(l3_ppg, (int, float)) else "N/A"
        season_avg_str = f"{season_ppg:.1f}/g" if isinstance(season_ppg, (int, float)) else "N/A"

        proc_live_line = ""
        if show_group and l3_proc is not None and l3_live is not None:
            proc_live_line = f"<li>Procedural: {_l3(l3_proc)} / Live-ball: {_l3(l3_live)}</li>"
        pi_line = ""
        if show_pi and l3_pi_drawn is not None and l3_pi_allowed is not None:
            pi_line = f"<li>PI Drawn: {_l3(l3_pi_drawn)} / PI Allowed: {_l3(l3_pi_allowed)}</li>"
        holding_line = ""
        if show_holding and l3_off_holding is not None and l3_def_holding is not None:
            holding_line = f"<li>Off. Holding: {_l3(l3_off_holding)} / Def. Holding: {_l3(l3_def_holding)}</li>"

        last_n_html = f"""
      <div class=\"block\">
        <h4>Last {actual_n} Trending</h4>
        <ul>
          <li>Penalties: {pen_total_str} ({pen_avg_str}) — Season: {season_avg_str}{ppg_arrow}</li>
          <li>Offense: {_l3(l3_off_pg)} / Defense: {_l3(l3_def_pg)} / ST: {l3_st_total} ({l3_st_avg:.1f}/g)</li>
          {proc_live_line}
          {pi_line}
          {holding_line}
        </ul>
      </div>
        """

    return f"""
    <div class=\"team-card\">
      <h3>{team['display_name']}</h3>
      <div class=\"block\">
        <h4>Totals</h4>
        <ul>
          <li>Penalties/Game: {f"{pen_per_game:.1f}" if isinstance(pen_per_game, (int, float)) else 'N/A'} | Yards/Game: {f"{yds_per_game:.1f}" if isinstance(yds_per_game, (int, float)) else 'N/A'}{SRC_PBP}</li>
          <li>Penalties: {agg['total']} for {agg['yards']} yards{SRC_PBP}</li>
          <li>Offense: {offense['count']} / {offense['yards']} yds{SRC_PBP}</li>
          <li>Defense: {defense['count']} / {defense['yards']} yds{SRC_PBP}</li>
          <li>Procedural: {f"{procedural['count']} / {procedural['yards']} yds" if show_group else 'N/A'}{SRC_PBP}</li>
          <li>Live-ball: {f"{live_ball['count']} / {live_ball['yards']} yds" if show_group else 'N/A'}{SRC_PBP}</li>
          <li>Unattributed from official game totals: {f"{unattributed_count} / {unattributed_yards} yds" if unattributed_count or unattributed_yards else '0 / 0 yds'}{SRC_PBP}</li>
          <li>PI Drawn: {agg['pi_drawn'] if show_pi else 'N/A'} | PI Allowed: {agg['pi_allowed'] if show_pi else 'N/A'}{SRC_PBP}</li>
          <li>Offensive Holding: {f"{agg['off_holding']} / {agg['off_holding_yards']} yds" if show_holding else 'N/A'} | Defensive Holding: {f"{agg['def_holding']} / {agg['def_holding_yards']} yds" if show_holding else 'N/A'}{SRC_PBP}</li>
          <li>CFBStats Rank: {_penalties_rank(team)}{SRC_CFB}</li>
        </ul>
      </div>
      {last_n_html}
      <div class=\"block\">
        <h4>Top Types (Count)</h4>
        <ul>{common_html}</ul>
      </div>
      <div class=\"block\">
        <h4>Per-Game Breakdown</h4>
        <table class=\"rankings-table penalties-breakdown\">
          <thead>
            <tr>
              <th>G#</th>
              <th>Opp</th>
              <th>Pen</th>
              <th>Yds</th>
              <th>Procedural</th>
              <th>Live-ball</th>
            </tr>
          </thead>
          <tbody>{per_game_table}</tbody>
        </table>
        {delta_html}
        {residual_html}
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- Penalties: N/A"

    games = _games(team)
    game_count = max(len(games), 1)
    agg = _aggregate(team)
    stats_row = _penalty_stats_row(team) or {}
    has_source_data = bool(games) or bool(stats_row)
    top_common = agg["by_type_count"].most_common(1)
    worst = top_common[0][0] if top_common else "N/A"

    if stats_row:
        season_ppg = stats_row.get("total_penalties_pg")
        season_ypg = stats_row.get("total_penalty_yards_pg")
    else:
        season_ppg = (agg["total"] / game_count) if has_source_data else None
        season_ypg = (agg["yards"] / game_count) if has_source_data else None
    procedural = agg["by_group"].get("procedural", {"count": 0})
    live_ball = agg["by_group"].get("live_ball", {"count": 0})
    show_group = bool(agg.get("has_group_breakdown"))
    show_pi = bool(agg.get("has_pi_breakdown"))
    show_holding = bool(agg.get("has_holding_breakdown"))
    unattributed_count = agg.get("season_unattributed_count", 0)
    unattributed_yards = agg.get("season_unattributed_yards", 0)

    lines = [f"*{team['display_name']}*"]
    suffix = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_ppg = last_n.get("penalties_per_game")
        if isinstance(l3_ppg, (int, float)) and isinstance(season_ppg, (int, float)) and abs(l3_ppg - season_ppg) >= 0.8:
            suffix = f" (L{actual_n}: {l3_ppg:.1f}/gm)"

    lines.append(f"- Penalties/Game: {f'{season_ppg:.1f}' if isinstance(season_ppg, (int, float)) else 'N/A'}{suffix}")
    lines.append(f"- Penalty Yards/Game: {f'{season_ypg:.1f}' if isinstance(season_ypg, (int, float)) else 'N/A'}")
    lines.append(
        f"- Procedural vs Live-ball: "
        f"{procedural['count'] if show_group else 'N/A'} / {live_ball['count'] if show_group else 'N/A'}"
    )
    lines.append(
        f"- PI Drawn / Allowed: "
        f"{agg['pi_drawn'] if show_pi else 'N/A'} / {agg['pi_allowed'] if show_pi else 'N/A'}"
    )
    lines.append(
        f"- Off. Holding / Def. Holding: "
        f"{agg['off_holding'] if show_holding else 'N/A'} / {agg['def_holding'] if show_holding else 'N/A'}"
    )
    lines.append(f"- Unattributed from official game totals: {unattributed_count} / {unattributed_yards} yds")
    delta_rows = [
        r
        for r in agg["per_game"]
        if (r.get("delta_count") or 0) != 0 or (r.get("delta_yards") or 0) != 0
    ]
    if delta_rows:
        lines.append(
            "- Game deltas: "
            + "; ".join(
                f"G{r['game_number']} {r['opponent']} ({r.get('delta_count', 0):+d} / {r.get('delta_yards', 0):+d})"
                for r in delta_rows
            )
        )
    if agg.get("season_residual_count") or agg.get("season_residual_yards"):
        lines.append(
            f"- Season-source residual: {agg.get('season_residual_count', 0):+d} penalties, "
            f"{agg.get('season_residual_yards', 0):+d} yards"
        )
    lines.append(f"- Top Penalty Type: {worst}")
    return "\n".join(lines)


def build(team1: dict, team2: dict) -> dict:
    """Penalty breakdown section."""
    html_content = f"""
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Penalties*",
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Penalties",
        "html_content": html_content,
        "md_content": md_content,
        "key": "penalties",
    }
