from __future__ import annotations

from pathlib import Path

from scripts.game_prep_brief.readiness_registry import render_markdown, validate_registry


def _ready_team(**overrides):
    team = {
        "display_name": "Utah",
        "conference": "Big 12",
        "status": "production_ready_2025",
        "deliverable_status": "ready_with_warnings",
        "statbroadcast": {
            "status": "complete",
            "expected_games": 13,
            "found_games": 13,
            "source": "StatBroadcast archive XML",
        },
        "cfbstats": {
            "status": "verified",
            "conference_scope": "Big 12",
            "snapshot_present": True,
        },
        "pff": {
            "status": "ready",
            "slug": "utah-utes",
        },
        "verification": {
            "status": "passed_with_warnings",
            "failures": 0,
            "warnings": 2,
            "notes": ["bounded source drift"],
        },
        "notes": ["ready"],
    }
    team.update(overrides)
    return team


def test_validate_registry_passes_production_ready_team() -> None:
    report = validate_registry({"teams": {"utah": _ready_team()}})

    assert report["summary"]["ready"] is True
    assert report["summary"]["status_counts"]["fail"] == 0


def test_validate_registry_warns_for_existing_supported_team() -> None:
    team = _ready_team(status="existing_supported")

    report = validate_registry({"teams": {"notre-dame": team}})

    assert report["summary"]["ready"] is True
    assert any(
        check["status"] == "warning"
        and check["team_slug"] == "notre-dame"
        and check["check"] == "status"
        for check in report["checks"]
    )


def test_validate_registry_blocks_onboarding_or_blocked_delivery() -> None:
    team = _ready_team(status="onboarding", deliverable_status="core_ready_enrichment_blocked")

    report = validate_registry({"teams": {"uconn": team}})

    assert report["summary"]["ready"] is False
    assert any(check["check"] == "status" and check["status"] == "fail" for check in report["checks"])
    assert any(check["check"] == "deliverable_status" and check["status"] == "fail" for check in report["checks"])


def test_validate_registry_blocks_game_count_mismatch() -> None:
    team = _ready_team(
        statbroadcast={
            "status": "complete",
            "expected_games": 13,
            "found_games": 12,
            "source": "StatBroadcast archive XML",
        }
    )

    report = validate_registry({"teams": {"utah": team}})

    assert report["summary"]["ready"] is False
    assert any(check["check"] == "statbroadcast.games" and check["status"] == "fail" for check in report["checks"])


def test_validate_registry_requires_pff_slug() -> None:
    team = _ready_team(pff={"status": "ready", "slug": None})

    report = validate_registry({"teams": {"utah": team}})

    assert report["summary"]["ready"] is False
    assert any(check["check"] == "pff.slug" and check["status"] == "fail" for check in report["checks"])


def test_validate_registry_warns_for_partial_pff_without_notes() -> None:
    team = _ready_team(pff={"status": "partial", "slug": "utah-utes"})

    report = validate_registry({"teams": {"utah": team}})

    assert report["summary"]["ready"] is True
    assert any(check["check"] == "pff.status" and check["status"] == "warning" for check in report["checks"])
    assert any(check["check"] == "pff.notes" and check["status"] == "warning" for check in report["checks"])


def test_render_markdown_omits_pass_checks_and_lists_findings() -> None:
    report = validate_registry({"teams": {"utah": _ready_team(status="existing_supported")}})

    markdown = render_markdown(report, registry_path=Path("config/team-readiness-2025.json"))

    assert "# Team Readiness Registry Report" in markdown
    assert "Status: `ready`" in markdown
    assert "| warning | utah | status |" in markdown
    assert "| pass |" not in markdown
