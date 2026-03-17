from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .published_artifacts import fetch_published_artifact_json, published_artifact_release_url


SUPPORTED_TEAMS = (
    {"slug": "illinois", "name": "Illinois", "conference": "Big Ten"},
    {"slug": "indiana", "name": "Indiana", "conference": "Big Ten"},
    {"slug": "iowa", "name": "Iowa", "conference": "Big Ten"},
    {"slug": "maryland", "name": "Maryland", "conference": "Big Ten"},
    {"slug": "michigan", "name": "Michigan", "conference": "Big Ten"},
    {"slug": "michigan-state", "name": "Michigan State", "conference": "Big Ten"},
    {"slug": "minnesota", "name": "Minnesota", "conference": "Big Ten"},
    {"slug": "nebraska", "name": "Nebraska", "conference": "Big Ten"},
    {"slug": "northwestern", "name": "Northwestern", "conference": "Big Ten"},
    {"slug": "notre-dame", "name": "Notre Dame", "conference": "Independent"},
    {"slug": "ohio-state", "name": "Ohio State", "conference": "Big Ten"},
    {"slug": "oregon", "name": "Oregon", "conference": "Big Ten"},
    {"slug": "penn-state", "name": "Penn State", "conference": "Big Ten"},
    {"slug": "purdue", "name": "Purdue", "conference": "Big Ten"},
    {"slug": "rutgers", "name": "Rutgers", "conference": "Big Ten"},
    {"slug": "ucla", "name": "UCLA", "conference": "Big Ten"},
    {"slug": "usc", "name": "USC", "conference": "Big Ten"},
    {"slug": "washington", "name": "Washington", "conference": "Big Ten"},
    {"slug": "wisconsin", "name": "Wisconsin", "conference": "Big Ten"},
)

PENDING_SWEEP = "pending sweep"
DEFAULT_SWEEP_REPORT = Path("docs/bigten-nd-validation-sweep.json")


@dataclass(frozen=True)
class TeamReadinessRow:
    conference: str
    name: str
    slug: str
    bundle: str
    snapshot: str
    verification: str
    enrichment: str
    warnings: str
    confidence: str
    notes: str


def _norm(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.lower().replace("&", " and ")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in cleaned).split())


def _slug_variants(team_slug: str, team_name: str) -> set[str]:
    variants = {
        team_slug.strip().lower(),
        _norm(team_slug),
        _norm(team_name),
    }
    name_slug = team_name.strip().lower().replace("&", " and ").replace(" ", "-")
    variants.add(name_slug)
    if team_slug == "notre-dame":
        variants.update({"notredame", "notre dame", "nd"})
    return {variant for variant in variants if variant}


