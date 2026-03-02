from __future__ import annotations
import re

CATEGORIES = [
    "scoring_offense",
    "scoring_defense",
    "total_offense",
    "total_defense",
    "rushing_offense",
    "rushing_defense",
    "passing_offense",
    "passing_defense",
    "scoring_margin",
    "turnover_margin",
    "red_zone",
    "third_down",
    "fourth_down",
    "explosives",
    "penalties",
    "time_of_possession",
    "sacks_offense",
    "sacks_defense",
    "tfl_offense",
    "tfl_defense",
]

LABELS = {
    "scoring_offense": "Scoring Offense",
    "scoring_defense": "Scoring Defense",
    "total_offense": "Total Offense",
    "total_defense": "Total Defense",
    "rushing_offense": "Rushing Offense",
    "rushing_defense": "Rushing Defense",
    "passing_offense": "Passing Offense",
    "passing_defense": "Passing Defense",
    "scoring_margin": "Scoring Margin",
    "turnover_margin": "Turnover Margin",
    "red_zone": "Red Zone TD%",
    "third_down": "3rd Down %",
    "fourth_down": "4th Down %",
    "explosives": "Explosive Plays",
    "penalties": "Penalties",
    "time_of_possession": "Time of Possession",
    "sacks_offense": "Sacks Allowed",
    "sacks_defense": "Sacks",
    "tfl_offense": "TFL Allowed",
    "tfl_defense": "TFL",
}


def _rank(rankings: dict, key: str) -> dict:
    r = rankings.get(key, {}) if rankings else {}
    return {
        "value": r.get("value"),
        "rank": r.get("rank"),
    }


def _fmt(rank_data: dict) -> str:
    val = rank_data.get("value")
    rnk = rank_data.get("rank")
    if val is None and rnk is None:
        return "N/A"
    if val is not None and rnk is not None:
        return f"{val} (#{rnk})"
    return str(val) if val is not None else "N/A"


def _table_html(team1: dict, team2: dict, scope: str) -> str:
    r1 = (team1.get("pbp_entry") or {}).get("cfbstats", {}).get("rankings", {}).get(scope, {})
    r2 = (team2.get("pbp_entry") or {}).get("cfbstats", {}).get("rankings", {}).get(scope, {})
    rows = []
    for key in CATEGORIES:
        rows.append(
            f"<tr><td>{LABELS.get(key, key)}</td><td>{_fmt(_rank(r1, key))}</td><td>{_fmt(_rank(r2, key))}</td></tr>"
        )
    rows_html = "".join(rows)
    return f"""
    <h4>{scope.title()} Rankings</h4>
    <table class="rankings-table">
      <tr><th>Category</th><th>{team1['display_name']}</th><th>{team2['display_name']}</th></tr>
      {rows_html}
    </table>
    """


def _top_bottom_md(team: dict) -> str:
    rankings = (team.get("pbp_entry") or {}).get("cfbstats", {}).get("rankings", {}).get("all", {})
    parsed = []
    for key in CATEGORIES:
        r = rankings.get(key, {})
        rank = r.get("rank")
        if rank is None:
            continue
        parsed.append((key, rank, r.get("value")))

    top = sorted(parsed, key=lambda x: x[1])[:5]
    bottom = sorted(parsed, key=lambda x: x[1], reverse=True)[:3]

    lines = [f"*{team['display_name']}*"]
    if top:
        lines.append("- Top 10s:")
        for key, rank, value in top:
            if rank <= 10:
                lines.append(f"  • {LABELS.get(key, key)}: {value} (#{rank})")
    if bottom:
        lines.append("- Bottom 3:")
        for key, rank, value in bottom:
            lines.append(f"  • {LABELS.get(key, key)}: {value} (#{rank})")
    return "\n".join(lines)


