from __future__ import annotations


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", [])


def _sum(values: list[float]) -> float:
    return sum(v for v in values if v is not None)


def _avg(values: list[float]) -> float:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def _fmt_num(v: object, suffix: str = "") -> str:
    try:
        return f"{float(v):.1f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_two_pt(conv: object, att: object) -> str:
    try:
        c = int(conv)
        a = int(att)
    except (TypeError, ValueError):
        return "N/A"
    if a <= 0:
        return "N/A"
    return f"{c}/{a}"


def _team_stats(team: dict) -> dict:
    games = _games(team)
    pbp = team.get("pbp_entry") or {}
    xml_stats = pbp.get("xml_stats") or {}
    xml_st = xml_stats.get("special_teams") if isinstance(xml_stats.get("special_teams"), dict) else {}
    xml_tp = xml_stats.get("two_point") if isinstance(xml_stats.get("two_point"), dict) else {}

    def _xml_row(category: dict) -> dict:
        if not category:
            return {}
        _, row = max(
            category.items(),
            key=lambda item: (item[1].get("games", 0) if isinstance(item[1], dict) else 0),
        )
        return row if isinstance(row, dict) else {}

    xml_st_row = _xml_row(xml_st)
    xml_tp_row = _xml_row(xml_tp)
    st_list = [g.get("special_teams", {}) or {} for g in games]
    has_any_data = bool(st_list) or bool(xml_st_row) or bool(xml_tp_row)

    fg_made = _sum([st.get("field_goals_made") for st in st_list])
    fg_att = _sum([st.get("field_goals_attempts") for st in st_list])
    fg_pct = round((fg_made / fg_att) * 100, 1) if fg_att else 0.0
    fg_long = max([st.get("field_goal_long", 0) or 0 for st in st_list] or [0])

    punts = _sum([st.get("punts") for st in st_list])
    punt_yards = _sum([st.get("punt_yards") for st in st_list])
    punt_net = _sum([st.get("punt_net_yards") for st in st_list])
    punt_avg = round(punt_yards / punts, 2) if punts else _avg([st.get("punt_avg") for st in st_list])
    punt_net_avg = round(punt_net / punts, 2) if punts else _avg([st.get("punt_net_avg") for st in st_list])
    punt_long = max([st.get("punt_long", 0) or 0 for st in st_list] or [0])
    punts_inside_20 = _sum([st.get("punts_inside_20") for st in st_list])
    punt_touchbacks = _sum([st.get("punt_touchbacks") for st in st_list])

    punt_returns = _sum([st.get("punt_returns") for st in st_list])
    punt_return_yards = _sum([st.get("punt_return_yards") for st in st_list])
    punt_return_avg = round(punt_return_yards / punt_returns, 2) if punt_returns else _avg([st.get("punt_return_avg") for st in st_list])
    punt_return_long = max([st.get("punt_return_long", 0) or 0 for st in st_list] or [0])
    punt_20_plus = _sum([st.get("punt_return_20_plus") for st in st_list])

    kick_returns = _sum([st.get("kickoff_returns") for st in st_list])
    kick_return_yards = _sum([st.get("kickoff_return_yards") for st in st_list])
    kick_return_avg = round(kick_return_yards / kick_returns, 2) if kick_returns else _avg([st.get("kickoff_return_avg") for st in st_list])
    kick_return_long = max([st.get("kickoff_return_long", 0) or 0 for st in st_list] or [0])
    kick_30_plus = _sum([st.get("kick_return_30_plus") for st in st_list])

    two_pt_att = int(_sum([g.get("two_pt_attempts") for g in games]))
    two_pt_conv = int(_sum([g.get("two_pt_conversions") for g in games]))
    two_pt_allowed_att = int(_sum([g.get("opp_two_pt_attempts") for g in games]))
    two_pt_allowed_conv = int(_sum([g.get("opp_two_pt_conversions") for g in games]))

    last3_games = sorted(games, key=lambda g: g.get("game_number", 0))[-3:]
    l3_two_pt_att = int(_sum([g.get("two_pt_attempts") for g in last3_games]))
    l3_two_pt_conv = int(_sum([g.get("two_pt_conversions") for g in last3_games]))
    l3_two_pt_allowed_att = int(_sum([g.get("opp_two_pt_attempts") for g in last3_games]))
    l3_two_pt_allowed_conv = int(_sum([g.get("opp_two_pt_conversions") for g in last3_games]))

    out = {
        "fg_made": int(fg_made),
        "fg_att": int(fg_att),
        "fg_pct": fg_pct if has_any_data else "N/A",
        "fg_long": fg_long if has_any_data else "N/A",
        "punts": int(punts),
        "punt_avg": punt_avg,
        "punt_net_avg": punt_net_avg,
        "punt_long": punt_long if has_any_data else "N/A",
        "punts_inside_20": int(punts_inside_20),
        "punt_touchbacks": int(punt_touchbacks),
        "punt_return_avg": punt_return_avg,
        "punt_return_long": punt_return_long if has_any_data else "N/A",
        "punt_20_plus": int(punt_20_plus),
        "kick_return_avg": kick_return_avg,
        "kick_return_long": kick_return_long if has_any_data else "N/A",
        "kick_30_plus": int(kick_30_plus),
        "special_teams_tds": int(_sum([st.get("special_teams_tds") for st in st_list])),
        "fg_blocks": int(_sum([st.get("fg_blocks") for st in st_list])),
        "punt_blocks": int(_sum([st.get("punt_blocks") for st in st_list])),
        "onside_attempts": int(_sum([st.get("onside_kicks_attempted") for st in st_list])),
        "onside_recovered": int(_sum([st.get("onside_kicks_recovered") for st in st_list])),
        "two_pt_att": two_pt_att,
        "two_pt_conv": two_pt_conv,
        "two_pt_allowed_att": two_pt_allowed_att,
        "two_pt_allowed_conv": two_pt_allowed_conv,
        "l3_two_pt_att": l3_two_pt_att,
        "l3_two_pt_conv": l3_two_pt_conv,
        "l3_two_pt_allowed_att": l3_two_pt_allowed_att,
        "l3_two_pt_allowed_conv": l3_two_pt_allowed_conv,
    }
    if xml_st_row:
        out["fg_att"] = int(xml_st_row.get("fg_attempts", out["fg_att"]) or 0)
        out["fg_made"] = int(xml_st_row.get("fg_made", out["fg_made"]) or 0)
        out["fg_pct"] = round((out["fg_made"] / out["fg_att"]) * 100, 1) if out["fg_att"] else "N/A"
        out["fg_long"] = xml_st_row.get("fg_longest", out["fg_long"])
    if xml_tp_row:
        out["two_pt_att"] = int(xml_tp_row.get("two_point_attempts", out["two_pt_att"]) or 0)
        out["two_pt_conv"] = int(xml_tp_row.get("two_point_conversions", out["two_pt_conv"]) or 0)
        out["two_pt_allowed_att"] = int(xml_tp_row.get("two_point_allowed_attempts", out["two_pt_allowed_att"]) or 0)
        out["two_pt_allowed_conv"] = int(xml_tp_row.get("two_point_allowed_conversions", out["two_pt_allowed_conv"]) or 0)
    elif not games:
        out["two_pt_att"] = "N/A"
        out["two_pt_conv"] = "N/A"
        out["two_pt_allowed_att"] = "N/A"
        out["two_pt_allowed_conv"] = "N/A"
        out["l3_two_pt_att"] = "N/A"
        out["l3_two_pt_conv"] = "N/A"
        out["l3_two_pt_allowed_att"] = "N/A"
        out["l3_two_pt_allowed_conv"] = "N/A"
    if not has_any_data:
        out.update(
            {
                "fg_made": "N/A",
                "fg_att": "N/A",
                "fg_pct": "N/A",
                "punts": "N/A",
                "punts_inside_20": "N/A",
                "punt_touchbacks": "N/A",
                "punt_20_plus": "N/A",
                "kick_30_plus": "N/A",
                "special_teams_tds": "N/A",
                "fg_blocks": "N/A",
                "punt_blocks": "N/A",
                "onside_attempts": "N/A",
                "onside_recovered": "N/A",
                "two_pt_att": "N/A",
                "two_pt_conv": "N/A",
                "two_pt_allowed_att": "N/A",
                "two_pt_allowed_conv": "N/A",
                "l3_two_pt_att": "N/A",
                "l3_two_pt_conv": "N/A",
                "l3_two_pt_allowed_att": "N/A",
                "l3_two_pt_allowed_conv": "N/A",
            }
        )
    return out


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No PBP data.</em></p></div>"
    stats = _team_stats(team)

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Field Goals</h4>
        <ul>
          <li>Made/Att: {stats['fg_made']} / {stats['fg_att']} ({_fmt_num(stats['fg_pct'], '%')})</li>
          <li>Long: {stats['fg_long']}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Punting</h4>
        <ul>
          <li>Avg / Net: {_fmt_num(stats['punt_avg'])} / {_fmt_num(stats['punt_net_avg'])}</li>
          <li>Long: {stats['punt_long']}</li>
          <li>Inside 20: {stats['punts_inside_20']} · TB: {stats['punt_touchbacks']}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Returns</h4>
        <ul>
          <li>Punt Return Avg/Long: {_fmt_num(stats['punt_return_avg'])} / {stats['punt_return_long']} (20+ {stats['punt_20_plus']})</li>
          <li>KO Return Avg/Long: {_fmt_num(stats['kick_return_avg'])} / {stats['kick_return_long']} (30+ {stats['kick_30_plus']})</li>
        </ul>
      </div>
      <div class="block">
        <h4>Impact Plays</h4>
        <ul>
          <li>ST TDs: {stats['special_teams_tds']}</li>
          <li>FG Blocks: {stats['fg_blocks']} · Punt Blocks: {stats['punt_blocks']}</li>
          <li>Onside: {stats['onside_recovered']} / {stats['onside_attempts']}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Two-Point Conversions</h4>
        <ul>
          <li>Offense: {_fmt_two_pt(stats['two_pt_conv'], stats['two_pt_att'])}</li>
          <li>Defense Allowed: {_fmt_two_pt(stats['two_pt_allowed_conv'], stats['two_pt_allowed_att'])}</li>
          <li>Last 3 O/D: {_fmt_two_pt(stats['l3_two_pt_conv'], stats['l3_two_pt_att'])} · {_fmt_two_pt(stats['l3_two_pt_allowed_conv'], stats['l3_two_pt_allowed_att'])}</li>
        </ul>
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- Special Teams: N/A"
    stats = _team_stats(team)
    return "\n".join([
        f"*{team['display_name']}*",
        f"- FG%: {_fmt_num(stats['fg_pct'], '%')} (Long {stats['fg_long']})",
        f"- Punt Avg: {_fmt_num(stats['punt_avg'])} (Net {_fmt_num(stats['punt_net_avg'])})",
        f"- 2PT O/D: {_fmt_two_pt(stats['two_pt_conv'], stats['two_pt_att'])} · {_fmt_two_pt(stats['two_pt_allowed_conv'], stats['two_pt_allowed_att'])}",
        f"- Return TDs: {stats['special_teams_tds']}",
    ])


def build(team1: dict, team2: dict) -> dict:
    """Special teams deep-dive section."""
    html_content = f"""
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Special Teams*",
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Special Teams",
        "html_content": html_content,
        "md_content": md_content,
        "key": "special_teams",
    }
