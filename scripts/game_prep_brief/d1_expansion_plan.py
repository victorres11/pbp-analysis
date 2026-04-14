from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .loaders import slugify
from .selected_matchup import find_readiness_entry


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = ROOT / "config" / "d1-matchup-expansion-2025.json"
DEFAULT_REGISTRY = ROOT / "config" / "team-readiness-2025.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "d1-matchup-expansion-report.md"

PASS = "pass"
WARNING = "warning"
FAIL = "fail"

MATCHUP_STATUSES = {"complete", "next", "planned", "deferred"}
READY_DELIVERY_STATUSES = {"ready", "ready_with_warnings"}
REQUIRED_COMPLETE_MAPS = ("expected_games", "expected_conference")


@dataclass(frozen=True)
class ExpansionCheck:
    status: str
    wave_id: str | None
    matchup_id: str | None
    team: str | None
    check: str
    message: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "wave_id": self.wave_id,
            "matchup_id": self.matchup_id,
            "team": self.team,
            "check": self.check,
            "message": self.message,
        }


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _team_names(matchup: dict[str, Any]) -> list[str]:
    teams = matchup.get("teams")
    if isinstance(teams, list):
        names = [team for team in teams if isinstance(team, str) and team.strip()]
        if names:
            return names
    names = []
    for field in ("team1", "team2"):
        value = matchup.get(field)
        if isinstance(value, str) and value.strip():
            names.append(value)
    return names


def _expected_value(mapping: dict[str, Any], team_name: str) -> Any:
    variants = {team_name, slugify(team_name)}
    for key, value in mapping.items():
        if not isinstance(key, str):
            continue
        if key in variants or slugify(key) in variants:
            return value
    return None


def _readiness_status(entry: dict[str, Any]) -> str:
    return str(entry.get("status") or "").strip()


def _readiness_level(entry: dict[str, Any], *, strict: bool) -> tuple[str, str]:
    status = _readiness_status(entry)
    deliverable_status = str(entry.get("deliverable_status") or "").strip().lower()
    if "blocked" in deliverable_status:
        return FAIL, f"deliverable_status is {deliverable_status}."
    if status.startswith("production_ready") and deliverable_status in READY_DELIVERY_STATUSES:
        return PASS, f"readiness status is {status}."
    if status.startswith("production_ready"):
        return WARNING, f"readiness status is {status}, but deliverable_status is {deliverable_status or 'missing'}."
    if status == "existing_supported":
        return WARNING, "team is existing-supported, but not fully production-ready in the registry."
    if strict:
        return FAIL, f"readiness status is {status or 'missing'}."
    return WARNING, f"team still needs production-ready registry evidence; current status is {status or 'missing'}."


def _check_complete_expectations(
    *,
    wave_id: str,
    matchup_id: str,
    matchup: dict[str, Any],
    team_name: str,
    entry: dict[str, Any],
) -> list[ExpansionCheck]:
    checks: list[ExpansionCheck] = []
    expected_games = _as_dict(matchup.get("expected_games"))
    expected_conference = _as_dict(matchup.get("expected_conference"))

    expected_game_count = _expected_value(expected_games, team_name)
    registry_games = _as_dict(entry.get("statbroadcast")).get("expected_games")
    if expected_game_count is None:
        checks.append(
            ExpansionCheck(FAIL, wave_id, matchup_id, team_name, "expected_games", "complete matchup is missing expected games.")
        )
    elif registry_games == expected_game_count:
        checks.append(
            ExpansionCheck(PASS, wave_id, matchup_id, team_name, "expected_games", f"expected games match registry ({registry_games}).")
        )
    else:
        checks.append(
            ExpansionCheck(
                FAIL,
                wave_id,
                matchup_id,
                team_name,
                "expected_games",
                f"plan expected {expected_game_count}; registry expected {registry_games}.",
            )
        )

    expected_scope = _expected_value(expected_conference, team_name)
    registry_scope = _as_dict(entry.get("cfbstats")).get("conference_scope")
    if expected_scope is None:
        checks.append(
            ExpansionCheck(
                FAIL,
                wave_id,
                matchup_id,
                team_name,
                "expected_conference",
                "complete matchup is missing expected CFBStats conference scope.",
            )
        )
    elif registry_scope == expected_scope:
        checks.append(
            ExpansionCheck(
                PASS,
                wave_id,
                matchup_id,
                team_name,
                "expected_conference",
                f"expected conference scope matches registry ({registry_scope}).",
            )
        )
    else:
        checks.append(
            ExpansionCheck(
                FAIL,
                wave_id,
                matchup_id,
                team_name,
                "expected_conference",
                f"plan expected {expected_scope}; registry has {registry_scope}.",
            )
        )
    return checks


