from scripts.game_prep_brief import loaders


def _game_with_offenses(*offenses: str) -> dict:
    plays = [
        {
            "offense": offense,
            "description": f"{offense} play",
            "is_no_play": False,
            "is_turnover": False,
        }
        for offense in offenses
    ]
    return {
        "game_number": 1,
        "opponent_abbr": "UMD",
        "opponent": "Maryland",
        "play_tree": [{"quarter": 1, "drives": [{"plays": plays}]}],
    }


def test_play_side_resolver_handles_direct_match_tokens() -> None:
    resolver = loaders._build_play_side_resolver(
        _game_with_offenses("UW", "UMD"),
        team_aliases={"UW"},
        opp_aliases={"UMD"},
    )

    assert resolver.resolve("UW") == "team"
    assert resolver.resolve("UMD") == "opp"
    assert resolver.warnings == ()


def test_play_side_resolver_assigns_team_alias_by_two_token_elimination() -> None:
    resolver = loaders._build_play_side_resolver(
        _game_with_offenses("WASH", "UMD"),
        team_aliases={"UW"},
        opp_aliases={"UMD"},
    )

    assert resolver.resolve("WASH") == "team"
    assert resolver.resolve("UMD") == "opp"
    assert resolver.warnings == ()


def test_play_side_resolver_reports_unresolved_tokens() -> None:
    resolver = loaders._build_play_side_resolver(
        _game_with_offenses("AAA", "BBB", "CCC"),
        team_aliases={"UW"},
        opp_aliases={"UMD"},
    )

    assert resolver.resolve("AAA") == "unknown"
    assert "multiple offense tokens detected: AAA, BBB, CCC" in resolver.warnings
    assert "unresolved offense tokens: AAA, BBB, CCC" in resolver.warnings
    assert "team offense token unresolved after alias resolution" in resolver.warnings


def test_extract_pbp_stats_uses_alias_resolver_for_sacks_and_tfl() -> None:
    team_data = {
        "name": "Washington",
        "abbr": "UW",
        "abbr_aliases": ["UW"],
        "games": [
            {
                "game_number": 1,
                "date": "2025-09-01",
                "opponent": "Maryland",
                "opponent_abbr": "UMD",
                "points_for": 24,
                "points_against": 17,
                "4th_down_attempts": 0,
                "4th_down_conversions": 0,
                "third_down_attempts": 0,
                "third_down_conversions": 0,
                "play_tree": [
                    {
                        "quarter": 1,
                        "drives": [
                            {
                                "plays": [
                                    {
                                        "offense": "WAS",
                                        "description": "Shotgun Washington sacked for loss",
                                        "is_no_play": False,
                                        "yards": -7,
                                    },
                                    {
                                        "offense": "UMD",
                                        "description": "Maryland rush left for -3 yards",
                                        "is_no_play": False,
                                        "yards": -3,
                                    },
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
        "aggregates": {},
        "cfbstats": {"rankings": {"all": {}}},
        "xml_stats": {},
        "xml_rollups": {},
        "color": "#000000",
        "conference": "Big Ten",
    }

    stats = loaders._extract_pbp_stats(team_data)

    assert stats["sacks_allowed_derived_pg"] == 1.0
    assert stats["tfl_forced_derived_pg"] == 1.0


def test_turnover_events_for_game_use_alias_resolver() -> None:
    game = {
        "opponent_abbr": "UMD",
        "play_tree": [
            {
                "quarter": 1,
                "drives": [
                    {
                        "plays": [
                            {
                                "offense": "WASH",
                                "description": "Shotgun Washington rush middle fumbled by Washington recovered by UMD",
                                "is_no_play": False,
                                "is_turnover": True,
                                "clock": "12:34",
                            }
                        ]
                    }
                ],
            }
        ],
    }

    events = loaders._turnover_events_for_game(game, {"UW"}, {"UMD"})

    assert len(events) == 1
    assert events[0]["offense"] == "WASH"
    assert events[0]["recovery_side"] == "opp"
