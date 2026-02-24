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


def _build_callouts(team1: dict, team2: dict) -> list[dict]:
    t1_name = team1.get("display_name", "Team 1")
    t2_name = team2.get("display_name", "Team 2")
    out: list[dict] = []

    all_ranks: list[int] = []
    for off_key, def_key, _ in MATCHUP_KEYS:
        for team, key in ((team1, off_key), (team1, def_key), (team2, off_key), (team2, def_key)):
            r = _rank(team, key)
            if r is not None:
                all_ranks.append(r)
    max_rank = max(all_ranks) if all_ranks else 134
    strong_cutoff = max(3, round(max_rank * 0.25))
    weak_cutoff = max(strong_cutoff + 2, round(max_rank * 0.75))

    def add_adv(off_team: str, def_team: str, label: str, off_rank: int, def_rank: int) -> None:
        diff = def_rank - off_rank
        if abs(diff) < 3:
            return
        if diff > 0:
            text = (
                f"{off_team} {label} has an edge: offense rank #{off_rank} "
                f"vs {def_team} defense rank #{def_rank}."
            )
            color = "#166534"
        else:
            text = (
                f"{def_team} can neutralize {off_team} {label.lower()}: defense rank #{def_rank} "
                f"vs offense rank #{off_rank}."
            )
            color = "#991b1b"
        out.append({"score": abs(diff), "text": text, "color": color})

    for off_key, def_key, label in MATCHUP_KEYS:
        t1_off = _rank(team1, off_key)
        t1_def = _rank(team1, def_key)
        t2_off = _rank(team2, off_key)
        t2_def = _rank(team2, def_key)

        if t1_off is not None and t2_def is not None:
            add_adv(t1_name, t2_name, label, t1_off, t2_def)
            if t1_off <= strong_cutoff and t2_def <= strong_cutoff:
                out.append(
                    {
                        "score": 2,
                        "text": f"{label} is strength-on-strength: {t1_name} offense #{t1_off} vs {t2_name} defense #{t2_def}.",
                        "color": "#334155",
                    }
                )
            elif t1_off >= weak_cutoff and t2_def >= weak_cutoff:
                out.append(
                    {
                        "score": 2,
                        "text": f"{label} is weakness-on-weakness: {t1_name} offense #{t1_off} vs {t2_name} defense #{t2_def}.",
                        "color": "#7c2d12",
                    }
                )
        if t2_off is not None and t1_def is not None:
            add_adv(t2_name, t1_name, label, t2_off, t1_def)
            if t2_off <= strong_cutoff and t1_def <= strong_cutoff:
                out.append(
                    {
                        "score": 2,
                        "text": f"{label} is strength-on-strength: {t2_name} offense #{t2_off} vs {t1_name} defense #{t1_def}.",
                        "color": "#334155",
                    }
                )
            elif t2_off >= weak_cutoff and t1_def >= weak_cutoff:
                out.append(
                    {
                        "score": 2,
                        "text": f"{label} is weakness-on-weakness: {t2_name} offense #{t2_off} vs {t1_name} defense #{t1_def}.",
                        "color": "#7c2d12",
                    }
                )

    unique = []
    seen = set()
    for row in sorted(out, key=lambda item: item["score"], reverse=True):
        text = row["text"]
        if text in seen:
            continue
        seen.add(text)
        unique.append(row)
        if len(unique) >= 5:
            break
    return unique


def build(team1: dict, team2: dict) -> dict:
    callouts = _build_callouts(team1, team2)
    if not callouts:
        return {
            "title": "Key Matchups",
            "html_content": "<p>No matchup callouts available.</p>",
            "md_content": "*Key Matchups*\n- No matchup callouts available.",
            "key": "matchups",
        }

    html_content = (
        "<ul>"
        + "".join(
            f"<li><span style='color:{item['color']};font-weight:600'>{item['text']}</span></li>"
            for item in callouts
        )
        + "</ul>"
    )
    md_content = "\n".join(["*Key Matchups*"] + [f"- {item['text']}" for item in callouts])
    return {
        "title": "Key Matchups",
        "html_content": html_content,
        "md_content": md_content,
        "key": "matchups",
    }
