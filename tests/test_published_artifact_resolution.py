from __future__ import annotations

import json
from pathlib import Path

from scripts.game_prep_brief import loaders


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_FIXTURES = ROOT / "tests" / "fixtures" / "pipeline"


def _fixture_payload(filename: str) -> dict:
    return json.loads((PIPELINE_FIXTURES / filename).read_text(encoding="utf-8"))


def test_default_loaders_resolve_published_release_artifacts(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    payloads = {
        "bundle": _fixture_payload("pbp_stats_bundle_2025.json"),
        "cfbstats_snapshot": _fixture_payload("cfbstats_2025_snapshot.json"),
        "cfbstats_verification_report": _fixture_payload("cfbstats_verification_2025_report.json"),
    }

    def _fake_fetch(logical_name: str, season: int, *, repo: str | None = None) -> dict:
        calls.append((logical_name, season))
        return payloads[logical_name]

    monkeypatch.setattr(loaders, "fetch_published_artifact_json", _fake_fetch)

    bundle = loaders.load_pbp_data(season=2025)
    snapshot = loaders.load_cfbstats_snapshot(2025)
    report = loaders.load_cfbstats_verification_report(2025)

    assert calls == [
        ("bundle", 2025),
        ("cfbstats_snapshot", 2025),
        ("cfbstats_verification_report", 2025),
    ]
    assert "washington" in bundle
    assert snapshot["meta"]["artifact"] == "cfbstats_snapshot"
    assert report["meta"]["artifact"] == "cfbstats_bundle_verification_report"


def test_explicit_local_artifact_overrides_bypass_published_release(monkeypatch) -> None:
    def _unexpected_fetch(*args, **kwargs):
        raise AssertionError("published release fetch should not run when local overrides are explicit")

    monkeypatch.setattr(loaders, "fetch_published_artifact_json", _unexpected_fetch)

    bundle = loaders.load_pbp_data(
        season=2025,
        bundle_source=PIPELINE_FIXTURES / "pbp_stats_bundle_2025.json",
    )
    snapshot = loaders.load_cfbstats_snapshot(
        2025,
        PIPELINE_FIXTURES / "cfbstats_2025_snapshot.json",
    )
    report = loaders.load_cfbstats_verification_report(
        2025,
        PIPELINE_FIXTURES / "cfbstats_verification_2025_report.json",
    )

    assert "washington" in bundle
    assert snapshot["meta"]["artifact"] == "cfbstats_snapshot"
    assert report["meta"]["artifact"] == "cfbstats_bundle_verification_report"


def test_load_pbp_data_keeps_matchup_slug_as_first_positional_argument() -> None:
    bundle = loaders.load_pbp_data(
        "missing-matchup-slug",
        season=2025,
        bundle_source=PIPELINE_FIXTURES / "pbp_stats_bundle_2025.json",
    )

    assert "washington" in bundle
