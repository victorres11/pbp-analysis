from __future__ import annotations


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_delta(value: float | None, inverse: bool = False) -> str:
    if value is None:
        return "N/A"
    adjusted = -value if inverse else value
    return f"{adjusted:+.1f}"


def _perf_badge(score: int) -> tuple[str, str]:
    if score >= 2:
        return ("Good", "#166534")
    if score <= -2:
        return ("Poor", "#991b1b")
    return ("Neutral", "#475569")


def _sort_games(games: list[dict]) -> list[dict]:
    return sorted(
        games,
        key=lambda g: (
            int(g.get("game_number") or 999),
            str(g.get("date") or ""),
        ),
    )


def _sort_schedule_games(schedule_games: list[dict]) -> list[dict]:
    return sorted(
        schedule_games,
        key=lambda g: (
            int(g.get("week") or 999),
            str(g.get("game_date") or ""),
        ),
    )


def _location(is_home: object, is_bye: object) -> tuple[str, str]:
    if is_bye:
        return ("BYE", "BYE")
    if is_home is True:
        return ("Home", "vs")
    if is_home is False:
        return ("Away", "@")
    return ("Neutral", "vs")


def _build_rows(team: dict) -> list[dict]:
    pbp_games = _sort_games((team.get("pbp_entry") or {}).get("games") or [])
    pbp_by_week = {g.get("week"): g for g in pbp_games if g.get("week") is not None}

    schedule = ((team.get("pbp_entry") or {}).get("schedule") or {})
    schedule_games = _sort_schedule_games(schedule.get("games") or [])
    if not schedule_games:
        return [{"week": g.get("week") or g.get("game_number"), "loc": "N/A", "prefix": "vs", "opponent": g.get("opponent_abbr") or g.get("opponent") or "OPP", "pbp": g, "is_bye": False} for g in pbp_games]

    rows = []
    for sg in schedule_games:
        week = sg.get("week")
        pbp = pbp_by_week.get(week)
        loc, prefix = _location(sg.get("is_home"), sg.get("is_bye"))
        opponent = sg.get("opponent") or (pbp.get("opponent_abbr") if pbp else None) or "OPP"
        rows.append(
            {
                "week": week,
                "loc": loc,
                "prefix": prefix,
                "opponent": opponent,
                "pbp": pbp,
                "is_bye": bool(sg.get("is_bye")),
            }
        )
    return rows


