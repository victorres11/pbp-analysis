from __future__ import annotations

from .delta import metric_delta_html, metric_delta_md


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", []) or []


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ranking(team: dict, key: str) -> dict:
    rankings = (
        ((team.get("pbp_entry") or {}).get("cfbstats", {}).get("rankings", {}).get("all", {}))
    )
    return rankings.get(key, {}) or {}


def _abbr(team: dict) -> str:
    return str((team.get("stats") or {}).get("abbr") or "").strip()


def _is_sack(play: dict) -> bool:
    desc = str(play.get("description") or "").lower()
    return "sack" in desc or "sacked" in desc


def _is_rush_tfl(play: dict) -> bool:
    desc = str(play.get("description") or "").lower()
    if "kneel" in desc:
        return False
    if "rush" not in desc:
        return False
    yards = play.get("yards")
    try:
        return float(yards) < 0
    except (TypeError, ValueError):
        return False


def _pbp_counts(team: dict) -> dict:
    team_abbr = _abbr(team)
    sacks_for = 0
    sacks_allowed = 0
    rush_tfl_for = 0
    rush_tfl_allowed = 0

    for g in _games(team):
        for q in g.get("play_tree", []) or []:
            for d in q.get("drives", []) or []:
                for p in d.get("plays", []) or []:
                    if not isinstance(p, dict) or p.get("is_no_play"):
                        continue
                    offense = str(p.get("offense") or "")
                    ours = offense == team_abbr if team_abbr else False
                    if _is_sack(p):
                        if ours:
                            sacks_allowed += 1
                        else:
                            sacks_for += 1
                    if _is_rush_tfl(p):
                        if ours:
                            rush_tfl_allowed += 1
                        else:
                            rush_tfl_for += 1

    return {
        "sacks_for": sacks_for,
        "sacks_allowed": sacks_allowed,
        "rush_tfl_for": rush_tfl_for,
        "rush_tfl_allowed": rush_tfl_allowed,
    }


def _season_totals(team: dict) -> dict:
    games = _games(team)
    game_count = max(len(games), 1)
    sacks_off_rank = _ranking(team, "sacks_offense")
    sacks_def_rank = _ranking(team, "sacks_defense")
    tfl_off_rank = _ranking(team, "tfl_offense")

    sacks_allowed_total = _safe_float(sacks_off_rank.get("value"))
    sacks_for_total = _safe_float(sacks_def_rank.get("value"))
    tfl_allowed_total = _safe_float(tfl_off_rank.get("value"))
    pbp = _pbp_counts(team)

    return {
        "games": len(games),
        "sacks_allowed_total": sacks_allowed_total,
        "sacks_for_total": sacks_for_total,
        "tfl_allowed_total": tfl_allowed_total,
        "rush_tfl_for_total": float(pbp["rush_tfl_for"]),
        "sacks_allowed_pg": (sacks_allowed_total / game_count) if sacks_allowed_total is not None else None,
        "sacks_for_pg": (sacks_for_total / game_count) if sacks_for_total is not None else None,
        "tfl_allowed_pg": (tfl_allowed_total / game_count) if tfl_allowed_total is not None else None,
        "rush_tfl_for_pg": (pbp["rush_tfl_for"] / game_count),
        "sacks_off_rank": sacks_off_rank.get("rank"),
        "sacks_def_rank": sacks_def_rank.get("rank"),
        "tfl_off_rank": tfl_off_rank.get("rank"),
    }


def _fmt(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No trenches data.</em></p></div>"

    t = _season_totals(team)
    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Sacks (CFBStats)</h4>
        <ul>
          <li>Sacks Allowed/Game: {_fmt(t['sacks_allowed_pg'])} (total {_fmt(t['sacks_allowed_total'])}, rank #{t['sacks_off_rank'] or 'N/A'})</li>
          <li>Sacks Made/Game: {_fmt(t['sacks_for_pg'])} (total {_fmt(t['sacks_for_total'])}, rank #{t['sacks_def_rank'] or 'N/A'})</li>
        </ul>
      </div>
      <div class="block">
        <h4>TFL (Off CFBStats + Def PBP)</h4>
        <ul>
          <li>TFL Allowed/Game: {_fmt(t['tfl_allowed_pg'])} (total {_fmt(t['tfl_allowed_total'])}, rank #{t['tfl_off_rank'] or 'N/A'})</li>
          <li>Rush TFL Made/Game (PBP): {_fmt(t['rush_tfl_for_pg'])} (total {_fmt(t['rush_tfl_for_total'])})</li>
        </ul>
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- Sacks/TFL: N/A"
    t = _season_totals(team)
    return "\n".join([
        f"*{team['display_name']}*",
        f"- Sacks Allowed/Game: {_fmt(t['sacks_allowed_pg'])} (#{t['sacks_off_rank'] or 'N/A'})",
        f"- Sacks Made/Game: {_fmt(t['sacks_for_pg'])} (#{t['sacks_def_rank'] or 'N/A'})",
        f"- TFL Allowed/Game: {_fmt(t['tfl_allowed_pg'])} (#{t['tfl_off_rank'] or 'N/A'})",
        f"- Rush TFL Made/Game (PBP): {_fmt(t['rush_tfl_for_pg'])}",
    ])


def build(team1: dict, team2: dict) -> dict:
    t1 = _season_totals(team1) if team1.get("has_pbp") else {"sacks_for_pg": None}
    t2 = _season_totals(team2) if team2.get("has_pbp") else {"sacks_for_pg": None}
    delta_html = metric_delta_html(
        "Sacks Made Per Game",
        team1["display_name"],
        t1.get("sacks_for_pg"),
        team2["display_name"],
        t2.get("sacks_for_pg"),
        higher_is_better=True,
    )
    delta_md = metric_delta_md(
        "Sacks Made Per Game",
        team1["display_name"],
        t1.get("sacks_for_pg"),
        team2["display_name"],
        t2.get("sacks_for_pg"),
        higher_is_better=True,
    )
    html_content = f"""
    {delta_html}
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Trenches (Sacks/TFL)*",
        delta_md,
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Trenches",
        "html_content": html_content,
        "md_content": md_content,
        "key": "trenches",
    }
