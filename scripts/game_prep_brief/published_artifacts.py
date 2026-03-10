from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_PUBLISHED_ARTIFACT_REPO = "victorres11/pbp-analysis"
PUBLISHED_ARTIFACT_FILENAMES = {
    "bundle": "pbp_stats_bundle_{season}.json",
    "cfbstats_snapshot": "cfbstats_{season}.json",
    "cfbstats_verification_report": "cfbstats_verification_{season}.json",
    "pipeline_summary": "game_prep_pipeline_summary_{season}.json",
}
_RELEASE_ASSET_CACHE: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}


def published_artifact_repo() -> str:
    return (os.getenv("GAME_PREP_PUBLISHED_ARTIFACT_REPO") or DEFAULT_PUBLISHED_ARTIFACT_REPO).strip()


def rolling_release_tag(season: int) -> str:
    return f"brief-artifacts-{season}"


def published_artifact_filename(logical_name: str, season: int) -> str:
    template = PUBLISHED_ARTIFACT_FILENAMES[logical_name]
    return template.format(season=season)


def published_artifact_download_url(
    logical_name: str,
    season: int,
    *,
    repo: str | None = None,
) -> str:
    resolved_repo = repo or published_artifact_repo()
    tag = rolling_release_tag(season)
    filename = published_artifact_filename(logical_name, season)
    return f"https://github.com/{resolved_repo}/releases/download/{tag}/{filename}"


def published_artifact_release_url(season: int, *, repo: str | None = None) -> str:
    resolved_repo = repo or published_artifact_repo()
    return f"https://github.com/{resolved_repo}/releases/tag/{rolling_release_tag(season)}"


def _github_token() -> str | None:
    for env_var in ("GAME_PREP_PUBLISHED_ARTIFACT_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        value = (os.getenv(env_var) or "").strip()
        if value:
            return value

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None

    token = (result.stdout or "").strip()
    return token or None


def _github_headers(*, token: str | None = None, accept: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "pbp-analysis-game-prep-brief",
    }
    if accept:
        headers["Accept"] = accept
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _read_json_response(url: str, *, token: str | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers=_github_headers(token=token, accept="application/vnd.github+json"),
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid GitHub API payload from {url}")
    return payload


def _release_asset_map(repo: str, tag: str, token: str | None) -> dict[str, dict[str, Any]]:
    cache_key = (repo, tag)
    cached = _RELEASE_ASSET_CACHE.get(cache_key)
    if cached is not None:
        return cached

    release_url = f"https://api.github.com/repos/{repo}/releases/tags/{urllib.parse.quote(tag, safe='')}"
    try:
        payload = _read_json_response(release_url, token=token)
    except urllib.error.HTTPError as exc:
        reason = exc.read().decode("utf-8", errors="ignore").strip()
        if exc.code == 404 and not token:
            raise RuntimeError(
                "Published artifact release is not accessible without GitHub auth. "
                "Set GAME_PREP_PUBLISHED_ARTIFACT_TOKEN, GH_TOKEN, or GITHUB_TOKEN, "
                "or authenticate gh CLI."
            ) from exc
        raise RuntimeError(
            f"Failed to resolve published artifact release '{tag}' from {repo}: "
            f"HTTP {exc.code} {reason or exc.reason}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Failed to resolve published artifact release '{tag}' from {repo}: {exc}"
        ) from exc

    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError(f"Release '{tag}' from {repo} did not include an asset list")
    asset_map = {
        asset.get("name"): asset
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("name"), str)
    }
    _RELEASE_ASSET_CACHE[cache_key] = asset_map
    return asset_map


def fetch_published_artifact_json(
    logical_name: str,
    season: int,
    *,
    repo: str | None = None,
) -> dict[str, Any]:
    resolved_repo = repo or published_artifact_repo()
    token = _github_token()
    tag = rolling_release_tag(season)
    filename = published_artifact_filename(logical_name, season)
    assets = _release_asset_map(resolved_repo, tag, token)
    asset = assets.get(filename)
    if not isinstance(asset, dict):
        raise RuntimeError(
            f"Published artifact '{filename}' was not found on release '{tag}' "
            f"({published_artifact_release_url(season, repo=resolved_repo)})"
        )

    asset_api_url = asset.get("url")
    if not isinstance(asset_api_url, str) or not asset_api_url:
        raise RuntimeError(
            f"Published artifact '{filename}' on release '{tag}' is missing an asset API url"
        )

    request = urllib.request.Request(
        asset_api_url,
        headers=_github_headers(token=token, accept="application/octet-stream"),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        reason = exc.read().decode("utf-8", errors="ignore").strip()
        raise RuntimeError(
            f"Failed to download published artifact '{filename}' from release '{tag}': "
            f"HTTP {exc.code} {reason or exc.reason}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download published artifact '{filename}' from release '{tag}': {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Published artifact '{filename}' from release '{tag}' did not decode to a JSON object"
        )
    return payload
