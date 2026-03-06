from __future__ import annotations

from .delta import metric_delta_html, metric_delta_md
from ._sources import SRC_PBP


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", []) or []


def _rate(conv: int, att: int) -> float | None:
    if not att:
        return None
    return round((conv / att) * 100.0, 1)


def _totals(team: dict) -> dict:
    games = _games(team)
    off_att = sum(g.get("two_pt_attempts", 0) or 0 for g in games)
    off_conv = sum(g.get("two_pt_conversions", 0) or 0 for g in games)
    off_rush_att = sum(g.get("two_pt_rush_attempts", 0) or 0 for g in games)
    off_rush_conv = sum(g.get("two_pt_rush_conversions", 0) or 0 for g in games)
    off_pass_att = sum(g.get("two_pt_pass_attempts", 0) or 0 for g in games)
    off_pass_conv = sum(g.get("two_pt_pass_conversions", 0) or 0 for g in games)

    def_att = sum(g.get("opp_two_pt_attempts", 0) or 0 for g in games)
    def_conv = sum(g.get("opp_two_pt_conversions", 0) or 0 for g in games)

    return {
        "off_att": off_att,
        "off_conv": off_conv,
        "off_pct": _rate(off_conv, off_att),
        "off_rush_att": off_rush_att,
        "off_rush_conv": off_rush_conv,
        "off_pass_att": off_pass_att,
        "off_pass_conv": off_pass_conv,
        "def_att": def_att,
        "def_conv": def_conv,
        "def_allowed_pct": _rate(def_conv, def_att),
    }


def _per_game_rows(games: list[dict]) -> str:
    rows = []
    for g in sorted(games, key=lambda x: x.get("game_number", 0)):
        wk = g.get("week") or "?"
        opp = g.get("opponent") or "?"
        off_att = g.get("two_pt_attempts", 0) or 0
        off_conv = g.get("two_pt_conversions", 0) or 0
        def_att = g.get("opp_two_pt_attempts", 0) or 0
        def_conv = g.get("opp_two_pt_conversions", 0) or 0
        rows.append(
            "<tr>"
            f"<td style=\"text-align:left;\">{wk}</td>"
            f"<td style=\"text-align:left;\">{opp}</td>"
            f"<td style=\"text-align:right;\">{off_conv}/{off_att}</td>"
            f"<td style=\"text-align:right;\">{def_conv}/{def_att}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='4'>N/A</td></tr>"


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No 2PT data.</em></p></div>"

    games = _games(team)
    t = _totals(team)
    off_pct = f"{t['off_pct']:.1f}%" if t["off_pct"] is not None else "N/A"
    def_pct = f"{t['def_allowed_pct']:.1f}%" if t["def_allowed_pct"] is not None else "N/A"

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Season Totals</h4>
        <ul>
          <li>Offense: {t['off_conv']}/{t['off_att']} ({off_pct}){SRC_PBP}</li>
          <li>Defense Allowed: {t['def_conv']}/{t['def_att']} ({def_pct}){SRC_PBP}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Offense Split</h4>
        <ul>
          <li>Rush: {t['off_rush_conv']}/{t['off_rush_att']}{SRC_PBP}</li>
          <li>Pass: {t['off_pass_conv']}/{t['off_pass_att']}{SRC_PBP}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Per-Game</h4>
        <table style="width:100%; border-collapse:collapse; font-size:0.9em;">
          <thead>
            <tr>
              <th style="text-align:left;">Wk</th>
              <th style="text-align:left;">Opp</th>
              <th style="text-align:right;">Off 2PT</th>
              <th style="text-align:right;">Allowed 2PT</th>
            </tr>
          </thead>
          <tbody>{_per_game_rows(games)}</tbody>
        </table>
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- Two-Point: N/A"
    t = _totals(team)
    off_pct = f"{t['off_pct']:.1f}%" if t["off_pct"] is not None else "N/A"
    def_pct = f"{t['def_allowed_pct']:.1f}%" if t["def_allowed_pct"] is not None else "N/A"
    return "\n".join([
        f"*{team['display_name']}*",
        f"- Offense 2PT: {t['off_conv']}/{t['off_att']} ({off_pct})",
        f"- Defense Allowed 2PT: {t['def_conv']}/{t['def_att']} ({def_pct})",
        f"- Offense Split: Rush {t['off_rush_conv']}/{t['off_rush_att']} | Pass {t['off_pass_conv']}/{t['off_pass_att']}",
    ])


def build(team1: dict, team2: dict) -> dict:
    t1 = _totals(team1) if team1.get("has_pbp") else {"off_pct": None}
    t2 = _totals(team2) if team2.get("has_pbp") else {"off_pct": None}
    delta_html = metric_delta_html(
        "Offensive 2PT Conversion %",
        team1["display_name"],
        t1.get("off_pct"),
        team2["display_name"],
        t2.get("off_pct"),
        higher_is_better=True,
        suffix="%",
    )
    delta_md = metric_delta_md(
        "Offensive 2PT Conversion %",
        team1["display_name"],
        t1.get("off_pct"),
        team2["display_name"],
        t2.get("off_pct"),
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
        "*Two-Point Conversions*",
        delta_md,
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Two-Point",
        "html_content": html_content,
        "md_content": md_content,
        "key": "two_point",
    }
