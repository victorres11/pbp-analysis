from __future__ import annotations

from .delta import metric_delta_html, metric_delta_md


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    games = pbp.get("games", []) or []
    return sorted(games, key=lambda g: g.get("game_number", 0))


def _record(games: list[dict]) -> tuple[int, int, int]:
    wins = losses = ties = 0
    for g in games:
        pf = g.get("points_for")
        pa = g.get("points_against")
        if pf is None or pa is None:
            continue
        if pf > pa:
            wins += 1
        elif pf < pa:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties


def _win_pct(games: list[dict]) -> float | None:
    wins, losses, ties = _record(games)
    total = wins + losses + ties
    if total == 0:
        return None
    return round((wins + 0.5 * ties) / total * 100.0, 1)


def _result_text(game: dict) -> str:
    pf = game.get("points_for")
    pa = game.get("points_against")
    if pf is None or pa is None:
        return "N/A"
    if pf > pa:
        return f"W {pf}-{pa}"
    if pf < pa:
        return f"L {pf}-{pa}"
    return f"T {pf}-{pa}"


def _row_html(g: dict) -> str:
    wk = g.get("week") or "?"
    opp = g.get("opponent") or "?"
    result = _result_text(g)
    plays = g.get("total_plays", 0) or 0
    yards = g.get("total_yards", 0) or 0
    explosives = g.get("explosives")
    if explosives is None:
        explosives = (g.get("explosive_passes", 0) or 0) + (g.get("explosive_rushes", 0) or 0)
    to_g = g.get("turnovers_gained", 0) or 0
    to_l = g.get("turnovers_lost", 0) or 0
    rz_tds = g.get("red_zone_tds", 0) or 0
    rz_trips = g.get("red_zone_trips", 0) or 0
    date = g.get("date") or ""
    return (
        "<tr>"
        f"<td style=\"text-align:left;\">{wk}</td>"
        f"<td style=\"text-align:left;\">{opp}<div style=\"color:#64748b;font-size:11px;\">{date}</div></td>"
        f"<td style=\"text-align:left;\">{result}</td>"
        f"<td style=\"text-align:right;\">{plays}</td>"
        f"<td style=\"text-align:right;\">{yards}</td>"
        f"<td style=\"text-align:right;\">{explosives}</td>"
        f"<td style=\"text-align:right;\">{to_g}/{to_l}</td>"
        f"<td style=\"text-align:right;\">{rz_tds}/{rz_trips}</td>"
        "</tr>"
    )


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No schedule data.</em></p></div>"

    games = _games(team)
    wins, losses, ties = _record(games)
    win_pct = _win_pct(games)
    record = f"{wins}-{losses}" if ties == 0 else f"{wins}-{losses}-{ties}"
    rows = "".join(_row_html(g) for g in games) or "<tr><td colspan='8'>N/A</td></tr>"

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Season Snapshot (V1 Raw Stats)</h4>
        <ul>
          <li>Record: {record}</li>
          <li>Win %: {win_pct if win_pct is not None else 'N/A'}%</li>
          <li>Games: {len(games)}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Schedule</h4>
        <table style="width:100%; border-collapse:collapse; font-size:0.9em;">
          <thead>
            <tr>
              <th style="text-align:left;">Wk</th>
              <th style="text-align:left;">Opponent</th>
              <th style="text-align:left;">Result</th>
              <th style="text-align:right;">Plays</th>
              <th style="text-align:right;">Yards</th>
              <th style="text-align:right;">Expl</th>
              <th style="text-align:right;">TO G/L</th>
              <th style="text-align:right;">RZ TD/Trips</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- Schedule: N/A"

    games = _games(team)
    wins, losses, ties = _record(games)
    win_pct = _win_pct(games)
    record = f"{wins}-{losses}" if ties == 0 else f"{wins}-{losses}-{ties}"
    lines = [f"*{team['display_name']}*", f"- Record: {record} ({win_pct if win_pct is not None else 'N/A'}%)"]

    for g in games:
        wk = g.get("week") or "?"
        opp = g.get("opponent") or "?"
        result = _result_text(g)
        plays = g.get("total_plays", 0) or 0
        yards = g.get("total_yards", 0) or 0
        explosives = g.get("explosives")
        if explosives is None:
            explosives = (g.get("explosive_passes", 0) or 0) + (g.get("explosive_rushes", 0) or 0)
        rz_tds = g.get("red_zone_tds", 0) or 0
        rz_trips = g.get("red_zone_trips", 0) or 0
        lines.append(
            f"- Wk {wk} vs {opp}: {result} | {plays} plays, {yards} yds, {explosives} expl, RZ {rz_tds}/{rz_trips}"
        )
    return "\n".join(lines)


def build(team1: dict, team2: dict) -> dict:
    t1_pct = _win_pct(_games(team1)) if team1.get("has_pbp") else None
    t2_pct = _win_pct(_games(team2)) if team2.get("has_pbp") else None
    delta_html = metric_delta_html(
        "Win Percentage",
        team1["display_name"],
        t1_pct,
        team2["display_name"],
        t2_pct,
        higher_is_better=True,
        suffix="%",
    )
    delta_md = metric_delta_md(
        "Win Percentage",
        team1["display_name"],
        t1_pct,
        team2["display_name"],
        t2_pct,
        higher_is_better=True,
        suffix="%",
    )

    html_content = f"""
    {delta_html}
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Schedule (V1 Raw Stats)*",
        delta_md,
        _team_md(team1),
        _team_md(team2),
    ])

    return {
        "title": "Schedule",
        "html_content": html_content,
        "md_content": md_content,
        "key": "schedule",
    }