def _read_json_url(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "pbp-analysis-supported-team-readiness"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return payload


def _load_artifact(source: str | None, *, logical_name: str, season: int) -> dict[str, Any]:
    if not source:
        return fetch_published_artifact_json(logical_name, season)
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return _read_json_url(source)
    path = Path(source).expanduser()
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {path}")
    return payload


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def triage_warning_status(status: str) -> str:
    if status == "artifact gap":
        return "must-fix"
    if status == "data quality":
        return "known gap"
    return status


def _team_present(artifact: dict[str, Any], team_slug: str, team_name: str) -> bool:
    teams = _artifact_team_map(artifact)
    if not isinstance(teams, dict):
        return False

    variants = _slug_variants(team_slug, team_name)
    for key, payload in teams.items():
        if not isinstance(key, str):
            continue
        payload_candidates = {
            _norm(key),
            _norm(payload.get("team_slug")) if isinstance(payload, dict) else "",
            _norm(payload.get("team_name")) if isinstance(payload, dict) else "",
            _norm(payload.get("name")) if isinstance(payload, dict) else "",
        }
        payload_candidates.discard("")
        if variants & payload_candidates:
            return True
    return False


def _artifact_team_map(artifact: dict[str, Any]) -> dict[str, Any]:
    teams = artifact.get("teams")
    if not isinstance(teams, dict):
        return {}
    nested_teams = teams.get("teams")
    nested_meta = teams.get("_meta")
    if isinstance(nested_teams, dict) and isinstance(nested_meta, dict):
        return nested_teams
    return teams


def build_readiness_rows(
    *,
    season: int,
    bundle: dict[str, Any],
    snapshot: dict[str, Any],
    verification: dict[str, Any],
    sweep_report: dict[str, Any] | None = None,
) -> list[TeamReadinessRow]:
    sweep_teams = sweep_report.get("teams", {}) if isinstance(sweep_report, dict) else {}
    rows: list[TeamReadinessRow] = []
    for team in SUPPORTED_TEAMS:
        bundle_status = "present" if _team_present(bundle, team["slug"], team["name"]) else "missing"
        snapshot_status = "present" if _team_present(snapshot, team["slug"], team["name"]) else "missing"
        verification_status = "present" if _team_present(verification, team["slug"], team["name"]) else "missing"
        sweep_payload = sweep_teams.get(team["slug"], {}) if isinstance(sweep_teams, dict) else {}
        if not isinstance(sweep_payload, dict):
            sweep_payload = {}
        enrichment_status = sweep_payload.get("enrichment_status", PENDING_SWEEP)
        warning_status = triage_warning_status(sweep_payload.get("warning_status", PENDING_SWEEP))
        confidence = sweep_payload.get("confidence", PENDING_SWEEP)
        notes_parts: list[str] = []
        if "missing" in {bundle_status, snapshot_status, verification_status}:
            notes_parts.append("artifact gap")
            confidence = "attention"
        sweep_notes = sweep_payload.get("notes")
        if isinstance(sweep_notes, str) and sweep_notes.strip():
            notes_parts.append(sweep_notes.strip())
        rows.append(
            TeamReadinessRow(
                conference=team["conference"],
                name=team["name"],
                slug=team["slug"],
                bundle=bundle_status,
                snapshot=snapshot_status,
                verification=verification_status,
                enrichment=enrichment_status,
                warnings=warning_status,
                confidence=confidence,
                notes=", ".join(notes_parts) if notes_parts else "",
            )
        )
    return rows


def render_markdown(
    *,
    season: int,
    rows: list[TeamReadinessRow],
    bundle_source: str | None,
    snapshot_source: str | None,
    verification_source: str | None,
    findings: list[str] | None = None,
) -> str:
    bundle_present = sum(1 for row in rows if row.bundle == "present")
    snapshot_present = sum(1 for row in rows if row.snapshot == "present")
    verification_present = sum(1 for row in rows if row.verification == "present")
    total = len(rows)

    lines = [
        "# Big Ten + Notre Dame Readiness Matrix",
        "",
        f"Season: `{season}`",
        "",
        "This matrix is the operator-facing readiness view for the currently supported production set:",
        "- Big Ten teams",
        "- Notre Dame",
        "",
        "Artifact coverage is auto-derived from the current production artifacts. Enrichment, warning triage, and confidence merge current artifact state with the latest supported-set validation sweep when one is available.",
        "",
        "Current operator warning policy is documented in [bigten-nd-warning-triage.md](./bigten-nd-warning-triage.md).",
        "",
        "## Sources",
        "",
        f"- Bundle: `{bundle_source or published_artifact_release_url(season)}`",
        f"- CFBStats snapshot: `{snapshot_source or published_artifact_release_url(season)}`",
        f"- Verification report: `{verification_source or published_artifact_release_url(season)}`",
        "",
        "## Coverage Summary",
        "",
        f"- Bundle coverage: `{bundle_present}/{total}` present",
        f"- Snapshot coverage: `{snapshot_present}/{total}` present",
        f"- Verification coverage: `{verification_present}/{total}` present",
    ]

    if findings:
        lines.extend(
            [
                "",
                "## Current Flagged Gaps",
                "",
                *[f"- {finding}" for finding in findings],
            ]
        )

    lines.extend(
        [
        "",
        "## Matrix",
        "",
        "| Team | Conf | Bundle | Snapshot | Verification | Enrichment | Warning triage | Confidence | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.name,
                    row.conference,
                    row.bundle,
                    row.snapshot,
                    row.verification,
                    row.enrichment,
                    row.warnings,
                    row.confidence,
                    row.notes or "",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `present` means the team resolves from the current artifact payload.",
            "- `missing` means the team could not be found in that artifact and should be treated as a production gap.",
            "- `pending sweep` means the supported-set validation sweep has not been recorded for that dimension yet.",
            "- `not checked` means the current sweep intentionally skipped enrichment validation.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_findings(
    *,
    rows: list[TeamReadinessRow],
    bundle: dict[str, Any],
    snapshot: dict[str, Any],
    verification: dict[str, Any],
    sweep_report: dict[str, Any] | None = None,
) -> list[str]:
    findings: list[str] = []
    missing_bundle = [row.name for row in rows if row.bundle == "missing"]
    missing_snapshot = [row.name for row in rows if row.snapshot == "missing"]
    missing_verification = [row.name for row in rows if row.verification == "missing"]

    if missing_bundle:
        findings.append(f"Bundle artifact is missing supported teams: {', '.join(missing_bundle)}.")
    if missing_snapshot:
        findings.append(f"Snapshot artifact is missing supported teams: {', '.join(missing_snapshot)}.")
    if missing_verification:
        findings.append(
            "Verification artifact is missing supported teams: "
            + ", ".join(missing_verification)
            + "."
        )

    verification_meta = verification.get("meta")
    if isinstance(verification_meta, dict):
        team_count = verification_meta.get("team_count")
        if isinstance(team_count, int) and team_count < len(rows):
            findings.append(
                f"Verification artifact meta reports only {team_count} team entries for the current published set."
            )

    snapshot_meta = snapshot.get("meta")
    if isinstance(snapshot_meta, dict):
        team_count = snapshot_meta.get("team_count")
        if isinstance(team_count, int) and team_count < len(rows):
            findings.append(
                f"Snapshot artifact meta reports only {team_count} team entries for the current published set."
            )

    bundle_meta = bundle.get("_meta")
    if isinstance(bundle_meta, dict):
        generated_at = bundle_meta.get("generated_at")
        if generated_at:
            findings.append(f"Bundle source was generated at {generated_at}.")

    if isinstance(sweep_report, dict):
        sweep_meta = sweep_report.get("meta")
        sweep_summary = sweep_report.get("summary")
        if isinstance(sweep_meta, dict) and isinstance(sweep_summary, dict):
            findings.append(
                "Latest supported-set sweep "
                f"({sweep_meta.get('mode', 'unknown mode')}) recorded "
                f"{sweep_summary.get('matchups_passed', 0)}/{sweep_meta.get('matchup_count', 0)} "
                "successful matchup runs."
            )

    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the Big Ten + Notre Dame readiness matrix.")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--bundle")
    parser.add_argument("--cfbstats-snapshot")
    parser.add_argument("--cfbstats-verification-report")
    parser.add_argument(
        "--sweep-report",
        type=Path,
        default=DEFAULT_SWEEP_REPORT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/bigten-nd-readiness-matrix.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = _load_artifact(args.bundle, logical_name="bundle", season=args.season)
    snapshot = _load_artifact(args.cfbstats_snapshot, logical_name="cfbstats_snapshot", season=args.season)
    verification = _load_artifact(
        args.cfbstats_verification_report,
        logical_name="cfbstats_verification_report",
        season=args.season,
    )
    sweep_report = _load_optional_json(args.sweep_report)

    rows = build_readiness_rows(
        season=args.season,
        bundle=bundle,
        snapshot=snapshot,
        verification=verification,
        sweep_report=sweep_report,
    )
    markdown = render_markdown(
        season=args.season,
        rows=rows,
        bundle_source=args.bundle,
        snapshot_source=args.cfbstats_snapshot,
        verification_source=args.cfbstats_verification_report,
        findings=build_findings(
            rows=rows,
            bundle=bundle,
            snapshot=snapshot,
            verification=verification,
            sweep_report=sweep_report,
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
