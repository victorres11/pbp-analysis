from __future__ import annotations


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", [])


def _sum(games: list[dict], key: str) -> int:
    return sum(g.get(key, 0) or 0 for g in games)


def _should_show_last_n(team: dict) -> bool:
    last_n = team.get("last_n", {}) or {}
    return last_n.get("actual_n", 0) >= last_n.get("required_n", 3)


def _fourth_down_rank(team: dict) -> str:
    pbp = team.get("pbp_entry") or {}
    rankings = pbp.get("cfbstats", {}).get("rankings", {}).get("all", {})
    r = rankings.get("fourth_down", {})
    val = r.get("value", "")
    rnk = r.get("rank", "")
    if val != "" and rnk != "":
        return f"{val} (#{rnk})"
    return val or "N/A"


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No PBP data.</em></p></div>"
    games = _games(team)
    game_count = max(len(games), 1)
    attempts = _sum(games, "4th_down_attempts")
    conversions = _sum(games, "4th_down_conversions")
    pct = round((conversions / attempts) * 100, 1) if attempts else 0.0
    offense_plays_total = _sum(games, "total_plays")
    offense_plays_pg = round(offense_plays_total / game_count, 1)
    defense_plays_pg = team.get("stats", {}).get("defensive_plays_allowed_per_game", 0.0)
    per_game = [
        f"G{g.get('game_number','?')} vs {g.get('opponent','?')}: {g.get('4th_down_attempts',0)} att"
        for g in sorted(games, key=lambda x: x.get("game_number", 0))
    ]
    per_game_html = "".join(f"<li>{l}</li>" for l in per_game) or "<li>N/A</li>"
    third_down = team.get("stats", {}).get("third_down", "N/A")
    plays_last_n_line = ""
    last_n_line = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_attempts = last_n.get("fourth_down_attempts", 0)
        l3_conversions = last_n.get("fourth_down_conversions", 0)
        l3_pct = round((l3_conversions / l3_attempts) * 100, 1) if l3_attempts else 0.0
        l3_offense_plays_pg = last_n.get("offensive_plays_per_game", 0.0)
        l3_defense_plays_pg = last_n.get("defensive_plays_allowed_per_game", 0.0)
        plays_last_n_line = (
            f"<li>L{actual_n}: {l3_offense_plays_pg:.1f} offensive / "
            f"{l3_defense_plays_pg:.1f} allowed</li>"
        )
        l3_display = f"L{actual_n}: {l3_attempts} att / {l3_conversions} conv ({l3_pct}%)"
        if l3_pct > pct:
            last_n_line = f"<li><span style=\"color: #1b7f3a;\">{l3_display}</span></li>"
        elif l3_pct < pct:
            last_n_line = f"<li><span style=\"color: #b3261e;\">{l3_display}</span></li>"
        else:
            last_n_line = f"<li>{l3_display}</li>"

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Plays/Game</h4>
        <ul>
          <li>Offense: {offense_plays_pg:.1f}</li>
          <li>Defense Allowed: {float(defense_plays_pg):.1f}</li>
          {plays_last_n_line}
        </ul>
      </div>
      <div class="block">
        <h4>3rd Down</h4>
        <ul>
          <li>CFBStats: {third_down}</li>
        </ul>
      </div>
      <div class="block">
        <h4>4th Down</h4>
        <ul>
          <li>Attempts / Conversions: {attempts} / {conversions}</li>
          <li>Conversion %: {pct}%</li>
          {last_n_line}
          <li>CFBStats: {_fourth_down_rank(team)}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Per-Game Attempts</h4>
        <ul>{per_game_html}</ul>
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- 3rd/4th Down: N/A"
    games = _games(team)
    game_count = max(len(games), 1)
    attempts = _sum(games, "4th_down_attempts")
    conversions = _sum(games, "4th_down_conversions")
    pct = round((conversions / attempts) * 100, 1) if attempts else 0.0
    offense_plays_pg = round(_sum(games, "total_plays") / game_count, 1)
    defense_plays_pg = float(team.get("stats", {}).get("defensive_plays_allowed_per_game", 0.0))
    third_down = team.get("stats", {}).get("third_down", "N/A")
    plays_suffix = ""
    last_n_suffix = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_attempts = last_n.get("fourth_down_attempts", 0)
        l3_conversions = last_n.get("fourth_down_conversions", 0)
        l3_pct = round((l3_conversions / l3_attempts) * 100, 1) if l3_attempts else 0.0
        l3_offense_plays_pg = float(last_n.get("offensive_plays_per_game", 0.0))
        l3_defense_plays_pg = float(last_n.get("defensive_plays_allowed_per_game", 0.0))
        if abs(l3_offense_plays_pg - offense_plays_pg) >= 2 or abs(l3_defense_plays_pg - defense_plays_pg) >= 2:
            plays_suffix = f" (L{actual_n}: {l3_offense_plays_pg:.1f} / {l3_defense_plays_pg:.1f})"
        if abs(l3_pct - pct) >= 8:
            last_n_suffix = f" (L{actual_n}: {l3_conversions}/{l3_attempts}, {l3_pct}%)"
    return "\n".join([
        f"*{team['display_name']}*",
        f"- Plays/Game: Off {offense_plays_pg:.1f} / Def Allowed {defense_plays_pg:.1f}{plays_suffix}",
        f"- 3rd Down: {third_down}",
        f"- 4th Down: {conversions}/{attempts} ({pct}%){last_n_suffix}",
    ])


def build(team1: dict, team2: dict) -> dict:
    """3rd and 4th down tendencies section."""
    html_content = f"""
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Situational (3rd/4th Down)*",
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Situational",
        "html_content": html_content,
        "md_content": md_content,
        "key": "situational",
    }
