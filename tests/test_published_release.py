from __future__ import annotations

from scripts.game_prep_brief.published_release import build_release_metadata


def test_build_release_metadata_uses_season_scoped_release_assets() -> None:
    summary = {
        "season": 2025,
        "generated_at": "2026-03-10T18:23:47.533830+00:00",
        "teams": ["Washington", "Ohio State"],
        "git": {
            "pbp_analysis_ref": "analysis-sha",
            "pbp_parser_ref": "parser-sha",
        },
        "validation": {
            "verification_fail_count": 0,
            "verification_warning_count": 0,
        },
        "artifact_contract": {
            "artifact_set_id": "2025-20260310T182347Z-9cf24d85d886",
            "publishable": True,
            "published_artifacts": {
                "bundle": {
                    "relative_path": "published/2025/pbp_stats_bundle_2025.json",
                },
                "cfbstats_snapshot": {
                    "relative_path": "published/2025/cfbstats_2025.json",
                },
                "cfbstats_verification_report": {
                    "relative_path": "published/2025/cfbstats_verification_2025.json",
                },
                "pipeline_summary": {
                    "relative_path": "published/2025/game_prep_pipeline_summary_2025.json",
                },
            },
        },
    }

    metadata = build_release_metadata(
        summary,
        repo="victorres11/pbp-analysis",
        run_url="https://github.com/victorres11/pbp-analysis/actions/runs/22916950471",
    )

    assert metadata["publishable"] is True
    assert metadata["release_tag"] == "brief-artifacts-2025"
    assert metadata["release_name"] == "Brief Published Artifacts 2025"
    assert metadata["release_url"] == (
        "https://github.com/victorres11/pbp-analysis/releases/tag/brief-artifacts-2025"
    )
    assert metadata["assets"] == [
        {
            "logical_name": "bundle",
            "filename": "pbp_stats_bundle_2025.json",
            "download_url": (
                "https://github.com/victorres11/pbp-analysis/releases/download/"
                "brief-artifacts-2025/pbp_stats_bundle_2025.json"
            ),
        },
        {
            "logical_name": "cfbstats_snapshot",
            "filename": "cfbstats_2025.json",
            "download_url": (
                "https://github.com/victorres11/pbp-analysis/releases/download/"
                "brief-artifacts-2025/cfbstats_2025.json"
            ),
        },
        {
            "logical_name": "cfbstats_verification_report",
            "filename": "cfbstats_verification_2025.json",
            "download_url": (
                "https://github.com/victorres11/pbp-analysis/releases/download/"
                "brief-artifacts-2025/cfbstats_verification_2025.json"
            ),
        },
        {
            "logical_name": "pipeline_summary",
            "filename": "game_prep_pipeline_summary_2025.json",
            "download_url": (
                "https://github.com/victorres11/pbp-analysis/releases/download/"
                "brief-artifacts-2025/game_prep_pipeline_summary_2025.json"
            ),
        },
    ]
    assert "rolling canonical published artifact set" in metadata["notes"]
    assert "2025-20260310T182347Z-9cf24d85d886" in metadata["notes"]
    assert "analysis-sha" in metadata["notes"]
    assert "parser-sha" in metadata["notes"]
    assert "22916950471" in metadata["notes"]


def test_build_release_metadata_keeps_release_target_stable_for_non_publishable_runs() -> None:
    summary = {
        "season": 2025,
        "teams": ["Washington", "Ohio State"],
        "artifact_contract": {
            "artifact_set_id": "artifact-id",
            "publishable": False,
            "published_artifacts": {},
        },
    }

    metadata = build_release_metadata(summary, repo="victorres11/pbp-analysis")

    assert metadata["publishable"] is False
    assert metadata["release_tag"] == "brief-artifacts-2025"
    assert metadata["release_url"].endswith("/brief-artifacts-2025")
