from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "config" / "team-readiness-2025.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "team-readiness-registry-report.md"

PASS = "pass"
WARNING = "warning"
FAIL = "fail"

READY_STATUSES = {"existing_supported"}
BLOCKING_STATUSES = {"blocked", "unknown", "onboarding", ""}
READY_DELIVERABLE_STATUSES = {"ready", "ready_with_warnings"}
BLOCKING_DELIVERABLE_MARKERS = ("blocked",)


@dataclass(frozen=True)
class RegistryCheck:
    status: str
    team_slug: str | None
    check: str
    message: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "team_slug": self.team_slug,
            "check": self.check,
            "message": self.message,
        }


def load_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected registry JSON object: {path}")
    return payload


def _is_production_ready(status: str) -> bool:
    return status.startswith("production_ready")


def _status_level(status: str) -> str:
    if _is_production_ready(status):
        return PASS
    if status in READY_STATUSES:
        return WARNING
    if status in BLOCKING_STATUSES:
        return FAIL
    return WARNING


def _deliverable_level(deliverable_status: str) -> str:
    lowered = deliverable_status.lower()
    if any(marker in lowered for marker in BLOCKING_DELIVERABLE_MARKERS):
        return FAIL
    if lowered in READY_DELIVERABLE_STATUSES:
        return PASS
    if not lowered:
        return FAIL
    return WARNING


def _has_note(payload: Any) -> bool:
    if isinstance(payload, list):
        return any(isinstance(item, str) and item.strip() for item in payload)
    if isinstance(payload, str):
        return bool(payload.strip())
    return False


def _check_required_string(team_slug: str, team: dict[str, Any], field: str) -> RegistryCheck:
    value = team.get(field)
    if isinstance(value, str) and value.strip():
        return RegistryCheck(PASS, team_slug, field, f"{field} is present.")
    return RegistryCheck(FAIL, team_slug, field, f"{field} is missing.")


def _check_status(team_slug: str, team: dict[str, Any]) -> list[RegistryCheck]:
    status = str(team.get("status") or "").strip()
    level = _status_level(status)
    if level == PASS:
        message = f"status is {status}."
    elif level == WARNING:
        message = f"status is {status or 'missing'}; delivery may require operator review."
    else:
        message = f"status is {status or 'missing'}; team is not deliverable."
    return [RegistryCheck(level, team_slug, "status", message)]


def _check_deliverable_status(team_slug: str, team: dict[str, Any]) -> list[RegistryCheck]:
    deliverable_status = str(team.get("deliverable_status") or "").strip()
    level = _deliverable_level(deliverable_status)
    if level == PASS:
        message = f"deliverable_status is {deliverable_status}."
    elif level == WARNING:
        message = f"deliverable_status is {deliverable_status}; operator review required."
    else:
        message = f"deliverable_status is {deliverable_status or 'missing'}; delivery is blocked."
    return [RegistryCheck(level, team_slug, "deliverable_status", message)]


def _check_statbroadcast(team_slug: str, team: dict[str, Any]) -> list[RegistryCheck]:
    checks: list[RegistryCheck] = []
    statbroadcast = team.get("statbroadcast")
    if not isinstance(statbroadcast, dict):
        return [RegistryCheck(FAIL, team_slug, "statbroadcast", "statbroadcast evidence is missing.")]

    status = str(statbroadcast.get("status") or "").strip().lower()
    checks.append(
        RegistryCheck(
            PASS if status in {"ready", "complete"} else FAIL,
            team_slug,
            "statbroadcast.status",
            f"statbroadcast.status is {status or 'missing'}.",
        )
    )

    expected = statbroadcast.get("expected_games")
    found = statbroadcast.get("found_games")
    if isinstance(expected, int) and isinstance(found, int):
        checks.append(
            RegistryCheck(
                PASS if expected == found else FAIL,
                team_slug,
                "statbroadcast.games",
                f"expected_games={expected}, found_games={found}.",
            )
        )
    else:
        checks.append(
            RegistryCheck(
                FAIL,
                team_slug,
                "statbroadcast.games",
                "expected_games and found_games must be numeric.",
            )
        )
    source = statbroadcast.get("source")
    checks.append(
        RegistryCheck(
            PASS if isinstance(source, str) and source.strip() else WARNING,
            team_slug,
            "statbroadcast.source",
            "statbroadcast source is documented." if isinstance(source, str) and source.strip() else "statbroadcast source is missing.",
        )
    )
    return checks


def _check_cfbstats(team_slug: str, team: dict[str, Any]) -> list[RegistryCheck]:
    checks: list[RegistryCheck] = []
    cfbstats = team.get("cfbstats")
    if not isinstance(cfbstats, dict):
        return [RegistryCheck(FAIL, team_slug, "cfbstats", "cfbstats evidence is missing.")]
    status = str(cfbstats.get("status") or "").strip().lower()
    checks.append(
        RegistryCheck(
            PASS if status in {"ready", "verified"} else FAIL,
            team_slug,
            "cfbstats.status",
            f"cfbstats.status is {status or 'missing'}.",
        )
    )
    conference_scope = cfbstats.get("conference_scope")
    checks.append(
        RegistryCheck(
            PASS if isinstance(conference_scope, str) and conference_scope.strip() else FAIL,
            team_slug,
            "cfbstats.conference_scope",
            f"cfbstats conference_scope is {conference_scope or 'missing'}.",
        )
    )
    checks.append(
        RegistryCheck(
            PASS if cfbstats.get("snapshot_present") is True else FAIL,
            team_slug,
            "cfbstats.snapshot_present",
            f"snapshot_present is {cfbstats.get('snapshot_present')}.",
        )
    )
    return checks


