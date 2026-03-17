from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .supported_team_readiness import SUPPORTED_TEAMS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = Path("/tmp/bigten_nd_validation_sweep")
DEFAULT_REPORT_JSON = Path("docs/bigten-nd-validation-sweep.json")
DEFAULT_REPORT_MD = Path("docs/bigten-nd-validation-sweep.md")

SUPPORTED_SWEEP_MATCHUPS = (
    ("Illinois", "Indiana"),
    ("Iowa", "Wisconsin"),
    ("Maryland", "Rutgers"),
    ("Michigan", "Michigan State"),
    ("Minnesota", "Nebraska"),
    ("Northwestern", "Illinois"),
    ("Notre Dame", "Purdue"),
    ("Ohio State", "Penn State"),
    ("Oregon", "Washington"),
    ("UCLA", "USC"),
)

TEAM_NAME_TO_SLUG = {team["name"]: team["slug"] for team in SUPPORTED_TEAMS}
TEAM_SLUG_TO_NAME = {team["slug"]: team["name"] for team in SUPPORTED_TEAMS}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def stable_unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def find_python_bin_dir() -> Path | None:
    for parent in (ROOT, *ROOT.parents):
        candidate = parent / ".venv" / "bin"
        if (candidate / "python").exists():
            return candidate
    return None


def classify_warning(line: str) -> str:
    lowered = line.lower()
    if "missing enrichment artifact" in lowered or "artifact gap" in lowered:
        return "artifact_gap"
    if (
        "team data not found" in lowered
        or "no data found" in lowered
        or "missing team payload" in lowered
        or "missing team payload in xml bundle" in lowered
    ):
        return "artifact_gap"
    if (
        "yr-data-api fetch failed" in lowered
        or "failed to load" in lowered
        or "httperror" in lowered
        or "timeout" in lowered
        or "timed out" in lowered
        or "python 3.10+" in lowered
    ):
        return "infrastructure"
    if (
        "reconciliation mismatch" in lowered
        or "parity delta" in lowered
        or " residual " in f" {lowered} "
        or "mismatch" in lowered
        or "xml parity gaps detected" in lowered
        or "differ from xml" in lowered
    ):
        return "data_quality"
    return "other"


def warning_targets(line: str, matchup_slugs: tuple[str, str]) -> list[str]:
    lowered = line.lower()
    matches = []
    for slug in matchup_slugs:
        team_name = TEAM_SLUG_TO_NAME.get(slug, slug).lower()
        if team_name in lowered or slug in lowered:
            matches.append(slug)
    return matches or list(matchup_slugs)


def summarize_warning_status(kinds: set[str]) -> str:
    if not kinds:
        return "clean"
    if "artifact_gap" in kinds:
        return "artifact gap"
    if "infrastructure" in kinds:
        return "infrastructure"
    if "data_quality" in kinds:
        return "data quality"
    return "other"


def summarize_confidence(exit_codes: list[int], kinds: set[str]) -> str:
    if any(code != 0 for code in exit_codes):
        return "blocked"
    if "artifact_gap" in kinds or "infrastructure" in kinds:
        return "attention"
    if "data_quality" in kinds or "other" in kinds:
        return "caution"
    return "ready"


def summarize_enrichment(mode: str, warning_lines: list[str], exit_codes: list[int]) -> str:
    if mode == "no-enrichment":
        return "not checked"
    if any(code != 0 for code in exit_codes):
        return "blocked"
    if any("yr-data-api fetch failed" in line.lower() for line in warning_lines):
        return "provider warnings"
    return "validated"


