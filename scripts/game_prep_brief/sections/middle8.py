from __future__ import annotations
import re

from ._names import format_player_name
from ._sources import SRC_PBP

_NAME_COMMA_RE = r"([A-Z][A-Za-z]+(?:\s+(?:Jr|Jr\.|Sr|Sr\.|II|III|IV|V|[A-Z]+))?,\s*[A-Za-z]+)"


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


def _parse_play_fields(p: dict) -> dict:
    """Extract yards, type, player from description when raw fields are missing."""
    out = dict(p)
    desc = out.get("description") or out.get("play_text") or out.get("text") or ""

    # --- yards ---
    if not out.get("yards") or out.get("yards") == "?":
        m = re.search(r"for (\d+) yards?", desc)
        if m:
            out["yards"] = m.group(1)
        else:
            # FG: "from X yards"
            m2 = re.search(r"from (\d+) yards?", desc)
            if m2:
                out["yards"] = m2.group(1)
            # Returns: "return X yards" (only if not already set)
            elif re.search(r"return (\d+) yards?", desc):
                m3 = re.search(r"return (\d+) yards?", desc)
                out["yards"] = m3.group(1)

    # --- type ---
    if not out.get("type") or out.get("type") in ("?", "play", ""):
        dl = desc.lower()
        if "recovered by" in dl and "return" in dl:
            out["type"] = "return"
        elif "pass " in dl or "pass complete" in dl or "pass incomplete" in dl:
            out["type"] = "pass"
        elif "rush" in dl:
            out["type"] = "rush"
        elif "field goal" in dl:
            out["type"] = "FG"
        elif "return" in dl or "punt" in dl or "kickoff" in dl:
            out["type"] = "return"
        else:
            out["type"] = "play"

    # --- player ---
    if not out.get("player") or out.get("player") == "?":
        ptype = out.get("type", "")

        # For returns: find the returner (player before "return N yards"),
        # including turnover-return descriptions that begin with a rush/pass.
        if ptype == "return":
            # Format B: #N F.LastName return
            rm = re.search(r"#\d+\s+([A-Z]\.[A-Za-z]+(?:\s+(?:Jr\.|Sr\.|II|III|IV|V))*)\s+return", desc)
            # Format A: LastName,FirstName return
            rm_a = re.search(_NAME_COMMA_RE + r"\s+return", desc)
            # Turnover return: "recovered by TEAM Last,First at ... Last,First return"
            rm_b = re.search(r"recovered by\s+[A-Z]{2,5}\s+(" + _NAME_COMMA_RE[1:-1] + r").*?\b\1\s+return", desc, re.I)
            if rm:
                out["player"] = rm.group(1).strip()
            elif rm_a:
                out["player"] = rm_a.group(1).strip()
            elif rm_b:
                out["player"] = rm_b.group(1).strip()
            return out

        # Strip formation prefix
        clean = re.sub(
            r"^(No Huddle[- ]\w+|No Huddle|Shotgun|Under Center|Wildcat|Pistol)\s+",
            "",
            desc.strip(),
            flags=re.I,
        )

        # Format A: LastName,FirstName (e.g. "Aguilar,Joey", "Brazzell II,Chris")
        m_a = re.match(_NAME_COMMA_RE, clean)
        # Format B: #N F.LastName [optional Jr./Sr./II/III] — stop before lowercase words
        m_b = re.match(r"#\d+\s+([A-Z]\.[A-Za-z]+(?:\s+(?:Jr\.|Sr\.|II|III|IV|V))*)", clean)

        passer_name = (m_a.group(1) if m_a else m_b.group(1) if m_b else None)
        if passer_name:
            passer_name = passer_name.strip()

        if passer_name:
            if ptype == "pass":
                # Find receiver — Format A: "to LastName,FirstName"
                r_a = re.search(r"\b(?:to|for)\s+" + _NAME_COMMA_RE, desc)
                # Format B: "to #N F.LastName [Jr./Sr./II/III]"
                r_b = re.search(r"\b(?:to|for)\s+#\d+\s+([A-Z]\.[A-Za-z]+(?:\s+(?:Jr\.|Sr\.|II|III|IV|V))*)", desc)
                if r_a:
                    out["player"] = f"{passer_name} → {r_a.group(1).strip()}"
                elif r_b:
                    out["player"] = f"{passer_name} → {r_b.group(1).strip()}"
                else:
                    out["player"] = passer_name
            else:
                out["player"] = passer_name

        if not out.get("player") or out.get("player") == "?":
            if ptype == "rush":
                rush_a = re.search(_NAME_COMMA_RE + r"\s+rush\b", desc, re.I)
                rush_b = re.search(r"#\d+\s+([A-Z]\.[A-Za-z]+(?:\s+(?:Jr\.|Sr\.|II|III|IV|V))*)\s+rush\b", desc, re.I)
                if rush_a:
                    out["player"] = rush_a.group(1).strip()
                elif rush_b:
                    out["player"] = rush_b.group(1).strip()
            elif ptype == "pass":
                passer_a = re.search(_NAME_COMMA_RE + r"\s+pass\b", desc, re.I)
                passer_b = re.search(r"#\d+\s+([A-Z]\.[A-Za-z]+(?:\s+(?:Jr\.|Sr\.|II|III|IV|V))*)\s+pass\b", desc, re.I)
                receiver_a = re.search(r"\b(?:to|for)\s+" + _NAME_COMMA_RE, desc, re.I)
                receiver_b = re.search(
                    r"\b(?:to|for)\s+#\d+\s+([A-Z]\.[A-Za-z]+(?:\s+(?:Jr\.|Sr\.|II|III|IV|V))*)",
                    desc,
                    re.I,
                )
                passer = passer_a.group(1).strip() if passer_a else passer_b.group(1).strip() if passer_b else None
                receiver = receiver_a.group(1).strip() if receiver_a else receiver_b.group(1).strip() if receiver_b else None
                if passer and receiver:
                    out["player"] = f"{passer} → {receiver}"
                elif passer:
                    out["player"] = passer

    if out.get("player") and out.get("player") != "?":
        out["player"] = format_player_name(out["player"])
    return out


