from scripts.game_prep_brief import loaders
from scripts.game_prep_brief.sections import situational


def test_apply_raw_game_third_down_overrides_updates_game_totals(monkeypatch) -> None:
    pbp_entry = {
        "games": [
            {
                "game_number": 1,
                "date": "2025-08-30",
                "opponent_abbr": "NM",
                "third_down_attempts": 99,
                "third_down_conversions": 88,
            }
        ]
    }

    monkeypatch.setattr(
        loaders,
        "_load_raw_game_third_down_totals",
        lambda team_slug, team_name: {
            "2025-08-30": {
                "attempts": 13,
                "conversions": 6,
            }
        },
    )

    loaders._apply_raw_game_third_down_overrides(
        pbp_entry,
        team_slug="michigan",
        team_name="Michigan",
    )

    game = pbp_entry["games"][0]
    assert game["third_down_attempts"] == 13
    assert game["third_down_conversions"] == 6


def test_third_down_from_games_prefers_game_row_totals() -> None:
    team = {
        "pbp_entry": {
            "abbr": "MICH",
            "abbr_aliases": ["MICH"],
        }
    }
    games = [
        {
            "third_down_attempts": 13,
            "third_down_conversions": 6,
            "play_tree": [
                {
                    "quarter": 1,
                    "drives": [
                        {
                            "plays": [
                                {
                                    "is_no_play": False,
                                    "offense": "MICH",
                                    "down_distance": "3-10",
                                    "description": "1ST DOWN",
                                }
                            ]
                        }
                    ],
                }
            ],
        },
        {
            "third_down_attempts": 14,
            "third_down_conversions": 5,
            "play_tree": [],
        },
    ]

    conversions, attempts, pct = situational._third_down_from_games(team, games)

    assert conversions == 11
    assert attempts == 27
    assert pct == 40.7
