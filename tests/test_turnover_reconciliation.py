from scripts.game_prep_brief import loaders


def test_turnover_reconciliation_uses_game_level_int_and_fumble_loss_splits() -> None:
    pbp_entry = {
        "games": [
            {
                "game_number": 1,
                "opponent_abbr": "NM",
                "turnovers_gained": 3,
                "turnovers_lost": 1,
                "interceptions_gained": 3,
                "interceptions_lost": 0,
                "fumbles_gained": 0,
                "fumbles_lost": 1,
                "points_off_turnovers_for": 10,
                "points_off_turnovers_against": 0,
            }
        ],
        "xml_stats": {
            "turnovers": {
                "NM": {
                    "turnovers": 3,
                    "turnovers_forced": 1,
                    "interceptions": 3,
                    "interceptions_forced": 0,
                    "fumbles_lost": 0,
                    "fumbles_recovered": 1,
                }
            },
            "points_off_turnovers": {
                "NM": {
                    "points_off_turnovers": 0,
                    "points_off_turnovers_allowed": 10,
                }
            },
        },
        "xml_rollups": {
            "turnovers": {
                "turnovers_forced": 3,
                "turnovers": 1,
                "interceptions": 99,
                "fumbles_lost": 99,
            },
            "points_off_turnovers": {
                "points_off_turnovers": 10,
                "points_off_turnovers_allowed": 0,
            },
        },
    }

    game_recon = loaders._turnover_game_reconciliation(pbp_entry)
    season_recon = loaders._turnover_reconciliation(pbp_entry, game_recon)

    assert game_recon[0]["in_sync"] is True
    assert season_recon["cfbstats"]["int_lost"] == 0
    assert season_recon["cfbstats"]["fum_lost"] == 1
    assert season_recon["delta"]["int_lost"] == 0
    assert season_recon["delta"]["fum_lost"] == 0
    assert season_recon["in_sync"] is True


def test_turnover_reconciliation_keeps_season_rollup_when_duplicate_opponent_game_rows_are_ambiguous() -> None:
    pbp_entry = {
        "games": [
            {
                "game_number": 1,
                "opponent_abbr": "ORE",
                "turnovers_gained": 2,
                "turnovers_lost": 1,
                "interceptions_gained": 2,
                "interceptions_lost": 1,
                "fumbles_gained": 0,
                "fumbles_lost": 0,
                "points_off_turnovers_for": 3,
                "points_off_turnovers_against": 7,
            },
            {
                "game_number": 2,
                "opponent_abbr": "ORE",
                "turnovers_gained": 3,
                "turnovers_lost": 0,
                "interceptions_gained": 1,
                "interceptions_lost": 0,
                "fumbles_gained": 2,
                "fumbles_lost": 0,
                "points_off_turnovers_for": 21,
                "points_off_turnovers_against": 0,
            },
        ],
        "xml_stats": {
            "turnovers": {
                "ORE": {
                    "games": 2,
                    "turnovers": 5,
                    "turnovers_forced": 1,
                    "interceptions": 3,
                    "interceptions_forced": 1,
                    "fumbles_lost": 2,
                    "fumbles_recovered": 0,
                }
            },
            "points_off_turnovers": {
                "ORE": {
                    "games": 2,
                    "points_off_turnovers": 0,
                    "points_off_turnovers_allowed": 24,
                }
            },
        },
        "xml_rollups": {
            "turnovers": {
                "turnovers_forced": 5,
                "turnovers": 1,
                "interceptions": 1,
                "fumbles_lost": 0,
            },
            "points_off_turnovers": {
                "points_off_turnovers": 24,
                "points_off_turnovers_allowed": 7,
            },
        },
    }

    game_recon = loaders._turnover_game_reconciliation(pbp_entry)
    season_recon = loaders._turnover_reconciliation(pbp_entry, game_recon)

    assert game_recon == []
    assert season_recon["cfbstats"]["gained"] == 5
    assert season_recon["cfbstats"]["lost"] == 1
    assert season_recon["delta"]["gained"] == 0
    assert season_recon["delta"]["lost"] == 0
    assert season_recon["in_sync"] is True
