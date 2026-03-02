from __future__ import annotations
import re
from collections import defaultdict


def _abbr_set(value: object) -> set[str]:
    if isinstance(value, str):
        cleaned = value.strip().upper()
        return {cleaned} if cleaned else set()
    if isinstance(value, (list, tuple, set)):
        out: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                continue
            cleaned = item.strip().upper()
            if cleaned:
                out.add(cleaned)
        return out
    return set()


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


def _pct_display(value: object) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _num_display(value: object, suffix: str = "") -> str:
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def _is_na(value: object) -> bool:
    return value in ("N/A", None, "")


def _is_zero_like(value: object) -> bool:
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def _sanitize_charting_value(value: object) -> object:
    if _is_na(value) or _is_zero_like(value):
        return "N/A"
    return value


def _display_or_unavailable(value: object, suffix: str = "") -> str:
    if _is_na(value):
        return "Unavailable (API)"
    return _num_display(value, suffix)


def _last_n_games(team: dict, n: int = 3) -> list[dict]:
    games = _games(team)
    return sorted(games, key=lambda g: g.get("game_number", 0))[-n:]


def _parse_receiver(desc: str) -> str | None:
    # "to Last,First"
    m = re.search(r"\bto\s+([A-Z][A-Za-z]+(?: [A-Z]+)?,\s*[A-Za-z]+)", desc)
    if m:
        return m.group(1).strip()
    # "to #12 F.Lastname"
    m = re.search(r"\bto\s+#\d+\s+([A-Z]\.[A-Za-z]+(?:\s+(?:Jr\.|Sr\.|II|III|IV|V))*)", desc)
    if m:
        return m.group(1).strip()
    return None