def _games(team: dict) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    return pbp.get("games", [])


def _sum(games: list[dict], key: str) -> int:
    return sum(g.get(key, 0) or 0 for g in games)


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


def _scoring_plays(games: list[dict]) -> list[str]:
    plays = []
    for g in games:
        for p in g.get("middle8_scoring_plays", []) or []:
            plays.append(p)
    return plays


def _clock_to_seconds(clock: object) -> int | None:
    if not isinstance(clock, str) or ":" not in clock:
        return None
    try:
        mm, ss = clock.split(":", 1)
        return int(mm) * 60 + int(ss)
    except Exception:
        return None


def _is_middle8_window(quarter: object, clock: object) -> bool:
    if not isinstance(quarter, int):
        return False
    secs = _clock_to_seconds(clock)
    if secs is None:
        return False
    # Middle 8 = last 4:00 of Q2 + first 4:00 of Q3.
    if quarter == 2:
        return secs <= 240
    if quarter == 3:
        return secs >= 660
    return False


def _derived_middle8_scoring_plays(team: dict, games: list[dict], limit: int = 6) -> list[dict]:
    pbp = team.get("pbp_entry") or {}
    team_aliases = _abbr_set(pbp.get("abbr_aliases") or pbp.get("abbr"))
    out: list[dict] = []
    for g in sorted(games, key=lambda x: x.get("game_number", 0)):
        opp_aliases = _abbr_set(g.get("opponent_abbr"))
        for quarter in g.get("play_tree") or []:
            if not isinstance(quarter, dict):
                continue
            qnum = quarter.get("quarter")
            for drive in quarter.get("drives") or []:
                if not isinstance(drive, dict):
                    continue
                for play in drive.get("plays") or []:
                    if not isinstance(play, dict):
                        continue
                    if play.get("is_no_play") or not play.get("is_scoring"):
                        continue
                    desc = str(play.get("description") or "")
                    desc_up = desc.upper()
                    effective = desc_up.split("PLAY OVERTURNED", 1)[0]
                    if "TOUCHDOWN" not in effective and "FIELD GOAL" not in effective and "SAFETY" not in effective:
                        continue
                    if not _is_middle8_window(qnum, play.get("clock")):
                        continue
                    offense = str(play.get("offense") or "").upper()
                    derived = dict(play)
                    derived["quarter"] = qnum
                    derived["game_number"] = g.get("game_number")
                    derived["opponent"] = g.get("opponent")
                    out.append(derived)
    return out[:limit]


