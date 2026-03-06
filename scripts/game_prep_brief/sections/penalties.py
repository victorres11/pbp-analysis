from __future__ import annotations

import re
from collections import Counter, defaultdict

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
    ("Personal Foul", re.compile(r"\bPERSONAL\s+FOUL\b", re.IGNORECASE)),
]


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", [])


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
        r"\bPENALTY\s+ON\s+([A-Z0-9]{2,6})\b",
        r"\bPENALTY\s+([A-Z0-9]{2,6})\b",
    ]
    for pat in patterns:
        m = re.search(pat, upper)
        if m:
            return re.sub(r"[^A-Z0-9]", "", m.group(1))
    return ""


def _expand_aliases(base_set: set[str]) -> set[str]:
    """Expand a team abbreviation set with known raw-text aliases.

    The adapter normalizes abbreviations (e.g. WASH→UW), but play-text still
    uses the raw form.  Import the normalization table to reverse-map.
    """
    try:
        from pbp_parser.statbroadcast.adapter import _TEAM_ABBR_NORMALIZATION
    except ImportError:
        return base_set
    expanded = set(base_set)
    for raw, canonical in _TEAM_ABBR_NORMALIZATION.items():
        norm = re.sub(r"[^A-Z0-9]", "", canonical.upper())
        if norm in base_set:
            expanded.add(re.sub(r"[^A-Z0-9]", "", raw.upper()))
    return expanded


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
    team_aliases = _expand_aliases(_abbr_set(pbp.get("abbr_aliases") or pbp.get("abbr")))
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

    for g in games:
        opp_aliases = _abbr_set(g.get("opponent_abbr") or g.get("opponent"))
        game_row = {
            "game_number": g.get("game_number") or 0,
            "opponent": g.get("opponent") or "?",
            "count": 0,
            "yards": 0,
            "procedural_count": 0,
            "procedural_yards": 0,
            "live_ball_count": 0,
            "live_ball_yards": 0,
        }
        details = g.get("penalty_details", []) or []
        for p in details:
            if not p.get("accepted", False):
                continue

            y = p.get("yards", 0) or 0
            side = (p.get("offense_or_defense", "unknown") or "unknown").lower()
            ptype = _simplify_penalty(p)
            if ptype == "Holding":
                if side == "offense":
                    ptype = "Offensive Holding"
                elif side == "defense":
                    ptype = "Defensive Holding"
            group = _penalty_group(p)

            total += 1
            yards += y
            by_side[side]["count"] += 1
            by_side[side]["yards"] += y
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

            q = p.get("quarter")
            if q is not None:
                by_quarter[q] += 1

        # Fallback: derive penalty type/count from play descriptions when detail rows are absent.
        if not details and isinstance(g.get("play_tree"), list):
            for q in g.get("play_tree") or []:
                for drive in q.get("drives") or []:
                    for play in drive.get("plays") or []:
                        desc = str(play.get("description") or "")
                        if "PENALTY" not in desc.upper():
                            continue
                        desc_up = desc.upper()
                        pen_tok = _extract_penalized_team_token(desc_up)
                        play_off = re.sub(r"[^A-Z0-9]", "", str(play.get("offense") or "").upper())
                        is_team_penalty = pen_tok and pen_tok in team_aliases

                        # PI drawn/allowed tracking requires both teams' penalties.
                        if "PASS INTERFERENCE" in desc_up:
                            if pen_tok and pen_tok in team_aliases:
                                pi_allowed += 1
                            elif pen_tok and pen_tok in opp_aliases:
                                pi_drawn += 1
                            elif "DEFENSIVE PASS INTERFERENCE" in desc_up:
                                if play_off and play_off in team_aliases:
                                    pi_drawn += 1
                                elif play_off and play_off in opp_aliases:
                                    pi_allowed += 1
                            elif "OFFENSIVE PASS INTERFERENCE" in desc_up:
                                if play_off and play_off in team_aliases:
                                    pi_allowed += 1
                                elif play_off and play_off in opp_aliases:
                                    pi_drawn += 1

                        # Only count the team's own penalties in aggregates.
                        if not is_team_penalty:
                            continue

                        pen_obj = {"description": desc}
                        ptype = _simplify_penalty(pen_obj)
                        if ptype == "Holding" and pen_tok and play_off:
                            pen_is_offense = (
                                pen_tok == play_off
                                or (pen_tok in team_aliases and play_off in team_aliases)
                            )
                            ptype = "Offensive Holding" if pen_is_offense else "Defensive Holding"
                        y_match = re.search(r"(\d+)\s*yards?", desc, re.IGNORECASE)
                        y_val = int(y_match.group(1)) if y_match else 0
                        by_type_count[ptype] += 1
                        by_type_yards[ptype] += y_val
                        group = _penalty_group(pen_obj)
                        by_group[group]["count"] += 1
                        by_group[group]["yards"] += y_val
                        total += 1
                        yards += y_val
                        game_row["count"] += 1
                        game_row["yards"] += y_val
                        if group == "procedural":
                            game_row["procedural_count"] += 1
                            game_row["procedural_yards"] += y_val
                        else:
                            game_row["live_ball_count"] += 1
                            game_row["live_ball_yards"] += y_val

        per_game.append(game_row)

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
        # XML feeds can publish zeroed advanced splits while per-play details are present.
        if (
            total > 0
            and by_group["procedural"]["count"] == 0
            and by_group["live_ball"]["count"] == 0
            and (derived_procedural["count"] > 0 or derived_live_ball["count"] > 0)
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
        f"<td>{r['count']}</td>"
        f"<td>{r['yards']}</td>"
        f"<td>{r['procedural_count']} ({r['procedural_yards']})</td>"
        f"<td>{r['live_ball_count']} ({r['live_ball_yards']})</td>"
        f"</tr>"
        for r in per_game_rows
    ) or "<tr><td colspan='6'>N/A</td></tr>"

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
        l3_proc = stats_row.get("last_3_procedural_penalties_pg")
        l3_live = stats_row.get("last_3_live_ball_penalties_pg")
        l3_pi_drawn = stats_row.get("last_3_pass_interference_drawn_pg")
        l3_pi_allowed = stats_row.get("last_3_pass_interference_allowed_pg")
        l3_off_holding = stats_row.get("last_3_offensive_holding_pg")
        l3_def_holding = stats_row.get("last_3_defensive_holding_pg")

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
