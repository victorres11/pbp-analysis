from __future__ import annotations

from scripts.game_prep_brief.live_refresh_ops import (
    build_alert_payload,
    build_status_view,
    resolve_run_config,
)


def test_resolve_run_config_uses_schedule_repo_defaults() -> None:
    config = resolve_run_config(
        event_name="schedule",
        input_values={
            "team1": "Manual Team",
            "team2": "Manual Opponent",
            "season": "2030",
            "last_n": "5",
            "brief_format": "html",
            "run_tests": "true",
            "strict_verification": "false",
            "include_enrichment": "false",
        },
        variable_values={
            "team1": "Washington",
            "team2": "Ohio State",
            "season": "2025",
            "last_n": "3",
            "brief_format": "both",
            "run_tests": "false",
            "strict_verification": "true",
            "include_enrichment": "true",
        },
    )

    assert config == {
        "team1": "Washington",
        "team2": "Ohio State",
        "season": "2025",
        "last_n": "3",
        "brief_format": "both",
        "run_tests": "false",
        "strict_verification": "true",
        "include_enrichment": "true",
    }


def test_resolve_run_config_keeps_manual_dispatch_inputs() -> None:
    config = resolve_run_config(
        event_name="workflow_dispatch",
        input_values={
            "team1": "Oregon",
            "team2": "USC",
            "season": "2026",
            "last_n": "4",
            "brief_format": "both",
            "run_tests": "true",
            "strict_verification": "false",
            "include_enrichment": "false",
        },
        variable_values={},
    )

    assert config == {
        "team1": "Oregon",
        "team2": "USC",
        "season": "2026",
        "last_n": "4",
        "brief_format": "both",
        "run_tests": "true",
        "strict_verification": "false",
        "include_enrichment": "false",
    }


def test_build_alert_payload_skips_publishable_scheduled_success() -> None:
    payload = build_alert_payload(
        event_name="schedule",
        workflow_conclusion="success",
        run_url="https://example.com/run",
        release_url="https://example.com/release",
        summary={
            "season": 2025,
            "teams": ["Washington", "Ohio State"],
            "artifact_contract": {
                "artifact_set_id": "artifact-id",
                "publishable": True,
                "published_set_complete": True,
                "non_publishable_reasons": [],
            },
            "validation": {
                "verification_fail_count": 0,
                "verification_warning_count": 0,
                "smoke_brief_passed": True,
            },
            "enrichment_contract": {"artifact_status": "validated"},
            "run_state": {"interrupted_stages": []},
            "observability": {"slow_stages": []},
            "warnings": [],
        },
    )

    assert payload == {"should_notify": False}


def test_build_alert_payload_formats_non_publishable_schedule_failure() -> None:
    payload = build_alert_payload(
        event_name="schedule",
        workflow_conclusion="failure",
        run_url="https://example.com/run",
        release_url="https://example.com/release",
        summary={
            "season": 2025,
            "teams": ["Washington", "Ohio State"],
            "artifact_contract": {
                "artifact_set_id": "artifact-id",
                "publishable": False,
                "published_set_complete": False,
                "non_publishable_reasons": ["verification_fail_metrics", "enrichment_disabled"],
            },
            "validation": {
                "verification_fail_count": 2,
                "verification_warning_count": 1,
                "smoke_brief_passed": False,
            },
            "enrichment_contract": {"artifact_status": "disabled"},
            "run_state": {"interrupted_stages": ["cfbstats_snapshot"]},
            "observability": {"slow_stages": ["cfbstats_snapshot"]},
            "warnings": ["[warn] cfbstats_snapshot exceeded expected duration budget (1200s); waiting for completion"],
        },
    )

    assert payload["should_notify"] is True
    assert "workflow_failure" in payload["body"]
    assert "non_publishable" in payload["body"]
    assert "verification_fail_metrics" in payload["body"]
    assert "published_artifacts_incomplete" in payload["body"]
    assert "artifact-id" in payload["body"]
    assert "https://example.com/run" in payload["body"]
    assert "https://example.com/release" in payload["body"]
    assert "cfbstats_snapshot" in payload["body"]
    assert "enrichment_disabled" in payload["body"]


def test_build_alert_payload_notifies_when_summary_missing() -> None:
    payload = build_alert_payload(
        event_name="schedule",
        workflow_conclusion="failure",
        run_url="https://example.com/run",
        release_url=None,
        summary=None,
    )

    assert payload["should_notify"] is True
    assert "missing_pipeline_summary" in payload["body"]


def test_build_status_view_formats_publishable_latest_run() -> None:
    markdown = build_status_view(
        event_name="workflow_dispatch",
        workflow_conclusion="success",
        run_url="https://example.com/run",
        summary={
            "mode": "live-refresh",
            "season": 2025,
            "teams": ["Washington", "Ohio State"],
            "generated_at": "2026-03-10T20:00:00+00:00",
            "exit_code": 0,
            "artifact_contract": {
                "artifact_set_id": "artifact-id",
                "publishable": True,
                "published_set_complete": True,
                "non_publishable_reasons": [],
            },
            "validation": {
                "parser_tests_passed": True,
                "analysis_tests_passed": True,
                "verification_fail_count": 0,
                "verification_warning_count": 1,
                "smoke_brief_passed": True,
            },
            "enrichment_contract": {
                "policy": "required",
                "artifact_status": "validated",
                "team_statuses": {"washington": "ok", "ohio-state": "ok"},
            },
            "run_state": {"interrupted_stages": []},
            "observability": {"heartbeat_interval_seconds": 60, "slow_stages": []},
            "warnings": [],
        },
        release_publishable="true",
        rolling_release_url="https://example.com/release",
        archive_release_url="https://example.com/archive",
        rolling_release_result="published",
        archive_release_result="published",
        alert_posted=None,
        repo="victorres11/pbp-analysis",
    )

    assert "# Brief Live Refresh Status" in markdown
    assert "Overall status: `healthy`" in markdown
    assert "https://example.com/run" in markdown
    assert "artifact-id" in markdown
    assert "Authoritative Published Assets" in markdown
    assert "game_prep_pipeline_summary_2025.json" in markdown
    assert "pbp_stats_bundle_2025.json" in markdown
    assert "brief-live-refresh-status-view" in markdown


def test_build_status_view_handles_missing_summary() -> None:
    markdown = build_status_view(
        event_name="schedule",
        workflow_conclusion="failure",
        run_url="https://example.com/run",
        summary=None,
        release_publishable="false",
        rolling_release_url="https://example.com/release",
        archive_release_url=None,
        rolling_release_result=None,
        archive_release_result=None,
        alert_posted="posted",
        repo="victorres11/pbp-analysis",
    )

    assert "Overall status: `missing_summary`" in markdown
    assert "Pipeline summary JSON was not produced" in markdown
    assert "brief-live-refresh-summary" in markdown
