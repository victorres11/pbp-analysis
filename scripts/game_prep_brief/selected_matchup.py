from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .loaders import (
    build_enrichment_payload,
    load_enrichment_file,
    merge_enrichment_payload,
    slugify,
    validate_enrichment_payload,
    write_enrichment_file,
)
from .matchup_preflight import (
    DEFAULT_BUNDLE,
    DEFAULT_OUTPUT_DIR,
    TeamRequest,
    _expected_conference_for,
    _expected_games_for,
    _load_json,
    _parse_keyed_values,
    build_preflight_report,
    render_markdown as render_preflight_markdown,
)


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parent


@dataclass(frozen=True)
class OperatorPaths:
    output_dir: Path
    bundle: Path
    cfbstats_snapshot: Path
    cfbstats_verification_report: Path
    enrichment_file: Path
    preflight_json: Path
    preflight_md: Path
    summary_json: Path
    markdown: Path | None
    html: Path | None


def _default_snapshot_path(season: int) -> Path:
    return WORKSPACE_ROOT / "pbp-parser" / "data" / "cfbstats_snapshots" / f"cfbstats_{season}.json"


def _default_verification_path(season: int) -> Path:
    return (
        WORKSPACE_ROOT
        / "pbp-parser"
        / "data"
        / "cfbstats_reports"
        / f"cfbstats_verification_{season}.json"
    )


def _brief_base_name(team1_slug: str, team2_slug: str, season: int, week: int | None) -> str:
    week_tag = f"_week{week}" if week else ""
    return f"{team1_slug}_vs_{team2_slug}{week_tag}_{season}_v2"


def resolve_paths(args: argparse.Namespace) -> OperatorPaths:
    output_dir = args.output_dir.resolve()
    team1_slug = slugify(args.team1)
    team2_slug = slugify(args.team2)
    matchup_stem = f"{team1_slug}_vs_{team2_slug}_{args.season}"
    brief_base = _brief_base_name(team1_slug, team2_slug, args.season, args.week)

    markdown = output_dir / f"{brief_base}.md" if args.format in {"markdown", "both"} else None
    html = output_dir / f"{brief_base}.html" if args.format in {"html", "both"} else None

    return OperatorPaths(
        output_dir=output_dir,
        bundle=args.bundle.resolve(),
        cfbstats_snapshot=(args.cfbstats_snapshot or _default_snapshot_path(args.season)).resolve(),
        cfbstats_verification_report=(
            args.cfbstats_verification_report or _default_verification_path(args.season)
        ).resolve(),
        enrichment_file=(args.enrichment_file or output_dir / f"{matchup_stem}_enrichment.json").resolve(),
        preflight_json=(args.preflight_json or output_dir / f"{matchup_stem}_preflight.json").resolve(),
        preflight_md=(args.preflight_md or output_dir / f"{matchup_stem}_preflight.md").resolve(),
        summary_json=(args.summary_json or output_dir / f"{matchup_stem}_operator_summary.json").resolve(),
        markdown=markdown.resolve() if markdown else None,
        html=html.resolve() if html else None,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def refresh_enrichment(args: argparse.Namespace, paths: OperatorPaths) -> dict[str, Any] | None:
    if args.no_enrichment:
        return None

    if args.refresh_enrichment:
        team_specs = [
            {"slug": slugify(args.team1), "display_name": args.team1},
            {"slug": slugify(args.team2), "display_name": args.team2},
        ]
        existing = load_enrichment_file(paths.enrichment_file)
        refreshed = build_enrichment_payload(team_specs)
        merged = merge_enrichment_payload(existing, refreshed)
        payload = validate_enrichment_payload(merged, [spec["slug"] for spec in team_specs])
        write_enrichment_file(paths.enrichment_file, payload)
        print(f"[ok] Enrichment -> {paths.enrichment_file}", file=sys.stderr)
        return payload

    return _load_json(paths.enrichment_file)


def build_render_command(args: argparse.Namespace, paths: OperatorPaths) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "scripts.game_prep_brief",
        args.team1,
        args.team2,
        "--season",
        str(args.season),
        "--format",
        args.format,
        "--output-dir",
        str(paths.output_dir),
        "--last-n",
        str(args.last_n),
        "--xml-bundle",
        str(paths.bundle),
        "--cfbstats-snapshot",
        str(paths.cfbstats_snapshot),
        "--cfbstats-verification-report",
        str(paths.cfbstats_verification_report),
    ]
    if args.week:
        command.extend(["--week", str(args.week)])
    if args.no_enrichment:
        command.append("--no-enrichment")
    else:
        command.extend(["--enrichment-file", str(paths.enrichment_file)])
    if args.legacy_page_breaks:
        command.append("--legacy-page-breaks")
    if args.no_alerts:
        command.append("--no-alerts")
    return command


