from scripts.game_prep_brief import loaders
from scripts.game_prep_brief.sections import special_teams


def _play(
    description: str,
    *,
    offense: str | None,
    is_no_play: bool = False,
    is_scoring: bool = False,
    yards: int | None = None,
) -> dict:
    return {
        "offense": offense,
        "description": description,
        "is_no_play": is_no_play,
        "is_turnover": False,
        "is_scoring": is_scoring,
        "yards": yards,
    }


def _game(*plays: dict) -> dict:
    return {
        "game_number": 1,
        "opponent_abbr": "OSU",
        "opponent": "Ohio State",
        "play_tree": [{"quarter": 1, "drives": [{"plays": list(plays)}]}],
    }


def test_apply_special_teams_derivations_parses_impact_metrics_and_two_point_events() -> None:
    pbp_entry = {
        "abbr": "UW",
        "abbr_aliases": ["UW"],
        "games": [
            _game(
                _play(
                    "OSU punt 45 yards to the UW20 Mohammed return 25 yards to the UW45",
                    offense="OSU",
                    yards=25,
                ),
                _play(
                    "WASH punt 48 yards to the OSU40 return 12 yards to the OSU52",
                    offense="WASH",
                    yards=12,
                ),
                _play(
                    "OSU 42 yard field goal BLOCKED by UW recovered by UW return 65 yards TOUCHDOWN",
                    offense="OSU",
                    is_scoring=True,
                ),
                _play(
                    "OSU punt BLOCKED by UW recovered by UW at the OSU10",
                    offense="OSU",
                ),
                _play(
                    "WASH onside kickoff recovered by UW at the UW45",
                    offense="WASH",
                ),
                _play(
                    "#15 WASH pass attempt SUCCESSFUL TWO-POINT CONVERSION",
                    offense="WASH",
                    is_scoring=True,
                ),
                _play(
                    "OSU rush attempt FAILED TWO-POINT CONVERSION",
                    offense="OSU",
                    is_scoring=False,
                ),
            )
        ],
        "xml_stats": {
            "special_teams": {"UW": {"games": 1, "fg_attempts": 0, "fg_made": 0}},
            "two_point": {
                "UW": {
                    "games": 1,
                    "two_point_attempts": 0,
                    "two_point_conversions": 0,
                    "two_point_allowed_attempts": 0,
                    "two_point_allowed_conversions": 0,
                }
            },
        },
    }

    warnings = loaders._apply_special_teams_play_tree_derivations("Washington", pbp_entry)

    game = pbp_entry["games"][0]
    st = game["special_teams"]
    assert st["punt_returns"] == 1
    assert st["punt_return_yards"] == 25
    assert st["punt_returns_allowed"] == 1
    assert st["punt_return_yards_allowed"] == 12
    assert st["fg_blocks"] == 1
    assert st["punt_blocks"] == 1
    assert st["special_teams_tds"] == 1
    assert st["onside_kicks_attempted"] == 1
    assert st["onside_kicks_recovered"] == 1
    assert game["two_pt_attempts"] == 1
    assert game["two_pt_conversions"] == 1
    assert game["two_pt_pass_attempts"] == 1
    assert game["two_pt_pass_conversions"] == 1
    assert game["opp_two_pt_attempts"] == 1
    assert game["opp_two_pt_conversions"] == 0
    assert any("derived two-point totals differ from XML" in warning for warning in warnings)


def test_apply_special_teams_derivations_treats_scoring_context_failed_tries_as_failed() -> None:
    pbp_entry = {
        "abbr": "WSU",
        "abbr_aliases": ["WSU"],
        "games": [
            {
                "game_number": 1,
                "opponent_abbr": "SDS",
                "opponent": "San Diego State",
                "play_tree": [
                    {
                        "quarter": 2,
                        "drives": [
                            {
                                "plays": [
                                    _play(
                                        "WSU - Harris,Ryan rush attempt failed.",
                                        offense="WSU",
                                        is_scoring=True,
                                    ),
                                    _play(
                                        "SDS - Crum,Kyle rush attempt failed.",
                                        offense="SDS",
                                        is_scoring=True,
                                    ),
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
        "xml_stats": {
            "two_point": {
                "WSU": {
                    "games": 1,
                    "two_point_attempts": 1,
                    "two_point_conversions": 0,
                    "two_point_allowed_attempts": 1,
                    "two_point_allowed_conversions": 0,
                }
            }
        },
    }

    warnings = loaders._apply_special_teams_play_tree_derivations("Washington State", pbp_entry)

    game = pbp_entry["games"][0]
    assert game["two_pt_attempts"] == 1
    assert game["two_pt_conversions"] == 0
    assert game["two_pt_rush_attempts"] == 1
    assert game["two_pt_rush_conversions"] == 0
    assert game["opp_two_pt_attempts"] == 1
    assert game["opp_two_pt_conversions"] == 0
    assert not any("derived two-point totals differ from XML" in warning for warning in warnings)


def test_special_teams_markdown_uses_na_for_last3_two_point_when_no_game_level_signal() -> None:
    team = {
        "display_name": "Washington",
        "has_pbp": True,
        "pbp_entry": {
            "games": [{"game_number": 1, "opponent": "OSU"}],
            "xml_stats": {},
            "cfbstats": {"two_point_totals": {}},
        },
    }
    opponent = {"display_name": "Ohio State", "has_pbp": False}

    md = special_teams.build(team, opponent)["md_content"]

    assert "- Last 3 2PT O/D: N/A · N/A" in md


def test_apply_special_teams_derivations_does_not_reverse_kickoff_return_side() -> None:
    pbp_entry = {
        "abbr": "UW",
        "abbr_aliases": ["UW"],
        "games": [
            _game(
                _play(
                    "UW kickoff 65 yards to the OSU00 Smith return 20 yards to the OSU20",
                    offense="UW",
                    yards=20,
                )
            )
        ],
        "xml_stats": {},
    }

    loaders._apply_special_teams_play_tree_derivations("Washington", pbp_entry)

    st = pbp_entry["games"][0]["special_teams"]
    assert st["kickoff_returns"] == 0
    assert st["kickoff_return_yards"] == 0
