from __future__ import annotations

from datetime import datetime
import re


def _should_show_last_n(team: dict) -> bool:
    last_n = team.get("last_n", {})
    return last_n.get("actual_n", 0) >= last_n.get("required_n", 3)


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coach_lines(team: dict) -> list[str]:
    coaches = team.get("coaches", {})
    lines = [f"Head Coach: {coaches.get('head_coach', 'N/A')}"]
    play_caller = coaches.get("play_caller")
    if play_caller:
        title = coaches.get("play_caller_title") or "Play Caller"
        lines.append(f"Play Caller: {play_caller} ({title})")
    elif coaches.get("oc") and coaches.get("oc") != "N/A":
        title = coaches.get("oc_title") or "OC"
        lines.append(f"Off. Coord: {coaches.get('oc')} ({title})")

    if coaches.get("dc") and coaches.get("dc") != "N/A":
        title = coaches.get("dc_title") or "DC"
        lines.append(f"Def. Coord: {coaches.get('dc')} ({title})")
    return lines


def _season_summary(team: dict) -> list[str]:
    stats = team.get("stats", {})
    record = stats.get("record", "N/A")
    conf_record = stats.get("conf_record", "")
    conf = team.get("conference", "")
    record_line = record
    if conf_record and conf_record != "0-0":
        record_line = f"{record} ({conf_record} {conf})"
    ppg = stats.get("ppg", "N/A")
    opp_ppg = stats.get("opp_ppg", "N/A")
    ppg_line = f"PPG: {ppg} for / {opp_ppg} against"
    if _should_show_last_n(team):
        last_n = team.get("last_n", {})
        actual_n = last_n.get("actual_n", last_n.get("required_n", 0))
        l_ppg = _safe_float(last_n.get("ppg"))
        l_opp_ppg = _safe_float(last_n.get("opp_ppg"))
        l_ppg_str = f"{l_ppg:.1f}" if l_ppg is not None else "N/A"
        l_opp_ppg_str = f"{l_opp_ppg:.1f}" if l_opp_ppg is not None else "N/A"
        ppg_line = (
            f"PPG: {ppg} for / {opp_ppg} against  ·  "
            f"L{actual_n}: {l_ppg_str} for / {l_opp_ppg_str} against"
        )
    return [
        f"Record: {record_line}",
        ppg_line,
    ]


def _recent_results(team: dict) -> list[str]:
    stats = team.get("stats", {})
    return stats.get("recent_results", [])


def _count_pi_per_game(team: dict) -> tuple[float, float]:
    pbp = team.get("pbp_entry") or {}
    games = pbp.get("games", []) or []
    game_count = max(len(games), 1)
    drawn = 0
    allowed = 0
    for g in games:
        for p in g.get("penalty_details", []) or []:
            if not p.get("accepted", False):
                continue
            text = f"{p.get('type') or ''} {p.get('description') or ''}".lower()
            if not ("pass interference" in text or re.search(r"\b(dpi|opi)\b", text)):
                continue
            side = (p.get("offense_or_defense") or "").lower()
            if side == "defense":
                drawn += 1
            elif side == "offense":
                allowed += 1
    return round(drawn / game_count, 1), round(allowed / game_count, 1)


def _key_signals(team: dict) -> list[str]:
    stats = team.get("stats", {}) or {}
    last_n = team.get("last_n", {}) or {}

    off_plays_pg = _safe_float(stats.get("offensive_plays_per_game"))
    def_plays_pg = _safe_float(stats.get("defensive_plays_allowed_per_game"))
    turnover_margin = stats.get("turnover_margin", "N/A")
    pi_drawn_pg, pi_allowed_pg = _count_pi_per_game(team)

    plays_line = "Plays/Game: Off N/A / Def Allowed N/A"
    if off_plays_pg is not None and def_plays_pg is not None:
        plays_line = f"Plays/Game: Off {off_plays_pg:.1f} / Def Allowed {def_plays_pg:.1f}"
        if _should_show_last_n(team):
            actual_n = last_n.get("actual_n", last_n.get("required_n", 0))
            l_off = _safe_float(last_n.get("offensive_plays_per_game"))
            l_def = _safe_float(last_n.get("defensive_plays_allowed_per_game"))
            if l_off is not None and l_def is not None and (
                abs(l_off - off_plays_pg) >= 2 or abs(l_def - def_plays_pg) >= 2
            ):
                plays_line += f" (L{actual_n}: {l_off:.1f} / {l_def:.1f})"

    return [
        plays_line,
        f"Turnover Margin: {turnover_margin}",
        f"PI Drawn/Game: {pi_drawn_pg:.1f}",
        f"PI Allowed/Game: {pi_allowed_pg:.1f}",
    ]