def run_render_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _build_summary(
    *,
    args: argparse.Namespace,
    paths: OperatorPaths,
    preflight: dict[str, Any],
    render_result: subprocess.CompletedProcess[str] | None,
    render_command: list[str] | None,
) -> dict[str, Any]:
    render_status = "skipped"
    if render_result is not None:
        render_status = "passed" if render_result.returncode == 0 else "failed"

    ready = bool(preflight.get("summary", {}).get("ready")) and render_status in {"passed", "skipped"}
    if args.skip_render and preflight.get("summary", {}).get("ready"):
        status = "preflight_ready"
    elif ready:
        status = "ready"
    elif not preflight.get("summary", {}).get("ready"):
        status = "blocked"
    else:
        status = "render_failed"

    return {
        "meta": {
            "artifact": "selected_matchup_operator_summary",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "season": args.season,
        },
        "matchup": {
            "team1": args.team1,
            "team2": args.team2,
            "team1_slug": slugify(args.team1),
            "team2_slug": slugify(args.team2),
        },
        "status": status,
        "preflight": preflight.get("summary", {}),
        "render": {
            "status": render_status,
            "exit_code": render_result.returncode if render_result is not None else None,
            "command": render_command,
            "stderr": render_result.stderr.splitlines() if render_result and render_result.stderr else [],
        },
        "policy": {
            "require_expected_games": args.require_expected_games,
            "require_enrichment": not args.no_enrichment,
            "allow_blocked": args.allow_blocked,
        },
        "paths": {
            "bundle": str(paths.bundle),
            "cfbstats_snapshot": str(paths.cfbstats_snapshot),
            "cfbstats_verification_report": str(paths.cfbstats_verification_report),
            "enrichment_file": None if args.no_enrichment else str(paths.enrichment_file),
            "preflight_json": str(paths.preflight_json),
            "preflight_md": str(paths.preflight_md),
            "summary_json": str(paths.summary_json),
            "markdown": str(paths.markdown) if paths.markdown else None,
            "html": str(paths.html) if paths.html else None,
        },
    }