def validate_expansion_plan(
    plan: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    checks: list[ExpansionCheck] = []
    matchups_summary: list[dict[str, Any]] = []
    seen_teams: set[str] = set()

    season = plan.get("season")
    if not isinstance(season, int):
        checks.append(ExpansionCheck(FAIL, None, None, None, "season", "plan season must be numeric."))

    waves = _as_list(plan.get("waves"))
    if not waves:
        checks.append(ExpansionCheck(FAIL, None, None, None, "waves", "plan must include at least one wave."))

    for wave in waves:
        if not isinstance(wave, dict):
            checks.append(ExpansionCheck(FAIL, None, None, None, "wave", "wave entries must be objects."))
            continue
        wave_id = str(wave.get("id") or "").strip()
        if not wave_id:
            wave_id = "missing-wave-id"
            checks.append(ExpansionCheck(FAIL, None, None, None, "wave.id", "wave id is missing."))

        matchups = _as_list(wave.get("matchups"))
        if not matchups:
            checks.append(ExpansionCheck(FAIL, wave_id, None, None, "matchups", "wave must include matchups."))
            continue

        for matchup in matchups:
            if not isinstance(matchup, dict):
                checks.append(ExpansionCheck(FAIL, wave_id, None, None, "matchup", "matchup entries must be objects."))
                continue

            matchup_id = str(matchup.get("id") or "").strip()
            if not matchup_id:
                matchup_id = "missing-matchup-id"
                checks.append(ExpansionCheck(FAIL, wave_id, None, None, "matchup.id", "matchup id is missing."))

            status = str(matchup.get("status") or "").strip()
            if status not in MATCHUP_STATUSES:
                checks.append(
                    ExpansionCheck(
                        FAIL,
                        wave_id,
                        matchup_id,
                        None,
                        "matchup.status",
                        f"matchup status must be one of {sorted(MATCHUP_STATUSES)}.",
                    )
                )
            else:
                checks.append(ExpansionCheck(PASS, wave_id, matchup_id, None, "matchup.status", f"matchup status is {status}."))

            strict = status == "complete"
            team_names = _team_names(matchup)
            if len(team_names) != 2:
                checks.append(ExpansionCheck(FAIL, wave_id, matchup_id, None, "teams", "matchup must include exactly two teams."))

            coverage = [item for item in _as_list(matchup.get("coverage")) if isinstance(item, str) and item.strip()]
            if coverage:
                checks.append(ExpansionCheck(PASS, wave_id, matchup_id, None, "coverage", "coverage tags are present."))
            else:
                checks.append(ExpansionCheck(WARNING, wave_id, matchup_id, None, "coverage", "coverage tags are missing."))

            evidence = [item for item in _as_list(matchup.get("evidence")) if isinstance(item, str) and item.strip()]
            if strict and not evidence:
                checks.append(ExpansionCheck(FAIL, wave_id, matchup_id, None, "evidence", "complete matchup needs evidence notes."))
            elif evidence:
                checks.append(ExpansionCheck(PASS, wave_id, matchup_id, None, "evidence", "evidence notes are present."))

            for field in REQUIRED_COMPLETE_MAPS:
                mapping = matchup.get(field)
                if strict and not isinstance(mapping, dict):
                    checks.append(ExpansionCheck(FAIL, wave_id, matchup_id, None, field, f"complete matchup needs {field}."))

            missing_ready = False
            blocked = False
            for team_name in team_names:
                seen_teams.add(slugify(team_name))
                if registry is None:
                    level = FAIL if strict else WARNING
                    checks.append(
                        ExpansionCheck(
                            level,
                            wave_id,
                            matchup_id,
                            team_name,
                            "readiness_registry",
                            f"readiness registry is unavailable: {registry_path}",
                        )
                    )
                    missing_ready = True
                    continue

                match = find_readiness_entry(registry, team_name)
                if match is None:
                    level = FAIL if strict else WARNING
                    checks.append(
                        ExpansionCheck(
                            level,
                            wave_id,
                            matchup_id,
                            team_name,
                            "readiness_entry",
                            "team is missing from readiness registry.",
                        )
                    )
                    missing_ready = True
                    if strict:
                        blocked = True
                    continue

                entry_key, entry = match
                level, message = _readiness_level(entry, strict=strict)
                checks.append(ExpansionCheck(level, wave_id, matchup_id, team_name, "readiness_status", message))
                if level == FAIL:
                    blocked = True
                elif level != PASS:
                    missing_ready = True

                if strict:
                    checks.extend(
                        _check_complete_expectations(
                            wave_id=wave_id,
                            matchup_id=matchup_id,
                            matchup=matchup,
                            team_name=team_name,
                            entry=entry,
                        )
                    )
                else:
                    checks.append(
                        ExpansionCheck(
                            PASS,
                            wave_id,
                            matchup_id,
                            team_name,
                            "readiness_entry",
                            f"registry matched {entry_key}.",
                        )
                    )

            if blocked:
                readiness = "blocked"
            elif missing_ready:
                readiness = "needs_onboarding"
            else:
                readiness = "ready"
            matchups_summary.append(
                {
                    "wave_id": wave_id,
                    "id": matchup_id,
                    "status": status,
                    "teams": team_names,
                    "coverage": coverage,
                    "readiness": readiness,
                }
            )

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
            "wave_count": len(waves),
            "matchup_count": len(matchups_summary),
            "team_count": len(seen_teams),
        },
        "matchups": matchups_summary,
        "checks": [check.to_dict() for check in checks],
    }