def _receiver_key(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def _yards_to_goal(spot: str, offense_abbr: str, opp_abbr: str) -> int | None:
    if not spot:
        return None
    s = spot.strip().upper()
    offense_abbr = (offense_abbr or "").upper()
    opp_abbr = (opp_abbr or "").upper()
    if s == "50":
        return 50
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    n = int(m.group(1))
    if opp_abbr and opp_abbr in s:
        return n
    if offense_abbr and offense_abbr in s:
        return 100 - n
    return n if n <= 50 else 100 - n


def _is_pass_target(play: dict) -> bool:
    desc = (play.get("description") or "").lower()
    return " pass " in f" {desc} "


def _target_outcome(play: dict) -> tuple[bool, bool, bool]:
    desc = str(play.get("description") or "")
    desc_up = desc.upper()
    # Ignore overturned original-play text when deriving target outcomes.
    effective = desc_up.split("PLAY OVERTURNED", 1)[0]
    caught = (" COMPLETE" in effective or "PASS COMPLETE" in effective) and "INCOMPLETE" not in effective
    first_down = "1ST DOWN" in effective
    td = "TOUCHDOWN" in effective
    # A target cannot produce a first down or TD without a catch in this summary.
    if not caught:
        first_down = False
        td = False
    return caught, first_down, td


def _collect_target_tendencies(team: dict) -> dict:
    """Last-3 target tendencies by receiver for 3rd down and red zone."""
    if not team.get("has_pbp"):
        return {"third_down": [], "red_zone": []}

    team_abbr = ((team.get("stats") or {}).get("abbr") or ((team.get("pbp_entry") or {}).get("abbr") or "")).upper()
    if not team_abbr:
        return {"third_down": [], "red_zone": []}

    third_down = defaultdict(lambda: {"receiver": "", "targets": 0, "catches": 0, "first_downs": 0, "td": 0})
    red_zone = defaultdict(lambda: {"receiver": "", "targets": 0, "catches": 0, "first_downs": 0, "td": 0})

    for g in _last_n_games(team, 3):
        opp_abbr = (g.get("opponent_abbr") or "").upper()
        for q in g.get("play_tree") or []:
            for drive in q.get("drives") or []:
                for p in drive.get("plays") or []:
                    if p.get("is_no_play"):
                        continue
                    if (p.get("offense") or "").upper() != team_abbr:
                        continue
                    if not _is_pass_target(p):
                        continue

                    receiver = _parse_receiver(p.get("description") or "")
                    if not receiver:
                        continue
                    receiver_norm = receiver.strip()
                    receiver_id = _receiver_key(receiver_norm)

                    dd = str(p.get("down_distance") or "")
                    is_third_down = dd.startswith("3-")
                    ytg = _yards_to_goal(str(p.get("spot") or ""), team_abbr, opp_abbr)
                    in_red_zone = ytg is not None and ytg <= 20
                    if not is_third_down and not in_red_zone:
                        continue

                    caught, first_down, td = _target_outcome(p)
                    if is_third_down:
                        row = third_down[receiver_id]
                        if not row["receiver"]:
                            row["receiver"] = receiver_norm
                        row["targets"] += 1
                        row["catches"] += 1 if caught else 0
                        row["first_downs"] += 1 if first_down else 0
                        row["td"] += 1 if td else 0
                    if in_red_zone:
                        row = red_zone[receiver_id]
                        if not row["receiver"]:
                            row["receiver"] = receiver_norm
                        row["targets"] += 1
                        row["catches"] += 1 if caught else 0
                        row["first_downs"] += 1 if first_down else 0
                        row["td"] += 1 if td else 0

    def _rows(src: dict) -> list[dict]:
        rows = [dict(v) for v in src.values()]
        return sorted(rows, key=lambda r: (r["targets"], r["catches"], r["first_downs"], r["td"]), reverse=True)[:6]

    return {"third_down": _rows(third_down), "red_zone": _rows(red_zone)}


def _third_down_from_games(team: dict, games: list[dict]) -> tuple[int, int, float | str]:
    pbp = team.get("pbp_entry") or {}
    team_aliases = _abbr_set(pbp.get("abbr_aliases") or pbp.get("abbr"))
    if not team_aliases:
        return 0, 0, "N/A"

    attempts = 0
    conversions = 0
    for g in games:
        for q in g.get("play_tree") or []:
            for drive in q.get("drives") or []:
                for p in drive.get("plays") or []:
                    if p.get("is_no_play"):
                        continue
                    offense = str(p.get("offense") or "").upper()
                    if offense not in team_aliases:
                        continue
                    dd = str(p.get("down_distance") or "").upper().strip()
                    if not (dd.startswith("3-") or dd.startswith("3RD")):
                        continue
                    attempts += 1
                    desc_up = str(p.get("description") or "").upper()
                    if "1ST DOWN" in desc_up or "TOUCHDOWN" in desc_up:
                        conversions += 1
    pct = round((conversions / attempts) * 100, 1) if attempts else "N/A"
    return conversions, attempts, pct


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No PBP data.</em></p></div>"
    games = _games(team)
    third_conv, third_att, third_pct_derived = _third_down_from_games(team, games)
    attempts = _sum(games, "4th_down_attempts") if games else None
    conversions = _sum(games, "4th_down_conversions") if games else None
    pct = round((conversions / attempts) * 100, 1) if isinstance(attempts, int) and attempts else "N/A"
    per_game = [
        f"G{g.get('game_number','?')} vs {g.get('opponent','?')}: {g.get('4th_down_attempts',0)} att"
        for g in sorted(games, key=lambda x: x.get("game_number", 0))
    ]
    per_game_html = "".join(f"<li>{l}</li>" for l in per_game) or "<li>N/A</li>"
    third_down = team.get("stats", {}).get("third_down", "N/A")
    if third_down in ("N/A", None, ""):
        third_down = team.get("stats", {}).get("third_down_derived", "N/A")
    blitz_pct = team.get("stats", {}).get("blitz_pct", "N/A")
    blitz_pct_last3 = team.get("stats", {}).get("blitz_pct_last3", "N/A")
    stats = team.get("stats", {}) or {}
    last_n_stats = team.get("last_n", {}) or {}
    neg_off = stats.get("negative_plays_per_game", stats.get("negative_plays_pg_api", "N/A"))
    neg_def = stats.get("negative_plays_forced_per_game", stats.get("negative_plays_forced_pg_api", "N/A"))
    neg_off_l3 = last_n_stats.get("negative_plays_per_game", stats.get("negative_plays_pg_last3_api", "N/A"))
    neg_def_l3 = last_n_stats.get("negative_plays_forced_per_game", stats.get("negative_plays_forced_pg_last3_api", "N/A"))
    off_plays_pg = stats.get("offense_plays_per_game", stats.get("pff_plays_offense_pg", "N/A"))
    def_plays_pg = stats.get("defense_plays_allowed_per_game", stats.get("pff_plays_defense_pg", "N/A"))
    off_plays_l3 = last_n_stats.get("offense_plays_per_game", "N/A")
    def_plays_l3 = last_n_stats.get("defense_plays_allowed_per_game", "N/A")
    sacks_allowed_pg = _sanitize_charting_value(stats.get("pff_sacks_allowed_pg", "N/A"))
    if sacks_allowed_pg in ("N/A", None, ""):
        sacks_allowed_pg = stats.get("sacks_allowed_derived_pg", "N/A")
    sacks_pg = _sanitize_charting_value(stats.get("pff_sacks_pg", "N/A"))
    if sacks_pg in ("N/A", None, ""):
        sacks_pg = stats.get("sacks_forced_derived_pg", "N/A")
    tfl_pg = _sanitize_charting_value(stats.get("pff_tfl_pg", "N/A"))
    if tfl_pg in ("N/A", None, ""):
        tfl_pg = stats.get("tfl_forced_derived_pg", "N/A")
    tfl_allowed = ((team.get("pbp_entry") or {}).get("cfbstats", {}).get("rankings", {}).get("all", {}).get("tfl_offense", {}).get("value", "N/A"))
    if tfl_allowed in ("N/A", None, ""):
        tfl_allowed = stats.get("tfl_allowed_derived_pg", "N/A")
    mt_pg = _sanitize_charting_value(stats.get("pff_missed_tackles_pg", "N/A"))
    fmt_pg = _sanitize_charting_value(stats.get("pff_fmt_pg", "N/A"))
    targets = _collect_target_tendencies(team)
    third_targets = targets["third_down"]
    rz_targets = targets["red_zone"]
    third_html = "".join(
        f"<li>{r['receiver']}: {r['targets']} tgt, {r['catches']} rec, {r['first_downs']} 1D, {r['td']} TD</li>"
        for r in third_targets
    ) or "<li>N/A</li>"
    rz_html = "".join(
        f"<li>{r['receiver']}: {r['targets']} tgt, {r['catches']} rec, {r['first_downs']} 1D, {r['td']} TD</li>"
        for r in rz_targets
    ) or "<li>N/A</li>"
    last_n_line = ""
    third_down_l3_line = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_games = sorted(games, key=lambda g: g.get("game_number", 0))[-actual_n:] if actual_n else []
        l3_3d_conv, l3_3d_att, l3_3d_pct = _third_down_from_games(team, l3_games)
        if l3_3d_att:
            third_down_l3_line = (
                f"<li>L{actual_n} Conversions / Attempts: {l3_3d_conv} / {l3_3d_att} "
                f"({l3_3d_pct if isinstance(l3_3d_pct, (int, float)) else 'N/A'}%)</li>"
            )
        l3_attempts = last_n.get("fourth_down_attempts", "N/A")
        l3_conversions = last_n.get("fourth_down_conversions", "N/A")
        l3_pct = round((l3_conversions / l3_attempts) * 100, 1) if isinstance(l3_attempts, (int, float)) and l3_attempts else "N/A"
        l3_display = f"L{actual_n}: {l3_attempts} att / {l3_conversions} conv ({l3_pct}%)"
        if isinstance(l3_pct, (int, float)) and isinstance(pct, (int, float)) and l3_pct > pct:
            last_n_line = f"<li><span style=\"color: #1b7f3a;\">{l3_display}</span></li>"
        elif isinstance(l3_pct, (int, float)) and isinstance(pct, (int, float)) and l3_pct < pct:
            last_n_line = f"<li><span style=\"color: #b3261e;\">{l3_display}</span></li>"
        else:
            last_n_line = f"<li>{l3_display}</li>"

    trenches_unavailable = all(_is_na(v) for v in (sacks_allowed_pg, sacks_pg, tfl_pg, tfl_allowed, mt_pg, fmt_pg))
    trenches_html = (
        "<li>XML source currently does not include blitz/missed-tackle charting.</li>"
        if trenches_unavailable
        else (
            f"<li>Sacks Allowed/G: {_num_display(sacks_allowed_pg)}</li>"
            f"<li>Sacks (Def)/G: {_num_display(sacks_pg)} | TFL/G: {_num_display(tfl_pg)}</li>"
            f"<li>TFL Allowed (season): {tfl_allowed}</li>"
            f"<li>Missed Tackles/G: {_num_display(mt_pg)} | FMT/G: {_num_display(fmt_pg)}</li>"
        )
    )

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>3rd Down</h4>
        <ul>
          <li>CFBStats: {third_down}</li>
          <li>Conversions / Attempts (PBP): {third_conv} / {third_att} ({f"{third_pct_derived}%" if isinstance(third_pct_derived, (int, float)) else "N/A"})</li>
          {third_down_l3_line}
        </ul>
      </div>
      <div class="block">
        <h4>Blitz Rate</h4>
        <ul>
          <li>Season: {_display_or_unavailable(blitz_pct, '%')}</li>
          <li>Last 3: {_display_or_unavailable(blitz_pct_last3, '%')}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Negative Plays</h4>
        <ul>
          <li>Offense (Season / L3): {_num_display(neg_off, '/gm')} / {_num_display(neg_off_l3, '/gm')}</li>
          <li>Defense Forced (Season / L3): {_num_display(neg_def, '/gm')} / {_num_display(neg_def_l3, '/gm')}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Tempo (Plays/Game)</h4>
        <ul>
          <li>Offense (Season / L3): {_num_display(off_plays_pg)} / {_num_display(off_plays_l3)}</li>
          <li>Defense Allowed (Season / L3): {_num_display(def_plays_pg)} / {_num_display(def_plays_l3)}</li>
        </ul>
      </div>
      <div class="block">
        <h4>Trenches Snapshot</h4>
        <ul>
          {trenches_html}
        </ul>
      </div>
      <div class="block">
        <h4>Targets Last 3 (3rd Down)</h4>
        <ul>{third_html}</ul>
      </div>
      <div class="block">
        <h4>Targets Last 3 (Red Zone)</h4>
        <ul>{rz_html}</ul>
      </div>
      <div class="block">
        <h4>4th Down</h4>
        <ul>
          <li>Attempts / Conversions: {attempts if attempts is not None else 'N/A'} / {conversions if conversions is not None else 'N/A'}</li>
          <li>Conversion %: {f"{pct}%" if isinstance(pct, (int, float)) else "N/A"}</li>
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
    third_conv, third_att, third_pct_derived = _third_down_from_games(team, games)
    attempts = _sum(games, "4th_down_attempts") if games else "N/A"
    conversions = _sum(games, "4th_down_conversions") if games else "N/A"
    pct = round((conversions / attempts) * 100, 1) if isinstance(attempts, (int, float)) and attempts else "N/A"
    third_down = team.get("stats", {}).get("third_down", "N/A")
    if third_down in ("N/A", None, ""):
        third_down = team.get("stats", {}).get("third_down_derived", "N/A")
    blitz_pct = team.get("stats", {}).get("blitz_pct", "N/A")
    blitz_pct_last3 = team.get("stats", {}).get("blitz_pct_last3", "N/A")
    stats = team.get("stats", {}) or {}
    last_n_stats = team.get("last_n", {}) or {}
    neg_off = stats.get("negative_plays_per_game", stats.get("negative_plays_pg_api", "N/A"))
    neg_def = stats.get("negative_plays_forced_per_game", stats.get("negative_plays_forced_pg_api", "N/A"))
    neg_off_l3 = last_n_stats.get("negative_plays_per_game", stats.get("negative_plays_pg_last3_api", "N/A"))
    neg_def_l3 = last_n_stats.get("negative_plays_forced_per_game", stats.get("negative_plays_forced_pg_last3_api", "N/A"))
    off_plays_pg = stats.get("offense_plays_per_game", stats.get("pff_plays_offense_pg", "N/A"))
    def_plays_pg = stats.get("defense_plays_allowed_per_game", stats.get("pff_plays_defense_pg", "N/A"))
    off_plays_l3 = last_n_stats.get("offense_plays_per_game", "N/A")
    def_plays_l3 = last_n_stats.get("defense_plays_allowed_per_game", "N/A")
    sacks_allowed_pg = _sanitize_charting_value(stats.get("pff_sacks_allowed_pg", "N/A"))
    if sacks_allowed_pg in ("N/A", None, ""):
        sacks_allowed_pg = stats.get("sacks_allowed_derived_pg", "N/A")
    sacks_pg = _sanitize_charting_value(stats.get("pff_sacks_pg", "N/A"))
    if sacks_pg in ("N/A", None, ""):
        sacks_pg = stats.get("sacks_forced_derived_pg", "N/A")
    tfl_pg = _sanitize_charting_value(stats.get("pff_tfl_pg", "N/A"))
    if tfl_pg in ("N/A", None, ""):
        tfl_pg = stats.get("tfl_forced_derived_pg", "N/A")
    mt_pg = _sanitize_charting_value(stats.get("pff_missed_tackles_pg", "N/A"))
    fmt_pg = _sanitize_charting_value(stats.get("pff_fmt_pg", "N/A"))
    targets = _collect_target_tendencies(team)
    top_3d = targets["third_down"][0]["receiver"] if targets["third_down"] else "N/A"
    top_rz = targets["red_zone"][0]["receiver"] if targets["red_zone"] else "N/A"
    last_n_suffix = ""
    third_down_l3_suffix = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_games = sorted(games, key=lambda g: g.get("game_number", 0))[-actual_n:] if actual_n else []
        l3_3d_conv, l3_3d_att, l3_3d_pct = _third_down_from_games(team, l3_games)
        if l3_3d_att:
            third_down_l3_suffix = f" (L{actual_n}: {l3_3d_conv}/{l3_3d_att}, {l3_3d_pct}%)"
        l3_attempts = last_n.get("fourth_down_attempts", "N/A")
        l3_conversions = last_n.get("fourth_down_conversions", "N/A")
        l3_pct = round((l3_conversions / l3_attempts) * 100, 1) if isinstance(l3_attempts, (int, float)) and l3_attempts else "N/A"
        if isinstance(l3_pct, (int, float)) and isinstance(pct, (int, float)) and abs(l3_pct - pct) >= 8:
            last_n_suffix = f" (L{actual_n}: {l3_conversions}/{l3_attempts}, {l3_pct}%)"
    trenches_line = (
        "- Sacks Allowed/Sacks/TFL: XML-only coverage; advanced charting unavailable"
        if all(_is_na(v) for v in (sacks_allowed_pg, sacks_pg, tfl_pg))
        else f"- Sacks Allowed/Sacks/TFL: {sacks_allowed_pg}/{sacks_pg}/{tfl_pg}"
    )
    miss_fmt_line = (
        "- Missed Tackles/FMT: XML-only coverage; advanced charting unavailable"
        if all(_is_na(v) for v in (mt_pg, fmt_pg))
        else f"- Missed Tackles/FMT: {mt_pg}/{fmt_pg}"
    )

    return "\n".join([
        f"*{team['display_name']}*",
        f"- 3rd Down: {third_down} · {third_conv}/{third_att} ({f'{third_pct_derived}%' if isinstance(third_pct_derived, (int, float)) else 'N/A'}){third_down_l3_suffix}",
        f"- Blitz %: {_display_or_unavailable(blitz_pct, '%')} (L3: {_display_or_unavailable(blitz_pct_last3, '%')})",
        f"- Negative Plays O/D: {neg_off}/{neg_def} (L3: {neg_off_l3}/{neg_def_l3})",
        f"- Plays/G O/D: {off_plays_pg}/{def_plays_pg} (L3: {off_plays_l3}/{def_plays_l3})",
        trenches_line,
        miss_fmt_line,
        f"- Top Targets (L3) 3rd/RZ: {top_3d} / {top_rz}",
        f"- 4th Down: {conversions}/{attempts} ({f'{pct}%' if isinstance(pct, (int, float)) else 'N/A'}){last_n_suffix}",
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
