from __future__ import annotations
import re

from ._names import format_player_name


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


def _team_aliases(team: dict) -> set[str]:
    pbp = team.get("pbp_entry") or {}
    aliases = _abbr_set(pbp.get("abbr_aliases"))
    if aliases:
        return aliases
    return _abbr_set(((team.get("stats") or {}).get("abbr") or pbp.get("abbr") or ""))


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


def _to_num(value: object) -> float | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^0-9.+-]", "", str(value))
    if not cleaned or cleaned in {"+", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _explosive_delta(cfb_total: float | None, pbp_total: float | None) -> tuple[str, str]:
    if cfb_total is None or pbp_total is None or cfb_total == 0:
        return "N/A", "N/A"
    delta = pbp_total - cfb_total
    pct = abs(delta) / cfb_total * 100.0
    if pct <= 10:
        status = "OK"
    elif pct <= 20:
        status = "Review"
    else:
        status = "High mismatch"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.0f} ({sign}{(delta / cfb_total * 100.0):.1f}%)", status


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


def _iter_offensive_plays(game: dict, team_abbr: object) -> list[dict]:
    """Flatten quarter/drive play_tree into offense-only play rows."""
    out: list[dict] = []
    team_aliases = _abbr_set(team_abbr)
    play_tree = game.get("play_tree") or []
    for quarter in play_tree:
        for drive in (quarter.get("drives") or []):
            for play in (drive.get("plays") or []):
                if (play.get("offense") or "").upper() not in team_aliases:
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


def _non_explosive_profile(games: list[dict], team_abbr: object) -> dict:
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


def _explosive_definition_breakdown(games: list[dict], team_abbr: object) -> dict:
    pass_20_plus = 0
    rush_20_plus = 0
    rush_15_19 = 0
    for g in games:
        for p in _iter_offensive_plays(g, team_abbr):
            desc = p.get("description") or ""
            desc_up = str(desc).upper()
            yards = _to_yards(p.get("yards"))
            if yards is None:
                continue
            if _is_pass(desc):
                if yards >= 20 and "INTERCEPT" not in desc_up:
                    pass_20_plus += 1
            elif _is_rush(desc):
                if yards >= 20:
                    rush_20_plus += 1
                elif yards >= 15:
                    rush_15_19 += 1
    pbp_20_total = pass_20_plus + rush_20_plus
    pbp_15_total = pbp_20_total + rush_15_19
    return {
        "pass_20_plus": pass_20_plus,
        "rush_20_plus": rush_20_plus,
        "rush_15_19": rush_15_19,
        "pbp_20_total": pbp_20_total,
        "pbp_15_total": pbp_15_total,
    }


def _top_explosive_plays(games: list[dict], team_abbr: object = "") -> list[dict]:
    def _extract_player(desc: str) -> str:
        text = (desc or "").strip()
        if not text:
            return "Unknown"
        text = re.sub(r"^\[[A-Z]+\]\s*", "", text).strip()
        text = re.sub(r"^(Shotgun|No Huddle(?:-Shotgun)?|Pistol)\s+", "", text, flags=re.IGNORECASE).strip()
        # Typical format: "Player Name pass ..." / "Player Name rush ..."
        m = re.match(r"([A-Za-z0-9'.,\\-\\s]+?)\\s+(?:pass|rush)\\b", text, flags=re.IGNORECASE)
        if m:
            return format_player_name(m.group(1).strip().rstrip(","))
        return format_player_name(text.split(" ", 1)[0].strip().rstrip(","))

    plays = []
    for g in games:
        explicit = g.get("explosive_details", []) or []
        for p in explicit:
            plays.append(p)
        if explicit:
            continue
        team_aliases = _abbr_set(team_abbr)
        # Fallback to offense plays in play_tree when explosive_details is missing.
        for q in g.get("play_tree") or []:
            for drive in q.get("drives") or []:
                for p in drive.get("plays") or []:
                    if p.get("is_no_play"):
                        continue
                    offense = (p.get("offense") or "").upper()
                    if team_aliases and offense not in team_aliases:
                        continue
                    desc = p.get("description") or ""
                    yards = p.get("yards")
                    if not isinstance(yards, (int, float)):
                        continue
                    desc_up = desc.upper()
                    if "INTERCEPTED BY" in desc_up or " FUMBLE " in f" {desc_up} ":
                        continue
                    is_pass = _is_pass(desc)
                    is_rush = _is_rush(desc)
                    if is_pass and yards >= 20:
                        plays.append(
                            {
                                "yards": int(yards),
                                "type": "pass",
                                "player": _extract_player(desc),
                                "description": desc,
                            }
                        )
                    elif is_rush and yards >= 15:
                        plays.append(
                            {
                                "yards": int(yards),
                                "type": "run",
                                "player": _extract_player(desc),
                                "description": desc,
                            }
                        )
    plays.sort(key=lambda p: p.get("yards", 0), reverse=True)
    return plays[:10]


