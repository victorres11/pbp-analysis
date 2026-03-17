from __future__ import annotations

from pathlib import Path

from scripts.game_prep_brief.supported_team_sweep import (
    build_report,
    classify_warning,
    collect_warning_lines,
    render_markdown,
    summarize_confidence,
    warning_targets,
)


def test_classify_warning_distinguishes_infrastructure_and_data_quality() -> None:
    assert classify_warning("[warn] yr-data-api fetch failed for pff/plays: HTTPError: 422") == "infrastructure"
    assert classify_warning("error: Python 3.10+ is required for game brief generation.") == "infrastructure"
    assert classify_warning("[warn] UCLA: 4th-down parity delta +5.4 pts") == "data_quality"
    assert classify_warning("Missing enrichment artifact") == "artifact_gap"
    assert classify_warning("[warn] XML parity gaps detected: Northwestern: missing team payload in XML bundle") == "artifact_gap"


def test_warning_targets_defaults_to_both_matchup_teams() -> None:
    assert warning_targets("[warn] generic failure", ("ucla", "usc")) == ["ucla", "usc"]
    assert warning_targets("[warn] Turnover reconciliation mismatch for UCLA", ("ucla", "usc")) == ["ucla"]


def test_build_report_rolls_matchups_into_team_summary() -> None:
    report = build_report(
        season=2025,
        mode="refresh-enrichment",
        format="markdown",
        output_dir="/tmp/bigten",
        matchup_results=[
            {
                "team1": "UCLA",
                "team2": "USC",
                "team1_slug": "ucla",
                "team2_slug": "usc",
                "exit_code": 0,
                "classification": "warning_data_quality",
                "warning_lines": ["[warn] UCLA: 4th-down parity delta +5.4 pts"],
                "warning_kinds": ["data_quality"],
                "stderr_lines": [],
                "stdout_lines": [],
                "outputs": {"markdown": "/tmp/ucla_vs_usc.md"},
                "command": [],
            }
        ],
    )

    assert report["summary"]["matchups_passed"] == 1
    assert report["teams"]["ucla"]["warning_status"] == "data quality"
    assert report["teams"]["ucla"]["confidence"] == "caution"
    assert report["teams"]["ucla"]["enrichment_status"] == "validated"
    assert report["teams"]["ucla"]["notes"] == "1 data-quality warning(s)"

    markdown = render_markdown(report)
    assert "# Big Ten + Notre Dame Validation Sweep" in markdown
    assert "| UCLA | Big Ten | data quality | validated | caution | 1 data-quality warning(s) |" in markdown


def test_build_report_dedupes_team_warning_lines_across_matchups() -> None:
    report = build_report(
        season=2025,
        mode="no-enrichment",
        format="markdown",
        output_dir="/tmp/bigten",
        matchup_results=[
            {
                "team1": "Illinois",
                "team2": "Indiana",
                "team1_slug": "illinois",
                "team2_slug": "indiana",
                "exit_code": 0,
                "classification": "warning_data_quality",
                "warning_lines": ["[warn] Illinois: 4th-down parity delta +5.4 pts"],
                "warning_kinds": ["data_quality"],
                "stderr_lines": [],
                "stdout_lines": [],
                "outputs": {"markdown": "/tmp/illinois_vs_indiana.md"},
                "command": [],
            },
            {
                "team1": "Northwestern",
                "team2": "Illinois",
                "team1_slug": "northwestern",
                "team2_slug": "illinois",
                "exit_code": 0,
                "classification": "warning_artifact_gap",
                "warning_lines": ["[warn] Illinois: 4th-down parity delta +5.4 pts"],
                "warning_kinds": ["data_quality"],
                "stderr_lines": [],
                "stdout_lines": [],
                "outputs": {"markdown": "/tmp/northwestern_vs_illinois.md"},
                "command": [],
            },
        ],
    )

    assert report["teams"]["illinois"]["notes"] == "1 data-quality warning(s)"
    assert report["teams"]["illinois"]["warning_lines"] == ["[warn] Illinois: 4th-down parity delta +5.4 pts"]


def test_summarize_confidence_blocks_failed_runs() -> None:
    assert summarize_confidence([1], {"artifact_gap"}) == "blocked"


def test_collect_warning_lines_reads_rendered_markdown_banner(tmp_path: Path) -> None:
    markdown_path = tmp_path / "brief.md"
    markdown_path.write_text(
        "🏈 *GAME PREP BRIEF v2*\n"
        "⚠️ XML parity gaps detected: Northwestern: missing team payload in XML bundle; Illinois: 4th-down parity delta +5.4 pts.\n",
        encoding="utf-8",
    )

    warning_lines = collect_warning_lines([], {"markdown": str(markdown_path)}, mode="refresh-enrichment")

    assert warning_lines == [
        "[warn] Northwestern: missing team payload in XML bundle",
        "[warn] Illinois: 4th-down parity delta +5.4 pts.",
    ]


def test_collect_warning_lines_dedupes_stderr_and_rendered_duplicates(tmp_path: Path) -> None:
    markdown_path = tmp_path / "brief.md"
    markdown_path.write_text(
        "🏈 *GAME PREP BRIEF v2*\n"
        "⚠️ XML parity gaps detected: Illinois: 4th-down parity delta +5.4 pts\n",
        encoding="utf-8",
    )

    warning_lines = collect_warning_lines(
        ["[warn] Illinois: 4th-down parity delta +5.4 pts"],
        {"markdown": str(markdown_path)},
        mode="refresh-enrichment",
    )

    assert warning_lines == ["[warn] Illinois: 4th-down parity delta +5.4 pts"]


def test_collect_warning_lines_skips_expected_partial_enrichment_banner_in_no_enrichment_mode(
    tmp_path: Path,
) -> None:
    markdown_path = tmp_path / "brief.md"
    markdown_path.write_text(
        "🏈 *GAME PREP BRIEF v2*\n"
        "⚠️ PFF/API snapshot partial for Northwestern, Illinois; some situational/trenches fields may be unavailable.\n",
        encoding="utf-8",
    )

    warning_lines = collect_warning_lines([], {"markdown": str(markdown_path)}, mode="no-enrichment")

    assert warning_lines == []
