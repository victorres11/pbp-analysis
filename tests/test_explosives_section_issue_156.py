from pathlib import Path

from scripts.game_prep_brief import loaders
from scripts.game_prep_brief.sections import explosives


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_FIXTURES = ROOT / "tests" / "fixtures" / "pipeline"


def _load_team(team_name: str) -> dict:
    pbp_teams = loaders.load_pbp_data(season=2025, bundle_source=PIPELINE_FIXTURES / "pbp_stats_bundle_2025.json")
    snapshot = loaders.load_cfbstats_snapshot(2025, PIPELINE_FIXTURES / "cfbstats_2025_snapshot.json")
    verification = loaders.load_cfbstats_verification_report(
        2025,
        PIPELINE_FIXTURES / "cfbstats_verification_2025_report.json",
    )
    return loaders.gather_team_data(
        pbp_teams,
        team_name,
        2025,
        cfbstats_snapshot=snapshot,
        cfbstats_verification_report=verification,
    )


def test_explosives_section_uses_play_tree_counts_for_pbp_context() -> None:
    washington = _load_team("Washington")
    ohio_state = _load_team("Ohio State")

    washington_totals = explosives._aggregate_explosives(
        washington["pbp_entry"]["games"],
        explosives._team_aliases(washington),
    )
    ohio_state_totals = explosives._aggregate_explosives(
        ohio_state["pbp_entry"]["games"],
        explosives._team_aliases(ohio_state),
    )
    washington_game_row_totals = explosives._game_row_aggregate_explosives(washington["pbp_entry"]["games"])
    ohio_state_game_row_totals = explosives._game_row_aggregate_explosives(ohio_state["pbp_entry"]["games"])

    assert washington_totals["explosives"] == 83
    assert washington_totals["explosive_passes"] == 48
    assert washington_totals["explosive_rushes"] == 35
    assert washington_totals["pass_20_plus"] == 48
    assert washington_totals["rush_20_plus"] == 21
    assert washington_totals["rush_15_19"] == 14
    assert washington_game_row_totals == {
        "explosives": 100,
        "explosive_passes": 67,
        "explosive_rushes": 33,
    }

    assert ohio_state_totals["explosives"] == 71
    assert ohio_state_totals["explosive_passes"] == 45
    assert ohio_state_totals["explosive_rushes"] == 26
    assert ohio_state_totals["pass_20_plus"] == 45
    assert ohio_state_totals["rush_20_plus"] == 12
    assert ohio_state_totals["rush_15_19"] == 14
    assert ohio_state_game_row_totals == {
        "explosives": 75,
        "explosive_passes": 40,
        "explosive_rushes": 35,
    }


def test_explosives_markdown_surfaces_play_tree_counts_and_bundle_row_gap() -> None:
    washington = _load_team("Washington")
    ohio_state = _load_team("Ohio State")

    md = explosives.build(washington, ohio_state)["md_content"]

    assert "- PBP Explosives: 83 (Pass 48, Rush 35)" in md
    assert "- Delta using PBP 20+ vs CFBStats: -4 (-5.5%) (residual -4)" in md

    assert "- PBP Explosives: 71 (Pass 45, Rush 26)" in md
    assert "- Delta using PBP 20+ vs CFBStats: 0 (0.0%) (residual 0)" in md
