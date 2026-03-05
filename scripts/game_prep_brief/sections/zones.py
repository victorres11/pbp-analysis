from __future__ import annotations

import sys


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", [])


def _sum(games: list[dict], key: str) -> int:
    return sum(g.get(key, 0) or 0 for g in games)


def _xml_row(team: dict, category: str) -> dict:
    pbp = team.get("pbp_entry") or {}
    if not pbp.get("xml_source"):
        return {}
    stats = pbp.get("xml_stats") or {}
    cat = stats.get(category) or {}
    if not isinstance(cat, dict):
        return {}
    if cat:
        _, row = max(cat.items(), key=lambda item: (item[1].get("games", 0) if isinstance(item[1], dict) else 0))
        if isinstance(row, dict):
            return row
    return {}


def _should_show_last_n(team: dict) -> bool:
    last_n = team.get("last_n", {}) or {}
    return last_n.get("actual_n", 0) >= last_n.get("required_n", 3)


def _trend_arrow(current, l3, higher_is_better: bool = True) -> str:
    if current is None or l3 is None or current == l3:
        return ""
    if higher_is_better:
        is_up = l3 > current
    else:
        is_up = l3 < current
    color = "#1b7f3a" if is_up else "#b3261e"
    arrow = "↑" if is_up else "↓"
    return f" <span style=\"color: {color};\">{arrow}</span>"


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rate(n: int, d: int) -> float:
    if not isinstance(n, (int, float)) or not isinstance(d, (int, float)) or not d:
        return None
    return round((n / d) * 100.0, 1)


def _warn_zone_invariants(team_name: str, scope: str, stats: dict) -> None:
    gz_trips = _to_float(stats.get("gz_trips"))
    rz_trips = _to_float(stats.get("rz_trips"))
    trz_trips = _to_float(stats.get("trz_trips"))
    rz_tds = _to_float(stats.get("rz_tds"))
    trz_tds = _to_float(stats.get("trz_tds"))

    def _warn(message: str) -> None:
        print(f"[warn] {team_name} {scope}: {message}", file=sys.stderr)

    if gz_trips is not None and rz_trips is not None and rz_trips > gz_trips:
        _warn(f"RZ trips ({int(rz_trips)}) > GZ trips ({int(gz_trips)})")
    if rz_trips is not None and trz_trips is not None and trz_trips > rz_trips:
        _warn(f"TRZ trips ({int(trz_trips)}) > RZ trips ({int(rz_trips)})")
    if rz_trips is not None and rz_tds is not None and rz_tds > rz_trips:
        _warn(f"RZ TDs ({int(rz_tds)}) > RZ trips ({int(rz_trips)})")
    if trz_trips is not None and trz_tds is not None and trz_tds > trz_trips:
        _warn(f"TRZ TDs ({int(trz_tds)}) > TRZ trips ({int(trz_trips)})")