def _middle8_game_score(team: dict, game: dict) -> tuple[int, int] | None:
    pbp = team.get("pbp_entry") or {}
    xml_stats = pbp.get("xml_stats") or {}
    cat = xml_stats.get("middle_eight") or {}
    if isinstance(cat, dict):
        opp = str(game.get("opponent_abbr") or "").upper()
        row = cat.get(opp) if isinstance(cat.get(opp), dict) else {}
        if isinstance(row, dict) and row:
            # Opponent-keyed row is opponent perspective; flip to team perspective.
            pf = row.get("middle_eight_points_allowed")
            pa = row.get("middle_eight_points")
            if isinstance(pf, (int, float)) and isinstance(pa, (int, float)):
                return int(pf), int(pa)
    pf = game.get("middle8_points_for")
    pa = game.get("middle8_points_against")
    if isinstance(pf, (int, float)) and isinstance(pa, (int, float)):
        return int(pf), int(pa)
    return None


def _play_html(p):
    if isinstance(p, dict):
        p = _parse_play_fields(p)
        clock = p.get("clock") or p.get("time") or ""
        yards = p.get("yards", "?")
        ptype = p.get("type", "play")
        player = p.get("player", "?")
        game_tag = ""
        if p.get("game_number") is not None and p.get("opponent"):
            game_tag = f"G{p.get('game_number')} vs {p.get('opponent')} · "
        header = f"<strong>{game_tag}Q{p.get('quarter','?')} {clock} — {yards} yd {ptype}, {player}</strong>"
        desc = p.get("description") or p.get("play_text") or p.get("text") or ""
        if desc:
            return f"<li>{header}<br><span style=\"color:#555;font-size:0.9em;\">{desc}</span></li>"
        else:
            return f"<li>{header}</li>"
    else:
        return f"<li>{p}</li>"


def _play_md(p):
    if isinstance(p, dict):
        p = _parse_play_fields(p)
        clock = p.get("clock") or p.get("time") or ""
        yards = p.get("yards", "?")
        ptype = p.get("type", "play")
        player = p.get("player", "?")
        game_tag = ""
        if p.get("game_number") is not None and p.get("opponent"):
            game_tag = f"G{p.get('game_number')} vs {p.get('opponent')} · "
        header = f"**{game_tag}Q{p.get('quarter','?')} {clock} — {yards} yd {ptype}, {player}**"
        desc = p.get("description") or p.get("play_text") or p.get("text") or ""
        if desc:
            return f"  {header}\n    {desc}"
        else:
            return f"  {header}"
    else:
        return f"  {p}"


def _should_show_last_n(team: dict) -> bool:
    last_n = team.get("last_n", {}) or {}
    return last_n.get("actual_n", 0) >= last_n.get("required_n", 3)


