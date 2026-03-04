from __future__ import annotations


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_display(v) -> str:
    """Format fraction (0.12) or already-formatted string (12.0%) for display."""
    if v in (None, "N/A", ""):
        return "N/A"
    s = str(v)
    if "%" in s:
        return s
    try:
        return f"{round(float(s) * 100, 1)}%"
    except (ValueError, TypeError):
        return str(v)


def tempo_html(team: dict, label: str = "") -> str:
    """Render a tempo/play clock card for the game prep brief HTML output."""
    stats = team.get("stats") or {}
    avg_clock = stats.get("pff_avg_play_clock", "N/A")
    hurry_pct = stats.get("pff_hurry_up_pct", "N/A")
    tempo_label = stats.get("pff_tempo_label", "N/A")

    color_map = {"Fast": "#e74c3c", "Moderate": "#f39c12", "Deliberate": "#27ae60"}
    badge_color = color_map.get(str(tempo_label), "#888")

    avg_display = f"{round(float(avg_clock), 1)}s" if avg_clock not in ("N/A", "") else "N/A"
    try:
        float(avg_clock)
    except (TypeError, ValueError):
        avg_display = "N/A"

    hurry_display = _pct_display(hurry_pct)

    return f"""
<div class=\"tempo-card\">
  <div class=\"tempo-label\" style=\"color:{badge_color}; font-weight:bold;\">{tempo_label} Tempo</div>
  <div class=\"tempo-stats\">
    <span>Avg Clock: <strong>{avg_display}</strong></span>
    &nbsp;|&nbsp;
    <span>Hurry-Up: <strong>{hurry_display}</strong></span>
  </div>
</div>"""


def tempo_md(team: dict, label: str = "") -> str:
    """Render tempo section as markdown."""
    stats = team.get("stats") or {}
    avg_clock = stats.get("pff_avg_play_clock", "N/A")
    hurry_pct = stats.get("pff_hurry_up_pct", "N/A")
    tempo_label = stats.get("pff_tempo_label", "N/A")

    avg = _safe_float(avg_clock)
    avg_display = f"{round(avg, 1)}s" if avg is not None else "N/A"

    hurry_display = _pct_display(hurry_pct)

    lines = [f"### ⏱ Tempo — {tempo_label}"]
    lines.append(f"- Avg Play Clock at Snap: **{avg_display}**")
    lines.append(f"- Hurry-Up % (≤10s): **{hurry_display}**")
    return "\n".join(lines)


_TEMPO_KEYS = ("pff_avg_play_clock", "pff_hurry_up_pct", "pff_tempo_label")


def _has_data(team: dict) -> bool:
    """Return True if at least one tempo key has a real value (not N/A / missing)."""
    stats = team.get("stats") or {}
    return any(stats.get(k) not in (None, "N/A", "") for k in _TEMPO_KEYS)


def build(team1: dict, team2: dict) -> dict | None:
    """Return section dict, or None if tempo data is absent (e.g. stale enrichment cache).

    Callers should filter out None sections. Re-run with --refresh-enrichment to populate.
    """
    if not _has_data(team1) and not _has_data(team2):
        return None

    html_content = f"""
    <div class=\"section-grid\">
      <div class=\"team-card\">
        <h3>{team1['display_name']}</h3>
        {tempo_html(team1, label=team1['display_name'])}
      </div>
      <div class=\"team-card\">
        <h3>{team2['display_name']}</h3>
        {tempo_html(team2, label=team2['display_name'])}
      </div>
    </div>
    """

    md_content = "\n\n".join([
        f"*{team1['display_name']}*\n" + tempo_md(team1, label=team1['display_name']),
        f"*{team2['display_name']}*\n" + tempo_md(team2, label=team2['display_name']),
    ])

    return {
        "title": "Tempo",
        "html_content": html_content,
        "md_content": md_content,
        "key": "tempo",
    }
