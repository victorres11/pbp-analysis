from scripts.game_prep_brief import loaders
from scripts.game_prep_brief.sections import turnovers


def _play(
    description: str,
    *,
    offense: str,
    clock: str,
    quarter: int,
    is_turnover: bool = False,
    is_no_play: bool = False,
    is_scrimmage_play: bool = True,
) -> dict:
    return {
        "quarter": quarter,
        "offense": offense,
        "clock": clock,
        "description": description,
        "is_turnover": is_turnover,
        "is_no_play": is_no_play,
        "is_scrimmage_play": is_scrimmage_play,
    }


def _drive(*plays: dict, offense: str | None = None) -> dict:
    return {
        "offense": offense,
        "plays": list(plays),
    }


def _raw_game(*quarters: dict) -> dict:
    return {
        "team": "UW",
        "opponent_abbr": "OSU",
        "play_tree": list(quarters),
    }


def _quarter(number: int, *drives: dict) -> dict:
    return {"quarter": number, "drives": list(drives)}


def test_enrich_post_turnover_drives_adds_same_quarter_top() -> None:
    turnover_desc = "OSU pass intercepted by UW at the UW35"
    raw_game = _raw_game(
        _quarter(
            1,
            _drive(
                _play(turnover_desc, offense="OSU", clock="10:00", quarter=1, is_turnover=True),
                offense="OSU",
            ),
            _drive(
                _play("UW rush for 4", offense="UW", clock="9:40", quarter=1),
                _play("UW rush for 6", offense="UW", clock="9:05", quarter=1),
                _play("UW field goal good", offense="UW", clock="8:35", quarter=1),
                offense="UW",
            ),
        )
    )

    entries = [
        {
            "side": "team_gained",
            "quarter": 1,
            "clock": "10:00",
            "turnover_description": turnover_desc,
            "drive_result": "FG",
            "num_plays": 3,
            "total_yards": 19,
            "points_scored": 3,
            "turnover_type": "INT",
        }
    ]

    enriched = loaders._enrich_post_turnover_drives(
        raw_game,
        entries,
        team_aliases={"UW"},
        opp_aliases={"OSU"},
    )

    assert enriched[0]["drive_top_seconds"] == 65
    assert enriched[0]["drive_top"] == "1:05"


def test_enrich_post_turnover_drives_spans_quarter_boundary() -> None:
    turnover_desc = "OSU rush fumbled and recovered by UW at the UW20"
    raw_game = _raw_game(
        _quarter(
            1,
            _drive(
                _play(turnover_desc, offense="OSU", clock="0:20", quarter=1, is_turnover=True),
                offense="OSU",
            ),
            _drive(
                _play("UW rush for 5", offense="UW", clock="0:15", quarter=1),
                _play("UW rush for 7", offense="UW", clock="0:03", quarter=1),
                offense="UW",
            ),
        ),
        _quarter(
            2,
            _drive(
                _play("UW rush for 3", offense="UW", clock="15:00", quarter=2),
                _play("UW punt", offense="UW", clock="14:38", quarter=2),
                offense="UW",
            )
        ),
    )

    entries = [
        {
            "side": "team_gained",
            "quarter": 1,
            "clock": "0:20",
            "turnover_description": turnover_desc,
            "drive_result": "PUNT",
            "num_plays": 4,
            "total_yards": 15,
            "points_scored": 0,
            "turnover_type": "FUM",
        }
    ]

    enriched = loaders._enrich_post_turnover_drives(
        raw_game,
        entries,
        team_aliases={"UW"},
        opp_aliases={"OSU"},
    )

    assert enriched[0]["drive_top_seconds"] == 37
    assert enriched[0]["drive_top"] == "0:37"


def test_enrich_post_turnover_drives_sets_zero_top_for_defensive_touchdown() -> None:
    turnover_desc = "OSU pass intercepted by UW and returned for touchdown"
    raw_game = _raw_game(
        _quarter(
            1,
            _drive(
                _play(turnover_desc, offense="OSU", clock="11:22", quarter=1, is_turnover=True),
                offense="OSU",
            )
        )
    )

    entries = [
        {
            "side": "team_gained",
            "quarter": 1,
            "clock": "11:22",
            "turnover_description": turnover_desc,
            "drive_result": "DEF TD",
            "num_plays": 0,
            "total_yards": 0,
            "points_scored": 7,
            "turnover_type": "INT",
        }
    ]

    enriched = loaders._enrich_post_turnover_drives(
        raw_game,
        entries,
        team_aliases={"UW"},
        opp_aliases={"OSU"},
    )

    assert enriched[0]["drive_top_seconds"] == 0
    assert enriched[0]["drive_top"] == "0:00"


def test_enrich_post_turnover_drives_omits_top_for_overtime_drive() -> None:
    turnover_desc = "OSU rush fumbled and recovered by UW in overtime"
    raw_game = _raw_game(
        _quarter(
            5,
            _drive(
                _play(turnover_desc, offense="OSU", clock="0:00", quarter=5, is_turnover=True),
                offense="OSU",
            ),
            _drive(
                _play("UW rush for 2", offense="UW", clock="0:00", quarter=5),
                _play("UW field goal good", offense="UW", clock="0:00", quarter=5),
                offense="UW",
            ),
        )
    )

    entries = [
        {
            "side": "team_gained",
            "quarter": 5,
            "clock": "0:00",
            "turnover_description": turnover_desc,
            "drive_result": "FG",
            "num_plays": 2,
            "total_yards": 2,
            "points_scored": 3,
            "turnover_type": "FUM",
        }
    ]

    enriched = loaders._enrich_post_turnover_drives(
        raw_game,
        entries,
        team_aliases={"UW"},
        opp_aliases={"OSU"},
    )

    assert "drive_top_seconds" not in enriched[0]
    assert "drive_top" not in enriched[0]


def test_turnovers_html_renders_drive_top_detail() -> None:
    team = {
        "display_name": "Washington",
        "has_pbp": True,
        "stats": {
            "source_points_off_turnovers_for": 7,
            "source_points_off_turnovers_against": 0,
            "source_post_turnover_drives_for": 1,
            "source_post_turnover_drives_against": 0,
        },
        "last_n": {"actual_n": 1, "required_n": 3},
        "pbp_entry": {
            "aggregates": {"turnover_margin": 1},
            "games": [
                {
                    "game_number": 1,
                    "opponent": "Ohio State",
                    "turnovers_gained": 1,
                    "turnovers_lost": 0,
                    "interceptions_gained": 1,
                    "interceptions_lost": 0,
                    "fumbles_gained": 0,
                    "fumbles_lost": 0,
                    "points_off_turnovers_for": 7,
                    "points_off_turnovers_against": 0,
                    "post_turnover_drives": [
                        {
                            "side": "team_gained",
                            "drive_result": "TD",
                            "total_yards": 42,
                            "num_plays": 5,
                            "drive_top": "1:05",
                            "points_scored": 7,
                            "turnover_type": "INT",
                        }
                    ],
                }
            ],
        },
    }

    html = turnovers.build(team, team)["html_content"]

    assert "TOP 1:05" in html
