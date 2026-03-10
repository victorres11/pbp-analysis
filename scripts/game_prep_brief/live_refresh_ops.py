from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ALERT_ISSUE_TITLE = "Brief Live Refresh Alerts"

DEFAULT_RUN_CONFIG = {
    "team1": "Washington",
    "team2": "Ohio State",
    "season": "2025",
    "last_n": "3",
    "brief_format": "markdown",
    "run_tests": "false",
    "strict_verification": "true",
    "include_enrichment": "true",
}


def _normalize_bool_string(value: str | None, default: str) -> str:
    if value is None or value == "":
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return "true"
    if lowered in {"0", "false", "no", "off"}:
        return "false"
    return default


def resolve_run_config(
    *,
    event_name: str,
    input_values: dict[str, str | None],
    variable_values: dict[str, str | None],
) -> dict[str, str]:
    resolved: dict[str, str] = {}

    for key, default in DEFAULT_RUN_CONFIG.items():
        if event_name == "schedule":
            source_value = variable_values.get(key)
        else:
            source_value = input_values.get(key)

        if key in {"run_tests", "strict_verification", "include_enrichment"}:
            resolved[key] = _normalize_bool_string(source_value, default)
        else:
            resolved[key] = (source_value or default).strip() or default

    return resolved


def build_alert_payload(
    *,
    event_name: str,
    workflow_conclusion: str,
    run_url: str,
    summary: dict[str, Any] | None,
    release_url: str | None,
) -> dict[str, Any]:
    if event_name != "schedule":
        return {"should_notify": False}

    if summary is None:
        body = "\n".join(
            [
                "## Scheduled live-refresh alert",
                "",
                "- Reason: `missing_pipeline_summary`",
                f"- Workflow conclusion: `{workflow_conclusion}`",
                f"- Workflow run: {run_url}",
                "",
                "The workflow completed without a readable pipeline summary JSON, so the scheduled run should be treated as failed.",
            ]
        )
        return {
            "should_notify": True,
            "body": body + "\n",
        }

    artifact_contract = summary.get("artifact_contract") or {}
    validation = summary.get("validation") or {}
    run_state = summary.get("run_state") or {}
    observability = summary.get("observability") or {}
    warnings = summary.get("warnings") or []

    publishable = bool(artifact_contract.get("publishable"))
    verification_fail_count = validation.get("verification_fail_count", 0)
    published_complete = bool(artifact_contract.get("published_set_complete"))

    should_notify = (
        workflow_conclusion != "success"
        or not publishable
        or verification_fail_count not in (0, None)
        or not published_complete
    )
    if not should_notify:
        return {"should_notify": False}

    reason_ids: list[str] = []
    if workflow_conclusion != "success":
        reason_ids.append("workflow_failure")
    if not publishable:
        reason_ids.append("non_publishable")
    if verification_fail_count not in (0, None):
        reason_ids.append("verification_fail_metrics")
    if not published_complete:
        reason_ids.append("published_artifacts_incomplete")

    teams = ", ".join(summary.get("teams") or [])
    slow_stages = ", ".join(observability.get("slow_stages") or []) or "none"
    interrupted_stages = ", ".join(run_state.get("interrupted_stages") or []) or "none"
    non_publishable_reasons = ", ".join(artifact_contract.get("non_publishable_reasons") or []) or "none"

    lines = [
        "## Scheduled live-refresh alert",
        "",
        f"- Reason ids: `{', '.join(reason_ids)}`",
        f"- Workflow conclusion: `{workflow_conclusion}`",
        f"- Workflow run: {run_url}",
        f"- Season: `{summary.get('season')}`",
        f"- Teams: `{teams}`",
        f"- Artifact set id: `{artifact_contract.get('artifact_set_id')}`",
        f"- Publishable: `{publishable}`",
        f"- Published set complete: `{published_complete}`",
        f"- Non-publishable reasons: `{non_publishable_reasons}`",
        f"- Verification fails: `{validation.get('verification_fail_count')}`",
        f"- Verification warnings: `{validation.get('verification_warning_count')}`",
        f"- Smoke brief passed: `{validation.get('smoke_brief_passed')}`",
        f"- Enrichment artifact status: `{(summary.get('enrichment_contract') or {}).get('artifact_status')}`",
        f"- Interrupted stages: `{interrupted_stages}`",
        f"- Slow stages: `{slow_stages}`",
    ]
    if release_url:
        lines.append(f"- Published release URL: {release_url}")
    if warnings:
        lines.extend(
            [
                "",
                "### Pipeline warnings",
                "",
                *[f"- {warning}" for warning in warnings],
            ]
        )

    return {
        "should_notify": True,
        "body": "\n".join(lines) + "\n",
    }


