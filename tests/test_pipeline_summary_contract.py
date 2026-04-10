from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_SCRIPT = ROOT / "scripts" / "refresh-game-prep-pipeline.sh"
FIXTURES = ROOT / "tests" / "fixtures" / "pipeline"


def test_offline_pipeline_summary_includes_artifact_contract(tmp_path: Path) -> None:
    summary_json = tmp_path / "game_prep_pipeline_summary.json"
    output_dir = tmp_path / "brief"
    bundle_path = FIXTURES / "pbp_stats_bundle_2025.json"
    snapshot_path = FIXTURES / "cfbstats_2025_snapshot.json"
    verification_path = FIXTURES / "cfbstats_verification_2025_report.json"

    env = os.environ.copy()
    env["PBP_PIPELINE_PYTHON"] = sys.executable

    subprocess.run(
        [
            str(PIPELINE_SCRIPT),
            "Washington",
            "Ohio State",
            "--season",
            "2025",
            "--mode",
            "offline-validate",
            "--bundle-path",
            str(bundle_path),
            "--reuse-bundle",
            "--cfbstats-snapshot",
            str(snapshot_path),
            "--cfbstats-verification-report",
            str(verification_path),
            "--no-enrichment",
            "--skip-tests",
            "--brief-format",
            "markdown",
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_json),
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )

    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    contract = summary["artifact_contract"]
    enrichment_contract = summary["enrichment_contract"]
    run_state = summary["run_state"]
    observability = summary["observability"]

    assert contract["version"] == 2
    assert contract["published_root_relative_path"] == "published/2025/"
    assert contract["scratch_root_relative_path"] == "scratch/"
    assert contract["publishable"] is False
    assert contract["published_set_complete"] is True
    assert "mode_must_be_live_refresh" in contract["non_publishable_reasons"]

    bundle = contract["published_artifacts"]["bundle"]
    assert bundle["tier"] == "published"
    assert bundle["required"] is True
    assert bundle["relative_path"] == "published/2025/pbp_stats_bundle_2025.json"
    assert bundle["exists"] is True

    verification_report = contract["published_artifacts"]["cfbstats_verification_report"]
    assert verification_report["relative_path"] == (
        "published/2025/cfbstats_verification_2025.json"
    )

    enrichment = contract["scratch_artifacts"]["enrichment"]
    assert enrichment["tier"] == "scratch"
    assert enrichment["required"] is False
    assert enrichment["relative_path"] == "scratch/game_prep_enrichment_2025.json"
    assert enrichment_contract["policy"] == "disabled"
    assert enrichment_contract["artifact_status"] == "disabled"
    assert enrichment_contract["runtime_live_fetch_allowed"] is False
    assert enrichment_contract["team_statuses"] == {}
    assert summary["validation"]["enrichment_artifact_validated"] is None
    assert "enrichment_disabled" in contract["non_publishable_reasons"]

    markdown = contract["scratch_artifacts"]["smoke_brief_markdown"]
    assert markdown["relative_path"] == "scratch/brief/washington_vs_ohio-state_2025_v2.md"

    assert run_state == {
        "completed": True,
        "interrupted": False,
        "interrupted_stages": [],
    }
    assert observability["heartbeat_interval_seconds"] == 60
    assert observability["slow_stages"] == []

    bundle_validation = next(stage for stage in summary["stages"] if stage["name"] == "bundle_validation")
    assert bundle_validation["status"] == "passed"
    assert bundle_validation["started_at"] is not None
    assert bundle_validation["finished_at"] is not None
    assert bundle_validation["heartbeat_count"] == 0
    assert bundle_validation["expected_duration_seconds"] == 60
    assert bundle_validation["exceeded_expected_duration"] is False