def _display_path(path: Path | None) -> str:
    if path is None:
        return "not provided"
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def render_markdown(report: dict[str, Any], *, plan_path: Path, registry_path: Path | None) -> str:
    summary = report["summary"]
    lines = [
        "# D1 Matchup Expansion Report",
        "",
        f"Plan: `{_display_path(plan_path)}`",
        f"Readiness registry: `{_display_path(registry_path)}`",
        f"Status: `{summary['status']}`",
        "",
        "## Summary",
        "",
        f"- Waves: `{summary['wave_count']}`",
        f"- Matchups: `{summary['matchup_count']}`",
        f"- Teams touched: `{summary['team_count']}`",
        f"- Pass: `{summary['status_counts'][PASS]}`",
        f"- Warning: `{summary['status_counts'][WARNING]}`",
        f"- Fail: `{summary['status_counts'][FAIL]}`",
        "",
        "## Matchups",
        "",
        "| Wave | Matchup | Status | Readiness | Teams | Coverage |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for matchup in report["matchups"]:
        teams = " vs ".join(matchup["teams"])
        coverage = ", ".join(matchup["coverage"])
        lines.append(
            f"| {matchup['wave_id']} | {matchup['id']} | {matchup['status']} | {matchup['readiness']} | {teams} | {coverage} |"
        )

    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| Status | Wave | Matchup | Team | Check | Message |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    finding_count = 0
    for check in report["checks"]:
        if check["status"] == PASS:
            continue
        finding_count += 1
        message = str(check["message"]).replace("|", "\\|")
        lines.append(
            f"| {check['status']} | {check.get('wave_id') or ''} | {check.get('matchup_id') or ''} | "
            f"{check.get('team') or ''} | {check['check']} | {message} |"
        )
    if finding_count == 0:
        lines.append("| pass |  |  |  | expansion_plan | No warning or fail findings. |")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the D1 matchup expansion plan.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--readiness-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--no-markdown", action="store_true")
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan_path = args.plan.resolve()
    registry_path = args.readiness_registry.resolve() if args.readiness_registry else None
    registry = load_json(registry_path) if registry_path and registry_path.exists() else None
    report = validate_expansion_plan(load_json(plan_path), registry=registry, registry_path=registry_path)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.no_markdown:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(
            render_markdown(report, plan_path=plan_path, registry_path=registry_path),
            encoding="utf-8",
        )

    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    if report["summary"]["status_counts"][FAIL] > 0:
        raise SystemExit(1)
    if args.fail_on_warning and report["summary"]["status_counts"][WARNING] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
