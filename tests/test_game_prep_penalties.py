from scripts.game_prep_brief.sections import penalties


def test_aggregate_prefers_structured_penalty_stats_for_pi_and_groups() -> None:
    team = {
        "pbp_entry": {
            "games": [
                {
                    "game_number": 1,
                    "opponent": "OPP",
                    "penalty_details": [
                        {
                            "accepted": True,
                            "yards": 15,
                            "offense_or_defense": "defense",
                            "type": "Pass Interference",
                            "description": "PENALTY on TEAM, Pass Interference, 15 yards.",
                        }
                    ],
                }
            ],
            "stats": {
                "penalties": {
                    "TEAM": {
                        "games": 1,
                        "offensive_penalties": 2,
                        "offensive_penalty_yards": 10,
                        "defensive_penalties": 3,
                        "defensive_penalty_yards": 25,
                        "procedural_penalties": 1,
                        "procedural_penalty_yards": 5,
                        "live_ball_penalties": 4,
                        "live_ball_penalty_yards": 30,
                        "pass_interference_drawn": 2,
                        "pass_interference_allowed": 1,
                        "total_penalties": 5,
                        "total_penalty_yards": 35,
                    }
                }
            },
        }
    }

    agg = penalties._aggregate(team)
    assert agg["total"] == 5
    assert agg["yards"] == 35
    assert agg["by_group"]["procedural"]["count"] == 1
    assert agg["by_group"]["live_ball"]["count"] == 4
    assert agg["pi_drawn"] == 2
    assert agg["pi_allowed"] == 1


def test_aggregate_without_structured_stats_does_not_infer_pi_from_side_only() -> None:
    team = {
        "pbp_entry": {
            "games": [
                {
                    "game_number": 1,
                    "opponent": "OPP",
                    "penalty_details": [
                        {
                            "accepted": True,
                            "yards": 15,
                            "offense_or_defense": "defense",
                            "type": "Pass Interference",
                            "description": "PENALTY on TEAM, Pass Interference, 15 yards.",
                        }
                    ],
                }
            ]
        }
    }

    agg = penalties._aggregate(team)
    assert agg["total"] == 1
    assert agg["pi_drawn"] == 0
    assert agg["pi_allowed"] == 0