def _team_zone_stats(team: dict) -> dict:
    xml_rz = _xml_row(team, "red_zone")
    games = _games(team)
    rz_trips = _sum(games, "red_zone_trips")
    rz_tds = _sum(games, "red_zone_tds")
    rz_fgs = _sum(games, "red_zone_fgs")
    trz_trips = _sum(games, "tight_red_zone_trips")
    trz_tds = _sum(games, "tight_red_zone_tds")
    trz_fgs = _sum(games, "tight_red_zone_fgs")
    gz_trips = _sum(games, "green_zone_trips")
    gz_tds = _sum(games, "green_zone_tds")
    gz_fgs = _sum(games, "green_zone_fgs")
    gz_failed = _sum(games, "green_zone_failed")

    # Use one consistent parser-derived source for zone trip/TD/FG totals so
    # GZ >= RZ >= TRZ invariants remain meaningful. Keep XML row only as a
    # fallback when local RZ data is missing and for external rank display.
    if not rz_trips and xml_rz:
        rz_rate = xml_rz.get("rz_td_rate")
        rz_trips = xml_rz.get("rz_trips")
        rz_tds = xml_rz.get("rz_tds")
        rz_fgs = xml_rz.get("rz_fgs")
        rz_td_pct = _rate(rz_tds, rz_trips)
        if rz_td_pct is None:
            if not isinstance(rz_rate, (int, float)):
                rz_rate = (
                    (rz_tds / rz_trips)
                    if isinstance(rz_tds, (int, float)) and isinstance(rz_trips, (int, float)) and rz_trips
                    else None
                )
            rz_td_pct = (
                round(rz_rate * 100, 1)
                if isinstance(rz_rate, (int, float)) and rz_rate <= 1
                else round(float(rz_rate), 1)
                if isinstance(rz_rate, (int, float))
                else "N/A"
            )
        rz_eff = _rate((rz_tds or 0) + (rz_fgs or 0), rz_trips)
        if rz_eff is None:
            conv_rate = xml_rz.get("rz_conversion_rate")
            rz_eff = round(conv_rate * 100, 1) if isinstance(conv_rate, (int, float)) else "N/A"
        return {
            "rz_trips": rz_trips if rz_trips is not None else "N/A",
            "rz_tds": rz_tds if rz_tds is not None else "N/A",
            "rz_fgs": rz_fgs if rz_fgs is not None else "N/A",
            "rz_td_pct": rz_td_pct,
            "rz_eff": rz_eff,
            "trz_trips": trz_trips if trz_trips else "N/A",
            "trz_tds": trz_tds if trz_trips else "N/A",
            "trz_fgs": trz_fgs if trz_trips else "N/A",
            "trz_td_pct": _rate(trz_tds, trz_trips) if trz_trips else "N/A",
            "gz_trips": gz_trips if gz_trips else "N/A",
            "gz_tds": gz_tds if gz_trips else "N/A",
            "gz_fgs": gz_fgs if gz_trips else "N/A",
            "gz_td_pct": _rate(gz_tds, gz_trips) if gz_trips else "N/A",
            "gz_success": _rate(gz_tds + gz_fgs, gz_trips) if gz_trips else "N/A",
            "gz_failed": gz_failed if gz_trips else "N/A",
        }

    return {
        "rz_trips": rz_trips,
        "rz_tds": rz_tds,
        "rz_fgs": rz_fgs,
        "rz_td_pct": _rate(rz_tds, rz_trips),
        "rz_eff": _rate(rz_tds + rz_fgs, rz_trips),
        "trz_trips": trz_trips,
        "trz_tds": trz_tds,
        "trz_fgs": trz_fgs,
        "trz_td_pct": _rate(trz_tds, trz_trips),
        "gz_trips": gz_trips,
        "gz_tds": gz_tds,
        "gz_fgs": gz_fgs,
        "gz_td_pct": _rate(gz_tds, gz_trips),
        "gz_success": _rate(gz_tds + gz_fgs, gz_trips),
        "gz_failed": gz_failed,
    }


