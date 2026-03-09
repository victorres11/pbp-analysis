from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts.game_prep_brief import __main__ as brief_main


def _args(tmp_path: Path, *, refresh: bool = False, no_enrichment: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        output_dir=tmp_path,
        enrichment_file=tmp_path / "enrichment.json",
        season=2025,
        refresh_enrichment=refresh,
        no_enrichment=no_enrichment,
    )


def test_resolve_enrichment_artifact_requires_existing_file_by_default(tmp_path: Path) -> None:
    args = _args(tmp_path)
    team_specs = [
        {"slug": "washington", "display_name": "Washington"},
        {"slug": "ohio-state", "display_name": "Ohio State"},
    ]

    with pytest.raises(SystemExit, match="Missing enrichment artifact"):
        brief_main._resolve_enrichment_artifact(args, team_specs)


def test_resolve_enrichment_artifact_refreshes_and_writes_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args(tmp_path, refresh=True)
    team_specs = [
        {"slug": "washington", "display_name": "Washington"},
        {"slug": "ohio-state", "display_name": "Ohio State"},
    ]

    monkeypatch.setattr(
        brief_main,
        "build_enrichment_payload",
        lambda specs: {
            spec["slug"]: {
                "_status": "ok",
                "_source": "test",
                "blitz_pct": "31.2%",
            }
            for spec in specs
        },
    )

    enrichment_file, payload = brief_main._resolve_enrichment_artifact(args, team_specs)

    assert enrichment_file.exists()
    assert payload["washington"]["blitz_pct"] == "31.2%"
    written = json.loads(enrichment_file.read_text(encoding="utf-8"))
    assert written["washington"]["_status"] == "ok"
    assert written["ohio-state"]["_source"] == "test"


def test_resolve_enrichment_artifact_allows_explicit_opt_out(tmp_path: Path) -> None:
    args = _args(tmp_path, no_enrichment=True)
    team_specs = [
        {"slug": "washington", "display_name": "Washington"},
        {"slug": "ohio-state", "display_name": "Ohio State"},
    ]

    enrichment_file, payload = brief_main._resolve_enrichment_artifact(args, team_specs)

    assert enrichment_file == tmp_path / "enrichment.json"
    assert payload == {}
