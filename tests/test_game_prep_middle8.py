from scripts.game_prep_brief.sections import middle8


def _play(description: str, *, offense: str, clock: str, quarter: int, is_scoring: bool = True) -> dict:
    return {
        "quarter": quarter,
        "offense": offense,
        "clock": clock,
        "description": description,
        "is_scoring": is_scoring,
        "is_no_play": False,
    }


def _drive(*plays: dict) -> dict:
    return {"plays": list(plays)}


def _quarter(number: int, *drives: dict) -> dict:
    return {"quarter": number, "drives": list(drives)}


def test_middle8_build_derives_per_game_scores_and_filters_missed_kicks() -> None:
    team = {
        "display_name": "Indiana",
        "has_pbp": True,
        "last_n": {
            "actual_n": 3,
            "required_n": 3,
            "middle8_points_for": 24,
            "middle8_points_against": 7,
            "middle8_margin": 17,
        },
        "pbp_entry": {
            "abbr": "IND",
            "abbr_aliases": ["IND"],
            "xml_stats": {
                "middle_eight": {
                    "IND": {
                        "games": 3,
                        "middle_eight_points": 21,
                        "middle_eight_points_allowed": 7,
                    },
                    "ORE": {
                        "games": 2,
                        "middle_eight_points": 0,
                        "middle_eight_points_allowed": 17,
                    },
                }
            },
            "games": [
                {
                    "game_number": 1,
                    "opponent": "Oregon",
                    "opponent_abbr": "ORE",
                    "play_tree": [
                        _quarter(
                            2,
                            _drive(
                                _play(
                                    "IND field goal attempt from 52 yards NO GOOD.",
                                    offense="IND",
                                    clock="02:30",
                                    quarter=2,
                                ),
                                _play(
                                    "IND rush up the middle for 14 yards TOUCHDOWN.",
                                    offense="IND",
                                    clock="01:45",
                                    quarter=2,
                                ),
                            ),
                        )
                    ],
                },
                {
                    "game_number": 2,
                    "opponent": "Oregon",
                    "opponent_abbr": "ORE",
                    "play_tree": [
                        _quarter(
                            2,
                            _drive(
                                _play(
                                    "IND pass complete for 22 yards TOUCHDOWN.",
                                    offense="IND",
                                    clock="00:45",
                                    quarter=2,
                                ),
                            ),
                        ),
                        _quarter(
                            3,
                            _drive(
                                _play(
                                    "IND rush left for 9 yards TOUCHDOWN.",
                                    offense="IND",
                                    clock="14:20",
                                    quarter=3,
                                ),
                            ),
                        ),
                    ],
                },
                {
                    "game_number": 3,
                    "opponent": "Miami",
                    "opponent_abbr": "MIAM",
                    "play_tree": [
                        _quarter(
                            2,
                            _drive(
                                _play(
                                    "MIAM pass complete for 18 yards TOUCHDOWN.",
                                    offense="MIAM",
                                    clock="02:05",
                                    quarter=2,
                                ),
                            ),
                        )
                    ],
                },
            ],
        },
    }

    html = middle8.build(team, team)["html_content"]

    assert "Points For / Against: 21 / 7" in html
    assert "G1 vs Oregon: 7-0" in html
    assert "G2 vs Oregon: 14-0" in html
    assert "G3 vs Miami: 0-7" in html
    assert "Last 3 Trending" in html
    assert "24 / 7" not in html
    assert "NO GOOD" not in html