def _team_html(team: dict, stats: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No PBP data.</em></p></div>"
    rz_rank = team.get("stats", {}).get("red_zone_rank", "N/A")
    last_n = team.get("last_n", {}) or {}
    show_last_n = _should_show_last_n(team)
    l3_rz_trips = last_n.get("rz_trips")
    l3_rz_tds = last_n.get("rz_tds")
    l3_rz_fgs = last_n.get("rz_fgs")
    l3_rz_td_pct = last_n.get("rz_td_pct")
    l3_trz_trips = last_n.get("tight_rz_trips")
    l3_trz_tds = last_n.get("tight_rz_tds")
    l3_trz_fgs = last_n.get("tight_rz_fgs")
    l3_trz_td_pct = last_n.get("tight_rz_td_pct")
    l3_gz_trips = last_n.get("green_zone_trips")
    l3_gz_tds = last_n.get("green_zone_tds")
    l3_gz_fgs = last_n.get("green_zone_fgs")
    l3_gz_td_pct = _rate((l3_gz_tds or 0), (l3_gz_trips or 0)) if l3_gz_trips else None
    l3_gz_success = last_n.get("green_zone_success")
    if l3_gz_success is None and l3_gz_trips is not None and l3_gz_tds is not None:
        l3_gz_success = _rate((l3_gz_tds or 0) + (l3_gz_fgs or 0), l3_gz_trips)

    def _last_n_compare(current, l3_value, suffix: str = "", higher_is_better: bool = True, show_arrow: bool = False) -> str:
        if not show_last_n or l3_value is None:
            return ""
        current_num = _to_float(current)
        l3_num = _to_float(l3_value)
        arrow = _trend_arrow(current_num, l3_num, higher_is_better) if show_arrow and current_num is not None and l3_num is not None else ""
        return f" →(L3) {l3_value}{suffix}{arrow}"

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Green Zone (Inside 30)</h4>
        <ul>
          <li>Trips: {stats['gz_trips']}{_last_n_compare(stats['gz_trips'], l3_gz_trips)}</li>
          <li>TDs: {stats['gz_tds']}{_last_n_compare(stats['gz_tds'], l3_gz_tds)}</li>
          <li>FGs: {stats['gz_fgs']}</li>
          <li>Success: {stats['gz_success']}%{_last_n_compare(stats['gz_success'], l3_gz_success, suffix="%", show_arrow=True)}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Red Zone</h4>
        <ul>
          <li>Trips: {stats['rz_trips']}{_last_n_compare(stats['rz_trips'], l3_rz_trips)}</li>
          <li>TDs: {stats['rz_tds']}{_last_n_compare(stats['rz_tds'], l3_rz_tds)}</li>
          <li>FGs: {stats['rz_fgs']}{_last_n_compare(stats['rz_fgs'], l3_rz_fgs)}</li>
          <li>TD%: {stats['rz_td_pct']}%{_last_n_compare(stats['rz_td_pct'], l3_rz_td_pct, suffix="%", show_arrow=True)}</li>
          <li>Efficiency: {stats['rz_eff']}%</li>
          <li>CFBStats Rank: {rz_rank}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Tight Red Zone (Inside 10)</h4>
        <ul>
          <li>Trips: {stats['trz_trips']}{_last_n_compare(stats['trz_trips'], l3_trz_trips)}</li>
          <li>TDs: {stats['trz_tds']}{_last_n_compare(stats['trz_tds'], l3_trz_tds)}</li>
          <li>FGs: {stats['trz_fgs']}{_last_n_compare(stats['trz_fgs'], l3_trz_fgs)}</li>
          <li>TD%: {stats['trz_td_pct']}%{_last_n_compare(stats['trz_td_pct'], l3_trz_td_pct, suffix="%", show_arrow=True)}</li>
        </ul>
      </div>
    </div>
    """


def _team_md(team: dict, stats: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- Red Zone: N/A"
    rz_note = ""
    trz_note = ""
    gz_note = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_rz_td_pct = last_n.get("rz_td_pct")
        l3_trz_td_pct = last_n.get("tight_rz_td_pct")
        l3_gz_trips = last_n.get("green_zone_trips")
        l3_gz_tds = last_n.get("green_zone_tds")
        l3_gz_fgs = last_n.get("green_zone_fgs")
        l3_gz_td_pct = _rate((l3_gz_tds or 0), (l3_gz_trips or 0)) if l3_gz_trips else None
        l3_gz_success = last_n.get("green_zone_success")
        if l3_gz_success is None and l3_gz_trips is not None and l3_gz_tds is not None:
            l3_gz_success = _rate((l3_gz_tds or 0) + (l3_gz_fgs or 0), l3_gz_trips)

        rz_now = _to_float(stats.get("rz_td_pct"))
        trz_now = _to_float(stats.get("trz_td_pct"))
        gz_now = _to_float(stats.get("gz_success"))
        l3_rz_num = _to_float(l3_rz_td_pct)
        l3_trz_num = _to_float(l3_trz_td_pct)
        l3_gz_num = _to_float(l3_gz_success)
        l3_gz_td_num = _to_float(l3_gz_td_pct)

        if l3_rz_num is not None and rz_now is not None and abs(l3_rz_num - rz_now) >= 8:
            rz_note = f" (L{actual_n}: {l3_rz_td_pct}%)"
        if l3_trz_num is not None and trz_now is not None and abs(l3_trz_num - trz_now) >= 8:
            trz_note = f" (L{actual_n}: {l3_trz_td_pct}%)"
        if l3_gz_num is not None and gz_now is not None and abs(l3_gz_num - gz_now) >= 8:
            gz_note = f" (L{actual_n}: {l3_gz_success}%)"
        gz_td_note = ""
        gz_td_now = _to_float(stats.get("gz_td_pct"))
        if l3_gz_td_num is not None and gz_td_now is not None and abs(l3_gz_td_num - gz_td_now) >= 8:
            gz_td_note = f" (L{actual_n}: {l3_gz_td_pct}%)"
    else:
        gz_td_note = ""
    rz_td = f"{stats['rz_td_pct']}%" if isinstance(stats.get("rz_td_pct"), (int, float)) else "N/A"
    trz_td = f"{stats['trz_td_pct']}%" if isinstance(stats.get("trz_td_pct"), (int, float)) else "N/A"
    gz_success = f"{stats['gz_success']}%" if isinstance(stats.get("gz_success"), (int, float)) else "N/A"
    gz_td = f"{stats['gz_td_pct']}%" if isinstance(stats.get("gz_td_pct"), (int, float)) else "N/A"
    return "\n".join([
        f"*{team['display_name']}*",
        f"- Green Zone Success: {gz_success}{gz_note}",
        f"- Red Zone TD%: {rz_td}{rz_note}",
        f"- Tight RZ TD%: {trz_td}{trz_note}",
        f"- Green Zone TD%: {gz_td}{gz_td_note}",
        f"- Green Zone Success (TD+FG / Trips): {gz_success}{gz_note}",
    ])


def build(team1: dict, team2: dict) -> dict:
    """Scoring zones section ordered as Green -> Red -> Tight Red."""
    t1_stats = _team_zone_stats(team1) if team1.get("has_pbp") else {"rz_td_pct": "N/A"}
    t2_stats = _team_zone_stats(team2) if team2.get("has_pbp") else {"rz_td_pct": "N/A"}
    t1_name = team1.get("display_name", "Team 1")
    t2_name = team2.get("display_name", "Team 2")
    _warn_zone_invariants(t1_name, "season", t1_stats)
    _warn_zone_invariants(t2_name, "season", t2_stats)
    if _should_show_last_n(team1):
        _warn_zone_invariants(
            t1_name,
            f"last-{team1.get('last_n', {}).get('actual_n', 0)}",
            {
                "gz_trips": (team1.get("last_n") or {}).get("green_zone_trips"),
                "rz_trips": (team1.get("last_n") or {}).get("rz_trips"),
                "trz_trips": (team1.get("last_n") or {}).get("tight_rz_trips"),
                "rz_tds": (team1.get("last_n") or {}).get("rz_tds"),
                "trz_tds": (team1.get("last_n") or {}).get("tight_rz_tds"),
            },
        )
    if _should_show_last_n(team2):
        _warn_zone_invariants(
            t2_name,
            f"last-{team2.get('last_n', {}).get('actual_n', 0)}",
            {
                "gz_trips": (team2.get("last_n") or {}).get("green_zone_trips"),
                "rz_trips": (team2.get("last_n") or {}).get("rz_trips"),
                "trz_trips": (team2.get("last_n") or {}).get("tight_rz_trips"),
                "rz_tds": (team2.get("last_n") or {}).get("rz_tds"),
                "trz_tds": (team2.get("last_n") or {}).get("tight_rz_tds"),
            },
        )
    t1_rz = t1_stats.get("rz_td_pct", "N/A")
    t2_rz = t2_stats.get("rz_td_pct", "N/A")

    html_content = f"""
    <div class="section-grid">
      {_team_html(team1, t1_stats)}
      {_team_html(team2, t2_stats)}
    </div>
    """

    md_content = "\n\n".join([
        "*Scoring Zones*",
        _team_md(team1, t1_stats),
        _team_md(team2, t2_stats),
    ])

    return {
        "title": "Scoring Zones",
        "html_content": html_content,
        "md_content": md_content,
        "key": "zones",
    }
