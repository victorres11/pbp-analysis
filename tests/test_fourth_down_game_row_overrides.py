from scripts.game_prep_brief import loaders


def test_apply_raw_game_fourth_down_overrides_updates_game_totals(monkeypatch) -> None:
    pbp_entry = {
        "games": [
            {
                "game_number": 1,
                "date": "2025-08-30",
                "opponent_abbr": "NM",
                "4th_down_attempts": 99,
                "4th_down_conversions": 88,
            }
        ]
    }

    monkeypatch.setattr(
        loaders,
        "_load_raw_game_fourth_down_totals",
        lambda team_slug, team_name: {
            "2025-08-30": {
                "attempts": 1,
                "conversions": 0,
            }
        },
    )

    loaders._apply_raw_game_fourth_down_overrides(
        pbp_entry,
        team_slug="michigan",
        team_name="Michigan",
    )

    game = pbp_entry["games"][0]
    assert game["4th_down_attempts"] == 1
    assert game["4th_down_conversions"] == 0