def _metric_text(team1: dict, team2: dict) -> str:
    rankings1 = (team1.get("pbp_entry") or {}).get("cfbstats", {}).get("rankings", {}).get("all", {})
    rankings2 = (team2.get("pbp_entry") or {}).get("cfbstats", {}).get("rankings", {}).get("all", {})

    def val(rankings: dict, key: str) -> float | None:
        v = rankings.get(key, {}).get("value")
        try:
            return float(v)
        except (TypeError, ValueError):
            m = re.search(r"[-+]?\d+(?:\.\d+)?", str(v or ""))
            if not m:
                return None
            try:
                return float(m.group(0))
            except ValueError:
                return None

    def val_display(rankings: dict, key: str) -> str:
        num = val(rankings, key)
        if isinstance(num, (int, float)):
            return f"{num:.1f}"
        raw = rankings.get(key, {}).get("value")
        return str(raw) if raw not in (None, "") else "N/A"

    lines = []
    for key in ["scoring_offense", "scoring_defense", "total_offense", "total_defense"]:
        v1_txt = val_display(rankings1, key)
        v2_txt = val_display(rankings2, key)
        lines.append(
            f"<p>{LABELS.get(key, key)}: {team1.get('display_name', 'Team 1')} {v1_txt} | {team2.get('display_name', 'Team 2')} {v2_txt}</p>"
        )
    return "".join(f"<div class=\"metric-compare\">{l}</div>" for l in lines)


def _verification_html(team: dict) -> str:
    verification = team.get("cfbstats_verification") or {}
    summary = verification.get("summary") or {}
    metrics = verification.get("metrics") or []
    if not metrics:
        return ""

    mismatch_rows = [
        m for m in metrics
        if m.get("status") in {"mismatch", "missing_source", "missing_derived", "special_case"}
    ]

    rows_html = "".join(
        "<tr>"
        f"<td>{m.get('label')}</td>"
        f"<td>{m.get('derived') if m.get('derived') is not None else 'N/A'}</td>"
        f"<td>{m.get('source') if m.get('source') is not None else 'N/A'}</td>"
        f"<td>{m.get('delta') if m.get('delta') is not None else 'N/A'}</td>"
        f"<td>{m.get('status')}</td>"
        "</tr>"
        for m in mismatch_rows[:10]
    ) or "<tr><td colspan='5'>No mismatches or special-case metrics.</td></tr>"

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>CFBStats Verification</h4>
        <ul>
          <li>Matched: {summary.get('match', 0)}</li>
          <li>Mismatched: {summary.get('mismatch', 0)}</li>
          <li>Missing Source: {summary.get('missing_source', 0)}</li>
          <li>Missing Derived: {summary.get('missing_derived', 0)}</li>
          <li>Special Cases: {summary.get('special_case', 0)}</li>
        </ul>
      </div>
      <table class="rankings-table">
        <tr><th>Metric</th><th>Derived</th><th>CFBStats</th><th>Delta</th><th>Status</th></tr>
        {rows_html}
      </table>
    </div>
    """


def _verification_md(team: dict) -> str:
    verification = team.get("cfbstats_verification") or {}
    summary = verification.get("summary") or {}
    metrics = verification.get("metrics") or []
    lines = [
        f"*{team['display_name']} Verification*",
        f"- Matched: {summary.get('match', 0)}",
        f"- Mismatched: {summary.get('mismatch', 0)}",
        f"- Missing Source: {summary.get('missing_source', 0)}",
        f"- Missing Derived: {summary.get('missing_derived', 0)}",
        f"- Special Cases: {summary.get('special_case', 0)}",
    ]
    flagged = [
        m for m in metrics
        if m.get("status") in {"mismatch", "missing_source", "missing_derived", "special_case"}
    ]
    for m in flagged[:8]:
        derived = m.get("derived") if m.get("derived") is not None else "N/A"
        source = m.get("source") if m.get("source") is not None else "N/A"
        delta = m.get("delta") if m.get("delta") is not None else "N/A"
        suffix = f" ({m.get('note')})" if m.get("note") else ""
        lines.append(f"- {m.get('label')}: derived {derived} vs CFBStats {source} (delta {delta}) [{m.get('status')}]{suffix}")
    return "\n".join(lines)


def build(team1: dict, team2: dict) -> dict:
    """Full rankings section with all/conf/nonconf splits."""
    html_content = (
        f"{_metric_text(team1, team2)}"
        f"{_table_html(team1, team2, 'all')}"
        f"<div class='section-grid'>{_verification_html(team1)}{_verification_html(team2)}</div>"
        f"{_table_html(team1, team2, 'conf')}"
        f"{_table_html(team1, team2, 'nonconf')}"
    )

    md_content = "\n\n".join([
        "*Rankings Highlights*",
        _top_bottom_md(team1),
        _top_bottom_md(team2),
        _verification_md(team1),
        _verification_md(team2),
    ])

    return {
        "title": "Rankings",
        "html_content": html_content,
        "md_content": md_content,
        "key": "rankings",
    }