def _team_table_html(team: dict) -> str:
    rows_in = _build_rows(team)
    if not rows_in:
        return f"<div class='team-card'><h3>{team['display_name']}</h3><div class='block'><ul><li>N/A</li></ul></div></div>"

    stats = team.get("stats", {})
    ppg = _safe_float(stats.get("ppg"))
    opp_ppg = _safe_float(stats.get("opp_ppg"))
    season_margin = (ppg - opp_ppg) if ppg is not None and opp_ppg is not None else None

    rows = []
    for row in rows_in:
        wk = row.get("week") or "?"
        loc = row.get("loc", "N/A")
        prefix = row.get("prefix", "vs")
        opponent = row.get("opponent", "OPP")
        if row.get("is_bye"):
            rows.append(
                f"""
                <tr>
                  <td>{wk}</td>
                  <td>{loc}</td>
                  <td>BYE</td>
                  <td>—</td>
                  <td>—</td>
                  <td>—</td>
                  <td>—</td>
                  <td>—</td>
                  <td><span style=\"font-weight:600;color:#334155\">Off</span></td>
                </tr>
                """
            )
            continue

        game = row.get("pbp") or {}
        pf = _safe_float(game.get("points_for"))
        pa = _safe_float(game.get("points_against"))
        margin = (pf - pa) if pf is not None and pa is not None else None
        pf_delta = (pf - ppg) if pf is not None and ppg is not None else None
        pa_delta = (pa - opp_ppg) if pa is not None and opp_ppg is not None else None
        margin_delta = (margin - season_margin) if margin is not None and season_margin is not None else None

        perf_score = 0
        if pf_delta is not None:
            perf_score += 1 if pf_delta >= 3 else -1 if pf_delta <= -3 else 0
        if pa_delta is not None:
            perf_score += 1 if pa_delta <= -3 else -1 if pa_delta >= 3 else 0
        if margin_delta is not None:
            perf_score += 1 if margin_delta >= 3 else -1 if margin_delta <= -3 else 0
        badge_text, badge_color = _perf_badge(perf_score)

        result = "W" if margin is not None and margin > 0 else "L" if margin is not None else "—"
        score_txt = f"{int(pf)}-{int(pa)}" if pf is not None and pa is not None else "—"
        yds = game.get("total_yards", "—")
        margin_txt = f"{margin:+.0f}" if margin is not None else "N/A"

        rows.append(
            f"""
            <tr>
              <td>{wk}</td>
              <td>{loc}</td>
              <td>{prefix} {opponent}</td>
              <td>{result}</td>
              <td>{score_txt}</td>
              <td>{margin_txt}</td>
              <td>{yds}</td>
              <td>{_fmt_delta(pf_delta)}</td>
              <td>{_fmt_delta(pa_delta, inverse=True)}</td>
              <td><span style=\"font-weight:600;color:{badge_color}\">{badge_text}</span></td>
            </tr>
            """
        )

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <table class="rankings-table">
        <thead>
          <tr>
            <th>Wk</th>
            <th>Loc</th>
            <th>Opp</th>
            <th>R</th>
            <th>Score</th>
            <th>Mov</th>
            <th>Yds</th>
            <th>PF vs Avg</th>
            <th>PA vs Avg</th>
            <th>Rel Perf</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
      <div class="section-note">Rel Perf v1 uses team season baselines. Opponent-baseline overlay can be added when full opponent averages are available.</div>
    </div>
    """


def _team_md(team: dict) -> str:
    rows_in = _build_rows(team)
    if not rows_in:
        return f"*{team['display_name']}*\n- N/A"

    stats = team.get("stats", {})
    ppg = _safe_float(stats.get("ppg"))
    opp_ppg = _safe_float(stats.get("opp_ppg"))
    season_margin = (ppg - opp_ppg) if ppg is not None and opp_ppg is not None else None

    lines = [f"*{team['display_name']}*"]
    for row in rows_in:
        wk = row.get("week") or "?"
        loc = row.get("loc", "N/A")
        prefix = row.get("prefix", "vs")
        opponent = row.get("opponent", "OPP")
        if row.get("is_bye"):
            lines.append(f"- Wk {wk}: BYE")
            continue

        game = row.get("pbp") or {}
        pf = _safe_float(game.get("points_for"))
        pa = _safe_float(game.get("points_against"))
        margin = (pf - pa) if pf is not None and pa is not None else None
        pf_delta = (pf - ppg) if pf is not None and ppg is not None else None
        pa_delta = (pa - opp_ppg) if pa is not None and opp_ppg is not None else None
        margin_delta = (margin - season_margin) if margin is not None and season_margin is not None else None

        perf_score = 0
        if pf_delta is not None:
            perf_score += 1 if pf_delta >= 3 else -1 if pf_delta <= -3 else 0
        if pa_delta is not None:
            perf_score += 1 if pa_delta <= -3 else -1 if pa_delta >= 3 else 0
        if margin_delta is not None:
            perf_score += 1 if margin_delta >= 3 else -1 if margin_delta <= -3 else 0
        badge_text, _ = _perf_badge(perf_score)

        result = "W" if margin is not None and margin > 0 else "L" if margin is not None else "—"
        score_txt = f"{int(pf)}-{int(pa)}" if pf is not None and pa is not None else "—"
        yds = game.get("total_yards", "—")
        lines.append(
            f"- Wk {wk} ({loc}) {prefix} {opponent}: {result} {score_txt} | Yds {yds} | PFΔ {_fmt_delta(pf_delta)} | PAΔ {_fmt_delta(pa_delta, inverse=True)} | {badge_text}"
        )
    lines.append("- Note: Relative performance v1 compares each game vs team season averages.")
    return "\n".join(lines)


def build(team1: dict, team2: dict) -> dict:
    html_content = f"""
    <div class="section-grid">
      {_team_table_html(team1)}
      {_team_table_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Schedule Snapshot*",
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Schedule Snapshot",
        "html_content": html_content,
        "md_content": md_content,
        "key": "schedule",
    }
