from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _published_asset_entries(summary: dict[str, Any], repo: str, release_tag: str) -> list[dict[str, str]]:
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


def build_release_metadata(
    summary: dict[str, Any],
    *,
    repo: str,
    run_url: str | None = None,
) -> dict[str, Any]:
    season = summary["season"]
    release_tag = f"brief-artifacts-{season}"
    release_name = f"Brief Published Artifacts {season}"
    release_url = f"https://github.com/{repo}/releases/tag/{release_tag}"
    assets = _published_asset_entries(summary, repo, release_tag)

    validation = summary.get("validation") or {}
    git_refs = summary.get("git") or {}
    artifact_contract = summary.get("artifact_contract") or {}

    notes_lines = [
        f"# {release_name}",
        "",
        f"This release is the rolling canonical published artifact set for the {season} season.",
        "Each successful publishable live-refresh run overwrites these release assets in place.",
        "",
        f"- Artifact set id: `{artifact_contract.get('artifact_set_id')}`",
        f"- Generated at: `{summary.get('generated_at')}`",
        f"- Teams: `{', '.join(summary.get('teams') or [])}`",
        f"- pbp-analysis ref: `{git_refs.get('pbp_analysis_ref')}`",
        f"- pbp-parser ref: `{git_refs.get('pbp_parser_ref')}`",
        f"- Verification fails: `{validation.get('verification_fail_count')}`",
        f"- Verification warnings: `{validation.get('verification_warning_count')}`",
    ]
    if run_url:
        notes_lines.append(f"- Workflow run: {run_url}")
    notes_lines.extend(
        [
            "",
            "## Published Assets",
        ]
    )
    for asset in assets:
        notes_lines.append(
            f"- `{asset['filename']}` (`{asset['logical_name']}`): {asset['download_url']}"
        )

    return {
        "publishable": bool(artifact_contract.get("publishable")),
        "release_tag": release_tag,
        "release_name": release_name,
        "release_url": release_url,
        "assets": assets,
        "notes": "\n".join(notes_lines) + "\n",
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
    parser.add_argument("--notes-path", required=True, type=Path)
    parser.add_argument("--run-url")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = json.loads(args.summary_json.read_text(encoding="utf-8"))
    metadata = build_release_metadata(summary, repo=args.repo, run_url=args.run_url)

    args.notes_path.parent.mkdir(parents=True, exist_ok=True)
    args.notes_path.write_text(metadata["notes"], encoding="utf-8")

    _write_github_output(
        {
            "publishable": "true" if metadata["publishable"] else "false",
            "release_tag": metadata["release_tag"],
            "release_name": metadata["release_name"],
            "release_url": metadata["release_url"],
            "release_notes_path": str(args.notes_path),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