def _team_html(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"<div class=\"team-card\"><h3>{team['display_name']}</h3><p><em>No PBP data.</em></p></div>"
    games = _games(team)
    xml_m8 = _xml_row(team, "middle_eight")
    pts_for = xml_m8.get("middle_eight_points", _sum(games, "middle8_points_for"))
    pts_against = xml_m8.get("middle_eight_points_allowed", _sum(games, "middle8_points_against"))
    margin = pts_for - pts_against
    per_game = []
    for g in sorted(games, key=lambda x: x.get("game_number", 0)):
        score_tuple = _middle8_game_score(team, g)
        score = f"{score_tuple[0]}-{score_tuple[1]}" if score_tuple else "N/A"
        per_game.append(f"G{g.get('game_number','?')} vs {g.get('opponent','?')}: {score}")
    per_game_html = "".join(f"<li>{l}</li>" for l in per_game) or "<li>N/A</li>"
    plays = _scoring_plays(games)
    if not plays:
        plays = _derived_middle8_scoring_plays(team, games, limit=6)
    plays_html = "".join(_play_html(p) for p in plays[:6]) or "<li>N/A</li>"
    last_n_html = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_pts_for = last_n.get("middle8_points_for", 0)
        l3_pts_against = last_n.get("middle8_points_against", 0)
        l3_margin = last_n.get("middle8_margin", 0)
        trend_color = ""
        if l3_margin > margin:
            trend_color = " style=\"color: #1b7f2a;\""
        elif l3_margin < margin:
            trend_color = " style=\"color: #b42318;\""
        last_n_html = f"""
      <div class="block">
        <h4>Last {actual_n} Trending</h4>
        <ul>
          <li>Points For / Against: {l3_pts_for} / {l3_pts_against}</li>
          <li>Margin: <span{trend_color}>{l3_margin}</span> (Season: {margin})</li>
        </ul>
      </div>
        """

    return f"""
    <div class="team-card">
      <h3>{team['display_name']}</h3>
      <div class="block">
        <h4>Season Totals</h4>
        <ul>
          <li>Points For / Against: {pts_for} / {pts_against}{SRC_PBP}</li>
          <li>Margin: {margin}{SRC_PBP}</li>
        </ul>
      </div>
      {last_n_html}
      <div class="block">
        <h4>Per-Game Breakdown</h4>
        <ul>{per_game_html}</ul>
      </div>
      <div class="block">
        <h4>Notable Scoring Plays</h4>
        <ul>{plays_html}</ul>
      </div>
    </div>
    """


def _team_md(team: dict) -> str:
    if not team.get("has_pbp"):
        return f"*{team['display_name']}*\n- Middle 8: N/A"
    games = _games(team)
    xml_m8 = _xml_row(team, "middle_eight")
    pts_for = xml_m8.get("middle_eight_points", _sum(games, "middle8_points_for"))
    pts_against = xml_m8.get("middle_eight_points_allowed", _sum(games, "middle8_points_against"))
    margin = pts_for - pts_against
    last_n_note = ""
    if _should_show_last_n(team):
        last_n = team.get("last_n", {}) or {}
        actual_n = last_n.get("actual_n", 0)
        l3_margin = last_n.get("middle8_margin", 0)
        if l3_margin != margin:
            last_n_note = f" (L{actual_n}: {l3_margin})"
    plays = _scoring_plays(games)
    if not plays:
        plays = _derived_middle8_scoring_plays(team, games, limit=3)
    plays = plays[:3]
    lines = [
        f"*{team['display_name']}*",
        f"- Middle 8 Margin: {margin} ({pts_for} for / {pts_against} against){last_n_note}",
    ]
    if plays:
        lines.append("- Notable Plays:")
        lines.extend(_play_md(p) for p in plays)
    return "\n".join(lines)


def build(team1: dict, team2: dict) -> dict:
    """Middle 8 momentum section."""
    html_content = f"""
    <div class="section-grid">
      {_team_html(team1)}
      {_team_html(team2)}
    </div>
    """
    md_content = "\n\n".join([
        "*Middle 8*",
        _team_md(team1),
        _team_md(team2),
    ])
    return {
        "title": "Middle 8",
        "html_content": html_content,
        "md_content": md_content,
        "key": "middle8",
    }
