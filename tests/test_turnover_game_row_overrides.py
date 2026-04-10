from scripts.game_prep_brief import loaders


def test_apply_turnover_xml_game_overrides_updates_game_totals_from_xml_rows() -> None:
    pbp_entry = {
        "aggregates": {"turnover_margin": 99},
        "games": [
            {
                "game_number": 1,
                "opponent_abbr": "NM",
                "turnovers_gained": 3,
                "turnovers_lost": 0,
                "interceptions_gained": 3,
                "interceptions_lost": 0,
                "fumbles_gained": 0,
                "fumbles_lost": 0,
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
    }

    loaders._apply_turnover_xml_game_overrides(pbp_entry)

    game = pbp_entry["games"][0]
    assert game["turnovers_gained"] == 3
    assert game["turnovers_lost"] == 1
    assert game["interceptions_gained"] == 3
    assert game["interceptions_lost"] == 0
    assert game["fumbles_gained"] == 0
    assert game["fumbles_lost"] == 1
    assert game["points_off_turnovers_for"] == 10
    assert game["points_off_turnovers_against"] == 0
    assert pbp_entry["aggregates"]["turnover_margin"] == 2


def test_apply_turnover_xml_game_overrides_skips_multi_game_opponent_rows() -> None:
    pbp_entry = {
        "aggregates": {"turnover_margin": 20},
        "games": [
            {
                "game_number": 1,
                "opponent_abbr": "ORE",
                "turnovers_gained": 2,
                "turnovers_lost": 1,
                "points_off_turnovers_for": 7,
                "points_off_turnovers_against": 0,
            },
            {
                "game_number": 2,
                "opponent_abbr": "ORE",
                "turnovers_gained": 3,
                "turnovers_lost": 0,
                "points_off_turnovers_for": 14,
                "points_off_turnovers_against": 0,
            },
            {
                "game_number": 3,
                "opponent_abbr": "KSU",
                "turnovers_gained": 1,
                "turnovers_lost": 0,
                "points_off_turnovers_for": 0,
                "points_off_turnovers_against": 0,
            },
        ],
        "xml_stats": {
            "turnovers": {
                "ORE": {
                    "games": 2,
                    "turnovers": 5,
                    "turnovers_forced": 1,
                },
                "KSU": {
                    "games": 1,
                    "turnovers": 2,
                    "turnovers_forced": 0,
                },
            },
            "points_off_turnovers": {
                "ORE": {
                    "games": 2,
                    "points_off_turnovers": 0,
                    "points_off_turnovers_allowed": 21,
                },
                "KSU": {
                    "games": 1,
                    "points_off_turnovers": 0,
                    "points_off_turnovers_allowed": 7,
                },
            },
        },
    }

    loaders._apply_turnover_xml_game_overrides(pbp_entry)

    ore_game_1, ore_game_2, ksu_game = pbp_entry["games"]
    assert (ore_game_1["turnovers_gained"], ore_game_1["turnovers_lost"]) == (2, 1)
    assert (ore_game_2["turnovers_gained"], ore_game_2["turnovers_lost"]) == (3, 0)
    assert ore_game_1["points_off_turnovers_for"] == 7
    assert ore_game_2["points_off_turnovers_for"] == 14
    assert (ksu_game["turnovers_gained"], ksu_game["turnovers_lost"]) == (2, 0)
    assert ksu_game["points_off_turnovers_for"] == 7
    assert pbp_entry["aggregates"]["turnover_margin"] == 6
