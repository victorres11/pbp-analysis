from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.game_prep_brief import loaders
from scripts.game_prep_brief.sections import penalties, rankings, special_teams, turnovers, zones


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_FIXTURES = ROOT / "tests" / "fixtures" / "pipeline"
GOLDEN_FIXTURES = ROOT / "tests" / "fixtures" / "golden"

CASES = [
    {
        "name": "washington-ohio-state",
        "season": 2025,
        "team1": "Washington",
        "team2": "Ohio State",
        "bundle": PIPELINE_FIXTURES / "pbp_stats_bundle_2025.json",
        "snapshot": PIPELINE_FIXTURES / "cfbstats_2025_snapshot.json",
        "verification": PIPELINE_FIXTURES / "cfbstats_verification_2025_report.json",
        "expected": GOLDEN_FIXTURES / "washington_ohio_state_sections.json",
    },
    {
        "name": "oregon-wisconsin",
        "season": 2025,
        "team1": "Oregon",
        "team2": "Wisconsin",
        "bundle": GOLDEN_FIXTURES / "oregon_wisconsin_bundle.json",
        "snapshot": GOLDEN_FIXTURES / "oregon_wisconsin_snapshot.json",
        "verification": GOLDEN_FIXTURES / "oregon_wisconsin_verification.json",
        "expected": GOLDEN_FIXTURES / "oregon_wisconsin_sections.json",
    },
]


def _normalize_md_lines(text: str) -> list[str]:
    return [re.sub(r"^\s+", "", line.rstrip()) for line in text.splitlines() if line.strip()]


def _render_golden_sections(
    *,
    bundle_path: Path,
    snapshot_path: Path,
    verification_path: Path,
    season: int,
    team1_name: str,
    team2_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[str]]:
    monkeypatch.setattr(loaders, "XML_BUNDLE_JSON", bundle_path)

    pbp_teams = loaders.load_pbp_data()
    snapshot = loaders.load_cfbstats_snapshot(season, snapshot_path)
    verification = loaders.load_cfbstats_verification_report(season, verification_path)

    team1 = loaders.gather_team_data(
        pbp_teams,
        team1_name,
        season,
        cfbstats_snapshot=snapshot,
        cfbstats_verification_report=verification,
    )
    team2 = loaders.gather_team_data(
        pbp_teams,
        team2_name,
        season,
        cfbstats_snapshot=snapshot,
        cfbstats_verification_report=verification,
    )

    selected_sections = [
        rankings.build(team1, team2, show_alerts=True),
        zones.build(team1, team2),
        turnovers.build(team1, team2),
        penalties.build(team1, team2),
        special_teams.build(team1, team2),
    ]
    return {section["key"]: _normalize_md_lines(section["md_content"]) for section in selected_sections}


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_artifact_backed_brief_sections_match_golden_snapshots(
    case: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = json.loads(case["expected"].read_text(encoding="utf-8"))
    actual = _render_golden_sections(
        bundle_path=case["bundle"],
        snapshot_path=case["snapshot"],
        verification_path=case["verification"],
        season=case["season"],
        team1_name=case["team1"],
        team2_name=case["team2"],
        monkeypatch=monkeypatch,
    )

    assert actual.keys() == expected.keys()
    for section_key, expected_lines in expected.items():
        assert actual[section_key] == expected_lines, f"{case['name']} section={section_key}"
