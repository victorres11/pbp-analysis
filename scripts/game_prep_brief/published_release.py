from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

FRESHNESS_WARNING_HOURS = 36
FRESHNESS_CRITICAL_HOURS = 72


def _published_asset_entries(
    summary: dict[str, Any],
    repo: str,
    release_tag: str,
) -> list[dict[str, str]]:
    artifact_contract = summary.get("artifact_contract") or {}
    published_artifacts = artifact_contract.get("published_artifacts") or {}
    base_download_url = f"https://github.com/{repo}/releases/download/{release_tag}"

    assets: list[dict[str, str]] = []
    for logical_name in sorted(published_artifacts):
        asset = published_artifacts[logical_name]
        relative_path = asset.get("relative_path")
        if not relative_path:
            continue
        filename = Path(relative_path).name
        assets.append(
            {
                "logical_name": logical_name,
                "filename": filename,
                "download_url": f"{base_download_url}/{filename}",
            }
        )
    return assets


def _rolling_release(season: int | str, repo: str) -> dict[str, str]:
    tag = f"brief-artifacts-{season}"
    return {
        "tag": tag,
        "name": f"Brief Published Artifacts {season}",
        "url": f"https://github.com/{repo}/releases/tag/{tag}",
    }


def _archive_release(artifact_set_id: str, season: int | str, repo: str) -> dict[str, str]:
    tag = f"brief-artifacts-archive-{artifact_set_id}"
    return {
        "tag": tag,
        "name": f"Brief Published Artifacts Archive {season} {artifact_set_id}",
        "url": f"https://github.com/{repo}/releases/tag/{tag}",
    }


def build_release_metadata(
    summary: dict[str, Any],
    *,
    repo: str,
    run_url: str | None = None,
) -> dict[str, Any]:
    season = summary["season"]
    validation = summary.get("validation") or {}
    git_refs = summary.get("git") or {}
    artifact_contract = summary.get("artifact_contract") or {}
    artifact_set_id = artifact_contract.get("artifact_set_id") or f"{season}-unversioned"

    rolling = _rolling_release(season, repo)
    archive = _archive_release(artifact_set_id, season, repo)
    rolling_assets = _published_asset_entries(summary, repo, rolling["tag"])
    archive_assets = _published_asset_entries(summary, repo, archive["tag"])

    rolling_notes = [
        f"# {rolling['name']}",
        "",
        f"This release is the rolling canonical published artifact set for the {season} season.",
        "It should be treated as the current last-known-good published set for downstream consumers.",
        "Each successful publishable live-refresh run overwrites these release assets in place.",
        "",
        f"- Artifact set id: `{artifact_set_id}`",
        f"- Generated at: `{summary.get('generated_at')}`",
        f"- Teams: `{', '.join(summary.get('teams') or [])}`",
        f"- pbp-analysis ref: `{git_refs.get('pbp_analysis_ref')}`",
        f"- pbp-parser ref: `{git_refs.get('pbp_parser_ref')}`",
        f"- Verification fails: `{validation.get('verification_fail_count')}`",
        f"- Verification warnings: `{validation.get('verification_warning_count')}`",
        f"- Archived rollback release: {archive['url']}",
        f"- Freshness warning threshold: `{FRESHNESS_WARNING_HOURS}h`",
        f"- Freshness critical threshold: `{FRESHNESS_CRITICAL_HOURS}h`",
    ]
    if run_url:
        rolling_notes.append(f"- Workflow run: {run_url}")
    rolling_notes.extend(["", "## Published Assets"])
    for asset in rolling_assets:
        rolling_notes.append(
            f"- `{asset['filename']}` (`{asset['logical_name']}`): {asset['download_url']}"
        )

    archive_notes = [
        f"# {archive['name']}",
        "",
        "This release preserves one immutable publishable artifact set for rollback and historical inspection.",
        "It should not be mutated after publication except to repair the same archived artifact set.",
        "",
        f"- Artifact set id: `{artifact_set_id}`",
        f"- Season: `{season}`",
        f"- Generated at: `{summary.get('generated_at')}`",
        f"- Teams: `{', '.join(summary.get('teams') or [])}`",
        f"- Rolling last-known-good release: {rolling['url']}",
        f"- pbp-analysis ref: `{git_refs.get('pbp_analysis_ref')}`",
        f"- pbp-parser ref: `{git_refs.get('pbp_parser_ref')}`",
    ]
    if run_url:
        archive_notes.append(f"- Workflow run: {run_url}")
    archive_notes.extend(["", "## Archived Assets"])
    for asset in archive_assets:
        archive_notes.append(
            f"- `{asset['filename']}` (`{asset['logical_name']}`): {asset['download_url']}"
        )

    return {
        "publishable": bool(artifact_contract.get("publishable")),
        "artifact_set_id": artifact_set_id,
        "freshness_policy": {
            "warning_hours": FRESHNESS_WARNING_HOURS,
            "critical_hours": FRESHNESS_CRITICAL_HOURS,
            "freshness_source": "pipeline_summary.generated_at",
        },
        "rolling_release": {
            **rolling,
            "assets": rolling_assets,
            "notes": "\n".join(rolling_notes) + "\n",
        },
        "archive_release": {
            **archive,
            "assets": archive_assets,
            "notes": "\n".join(archive_notes) + "\n",
        },
    }


def _write_github_output(outputs: dict[str, str]) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return

    with open(github_output, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare GitHub release metadata for published brief artifacts."
    )
    parser.add_argument("--summary-json", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--rolling-notes-path", required=True, type=Path)
    parser.add_argument("--archive-notes-path", required=True, type=Path)
    parser.add_argument("--run-url")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = json.loads(args.summary_json.read_text(encoding="utf-8"))
    metadata = build_release_metadata(summary, repo=args.repo, run_url=args.run_url)

    args.rolling_notes_path.parent.mkdir(parents=True, exist_ok=True)
    args.archive_notes_path.parent.mkdir(parents=True, exist_ok=True)
    args.rolling_notes_path.write_text(
        metadata["rolling_release"]["notes"],
        encoding="utf-8",
    )
    args.archive_notes_path.write_text(
        metadata["archive_release"]["notes"],
        encoding="utf-8",
    )

    _write_github_output(
        {
            "publishable": "true" if metadata["publishable"] else "false",
            "artifact_set_id": metadata["artifact_set_id"],
            "rolling_release_tag": metadata["rolling_release"]["tag"],
            "rolling_release_name": metadata["rolling_release"]["name"],
            "rolling_release_url": metadata["rolling_release"]["url"],
            "rolling_release_notes_path": str(args.rolling_notes_path),
            "archive_release_tag": metadata["archive_release"]["tag"],
            "archive_release_name": metadata["archive_release"]["name"],
            "archive_release_url": metadata["archive_release"]["url"],
            "archive_release_notes_path": str(args.archive_notes_path),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
