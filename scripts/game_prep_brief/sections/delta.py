from __future__ import annotations


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_value(value: float | None, suffix: str, precision: int) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{precision}f}{suffix}"


def _edge_text(
    team1_name: str,
    team1_value: float | None,
    team2_name: str,
    team2_value: float | None,
    higher_is_better: bool,
    suffix: str,
    precision: int,
) -> str:
    if team1_value is None or team2_value is None:
        return "Edge: N/A"

    if team1_value == team2_value:
        return "Edge: Even"

    if higher_is_better:
        better_team = team1_name if team1_value > team2_value else team2_name
    else:
        better_team = team1_name if team1_value < team2_value else team2_name

    delta = abs(team1_value - team2_value)
    return f"Edge: {better_team} by {_fmt_value(delta, suffix, precision)}"


def metric_delta_html(
    label: str,
    team1_name: str,
    team1_raw: object,
    team2_name: str,
    team2_raw: object,
    *,
    higher_is_better: bool = True,
    suffix: str = "",
    precision: int = 1,
) -> str:
    team1_value = _to_float(team1_raw)
    team2_value = _to_float(team2_raw)
    t1 = _fmt_value(team1_value, suffix, precision)
    t2 = _fmt_value(team2_value, suffix, precision)
    edge = _edge_text(
        team1_name,
        team1_value,
        team2_name,
        team2_value,
        higher_is_better,
        suffix,
        precision,
    )
    return (
        f"<div class=\"metric-compare\"><p><strong>Matchup Delta:</strong> {label} "
        f"({team1_name} {t1} vs {team2_name} {t2}) · {edge}</p></div>"
    )


def metric_delta_md(
    label: str,
    team1_name: str,
    team1_raw: object,
    team2_name: str,
    team2_raw: object,
    *,
    higher_is_better: bool = True,
    suffix: str = "",
    precision: int = 1,
) -> str:
    team1_value = _to_float(team1_raw)
    team2_value = _to_float(team2_raw)
    t1 = _fmt_value(team1_value, suffix, precision)
    t2 = _fmt_value(team2_value, suffix, precision)
    edge = _edge_text(
        team1_name,
        team1_value,
        team2_name,
        team2_value,
        higher_is_better,
        suffix,
        precision,
    )
    return f"*Matchup Delta:* {label} ({team1_name} {t1} vs {team2_name} {t2}) | {edge}"
