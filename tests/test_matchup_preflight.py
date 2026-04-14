from __future__ import annotations

from scripts.game_prep_brief.matchup_preflight import (
    TeamRequest,
    _expected_games_for,
    _parse_keyed_values,
    build_preflight_report,
    find_team_payload,
    render_markdown,
)


def _bundle(games: int = 13) -> dict:
    return {
        "teams": {
            "michigan": {
                "team_name": "michigan",
                "games_parsed": games,
                "games": [{"game_date": "2025-08-30"} for _ in range(games)],
            },
            "utah": {
                "team_name": "utah",
                "games_parsed": games,
                "games": [{"game_date": "2025-08-30"} for _ in range(games)],
            },
        }
    }


def _snapshot() -> dict:
    rankings = {"all": {"third_down": {"rank": 1, "value": "52.6%"}}}
    return {
        "teams": {
            "michigan": {"team_name": "Michigan", "team_slug": "michigan", "conference": "Big Ten", "rankings": rankings},
            "utah": {"team_name": "Utah", "team_slug": "utah", "conference": "Big 12", "rankings": rankings},
        }
    }


def _verification(warnings: int = 1, fails: int = 0) -> dict:
    row = {
        "summary": {
            "metric_results": {
                "pass": 20 - warnings - fails,
                "warning": warnings,
                "fail": fails,
            }
        }
    }
    return {"teams": {"michigan": row, "utah": row}}


def _enrichment() -> dict:
    team_payload = {
        "_status": "ok",
        "_providers": {"pff": {"status": "ok"}},
        "pff_avg_play_clock": "15.0",
        "pff_hurry_up_pct": "20.4%",
        "pff_plays_offense_pg": "72",
        "pff_plays_defense_pg": "68",
    }
    return {"michigan": team_payload, "utah": team_payload}


def test_matchup_preflight_passes_with_expected_games_and_team_conference() -> None:
    report = build_preflight_report(
        season=2025,
        team1=TeamRequest("Michigan", "michigan", expected_games=13, expected_conference="Big Ten"),
        team2=TeamRequest("Utah", "utah", expected_games=13, expected_conference="Big 12"),
        bundle=_bundle(),
        snapshot=_snapshot(),
        verification=_verification(),
        enrichment=_enrichment(),
        require_expected_games=True,
        require_enrichment=True,
        artifact_paths={},
    )

    assert report["summary"]["ready"] is True
    assert report["summary"]["status_counts"]["fail"] == 0
    assert any(
        check["check"] == "cfbstats_expected_conference"
        and check["team_slug"] == "utah"
        and check["status"] == "pass"
        for check in report["checks"]
    )
    assert "Status: `ready`" in render_markdown(report)


def test_matchup_preflight_blocks_expected_game_mismatch() -> None:
    report = build_preflight_report(
        season=2025,
        team1=TeamRequest("Michigan", "michigan", expected_games=13),
        team2=TeamRequest("Utah", "utah", expected_games=12),
        bundle=_bundle(games=13),
        snapshot=_snapshot(),
        verification=_verification(warnings=0),
        enrichment=_enrichment(),
        require_expected_games=True,
        require_enrichment=True,
        artifact_paths={},
    )

    assert report["summary"]["ready"] is False
    assert any(
        check["check"] == "expected_games"
        and check["team_slug"] == "utah"
        and check["status"] == "fail"
        for check in report["checks"]
    )


def test_matchup_preflight_blocks_missing_team() -> None:
    report = build_preflight_report(
        season=2025,
        team1=TeamRequest("Notre Dame", "notre-dame", expected_games=12),
        team2=TeamRequest("UConn", "uconn", expected_games=12),
        bundle={"teams": {"notre-dame": {"team_name": "Notre Dame", "games_parsed": 12}}},
        snapshot={"teams": {"notre-dame": {"team_name": "Notre Dame", "conference": "Independent", "rankings": {}}}},
        verification={"teams": {"notre-dame": {"summary": {"metric_results": {"pass": 20, "warning": 0, "fail": 0}}}}},
        enrichment=None,
        require_expected_games=True,
        require_enrichment=False,
        artifact_paths={},
    )

    assert report["summary"]["ready"] is False
    assert any(check["check"] == "bundle_team" and check["team_slug"] == "uconn" for check in report["checks"])


def test_uconn_alias_resolves_connecticut_payload() -> None:
    match = find_team_payload({"teams": {"connecticut": {"team_name": "Connecticut"}}}, "UConn")

    assert match is not None
    assert match[0] == "connecticut"


def test_expected_games_parser_matches_aliases() -> None:
    values = _parse_keyed_values(["UConn=2", "Notre Dame=3"])

    assert _expected_games_for("Connecticut", values) == 2
    assert _expected_games_for("Notre Dame", values) == 3