def test_offline_pipeline_summary_records_required_enrichment_contract(tmp_path: Path) -> None:
    summary_json = tmp_path / "game_prep_pipeline_summary.json"
    output_dir = tmp_path / "brief"
    enrichment_path = tmp_path / "enrichment.json"
    bundle_path = FIXTURES / "pbp_stats_bundle_2025.json"
    snapshot_path = FIXTURES / "cfbstats_2025_snapshot.json"
    verification_path = FIXTURES / "cfbstats_verification_2025_report.json"

    enrichment_path.write_text(
        json.dumps(
            {
                "washington": {"_status": "ok", "_source": "test"},
                "ohio-state": {"_status": "ok", "_source": "test"},
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PBP_PIPELINE_PYTHON"] = sys.executable

    subprocess.run(
        [
            str(PIPELINE_SCRIPT),
            "Washington",
            "Ohio State",
            "--season",
            "2025",
            "--mode",
            "offline-validate",
            "--bundle-path",
            str(bundle_path),
            "--reuse-bundle",
            "--cfbstats-snapshot",
            str(snapshot_path),
            "--cfbstats-verification-report",
            str(verification_path),
            "--enrichment-file",
            str(enrichment_path),
            "--skip-tests",
            "--brief-format",
            "markdown",
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_json),
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )

    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    contract = summary["artifact_contract"]
    enrichment_contract = summary["enrichment_contract"]

    assert contract["scratch_artifacts"]["enrichment"]["required"] is True
    assert summary["validation"]["enrichment_artifact_validated"] is True
    assert enrichment_contract["policy"] == "required"
    assert enrichment_contract["artifact_status"] == "validated"
    assert enrichment_contract["team_statuses"] == {
        "washington": "ok",
        "ohio-state": "ok",
    }
    assert enrichment_contract["offline_validate_behavior"] == "require_existing_artifact"


def test_offline_pipeline_summary_records_unavailable_enrichment_signal(tmp_path: Path) -> None:
    summary_json = tmp_path / "game_prep_pipeline_summary.json"
    output_dir = tmp_path / "brief"
    enrichment_path = tmp_path / "enrichment.json"
    bundle_path = FIXTURES / "pbp_stats_bundle_2025.json"
    snapshot_path = FIXTURES / "cfbstats_2025_snapshot.json"
    verification_path = FIXTURES / "cfbstats_verification_2025_report.json"

    enrichment_path.write_text(
        json.dumps(
            {
                "washington": {"_status": "unavailable", "_source": "test"},
                "ohio-state": {"_status": "ok", "_source": "test"},
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PBP_PIPELINE_PYTHON"] = sys.executable

    subprocess.run(
        [
            str(PIPELINE_SCRIPT),
            "Washington",
            "Ohio State",
            "--season",
            "2025",
            "--mode",
            "offline-validate",
            "--bundle-path",
            str(bundle_path),
            "--reuse-bundle",
            "--cfbstats-snapshot",
            str(snapshot_path),
            "--cfbstats-verification-report",
            str(verification_path),
            "--enrichment-file",
            str(enrichment_path),
            "--skip-tests",
            "--brief-format",
            "markdown",
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_json),
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )

    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    enrichment_contract = summary["enrichment_contract"]

    assert summary["validation"]["enrichment_artifact_validated"] is True
    assert enrichment_contract["artifact_status"] == "validated_with_unavailable_teams"
    assert enrichment_contract["team_statuses"] == {
        "washington": "unavailable",
        "ohio-state": "ok",
    }


def test_offline_pipeline_scopes_verification_gate_to_selected_teams(tmp_path: Path) -> None:
    summary_json = tmp_path / "game_prep_pipeline_summary.json"
    output_dir = tmp_path / "brief"
    bundle_path = FIXTURES / "pbp_stats_bundle_2025.json"
    snapshot_path = FIXTURES / "cfbstats_2025_snapshot.json"
    verification_path = tmp_path / "cfbstats_verification_scoped.json"

    verification_report = json.loads(
        (FIXTURES / "cfbstats_verification_2025_report.json").read_text(encoding="utf-8")
    )
    verification_report["summary"]["metric_results"]["fail"] = 1
    verification_report["summary"]["team_results"]["fail"] = 1
    verification_report["summary"]["has_failures"] = True
    verification_report["summary"]["metric_mismatches"] = 1
    verification_report["summary"]["mismatch"] = 1
    verification_report["summary"]["metric_status_counts"]["mismatch"] = 1
    verification_report["summary"]["team_status_counts"]["ok"] = 3
    verification_report["summary"]["teams_checked"] = 3
    verification_report["summary"]["metrics_checked"] = 11

    verification_report["teams"]["northwestern"] = {
        "team_slug": "northwestern",
        "team_name": "northwestern",
        "conference": "Big Ten",
        "verifier_status": "ok",
        "result": "fail",
        "reason_id": None,
        "summary": {
            "metrics_checked": 1,
            "metric_results": {
                "pass": 0,
                "warning": 0,
                "fail": 1,
            },
            "status_counts": {
                "mismatch": 1,
            },
            "result": "fail",
        },
        "flagged_metrics": ["scoring_margin_pg"],
        "metrics": {
            "scoring_margin_pg": {
                "key": "scoring_margin_pg",
                "label": "Scoring Margin",
                "status": "mismatch",
                "result": "fail",
                "reason_id": None,
                "note": None,
                "comparison": {
                    "parser_value": 1.6,
                    "cfbstats_value": 3.6,
                    "delta": -2.0,
                    "tolerance": 0.11,
                },
                "bundle": {
                    "team_abbr": "NU",
                    "category": "scoring_margin",
                    "field": "scoring_margin",
                },
                "cfbstats": {
                    "category_id": 10,
                    "side": "offense",
                    "rank": "11",
                    "conference": "Big Ten",
                    "value": 3.6,
                },
            }
        },
    }
    verification_path.write_text(json.dumps(verification_report), encoding="utf-8")

    env = os.environ.copy()
    env["PBP_PIPELINE_PYTHON"] = sys.executable

    subprocess.run(
        [
            str(PIPELINE_SCRIPT),
            "Washington",
            "Ohio State",
            "--season",
            "2025",
            "--mode",
            "offline-validate",
            "--bundle-path",
            str(bundle_path),
            "--reuse-bundle",
            "--cfbstats-snapshot",
            str(snapshot_path),
            "--cfbstats-verification-report",
            str(verification_path),
            "--no-enrichment",
            "--skip-tests",
            "--brief-format",
            "markdown",
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_json),
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )

    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    validation = summary["validation"]

    assert validation["verification_scope"] == "selected_teams"
    assert validation["verification_selected_teams"] == ["washington", "ohio-state"]
    assert validation["verification_fail_count"] == 0
    assert validation["verification_overall_fail_count"] == 1
    assert validation["verification_unrelated_fail_team_slugs"] == ["northwestern"]
    assert validation["verification_unrelated_fail_metric_count"] == 1
    assert summary["exit_code"] == 0
    assert validation["smoke_brief_passed"] is True
    assert any(
        "Verification report has fail metrics outside selected teams: northwestern" in warning
        for warning in summary["warnings"]
    )