def _team_html(team: dict) -> str:
    lines = _coach_lines(team)
    summary = _season_summary(team)
    recent = _recent_results(team)
    key_signals = _key_signals(team)

    coach_html = "".join(f"<li>{l}</li>" for l in lines)
    summary_html = "".join(f"<li>{l}</li>" for l in summary)
    recent_html = "".join(f"<li>{r}</li>" for r in recent) if recent else "<li>N/A</li>"
    key_html = "".join(f"<li>{l}</li>" for l in key_signals)

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Coaches</h4>
        <ul>{coach_html}</ul>
      </div>
      <div class="block">
        <h4>Season Summary</h4>
        <ul>{summary_html}</ul>
      </div>
      <div class="block">
        <h4>Key Signals</h4>
        <ul>{key_html}</ul>
      </div>
      <div class="block">
        <h4>Recent Results</h4>
        <ul>{recent_html}</ul>
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    lines = [f"*{team['display_name']}*"]
    lines.append("Coaches:")
    for l in _coach_lines(team):
        lines.append(f"- {l}")
    lines.append("Season Summary:")
    stats = team.get("stats", {})
    record = stats.get("record", "N/A")
    conf_record = stats.get("conf_record", "")
    conf = team.get("conference", "")
    record_line = record
    if conf_record and conf_record != "0-0":
        record_line = f"{record} ({conf_record} {conf})"
    lines.append(f"- Record: {record_line}")

    ppg = stats.get("ppg", "N/A")
    opp_ppg = stats.get("opp_ppg", "N/A")
    ppg_line = f"PPG: {ppg} for / {opp_ppg} against"
    if _should_show_last_n(team):
        last_n = team.get("last_n", {})
        actual_n = last_n.get("actual_n", last_n.get("required_n", 0))
        l_ppg = _safe_float(last_n.get("ppg"))
        l_opp_ppg = _safe_float(last_n.get("opp_ppg"))
        season_ppg = _safe_float(ppg)
        season_opp_ppg = _safe_float(opp_ppg)
        diffs = []
        if l_ppg is not None and season_ppg is not None:
            diffs.append(abs(l_ppg - season_ppg))
        if l_opp_ppg is not None and season_opp_ppg is not None:
            diffs.append(abs(l_opp_ppg - season_opp_ppg))
        if l_ppg is not None and l_opp_ppg is not None and diffs and any(diff >= 0.8 for diff in diffs):
            ppg_line += f" (L{actual_n}: {l_ppg:.1f} / {l_opp_ppg:.1f})"
    lines.append(f"- {ppg_line}")
    lines.append("Key Signals:")
    for sig in _key_signals(team):
        lines.append(f"- {sig}")
    lines.append("Recent Results (last 5):")
    recent = _recent_results(team)
    if recent:
        for r in recent:
            lines.append(f"- {r}")
    else:
        lines.append("- N/A")
    return "\n".join(lines)


def build(team1: dict, team2: dict, week: int | None, season: int) -> dict:
    """Returns section dict with keys: title, html_content, md_content."""
    now = datetime.now().strftime("%b %d, %Y %H:%M")
    week_str = f"Week {week} | " if week else ""

    html_content = f"""
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    <div class="section-note">Generated {now} · {week_str}{season} Season</div>
    """

    md_content = "\n\n".join([
        f"🏈 *GAME PREP BRIEF*\n{week_str}{season} Season\n{team1['display_name']} vs {team2['display_name']}",
        _team_md(team1),
        _team_md(team2),
    ])

    return {
        "title": "Overview",
        "html_content": html_content,
        "md_content": md_content,
        "key": "overview",
    }