def _best_explosive_player(p: dict) -> str:
    desc = p.get("description") or p.get("play_text") or p.get("text") or ""
    current = format_player_name(p.get("player", "?"))
    if not desc:
        return current

    text = re.sub(r"^\[[A-Z]+\]\s*", "", str(desc).strip())
    text = re.sub(r"^(Shotgun|No Huddle(?:-Shotgun)?|No Huddle|Pistol|Under Center|Wildcat)\s+", "", text, flags=re.IGNORECASE).strip()
    derived = None
    receiver = None

    m = re.match(r"([A-Z][A-Za-z]+(?:\s+(?:Jr|Jr\.|Sr|Sr\.|II|III|IV|V|[A-Z]+))?,\s*[A-Za-z]+)\s+(?:pass|rush)\b", text)
    if m:
        derived = format_player_name(m.group(1))
    else:
        m = re.match(r"([A-Z]+,\s*[A-Za-z]+)\s+(?:pass|rush)\b", text)
        if m:
            derived = format_player_name(m.group(1))

    if str(p.get("type", "")).lower() == "pass":
        r = re.search(r"\b(?:to|for)\s+([A-Z][A-Za-z]+(?:\s+(?:Jr|Jr\.|Sr|Sr\.|II|III|IV|V|[A-Z]+))?,\s*[A-Za-z]+)", text)
        if r:
            receiver = format_player_name(r.group(1))
        else:
            r = re.search(r"\b(?:to|for)\s+([A-Z]+,\s*[A-Za-z]+)", text)
            if r:
                receiver = format_player_name(r.group(1))

    if derived and receiver:
        return f"{derived} → {receiver}"
    if derived and (current in {"?", "Unknown"} or "," not in current and "→" not in current):
        return derived
    return current


def _explosive_play_html(p):
    header = f"<strong>{p.get('yards','?')} yd {p.get('type','play')} — {_best_explosive_player(p)}</strong>"
    desc = p.get('description') or p.get('play_text') or p.get('text') or ''
    if desc:
        return f"<li>{header}<br><span style=\"color:#555;font-size:0.9em;\">{desc}</span></li>"
    else:
        return f"<li>{header}</li>"


