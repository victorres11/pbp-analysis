from __future__ import annotations


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", [])


def _aggregate_explosives(games: list[dict]) -> dict:
    totals = {
        "explosives": 0,
        "explosive_passes": 0,
        "explosive_rushes": 0,
    }
    for g in games:
        totals["explosive_passes"] += g.get("explosive_passes", 0) or 0
        totals["explosive_rushes"] += g.get("explosive_rushes", 0) or 0
        if g.get("explosives") is not None:
            totals["explosives"] += g.get("explosives", 0) or 0
        else:
            totals["explosives"] += (g.get("explosive_passes", 0) or 0) + (
                g.get("explosive_rushes", 0) or 0
            )
    return totals


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


def _per_game_trend(games: list[dict]) -> list[str]:
    trend = []
    for g in sorted(games, key=lambda x: x.get("game_number", 0)):
        opp = g.get("opponent", "?")
        count = g.get("explosives")
        if count is None:
            count = (g.get("explosive_passes", 0) or 0) + (g.get("explosive_rushes", 0) or 0)
        trend.append(f"G{g.get('game_number', '?')} vs {opp}: {count}")
    return trend


def _iter_offensive_plays(game: dict, team_abbr: str) -> list[dict]:
    """Flatten quarter/drive play_tree into offense-only play rows."""
    out: list[dict] = []
    play_tree = game.get("play_tree") or []
    for quarter in play_tree:
        for drive in (quarter.get("drives") or []):
            for play in (drive.get("plays") or []):
                if (play.get("offense") or "").upper() != team_abbr:
                    continue
                if play.get("is_no_play"):
                    continue
                out.append(play)
    return out


def _is_rush(desc: str) -> bool:
    d = desc.lower()
    if "kneel" in d:
        return False
    return " rush " in f" {d} "


def _is_pass(desc: str) -> bool:
    d = desc.lower()
    return " pass " in f" {d} "


