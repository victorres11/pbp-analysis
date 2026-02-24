from __future__ import annotations

import re
from collections import Counter, defaultdict

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


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", [])


def _penalty_stats_row(team: dict) -> dict | None:
    """Best available team penalty row from bundled stats payload."""
    pbp = team.get("pbp_entry") or {}
    stats = pbp.get("stats") or {}
    penalties = stats.get("penalties") or {}
    if not isinstance(penalties, dict) or not penalties:
        return None
    rows = [v for v in penalties.values() if isinstance(v, dict)]
    if not rows:
        return None
    return max(rows, key=lambda r: int(r.get("games", 0) or 0))


def _simplify_penalty(pen: dict) -> str:
    desc = pen.get("description") or pen.get("type") or ""
    m = re.search(r"PENALTY\s+\w+\s+([^\d\.]+)", desc, re.IGNORECASE)
    if m:
        text = m.group(1)
    else:
        text = pen.get("type") or desc
    text = re.sub(r"Penalty\s+", "", text, flags=re.IGNORECASE)
    text = re.split(r"\s+\d", text)[0]
    text = text.replace("yards", "").replace("yard", "").strip()
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

    for g in games:
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
        for p in g.get("penalty_details", []) or []:
            if not p.get("accepted", False):
                continue

            y = p.get("yards", 0) or 0
            side = (p.get("offense_or_defense", "unknown") or "unknown").lower()
            ptype = _simplify_penalty(p)
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

        per_game.append(game_row)

    # Prefer bundle-level penalty rollups when available (source of truth).
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
    top_common = agg["by_type_count"].most_common(3)
    top_yards = agg["by_type_yards"].most_common(3)
    per_game_rows = agg["per_game"]

    common_html = "".join(f"<li>{k}: {v}</li>" for k, v in top_common) or "<li>N/A</li>"
    yards_html = "".join(f"<li>{k}: {v} yds</li>" for k, v in top_yards) or "<li>N/A</li>"

    offense = agg["by_side"].get("offense", {"count": 0, "yards": 0})
    defense = agg["by_side"].get("defense", {"count": 0, "yards": 0})
    procedural = agg["by_group"].get("procedural", {"count": 0, "yards": 0})
    live_ball = agg["by_group"].get("live_ball", {"count": 0, "yards": 0})
    pen_per_game = agg["total"] / game_count
    yds_per_game = agg["yards"] / game_count

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
        l3_ppg = last_n.get("penalties_per_game", 0) or 0
        season_ppg = pen_per_game
        ppg_arrow = ""
        if l3_ppg < season_ppg:
            ppg_arrow = " <span style=\"color: #1b7f3a;\">↓</span>"
        elif l3_ppg > season_ppg:
            ppg_arrow = " <span style=\"color: #b3261e;\">↑</span>"

        stats_row = _penalty_stats_row(team) or {}
        l3_off = float(
            stats_row.get("last_n_offensive_penalties_pg", last_n.get("penalties_offense", 0)) or 0
        )
        l3_def = float(
            stats_row.get("last_n_defensive_penalties_pg", last_n.get("penalties_defense", 0)) or 0
        )
        l3_proc = stats_row.get("last_n_procedural_penalties_pg")
        l3_live = stats_row.get("last_n_live_ball_penalties_pg")
        l3_pi_drawn = stats_row.get("last_n_pass_interference_drawn_pg")
        l3_pi_allowed = stats_row.get("last_n_pass_interference_allowed_pg")

        proc_live_line = ""
        if l3_proc is not None and l3_live is not None:
            proc_live_line = f"<li>Procedural: {l3_proc:.1f} / Live-ball: {l3_live:.1f}</li>"
        pi_line = ""
        if l3_pi_drawn is not None and l3_pi_allowed is not None:
            pi_line = f"<li>PI Drawn: {l3_pi_drawn:.1f} / PI Allowed: {l3_pi_allowed:.1f}</li>"

        last_n_html = f"""
      <div class=\"block\">
        <h4>Last {actual_n} Trending</h4>
        <ul>
          <li>Penalties/Game: {l3_ppg:.1f} (Season: {season_ppg:.1f}){ppg_arrow}</li>
          <li>Offense: {l3_off:.1f} / Defense: {l3_def:.1f} / ST: {last_n.get('penalties_special_teams', 0):.1f}</li>
          {proc_live_line}
          {pi_line}
        </ul>
      </div>
        """

    return f"""
    <div class=\"team-card\">
      <h3>{team['display_name']}</h3>
      <div class=\"block\">
        <h4>Totals</h4>
        <ul>
          <li>Penalties/Game: {pen_per_game:.1f} | Yards/Game: {yds_per_game:.1f}</li>
          <li>Penalties: {agg['total']} for {agg['yards']} yards</li>
          <li>Offense: {offense['count']} / {offense['yards']} yds</li>
          <li>Defense: {defense['count']} / {defense['yards']} yds</li>
          <li>Procedural: {procedural['count']} / {procedural['yards']} yds</li>
          <li>Live-ball: {live_ball['count']} / {live_ball['yards']} yds</li>
          <li>PI Drawn: {agg['pi_drawn']} | PI Allowed: {agg['pi_allowed']}</li>
          <li>CFBStats Rank: {_penalties_rank(team)}</li>
        </ul>
      </div>
      {last_n_html}
      <div class=\"block\">
        <h4>Top Types (Count)</h4>
        <ul>{common_html}</ul>
      </div>
      <div class=\"block\">
        <h4>Top Types (Yards)</h4>
        <ul>{yards_html}</ul>
      </div>
      <div class=\"block\">
        <h4>Per-Game Breakdown</h4>
        <table style=\"width:100%; border-collapse:collapse; font-size:0.9em;\">
          <thead>
            <tr>
              <th style=\"text-align:left;\">G#</th>
              <th style=\"text-align:left;\">Opp</th>
              <th style=\"text-align:right;\">Pen</th>
              <th style=\"text-align:right;\">Yds</th>
              <th style=\"text-align:right;\">Procedural</th>
              <th style=\"text-align:right;\">Live-ball</th>
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
    top_common = agg["by_type_count"].most_common(1)
    worst = top_common[0][0] if top_common else "N/A"

    season_ppg = agg["total"] / game_count
    season_ypg = agg["yards"] / game_count
    procedural = agg["by_group"].get("procedural", {"count": 0})
    live_ball = agg["by_group"].get("live_ball", {"count": 0})

    lines = [f"*{team['display_name']}*"]
    suffix = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_ppg = last_n.get("penalties_per_game", 0) or 0
        if abs(l3_ppg - season_ppg) >= 0.8:
            suffix = f" (L{actual_n}: {l3_ppg:.1f}/gm)"

    lines.append(f"- Penalties/Game: {season_ppg:.1f}{suffix}")
    lines.append(f"- Penalty Yards/Game: {season_ypg:.1f}")
    lines.append(f"- Procedural vs Live-ball: {procedural['count']} / {live_ball['count']}")
    lines.append(f"- PI Drawn / Allowed: {agg['pi_drawn']} / {agg['pi_allowed']}")
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