def _check_pff(team_slug: str, team: dict[str, Any]) -> list[RegistryCheck]:
    checks: list[RegistryCheck] = []
    pff = team.get("pff")
    if not isinstance(pff, dict):
        return [RegistryCheck(FAIL, team_slug, "pff", "pff evidence is missing.")]
    status = str(pff.get("status") or "").strip().lower()
    if status == "ready":
        level = PASS
    elif status == "partial":
        level = WARNING
    else:
        level = FAIL
    checks.append(RegistryCheck(level, team_slug, "pff.status", f"pff.status is {status or 'missing'}."))
    slug = pff.get("slug")
    checks.append(
        RegistryCheck(
            PASS if isinstance(slug, str) and slug.strip() else FAIL,
            team_slug,
            "pff.slug",
            "pff slug is present." if isinstance(slug, str) and slug.strip() else "pff slug is missing.",
        )
    )
    if status == "partial":
        checks.append(
            RegistryCheck(
                PASS if _has_note(pff.get("notes")) else WARNING,
                team_slug,
                "pff.notes",
                "partial PFF status has notes." if _has_note(pff.get("notes")) else "partial PFF status needs notes.",
            )
        )
    return checks


def _check_verification(team_slug: str, team: dict[str, Any]) -> list[RegistryCheck]:
    checks: list[RegistryCheck] = []
    verification = team.get("verification")
    if not isinstance(verification, dict):
        return [RegistryCheck(FAIL, team_slug, "verification", "verification evidence is missing.")]
    status = str(verification.get("status") or "").strip().lower()
    failures = verification.get("failures")
    warnings = verification.get("warnings")
    if isinstance(failures, int):
        failure_level = PASS if failures == 0 else FAIL
        checks.append(
            RegistryCheck(
                failure_level,
                team_slug,
                "verification.failures",
                f"verification failures={failures}.",
            )
        )
    else:
        checks.append(RegistryCheck(WARNING, team_slug, "verification.failures", "verification failures count is missing."))
    if warnings not in (None, 0) and not _has_note(verification.get("notes")):
        checks.append(RegistryCheck(WARNING, team_slug, "verification.notes", "warning verification status needs notes."))
    checks.append(
        RegistryCheck(
            PASS if status in {"ready", "warning", "passed_with_warnings"} else WARNING,
            team_slug,
            "verification.status",
            f"verification.status is {status or 'missing'}.",
        )
    )
    return checks


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    checks: list[RegistryCheck] = []
    teams = registry.get("teams")
    if not isinstance(teams, dict) or not teams:
        checks.append(RegistryCheck(FAIL, None, "teams", "registry must contain at least one team."))
    else:
        for team_slug, team in sorted(teams.items()):
            if not isinstance(team_slug, str) or not isinstance(team, dict):
                checks.append(RegistryCheck(FAIL, None, "team_entry", f"invalid team entry: {team_slug!r}"))
                continue
            checks.append(_check_required_string(team_slug, team, "display_name"))
            checks.append(_check_required_string(team_slug, team, "conference"))
            checks.extend(_check_status(team_slug, team))
            checks.extend(_check_deliverable_status(team_slug, team))
            checks.extend(_check_statbroadcast(team_slug, team))
            checks.extend(_check_cfbstats(team_slug, team))
            checks.extend(_check_pff(team_slug, team))
            checks.extend(_check_verification(team_slug, team))
            if _status_level(str(team.get("status") or "").strip()) != PASS and not _has_note(team.get("notes")):
                checks.append(RegistryCheck(WARNING, team_slug, "notes", "non-production-ready status should include notes."))

    status_counts = {
        PASS: sum(1 for check in checks if check.status == PASS),
        WARNING: sum(1 for check in checks if check.status == WARNING),
        FAIL: sum(1 for check in checks if check.status == FAIL),
    }
    return {
        "summary": {
            "ready": status_counts[FAIL] == 0,
            "status": "ready" if status_counts[FAIL] == 0 else "blocked",
            "status_counts": status_counts,
            "team_count": len(teams) if isinstance(teams, dict) else 0,
        },
        "checks": [check.to_dict() for check in checks],
    }


def render_markdown(report: dict[str, Any], *, registry_path: Path) -> str:
    summary = report["summary"]
    lines = [
        "# Team Readiness Registry Report",
        "",
        f"Registry: `{registry_path}`",
        f"Status: `{summary['status']}`",
        "",
        "## Summary",
        "",
        f"- Teams: `{summary['team_count']}`",
        f"- Pass: `{summary['status_counts'][PASS]}`",
        f"- Warning: `{summary['status_counts'][WARNING]}`",
        f"- Fail: `{summary['status_counts'][FAIL]}`",
        "",
        "## Findings",
        "",
        "| Status | Team | Check | Message |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        if check["status"] == PASS:
            continue
        message = str(check["message"]).replace("|", "\\|")
        lines.append(f"| {check['status']} | {check.get('team_slug') or ''} | {check['check']} | {message} |")
    if lines[-1] == "| --- | --- | --- | --- |":
        lines.append("| pass |  | registry | No warning or fail findings. |")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the team readiness registry.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--no-markdown", action="store_true")
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry_path = args.registry.resolve()
    report = validate_registry(load_registry(registry_path))

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.no_markdown:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(render_markdown(report, registry_path=registry_path), encoding="utf-8")

    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    if report["summary"]["status_counts"][FAIL] > 0:
        raise SystemExit(1)
    if args.fail_on_warning and report["summary"]["status_counts"][WARNING] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
