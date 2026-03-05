from __future__ import annotations


MATCHUP_KEYS = [
    ("scoring_offense", "scoring_defense", "Scoring"),
    ("total_offense", "total_defense", "Total Yards"),
    ("rushing_offense", "rushing_defense", "Run Game"),
    ("passing_offense", "passing_defense", "Pass Game"),
    ("sacks_offense", "sacks_defense", "Pass Protection vs Pass Rush"),
    ("tfl_offense", "tfl_defense", "TFL Avoidance vs TFL Creation"),
]


def _rank(team: dict, key: str) -> int | None:
    rankings = (team.get("pbp_entry") or {}).get("cfbstats", {}).get("rankings", {}).get("all", {})
    value = (rankings.get(key) or {}).get("rank")
    try:
        rank = int(value)
        return rank if rank > 0 else None
    except (TypeError, ValueError):
        return None


def _classify(off_rank: int, def_rank: int, max_rank: int) -> str:
    strong_cutoff = max(3, round(max_rank * 0.25))
    weak_cutoff = max(strong_cutoff + 2, round(max_rank * 0.75))
    off_strong = off_rank <= strong_cutoff
    off_weak = off_rank >= weak_cutoff
    def_strong = def_rank <= strong_cutoff
    def_weak = def_rank >= weak_cutoff
    if off_strong and def_strong:
        return "Strength vs Strength"
    if off_weak and def_weak:
        return "Weakness vs Weakness"
    if off_strong and def_weak:
        return "Strength vs Weakness"
    if off_weak and def_strong:
        return "Weakness vs Strength"
    return ""


_CLASS_COLORS = {
    "Strength vs Strength": "#334155",
    "Strength vs Weakness": "#166534",
    "Weakness vs Strength": "#991b1b",
    "Weakness vs Weakness": "#7c2d12",
}


def _build_matchup_rows(team1: dict, team2: dict) -> list[dict]:
    t1_name = team1.get("display_name", "Team 1")
    t2_name = team2.get("display_name", "Team 2")

    all_ranks: list[int] = []
    for off_key, def_key, _ in MATCHUP_KEYS:
        for team, key in ((team1, off_key), (team1, def_key), (team2, off_key), (team2, def_key)):
            r = _rank(team, key)
            if r is not None:
                all_ranks.append(r)
    max_rank = max(all_ranks) if all_ranks else 134

    rows: list[dict] = []
    for off_key, def_key, label in MATCHUP_KEYS:
        t1_off = _rank(team1, off_key)
        t2_def = _rank(team2, def_key)
        t2_off = _rank(team2, off_key)
        t1_def = _rank(team1, def_key)

        if t1_off is not None and t2_def is not None:
            classification = _classify(t1_off, t2_def, max_rank)
            rows.append({
                "label": label,
                "offense": t1_name,
                "off_rank": t1_off,
                "defense": t2_name,
                "def_rank": t2_def,
                "classification": classification,
                "color": _CLASS_COLORS.get(classification, "#a1a1aa"),
            })

        if t2_off is not None and t1_def is not None:
            classification = _classify(t2_off, t1_def, max_rank)
            rows.append({
                "label": label,
                "offense": t2_name,
                "off_rank": t2_off,
                "defense": t1_name,
                "def_rank": t1_def,
                "classification": classification,
                "color": _CLASS_COLORS.get(classification, "#a1a1aa"),
            })

    return rows


def build(team1: dict, team2: dict) -> dict:
    rows = [r for r in _build_matchup_rows(team1, team2) if r["classification"]]
    if not rows:
        return {
            "title": "Key Matchups",
            "html_content": "<p>No matchup data available.</p>",
            "md_content": "*Key Matchups*\n- No matchup data available.",
            "key": "matchups",
        }

    # HTML: table layout
    table_rows = ""
    for r in rows:
        tag = f"<span style='color:{r['color']};font-weight:600'>{r['classification']}</span>" if r["classification"] else ""
        table_rows += (
            f"<tr>"
            f"<td>{r['label']}</td>"
            f"<td>{r['offense']} OFF #{r['off_rank']}</td>"
            f"<td>{r['defense']} DEF #{r['def_rank']}</td>"
            f"<td>{tag}</td>"
            f"</tr>"
        )
    html_content = (
        "<table class='matchup-table'>"
        "<thead><tr><th>Category</th><th>Offense</th><th>Defense</th><th>Type</th></tr></thead>"
        f"<tbody>{table_rows}</tbody>"
        "</table>"
    )

    # Markdown: aligned rows
    md_lines = ["*Key Matchups*", ""]
    for r in rows:
        tag = f" — {r['classification']}" if r["classification"] else ""
        md_lines.append(
            f"- **{r['label']}**: {r['offense']} OFF #{r['off_rank']} vs {r['defense']} DEF #{r['def_rank']}{tag}"
        )

    return {
        "title": "Key Matchups",
        "html_content": html_content,
        "md_content": "\n".join(md_lines),
        "key": "matchups",
    }