def parse_output_paths(stderr_lines: list[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for line in stderr_lines:
        match = re.match(r"^\[ok\] (.+?) → (.+)$", line.strip())
        if not match:
            continue
        label = match.group(1).strip().lower().replace(" ", "_")
        paths[label] = match.group(2).strip()
    return paths


def collect_warning_lines(stderr_lines: list[str], outputs: dict[str, str], *, mode: str) -> list[str]:
    warning_lines = [line for line in stderr_lines if line.startswith("[warn]")]
    markdown_path = outputs.get("markdown")
    if not markdown_path:
        return warning_lines

    path = Path(markdown_path)
    if not path.exists():
        return warning_lines

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("⚠️"):
                if mode == "no-enrichment" and "PFF/API snapshot partial" in stripped:
                    continue
                banner = stripped[2:].strip()
                if banner.startswith("XML parity gaps detected:"):
                    payload = banner.removeprefix("XML parity gaps detected:").strip()
                    segments = [segment.strip() for segment in payload.split(";") if segment.strip()]
                    warning_lines.extend(f"[warn] {segment}" for segment in segments)
                else:
                    warning_lines.append(f"[warn] {banner}")
    except OSError:
        return stable_unique(warning_lines)

    return stable_unique(warning_lines)


def run_matchup(
    *,
    team1: str,
    team2: str,
    season: int,
    format: str,
    mode: str,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    command = [
        "./scripts/run-game-prep-brief.sh",
        team1,
        team2,
        "--season",
        str(season),
        "--format",
        format,
        "--output-dir",
        str(output_dir),
    ]
    if mode == "refresh-enrichment":
        command.append("--refresh-enrichment")
    elif mode == "no-enrichment":
        command.append("--no-enrichment")

    env = os.environ.copy()
    python_bin_dir = find_python_bin_dir()
    if python_bin_dir is not None:
        env["PATH"] = f"{python_bin_dir}:{env.get('PATH', '')}"

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stderr_lines = [line.strip() for line in (exc.stderr or "").splitlines() if line.strip()]
        stdout_lines = [line.strip() for line in (exc.stdout or "").splitlines() if line.strip()]
        warning_lines = [line for line in stderr_lines if line.startswith("[warn]")]
        warning_lines.append(
            f"[warn] Timeout after {timeout_seconds}s while generating {team1} vs {team2}"
        )
        return {
            "team1": team1,
            "team2": team2,
            "team1_slug": TEAM_NAME_TO_SLUG[team1],
            "team2_slug": TEAM_NAME_TO_SLUG[team2],
            "exit_code": 124,
            "classification": "failed_infrastructure",
            "warning_lines": warning_lines,
            "warning_kinds": ["infrastructure"],
            "stderr_lines": stderr_lines,
            "stdout_lines": stdout_lines,
            "outputs": parse_output_paths(stderr_lines),
            "command": command,
        }

    stderr_lines = [line.strip() for line in completed.stderr.splitlines() if line.strip()]
    stdout_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    outputs = parse_output_paths(stderr_lines)
    warning_lines = collect_warning_lines(stderr_lines, outputs, mode=mode)
    if completed.returncode != 0 and not warning_lines:
        warning_lines = [
            f"[warn] {line}" for line in stderr_lines if classify_warning(line) != "other"
        ]
    warning_kinds = sorted({classify_warning(line) for line in warning_lines})
    classification = "clean"
    if completed.returncode != 0:
        if "artifact_gap" in warning_kinds:
            classification = "failed_artifact_gap"
        elif "infrastructure" in warning_kinds:
            classification = "failed_infrastructure"
        else:
            classification = "failed_other"
    elif warning_kinds:
        if "artifact_gap" in warning_kinds:
            classification = "warning_artifact_gap"
        elif "infrastructure" in warning_kinds:
            classification = "warning_infrastructure"
        elif "data_quality" in warning_kinds:
            classification = "warning_data_quality"
        else:
            classification = "warning_other"

    return {
        "team1": team1,
        "team2": team2,
        "team1_slug": TEAM_NAME_TO_SLUG[team1],
        "team2_slug": TEAM_NAME_TO_SLUG[team2],
        "exit_code": completed.returncode,
        "classification": classification,
        "warning_lines": warning_lines,
        "warning_kinds": warning_kinds,
        "stderr_lines": stderr_lines,
        "stdout_lines": stdout_lines,
        "outputs": outputs,
        "command": command,
    }


def build_report(
    *,
    season: int,
    mode: str,
    format: str,
    output_dir: Path,
    matchup_results: list[dict[str, Any]],
) -> dict[str, Any]:
    classification_counts = Counter(result["classification"] for result in matchup_results)
    team_entries: dict[str, dict[str, Any]] = {
        team["slug"]: {
            "team_name": team["name"],
            "conference": team["conference"],
            "matchups": [],
            "warning_lines": [],
            "warning_kinds": set(),
            "exit_codes": [],
        }
        for team in SUPPORTED_TEAMS
    }

    for result in matchup_results:
        matchup_id = f"{result['team1_slug']}_vs_{result['team2_slug']}"
        matchup_slugs = (result["team1_slug"], result["team2_slug"])
        for slug in matchup_slugs:
            team_entries[slug]["matchups"].append(
                {
                    "matchup_id": matchup_id,
                    "opponent": TEAM_SLUG_TO_NAME[matchup_slugs[1] if slug == matchup_slugs[0] else matchup_slugs[0]],
                    "exit_code": result["exit_code"],
                    "classification": result["classification"],
                }
            )
            team_entries[slug]["exit_codes"].append(result["exit_code"])
            if result["exit_code"] != 0:
                team_entries[slug]["warning_kinds"].add(result["classification"])

        for warning in result["warning_lines"]:
            for slug in warning_targets(warning, matchup_slugs):
                if warning not in team_entries[slug]["warning_lines"]:
                    team_entries[slug]["warning_lines"].append(warning)
                team_entries[slug]["warning_kinds"].add(classify_warning(warning))

    normalized_teams: dict[str, Any] = {}
    for slug, entry in team_entries.items():
        warning_kinds = set(entry["warning_kinds"])
        warning_lines = list(entry["warning_lines"])
        exit_codes = list(entry["exit_codes"])
        data_quality_lines = [line for line in warning_lines if classify_warning(line) == "data_quality"]
        notes = ""
        if any(code != 0 for code in exit_codes):
            failed_classifications = sorted(
                {matchup["classification"] for matchup in entry["matchups"] if matchup["exit_code"] != 0}
            )
            notes = ", ".join(failed_classifications)
        elif data_quality_lines:
            notes = f"{len(data_quality_lines)} data-quality warning(s)"
        normalized_teams[slug] = {
            "team_name": entry["team_name"],
            "conference": entry["conference"],
            "warning_status": summarize_warning_status(warning_kinds),
            "enrichment_status": summarize_enrichment(mode, warning_lines, exit_codes),
            "confidence": summarize_confidence(exit_codes, warning_kinds),
            "notes": notes,
            "warning_kinds": sorted(warning_kinds),
            "warning_lines": warning_lines,
            "matchups": entry["matchups"],
        }

    return {
        "meta": {
            "artifact": "bigten_nd_validation_sweep",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "season": season,
            "mode": mode,
            "format": format,
            "output_dir": str(output_dir),
            "supported_team_count": len(SUPPORTED_TEAMS),
            "matchup_count": len(matchup_results),
        },
        "summary": {
            "matchups_passed": sum(1 for result in matchup_results if result["exit_code"] == 0),
            "matchups_failed": sum(1 for result in matchup_results if result["exit_code"] != 0),
            "classification_counts": dict(classification_counts),
        },
        "matchups": matchup_results,
        "teams": normalized_teams,
    }


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    summary = report["summary"]
    lines = [
        "# Big Ten + Notre Dame Validation Sweep",
        "",
        f"Generated: `{meta['generated_at']}`",
        f"Season: `{meta['season']}`",
        f"Mode: `{meta['mode']}`",
        f"Format: `{meta['format']}`",
        f"Output dir: `{meta['output_dir']}`",
        "",
        "## Summary",
        "",
        f"- Matchups passed: `{summary['matchups_passed']}`",
        f"- Matchups failed: `{summary['matchups_failed']}`",
    ]

    for classification, count in sorted(summary["classification_counts"].items()):
        lines.append(f"- {classification}: `{count}`")

    lines.extend(
        [
            "",
            "## Matchups",
            "",
            "| Matchup | Exit | Classification | Warning kinds | Output artifacts |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for matchup in report["matchups"]:
        outputs = ", ".join(sorted(matchup["outputs"].keys())) or "none"
        warning_kinds = ", ".join(matchup["warning_kinds"]) or "clean"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{matchup['team1']} vs {matchup['team2']}",
                    str(matchup["exit_code"]),
                    matchup["classification"],
                    warning_kinds,
                    outputs,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Team Summary",
            "",
            "| Team | Conf | Warnings | Enrichment | Confidence | Notes |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for slug, payload in sorted(report["teams"].items(), key=lambda item: item[1]["team_name"]):
        lines.append(
            "| "
            + " | ".join(
                [
                    payload["team_name"],
                    payload["conference"],
                    payload["warning_status"],
                    payload["enrichment_status"],
                    payload["confidence"],
                    payload["notes"],
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Warning Inventory",
            "",
        ]
    )
    all_warning_lines = []
    for payload in report["teams"].values():
        all_warning_lines.extend(payload["warning_lines"])
    if not all_warning_lines:
        lines.append("- No warnings recorded.")
    else:
        for warning in sorted(set(all_warning_lines)):
            lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Big Ten + Notre Dame validation sweep.")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--format", choices=["markdown", "html", "both"], default="markdown")
    parser.add_argument(
        "--mode",
        choices=["refresh-enrichment", "no-enrichment"],
        default="refresh-enrichment",
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-markdown", type=Path, default=DEFAULT_REPORT_MD)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    matchups = SUPPORTED_SWEEP_MATCHUPS[: args.limit] if args.limit else SUPPORTED_SWEEP_MATCHUPS
    results = [
        run_matchup(
            team1=team1,
            team2=team2,
            season=args.season,
            format=args.format,
            mode=args.mode,
            output_dir=args.output_dir,
            timeout_seconds=args.timeout_seconds,
        )
        for team1, team2 in matchups
    ]
    report = build_report(
        season=args.season,
        mode=args.mode,
        format=args.format,
        output_dir=args.output_dir,
        matchup_results=results,
    )

    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    args.report_markdown.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