def _to_yards(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _non_explosive_profile(games: list[dict], team_abbr: str) -> dict:
    """Avg run/pass yards excluding explosive plays (15+ rush, 20+ pass)."""
    rush_att = rush_yds = 0.0
    pass_att = pass_yds = 0.0

    for g in games:
        for p in _iter_offensive_plays(g, team_abbr):
            desc = p.get("description") or ""
            yards = _to_yards(p.get("yards"))
            if yards is None:
                continue
            if _is_rush(desc):
                if yards < 15:
                    rush_att += 1
                    rush_yds += yards
            elif _is_pass(desc):
                if yards < 20:
                    pass_att += 1
                    pass_yds += yards

    return {
        "rush_avg": round(rush_yds / rush_att, 2) if rush_att else 0.0,
        "pass_avg": round(pass_yds / pass_att, 2) if pass_att else 0.0,
        "rush_att": int(rush_att),
        "pass_att": int(pass_att),
    }


def _top_explosive_plays(games: list[dict]) -> list[dict]:
    plays = []
    for g in games:
        for p in g.get("explosive_details", []) or []:
            plays.append(p)
    plays.sort(key=lambda p: p.get("yards", 0), reverse=True)
    return plays[:10]


def _explosive_play_html(p):
    header = f"<strong>{p.get('yards','?')} yd {p.get('type','play')} — {p.get('player','?')}</strong>"
    desc = p.get('description') or p.get('play_text') or p.get('text') or ''
    if desc:
        return f"<li>{header}<br><span style=\"color:#555;font-size:0.9em;\">{desc}</span></li>"
    else:
        return f"<li>{header}</li>"


def _explosive_play_md(p):
    header = f"**{p.get('yards','?')} yd {p.get('type','play')} — {p.get('player','?')}**"
    desc = p.get('description') or p.get('play_text') or p.get('text') or ''
    if desc:
        return f"  • {header}\n    {desc}"
    else:
        return f"  • {header}"


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No PBP data.</em></p></div>"

    games = _games(team)
    totals = _aggregate_explosives(games)
    xml_expl = _xml_row(team, "explosives")
    if xml_expl:
        totals = {
            "explosives": xml_expl.get("explosives", totals["explosives"]),
            "explosive_passes": xml_expl.get("explosive_pass", totals["explosive_passes"]),
            "explosive_rushes": xml_expl.get("explosive_run", totals["explosive_rushes"]),
        }
    trend = _per_game_trend(games)
    top_plays = _top_explosive_plays(games)
    team_abbr = ((team.get("stats") or {}).get("abbr") or ((team.get("pbp_entry") or {}).get("abbr") or "")).upper()
    ne_season = _non_explosive_profile(games, team_abbr) if team_abbr else {"rush_avg": 0.0, "pass_avg": 0.0, "rush_att": 0, "pass_att": 0}

    trend_html = "".join(f"<li>{t}</li>" for t in trend) if trend else "<li>N/A</li>"
    plays_html = "".join(_explosive_play_html(p) for p in top_plays) or "<li>N/A</li>"

    last_n_html = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_epg = last_n.get("explosives_per_game", 0) or 0
        l3_ppg = last_n.get("explosive_passes_per_game", 0) or 0
        l3_rpg = last_n.get("explosive_rushes_per_game", 0) or 0
        season_epg = totals["explosives"] / len(games) if games else 0
        last_n_games = sorted(games, key=lambda x: x.get("game_number", 0))[-actual_n:] if actual_n else []
        ne_last_n = _non_explosive_profile(last_n_games, team_abbr) if team_abbr and last_n_games else {"rush_avg": 0.0, "pass_avg": 0.0}

        epg_arrow = ""
        if l3_epg > season_epg:
            epg_arrow = " <span style=\"color: #1b7f3a;\">↑</span>"
        elif l3_epg < season_epg:
            epg_arrow = " <span style=\"color: #b3261e;\">↓</span>"

        last_n_html = f"""
      <div class="block">
        <h4>Last {actual_n} Trending</h4>
        <ul>
          <li>Explosives/Game: {l3_epg:.1f} (Season: {season_epg:.1f}){epg_arrow}</li>
          <li>Pass/Game: {l3_ppg:.1f} / Rush/Game: {l3_rpg:.1f}</li>
          <li>Non-Explosive Avg (Run/Pass): {ne_last_n['rush_avg']:.2f} / {ne_last_n['pass_avg']:.2f}</li>
        </ul>
      </div>
        """

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Totals</h4>
        <ul>
          <li>Total Explosives: {totals['explosives']}</li>
          <li>Explosive Passes: {totals['explosive_passes']}</li>
          <li>Explosive Rushes: {totals['explosive_rushes']}</li>
        </ul>
      </div>
      {last_n_html}
      <div class="block">
        <h4>Per-Game Trend</h4>
        <ul>{trend_html}</ul>
      </div>
      <div class="block">
        <h4>Without Explosives</h4>
        <ul>
          <li>Run Avg (&lt;15y): {ne_season['rush_avg']:.2f} ({ne_season['rush_att']} att)</li>
          <li>Pass Avg (&lt;20y): {ne_season['pass_avg']:.2f} ({ne_season['pass_att']} att)</li>
        </ul>
      </div>
      <div class="block">
        <h4>Top Explosive Plays</h4>
        <ul>{plays_html}</ul>
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- Explosives: N/A"
    games = _games(team)
    totals = _aggregate_explosives(games)
    xml_expl = _xml_row(team, "explosives")
    if xml_expl:
        totals = {
            "explosives": xml_expl.get("explosives", totals["explosives"]),
            "explosive_passes": xml_expl.get("explosive_pass", totals["explosive_passes"]),
            "explosive_rushes": xml_expl.get("explosive_run", totals["explosive_rushes"]),
        }
    top_plays = _top_explosive_plays(games)[:3]
    team_abbr = ((team.get("stats") or {}).get("abbr") or ((team.get("pbp_entry") or {}).get("abbr") or "")).upper()
    ne_season = _non_explosive_profile(games, team_abbr) if team_abbr else {"rush_avg": 0.0, "pass_avg": 0.0}
    lines = [f"*{team['display_name']}*"]
    explosives_suffix = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_epg = last_n.get("explosives_per_game", 0) or 0
        season_epg = totals["explosives"] / len(games) if games else 0
        if abs(l3_epg - season_epg) >= 0.8:
            explosives_suffix = f" (L{actual_n}: {l3_epg:.1f}/gm)"
    lines.append(
        f"- Total Explosives: {totals['explosives']} (Pass {totals['explosive_passes']}, Rush {totals['explosive_rushes']}){explosives_suffix}"
    )
    lines.append(
        f"- Without Explosives: Run {ne_season['rush_avg']:.2f} / Pass {ne_season['pass_avg']:.2f}"
    )
    if top_plays:
        lines.append("- Top Plays:")
        for p in top_plays:
            lines.append(_explosive_play_md(p))
    return "\n".join(lines)


def build(team1: dict, team2: dict) -> dict:
    """Explosive plays section."""
    html_content = f"""
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Explosive Plays*",
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Explosive Plays",
        "html_content": html_content,
        "md_content": md_content,
        "key": "explosives",
    }
