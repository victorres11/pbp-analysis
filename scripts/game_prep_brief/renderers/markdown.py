from __future__ import annotations

from datetime import datetime


def _order_sections(sections: list[dict]) -> list[dict]:
    keys = [s.get("key") for s in sections]
    if "overview" in keys:
        ordered = [s for s in sections if s.get("key") == "overview"]
        ordered += [s for s in sections if s.get("key") != "overview"]
        return ordered
    return sections


PFF_WARNING_KEYS = (
    "blitz_pct",
    "blitz_pct_last3",
    "pff_plays_offense_pg",
    "pff_plays_defense_pg",
    "pff_missed_tackles_pg",
    "pff_tfl_pg",
    "pff_sacks_pg",
    "pff_sacks_allowed_pg",
    "pff_fmt_total",
    "pff_fmt_pg",
)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip()
        return not text or text.upper() == "N/A"
    return False


def _missing_warning(team1: dict, team2: dict) -> str:
    impacted: list[str] = []
    for team in (team1, team2):
        stats = team.get("stats", {})
        if any(_is_missing(stats.get(key)) for key in PFF_WARNING_KEYS):
            impacted.append(team.get("display_name", "Team"))
    if not impacted:
        return ""
    return (
        f"⚠️ PFF/API snapshot partial for {', '.join(impacted)}; "
        "some situational/trenches fields may be unavailable."
    )


def _parity_warning(team1: dict, team2: dict) -> str:
    gaps = list(team1.get("parity_gaps") or []) + list(team2.get("parity_gaps") or [])
    if not gaps:
        return ""
    preview = "; ".join(gaps[:6])
    more = f" (+{len(gaps) - 6} more)" if len(gaps) > 6 else ""
    return f"⚠️ XML parity gaps detected: {preview}{more}"


def render(sections: list[dict], team1: dict, team2: dict, week: int | None, season: int) -> str:
    """Render condensed Telegram markdown."""
    now = datetime.now().strftime("%b %d, %Y %H:%M")
    week_str = f"Week {week} | " if week else ""
    warning = _missing_warning(team1, team2)
    parity_warning = _parity_warning(team1, team2)

    header = [
        "🏈 *GAME PREP BRIEF v2*",
        f"📅 {week_str}{season} Season",
        f"*{team1['display_name']} vs {team2['display_name']}*",
        warning if warning else "",
        parity_warning if parity_warning else "",
        "",
    ]

    parts = []
    for s in _order_sections(sections):
        parts.append(s.get("md_content", ""))

    footer = [
        "",
        "━━━━━━━━━━━━━━━━━━",
        "📡 *Data Sources*",
        "• PBP Analysis (cfbstats + play-by-play aggregates)",
        "• Matchup overlay (optional matchups/<slug>/data.json)",
        f"• Generated: {now}",
    ]

    return "\n".join(header) + "\n\n".join(parts) + "\n" + "\n".join(footer)
