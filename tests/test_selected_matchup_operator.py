from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from scripts.game_prep_brief import selected_matchup


def _args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "team1": "Notre Dame",
        "team2": "UConn",
        "season": 2025,
        "week": None,
        "format": "both",
        "output_dir": tmp_path,
        "last_n": 3,
        "bundle": tmp_path / "bundle.json",
        "cfbstats_snapshot": None,
        "cfbstats_verification_report": None,
        "enrichment_file": None,
        "preflight_json": None,
        "preflight_md": None,
        "summary_json": None,
        "expected_games": [],
        "expected_conference": [],
        "require_expected_games": True,
        "refresh_enrichment": False,
        "no_enrichment": False,
        "skip_render": False,
        "allow_blocked": False,
        "legacy_page_breaks": False,
        "no_alerts": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_resolve_paths_uses_selected_matchup_names(tmp_path: Path) -> None:
    paths = selected_matchup.resolve_paths(_args(tmp_path))

    assert paths.enrichment_file == tmp_path / "notre-dame_vs_uconn_2025_enrichment.json"
    assert paths.preflight_json == tmp_path / "notre-dame_vs_uconn_2025_preflight.json"
    assert paths.preflight_md == tmp_path / "notre-dame_vs_uconn_2025_preflight.md"
    assert paths.summary_json == tmp_path / "notre-dame_vs_uconn_2025_operator_summary.json"
    assert paths.markdown == tmp_path / "notre-dame_vs_uconn_2025_v2.md"
    assert paths.html == tmp_path / "notre-dame_vs_uconn_2025_v2.html"


def test_build_render_command_passes_existing_artifacts(tmp_path: Path) -> None:
    args = _args(tmp_path, week=3, format="markdown")
    paths = selected_matchup.resolve_paths(args)

    command = selected_matchup.build_render_command(args, paths)

    assert command[:3] == [selected_matchup.sys.executable, "-m", "scripts.game_prep_brief"]
    assert "--week" in command
    assert "3" in command
    assert "--enrichment-file" in command
    assert str(paths.enrichment_file) in command
    assert "--no-enrichment" not in command


def test_build_render_command_allows_no_enrichment(tmp_path: Path) -> None:
    args = _args(tmp_path, no_enrichment=True)
    paths = selected_matchup.resolve_paths(args)

    command = selected_matchup.build_render_command(args, paths)

    assert "--no-enrichment" in command
    assert "--enrichment-file" not in command


def test_operator_summary_marks_blocked_preflight(tmp_path: Path) -> None:
    args = _args(tmp_path, skip_render=True)
    paths = selected_matchup.resolve_paths(args)
    preflight = {"summary": {"ready": False, "status_counts": {"pass": 1, "warning": 0, "fail": 1}}}

    summary = selected_matchup._build_summary(
        args=args,
        paths=paths,
        preflight=preflight,
        render_result=None,
        render_command=None,
    )

    assert summary["status"] == "blocked"
    assert summary["preflight"]["status_counts"]["fail"] == 1
    assert summary["render"]["status"] == "skipped"


def test_operator_summary_marks_render_failure(tmp_path: Path) -> None:
    args = _args(tmp_path)
    paths = selected_matchup.resolve_paths(args)
    preflight = {"summary": {"ready": True, "status_counts": {"pass": 10, "warning": 0, "fail": 0}}}
    render_result = subprocess.CompletedProcess(args=["brief"], returncode=2, stdout="", stderr="boom\n")

    summary = selected_matchup._build_summary(
        args=args,
        paths=paths,
        preflight=preflight,
        render_result=render_result,
        render_command=["brief"],
    )

    assert summary["status"] == "render_failed"
    assert summary["render"]["exit_code"] == 2
    assert summary["render"]["stderr"] == ["boom"]
