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


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_opponent_index(team: dict) -> dict:
    pbp_teams = team.get("_pbp_teams") or {}
    index: dict[str, dict] = {}
    for slug, entry in pbp_teams.items():
        if not isinstance(entry, dict):
            continue
        index[str(slug).strip().lower()] = entry
        abbr = str(entry.get("abbr") or "").strip().lower()
        name = str(entry.get("name") or "").strip().lower()
        if abbr:
            index[abbr] = entry
        if name:
            index[name] = entry
    return index


def _get_opponent_entry(opponent_index: dict, game: dict) -> dict | None:
    keys = [
        str(game.get("opponent") or "").strip().lower(),
        str(game.get("opponent_abbr") or "").strip().lower(),
    ]
    for key in keys:
        if key and key in opponent_index:
            return opponent_index[key]
    return None


def _opponent_baseline(opponent: dict | None) -> dict:
    if not opponent:
        return {
            "opp_scoring_offense_ppg": None,
            "opp_scoring_defense_ppga": None,
            "opp_total_offense_ypg": None,
            "opp_total_defense_ypga": None,
        }
    agg = opponent.get("aggregates", {}) or {}
    rankings_all = ((opponent.get("cfbstats") or {}).get("rankings") or {}).get("all", {}) or {}
    return {
        "opp_scoring_offense_ppg": _safe_float(agg.get("ppg")),
        "opp_scoring_defense_ppga": _safe_float(agg.get("opp_ppg")),
        "opp_total_offense_ypg": _safe_float((rankings_all.get("total_offense") or {}).get("value")),
        "opp_total_defense_ypga": _safe_float((rankings_all.get("total_defense") or {}).get("value")),
    }


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}"


def _delta_color(value: float | None) -> str:
    if value is None:
        return "#94a3b8"
    if value > 0:
        return "#16a34a"
    if value < 0:
        return "#dc2626"
    return "#94a3b8"


def _relative_deltas(team: dict, game: dict, opponent_index: dict) -> tuple[float | None, float | None, bool]:
    pf = _safe_float(game.get("points_for"))
    pa = _safe_float(game.get("points_against"))
    opp_entry = _get_opponent_entry(opponent_index, game)
    opp_base = _opponent_baseline(opp_entry)

    off_vs_opp_avg = None
    def_vs_opp_avg = None
    used_fallback = False

    opp_def_ppga = opp_base["opp_scoring_defense_ppga"]
    opp_off_ppg = opp_base["opp_scoring_offense_ppg"]
    if opp_def_ppga is None:
        opp_def_ppga = _safe_float((team.get("stats") or {}).get("ppg"))
        used_fallback = True
    if opp_off_ppg is None:
        opp_off_ppg = _safe_float((team.get("stats") or {}).get("opp_ppg"))
        used_fallback = True

    if pf is not None and opp_def_ppga is not None:
        off_vs_opp_avg = pf - opp_def_ppga
    if pa is not None and opp_off_ppg is not None:
        # Positive means defense held offense below baseline expectation.
        def_vs_opp_avg = opp_off_ppg - pa

    return off_vs_opp_avg, def_vs_opp_avg, used_fallback


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


def _row_html(team: dict, g: dict, opponent_index: dict) -> str:
    wk = g.get("week") or "?"
    opp = g.get("opponent") or "?"
    result = _result_text(g)
    plays = int(g.get("total_plays", 0) or 0)
    yards = _safe_float(g.get("total_yards"))
    explosives = g.get("explosives")
    if explosives is None:
        explosives = (g.get("explosive_passes", 0) or 0) + (g.get("explosive_rushes", 0) or 0)
    to_g = g.get("turnovers_gained", 0) or 0
    to_l = g.get("turnovers_lost", 0) or 0
    rz_tds = g.get("red_zone_tds", 0) or 0
    rz_trips = g.get("red_zone_trips", 0) or 0
    off_vs_opp_avg, def_vs_opp_avg, used_fallback = _relative_deltas(team, g, opponent_index)
    marker = "*" if used_fallback else ""

    date = g.get("date") or ""
    return (
        "<tr>"
        f"<td style=\"text-align:left;\">{wk}</td>"
        f"<td style=\"text-align:left;\">{opp}<div style=\"color:#64748b;font-size:11px;\">{date}</div></td>"
        f"<td style=\"text-align:left;\">{result}</td>"
        f"<td style=\"text-align:right;\">{plays}</td>"
        f"<td style=\"text-align:right;\">{int(yards) if yards is not None else 'N/A'}</td>"
        f"<td style=\"text-align:right;\">{explosives}</td>"
        f"<td style=\"text-align:right;\">{to_g}/{to_l}</td>"
        f"<td style=\"text-align:right;\">{rz_tds}/{rz_trips}</td>"
        f"<td style=\"text-align:right; color:{_delta_color(off_vs_opp_avg)};\">{_fmt_delta(off_vs_opp_avg)}{marker}</td>"
        f"<td style=\"text-align:right; color:{_delta_color(def_vs_opp_avg)};\">{_fmt_delta(def_vs_opp_avg)}{marker}</td>"
        "</tr>"
    )


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No schedule data.</em></p></div>"

    games = _games(team)
    opponent_index = _build_opponent_index(team)
    wins, losses, ties = _record(games)
    win_pct = _win_pct(games)
    record = f"{wins}-{losses}" if ties == 0 else f"{wins}-{losses}-{ties}"
    rows = "".join(_row_html(team, g, opponent_index) for g in games) or "<tr><td colspan='10'>N/A</td></tr>"

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Season Snapshot (V1 Raw Stats)</h4>
        <ul>
          <li>Record: {record}</li>
          <li>Win %: {win_pct if win_pct is not None else 'N/A'}%</li>
          <li>Games: {len(games)}</li>
          <li>Relative colors: <span style="color:#16a34a;">green = better than baseline</span>, <span style="color:#dc2626;">red = worse</span></li>
          <li>* fallback baseline when opponent season data is unavailable</li>
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
              <th style="text-align:right;">Off vs Opp Avg</th>
              <th style="text-align:right;">Def vs Opp Avg</th>
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
    opponent_index = _build_opponent_index(team)
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
        off_vs_opp_avg, def_vs_opp_avg, used_fallback = _relative_deltas(team, g, opponent_index)
        marker = "*" if used_fallback else ""
        lines.append(
            f"- Wk {wk} vs {opp}: {result} | {plays} plays, {yards} yds, {explosives} expl, RZ {rz_tds}/{rz_trips}, OffΔ {_fmt_delta(off_vs_opp_avg)}{marker}, DefΔ {_fmt_delta(def_vs_opp_avg)}{marker}"
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
