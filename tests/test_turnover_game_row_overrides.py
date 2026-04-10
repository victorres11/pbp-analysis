from scripts.game_prep_brief import loaders


def test_apply_turnover_xml_game_overrides_updates_game_totals_from_xml_rows() -> None:
    pbp_entry = {
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