def _explosive_play_md(p):
    header = f"**{p.get('yards','?')} yd {p.get('type','play')} — {_best_explosive_player(p)}**"
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
    rankings_all = (
        (team.get("pbp_entry") or {})
        .get("cfbstats", {})
        .get("rankings", {})
        .get("all", {})
    )
    expl_rank = rankings_all.get("explosives", {}) if isinstance(rankings_all, dict) else {}
    cfb_expl_raw = expl_rank.get("value")
    cfb_expl_rank = expl_rank.get("rank")
    cfb_expl_total = _to_num(cfb_expl_raw)
    delta_text, delta_status = _explosive_delta(cfb_expl_total, float(totals["explosives"]))
    trend = _per_game_trend(games)
    team_abbr = _team_aliases(team)
    top_plays = _top_explosive_plays(games, team_abbr=team_abbr)
    ne_season = _non_explosive_profile(games, team_abbr) if team_abbr else {"rush_avg": 0.0, "pass_avg": 0.0, "rush_att": 0, "pass_att": 0}
    defs = _explosive_definition_breakdown(games, team_abbr) if team_abbr else {
        "pass_20_plus": 0,
        "rush_20_plus": 0,
        "rush_15_19": 0,
        "pbp_20_total": 0,
        "pbp_15_total": 0,
    }
    threshold_delta_text, _ = _explosive_delta(cfb_expl_total, float(defs["pbp_20_total"]))
    residual_text = "N/A"
    if cfb_expl_total is not None:
        residual = defs["pbp_20_total"] - cfb_expl_total
        sign = "+" if residual > 0 else ""
        residual_text = f"{sign}{int(residual)}"

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
          <li>CFBStats Explosives (20+): {cfb_expl_raw if cfb_expl_raw not in (None, '') else 'N/A'}{f' (#{cfb_expl_rank})' if cfb_expl_rank not in (None, '') else ''}</li>
          <li>PBP Explosives: {totals['explosives']} (Pass {totals['explosive_passes']}, Rush {totals['explosive_rushes']})</li>
          <li>Delta (PBP-CFBStats): {delta_text} · {delta_status}</li>
          <li>15-19y Rushes (PBP only): {defs['rush_15_19']} (expected definition delta)</li>
          <li>PBP 20+ (pass/rush): {defs['pbp_20_total']} (Pass {defs['pass_20_plus']}, Rush {defs['rush_20_plus']})</li>
          <li>Delta using PBP 20+ vs CFBStats: {threshold_delta_text} (residual {residual_text})</li>
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
    rankings_all = (
        (team.get("pbp_entry") or {})
        .get("cfbstats", {})
        .get("rankings", {})
        .get("all", {})
    )
    expl_rank = rankings_all.get("explosives", {}) if isinstance(rankings_all, dict) else {}
    cfb_expl_raw = expl_rank.get("value")
    cfb_expl_rank = expl_rank.get("rank")
    cfb_expl_total = _to_num(cfb_expl_raw)
    delta_text, delta_status = _explosive_delta(cfb_expl_total, float(totals["explosives"]))
    team_abbr = _team_aliases(team)
    top_plays = _top_explosive_plays(games, team_abbr=team_abbr)[:3]
    ne_season = _non_explosive_profile(games, team_abbr) if team_abbr else {"rush_avg": 0.0, "pass_avg": 0.0}
    defs = _explosive_definition_breakdown(games, team_abbr) if team_abbr else {
        "pass_20_plus": 0,
        "rush_20_plus": 0,
        "rush_15_19": 0,
        "pbp_20_total": 0,
        "pbp_15_total": 0,
    }
    threshold_delta_text, _ = _explosive_delta(cfb_expl_total, float(defs["pbp_20_total"]))
    residual_text = "N/A"
    if cfb_expl_total is not None:
        residual = defs["pbp_20_total"] - cfb_expl_total
        sign = "+" if residual > 0 else ""
        residual_text = f"{sign}{int(residual)}"
    lines = [f"*{team['display_name']}*"]
    explosives_suffix = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_epg = last_n.get("explosives_per_game", 0) or 0
        season_epg = totals["explosives"] / len(games) if games else 0
        if abs(l3_epg - season_epg) >= 0.8:
            explosives_suffix = f" (L{actual_n}: {l3_epg:.1f}/gm)"
    cfb_rank_suffix = f" (#{cfb_expl_rank})" if cfb_expl_rank not in (None, "") else ""
    lines.append(f"- CFBStats Explosives (20+): {cfb_expl_raw if cfb_expl_raw not in (None, '') else 'N/A'}{cfb_rank_suffix}")
    lines.append(
        f"- PBP Explosives: {totals['explosives']} (Pass {totals['explosive_passes']}, Rush {totals['explosive_rushes']}){explosives_suffix}"
    )
    lines.append(f"- Delta (PBP-CFBStats): {delta_text} · {delta_status}")
    lines.append(f"- 15-19y Rushes (PBP only): {defs['rush_15_19']} (expected definition delta)")
    lines.append(
        f"- PBP 20+ (pass/rush): {defs['pbp_20_total']} (Pass {defs['pass_20_plus']}, Rush {defs['rush_20_plus']})"
    )
    lines.append(f"- Delta using PBP 20+ vs CFBStats: {threshold_delta_text} (residual {residual_text})")
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
    <div class="section-note">Explosives are shown as dual-source due to definition differences: CFBStats is source-of-truth; PBP is play-level context.</div>
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Explosive Plays*",
        "- Note: Explosives shown as dual-source due to definition differences (CFBStats = source-of-truth, PBP = play-level context).",
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Explosive Plays",
        "html_content": html_content,
        "md_content": md_content,
        "key": "explosives",
    }