def run(args: argparse.Namespace) -> int:
    paths = resolve_paths(args)
    paths.output_dir.mkdir(parents=True, exist_ok=True)

    expected_games = _parse_keyed_values(args.expected_games)
    expected_conferences = _parse_keyed_values(args.expected_conference)
    team1 = TeamRequest(
        args.team1,
        slugify(args.team1),
        expected_games=_expected_games_for(args.team1, expected_games),
        expected_conference=_expected_conference_for(args.team1, expected_conferences),
    )
    team2 = TeamRequest(
        args.team2,
        slugify(args.team2),
        expected_games=_expected_games_for(args.team2, expected_games),
        expected_conference=_expected_conference_for(args.team2, expected_conferences),
    )

    enrichment = refresh_enrichment(args, paths)
    preflight = build_preflight_report(
        season=args.season,
        team1=team1,
        team2=team2,
        bundle=_load_json(paths.bundle),
        snapshot=_load_json(paths.cfbstats_snapshot),
        verification=_load_json(paths.cfbstats_verification_report),
        enrichment=enrichment,
        require_expected_games=args.require_expected_games,
        require_enrichment=not args.no_enrichment,
        artifact_paths={
            "bundle": str(paths.bundle),
            "cfbstats_snapshot": str(paths.cfbstats_snapshot),
            "cfbstats_verification_report": str(paths.cfbstats_verification_report),
            "enrichment_file": None if args.no_enrichment else str(paths.enrichment_file),
        },
    )
    _write_json(paths.preflight_json, preflight)
    _write_text(paths.preflight_md, render_preflight_markdown(preflight))
    print(f"[ok] Preflight JSON -> {paths.preflight_json}", file=sys.stderr)
    print(f"[ok] Preflight MD -> {paths.preflight_md}", file=sys.stderr)

    render_result: subprocess.CompletedProcess[str] | None = None
    render_command: list[str] | None = None
    preflight_ready = bool(preflight["summary"]["ready"])
    if args.skip_render:
        print("[skip] Brief render disabled by --skip-render", file=sys.stderr)
    elif preflight_ready or args.allow_blocked:
        render_command = build_render_command(args, paths)
        render_result = run_render_command(render_command)
        if render_result.stdout:
            print(render_result.stdout, end="")
        if render_result.stderr:
            print(render_result.stderr, end="", file=sys.stderr)
    else:
        print("[block] Preflight failed; render skipped. Use --allow-blocked to force render.", file=sys.stderr)

    summary = _build_summary(
        args=args,
        paths=paths,
        preflight=preflight,
        render_result=render_result,
        render_command=render_command,
    )
    _write_json(paths.summary_json, summary)
    print(f"[ok] Operator summary -> {paths.summary_json}", file=sys.stderr)

    if not preflight_ready and not args.allow_blocked:
        return 1
    if render_result is not None and render_result.returncode != 0:
        return render_result.returncode
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run selected-matchup preflight and brief rendering from existing artifacts."
    )
    parser.add_argument("team1")
    parser.add_argument("team2")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--week", type=int, default=None)
    parser.add_argument("--format", choices=["markdown", "html", "both"], default="both")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--last-n", type=int, default=3)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--cfbstats-snapshot", type=Path, default=None)
    parser.add_argument("--cfbstats-verification-report", type=Path, default=None)
    parser.add_argument("--enrichment-file", type=Path, default=None)
    parser.add_argument("--preflight-json", type=Path, default=None)
    parser.add_argument("--preflight-md", type=Path, default=None)
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument(
        "--expected-games",
        action="append",
        default=[],
        metavar="TEAM=COUNT",
        help="Expected completed games for a selected team. Repeat for each team.",
    )
    parser.add_argument(
        "--expected-conference",
        action="append",
        default=[],
        metavar="TEAM=CONFERENCE",
        help="Expected CFBStats conference scope. Repeat for each team.",
    )
    parser.add_argument(
        "--no-require-expected-games",
        dest="require_expected_games",
        action="store_false",
        help="Warn instead of failing when expected game counts are omitted.",
    )
    parser.set_defaults(require_expected_games=True)
    parser.add_argument(
        "--refresh-enrichment",
        action="store_true",
        help="Refresh the matchup enrichment artifact from yr-data-api before preflight.",
    )
    parser.add_argument("--no-enrichment", action="store_true", help="Disable enrichment checks and rendering input.")
    parser.add_argument("--skip-render", action="store_true", help="Run preflight and summary only.")
    parser.add_argument("--allow-blocked", action="store_true", help="Render even when preflight has fail checks.")
    parser.add_argument("--legacy-page-breaks", action="store_true")
    parser.add_argument("--no-alerts", action="store_true")
    return parser.parse_args()


def main() -> None:
    raise SystemExit(run(parse_args()))


if __name__ == "__main__":
    main()
