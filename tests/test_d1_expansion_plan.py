from __future__ import annotations

from pathlib import Path

from scripts.game_prep_brief.d1_expansion_plan import render_markdown, validate_expansion_plan


def _registry_team(**overrides):
    team = {
        "display_name": "Michigan",
        "conference": "Big Ten",
        "status": "production_ready_2025",
        "deliverable_status": "ready_with_warnings",
        "statbroadcast": {"expected_games": 13},
        "cfbstats": {"conference_scope": "Big Ten"},
    }
    team.update(overrides)
    return team


def _plan(**matchup_overrides):
    matchup = {
        "id": "michigan-utah",
        "status": "complete",
        "team1": "Michigan",
        "team2": "Utah",
        "coverage": ["Big Ten", "Big 12"],
        "expected_games": {"Michigan": 13, "Utah": 13},
        "expected_conference": {"Michigan": "Big Ten", "Utah": "Big 12"},
        "evidence": ["operator-approved"],
    }
    matchup.update(matchup_overrides)
    return {"season": 2025, "waves": [{"id": "proof", "matchups": [matchup]}]}


def test_validate_expansion_plan_passes_complete_ready_matchup() -> None:
    registry = {
        "teams": {
            "michigan": _registry_team(),
            "utah": _registry_team(
                display_name="Utah",
                conference="Big 12",
                statbroadcast={"expected_games": 13},
                cfbstats={"conference_scope": "Big 12"},
            ),
        }
    }

    report = validate_expansion_plan(_plan(), registry=registry, registry_path=Path("registry.json"))

    assert report["summary"]["ready"] is True
    assert report["summary"]["status_counts"]["fail"] == 0
    assert report["matchups"][0]["readiness"] == "ready"


def test_validate_expansion_plan_blocks_complete_missing_registry_team() -> None:
    registry = {"teams": {"michigan": _registry_team()}}

    report = validate_expansion_plan(_plan(), registry=registry, registry_path=Path("registry.json"))

    assert report["summary"]["ready"] is False
    assert any(
        check["status"] == "fail"
        and check["check"] == "readiness_entry"
        and check["team"] == "Utah"
        for check in report["checks"]
    )


def test_validate_expansion_plan_warns_for_planned_missing_registry_team() -> None:
    registry = {"teams": {"michigan": _registry_team()}}

    report = validate_expansion_plan(
        _plan(status="planned", evidence=[], expected_games=None),
        registry=registry,
        registry_path=Path("registry.json"),
    )

    assert report["summary"]["ready"] is True
    assert report["matchups"][0]["readiness"] == "needs_onboarding"
    assert any(
        check["status"] == "warning"
        and check["check"] == "readiness_entry"
        and check["team"] == "Utah"
        for check in report["checks"]
    )


def test_validate_expansion_plan_blocks_complete_expected_game_mismatch() -> None:
    registry = {
        "teams": {
            "michigan": _registry_team(statbroadcast={"expected_games": 12}),
            "utah": _registry_team(
                display_name="Utah",
                conference="Big 12",
                statbroadcast={"expected_games": 13},
                cfbstats={"conference_scope": "Big 12"},
            ),
        }
    }

    report = validate_expansion_plan(_plan(), registry=registry, registry_path=Path("registry.json"))

    assert report["summary"]["ready"] is False
    assert any(
        check["status"] == "fail"
        and check["check"] == "expected_games"
        and check["team"] == "Michigan"
        for check in report["checks"]
    )


def test_render_markdown_lists_matchups_and_findings() -> None:
    report = validate_expansion_plan(
        _plan(status="planned", evidence=[], expected_games=None),
        registry={"teams": {"michigan": _registry_team()}},
        registry_path=Path("registry.json"),
    )

    markdown = render_markdown(report, plan_path=Path("plan.json"), registry_path=Path("registry.json"))

    assert "# D1 Matchup Expansion Report" in markdown
    assert "| proof | michigan-utah | planned | needs_onboarding | Michigan vs Utah | Big Ten, Big 12 |" in markdown
    assert "| warning | proof | michigan-utah | Utah | readiness_entry |" in markdown