def _write_github_output(outputs: dict[str, str]) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return

    with open(github_output, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def _resolve_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--input-team1")
    parser.add_argument("--input-team2")
    parser.add_argument("--input-season")
    parser.add_argument("--input-last-n")
    parser.add_argument("--input-brief-format")
    parser.add_argument("--input-run-tests")
    parser.add_argument("--input-strict-verification")
    parser.add_argument("--input-include-enrichment")
    parser.add_argument("--var-team1")
    parser.add_argument("--var-team2")
    parser.add_argument("--var-season")
    parser.add_argument("--var-last-n")
    parser.add_argument("--var-brief-format")
    parser.add_argument("--var-run-tests")
    parser.add_argument("--var-strict-verification")
    parser.add_argument("--var-include-enrichment")


def _prepare_alert_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--workflow-conclusion", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--release-url")
    parser.add_argument("--message-path", required=True, type=Path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live refresh workflow helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_config = subparsers.add_parser("resolve-config")
    _resolve_config_args(resolve_config)

    prepare_alert = subparsers.add_parser("prepare-alert")
    _prepare_alert_args(prepare_alert)

    return parser.parse_args()


def _run_resolve_config(args: argparse.Namespace) -> int:
    config = resolve_run_config(
        event_name=args.event_name,
        input_values={
            "team1": args.input_team1,
            "team2": args.input_team2,
            "season": args.input_season,
            "last_n": args.input_last_n,
            "brief_format": args.input_brief_format,
            "run_tests": args.input_run_tests,
            "strict_verification": args.input_strict_verification,
            "include_enrichment": args.input_include_enrichment,
        },
        variable_values={
            "team1": args.var_team1,
            "team2": args.var_team2,
            "season": args.var_season,
            "last_n": args.var_last_n,
            "brief_format": args.var_brief_format,
            "run_tests": args.var_run_tests,
            "strict_verification": args.var_strict_verification,
            "include_enrichment": args.var_include_enrichment,
        },
    )

    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as handle:
        for env_key, value in (
            ("TEAM1", config["team1"]),
            ("TEAM2", config["team2"]),
            ("SEASON", config["season"]),
            ("LAST_N", config["last_n"]),
            ("BRIEF_FORMAT", config["brief_format"]),
            ("RUN_TESTS", config["run_tests"]),
            ("STRICT_VERIFICATION", config["strict_verification"]),
            ("INCLUDE_ENRICHMENT", config["include_enrichment"]),
        ):
            handle.write(f"{env_key}={value}\n")
    return 0


def _run_prepare_alert(args: argparse.Namespace) -> int:
    summary = None
    if args.summary_json and args.summary_json.exists():
        summary = json.loads(args.summary_json.read_text(encoding="utf-8"))

    payload = build_alert_payload(
        event_name=args.event_name,
        workflow_conclusion=args.workflow_conclusion,
        run_url=args.run_url,
        summary=summary,
        release_url=args.release_url,
    )

    args.message_path.parent.mkdir(parents=True, exist_ok=True)
    if payload.get("should_notify"):
        args.message_path.write_text(payload["body"], encoding="utf-8")
    elif args.message_path.exists():
        args.message_path.unlink()

    _write_github_output(
        {
            "should_notify": "true" if payload.get("should_notify") else "false",
            "issue_title": ALERT_ISSUE_TITLE,
            "message_path": str(args.message_path),
        }
    )
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "resolve-config":
        return _run_resolve_config(args)
    if args.command == "prepare-alert":
        return _run_prepare_alert(args)
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
