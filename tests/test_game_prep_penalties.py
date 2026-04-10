import json

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


def test_aggregate_derives_team_penalties_without_counting_opponent_raw_aliases() -> None:
    team = {
        "pbp_entry": {
            "abbr": "MICH",
            "abbr_aliases": ["MICH", "UOM"],
            "games": [
                {
                    "game_number": 1,
                    "opponent": "Washington",
                    "opponent_abbr": "UW",
                    "play_tree": [
                        {
                            "quarter": 1,
                            "drives": [
                                {
                                    "plays": [
                                        {
                                            "quarter": 1,
                                            "offense": "MICH",
                                            "description": "PENALTY Before the snap, UM False Start on LT enforced 5 yards from the MICH25 to the MICH20.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 1,
                                            "offense": "MICH",
                                            "description": "PENALTY Before the snap, UM Delay Of Game enforced 5 yards from the MICH20 to the MICH15.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 1,
                                            "offense": "UW",
                                            "description": "PENALTY WASH False Start (RT) 5 yards from the UW30 to the UW25. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 1,
                                            "offense": "UW",
                                            "description": "Shotgun QB pass incomplete deep right PENALTY UOM Pass Interference (CB) 15 yards from the MICH35 to the UW50, 1ST DOWN. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 1,
                                            "offense": "UW",
                                            "description": "PENALTY UOM Offside 5 yards from the UW40 to the UW35. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    }

    agg = penalties._aggregate(team)

    assert agg["total"] == 4
    assert agg["yards"] == 30
    assert agg["pi_allowed"] == 1
    assert agg["per_game"][0]["count"] == 4
    assert agg["per_game"][0]["yards"] == 30


def test_aggregate_skips_offsetting_zero_yard_penalties() -> None:
    team = {
        "pbp_entry": {
            "abbr": "MICH",
            "abbr_aliases": ["MICH", "UOM"],
            "games": [
                {
                    "game_number": 1,
                    "opponent": "OSU",
                    "opponent_abbr": "OSU",
                    "play_tree": [
                        {
                            "quarter": 1,
                            "drives": [
                                {
                                    "plays": [
                                        {
                                            "quarter": 1,
                                            "offense": "OSU",
                                            "description": "PENALTY UOM UNS: Unsportsmanlike Conduct (Barham,Jaishawn) 3 yards from UOM05 to UOM02, 1ST DOWN. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 2,
                                            "offense": "MICH",
                                            "description": "PENALTY UOM UNS: Unsportsmanlike Conduct offsetting OSU UNS: Unsportsmanlike Conduct offsetting. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 4,
                                            "offense": "OSU",
                                            "description": "PENALTY UOM UNS: Unsportsmanlike Conduct offsetting OSU UNS: Unsportsmanlike Conduct offsetting. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    }

    agg = penalties._aggregate(team)

    assert agg["total"] == 1
    assert agg["yards"] == 3
    assert agg["per_game"][0]["count"] == 1
    assert agg["per_game"][0]["yards"] == 3


def test_aggregate_uses_official_game_totals_and_surfaces_deltas() -> None:
    team = {
        "slug": "michigan",
        "display_name": "Michigan",
        "penalty_totals_by_game": {
            "date:2025-09-06": {"total_count": 3, "total_yards": 32},
        },
        "pbp_entry": {
            "abbr": "MICH",
            "abbr_aliases": ["MICH"],
            "games": [
                {
                    "game_number": 2,
                    "date": "2025-09-06",
                    "opponent": "OKL",
                    "opponent_abbr": "OKL",
                    "play_tree": [
                        {
                            "quarter": 3,
                            "drives": [
                                {
                                    "plays": [
                                        {
                                            "quarter": 3,
                                            "offense": "MICH",
                                            "description": "Shotgun QB rush PENALTY MICH Holding 8 yards from MICH17 to MICH09. NO PLAY.",
                                            "is_no_play": True,
                                        }
                                    ]
                                }
                            ],
                        },
                        {
                            "quarter": 4,
                            "drives": [
                                {
                                    "plays": [
                                        {
                                            "quarter": 4,
                                            "offense": "OKL",
                                            "description": "Shotgun QB rush PENALTY MICH Face Mask 9 yards from MICH17 to MICH08, 1ST DOWN.",
                                            "is_no_play": False,
                                        }
                                    ]
                                }
                            ],
                        },
                    ],
                }
            ],
            "stats": {
                "penalties": {
                    "TEAM": {
                        "games": 1,
                        "total_penalties": 3,
                        "total_penalty_yards": 32,
                    }
                }
            },
        },
    }

    agg = penalties._aggregate(team)

    assert agg["total"] == 3
    assert agg["yards"] == 32
    assert agg["season_unattributed_count"] == 1
    assert agg["season_unattributed_yards"] == 15
    assert agg["season_residual_count"] == 0
    assert agg["season_residual_yards"] == 0
    assert agg["per_game"][0]["count"] == 2
    assert agg["per_game"][0]["yards"] == 17
    assert agg["per_game"][0]["official_count"] == 3
    assert agg["per_game"][0]["official_yards"] == 32
    assert agg["per_game"][0]["delta_count"] == 1
    assert agg["per_game"][0]["delta_yards"] == 15


def test_aggregate_skips_official_game_totals_when_they_worsen_season_reconciliation() -> None:
    team = {
        "slug": "indiana",
        "display_name": "Indiana",
        "penalty_totals_by_game": {
            "date:2025-09-06": {"total_count": 5, "total_yards": 40},
        },
        "pbp_entry": {
            "abbr": "IND",
            "abbr_aliases": ["IND"],
            "games": [
                {
                    "game_number": 1,
                    "date": "2025-09-06",
                    "opponent": "KSU",
                    "opponent_abbr": "KSU",
                    "play_tree": [
                        {
                            "quarter": 1,
                            "drives": [
                                {
                                    "plays": [
                                        {
                                            "quarter": 1,
                                            "offense": "IND",
                                            "description": "PENALTY IND False Start enforced 5 yards from the IND25 to the IND20.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 1,
                                            "offense": "KSU",
                                            "description": "Shotgun QB pass incomplete PENALTY IND Pass Interference 15 yards from the IND35 to the 50, 1ST DOWN. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
            "stats": {
                "penalties": {
                    "TEAM": {
                        "games": 1,
                        "total_penalties": 2,
                        "total_penalty_yards": 20,
                    }
                }
            },
        },
    }

    agg = penalties._aggregate(team)

    assert agg["total"] == 2
    assert agg["yards"] == 20
    assert agg["season_unattributed_count"] == 0
    assert agg["season_unattributed_yards"] == 0
    assert agg["season_residual_count"] == 0
    assert agg["season_residual_yards"] == 0
    assert agg["per_game"][0]["official_count"] is None
    assert agg["per_game"][0]["official_yards"] is None
    assert agg["per_game"][0]["delta_count"] == 0
    assert agg["per_game"][0]["delta_yards"] == 0


def test_load_raw_game_penalty_totals_prefers_penalty_summary_over_team_stats(
    tmp_path, monkeypatch
) -> None:
    team_dir = tmp_path / "sample-team"
    team_dir.mkdir()
    payload = {
        "meta": {"game_date": "2025-08-30"},
        "team_names": ["Old Dominion", "Indiana"],
        "teams": ["ODU", "IND"],
        "team_stats": {
            "IND": {
                "penalties": 3,
                "penalty_yards": 25,
            }
        },
        "penalty_summary": {
            "IND": {
                "total_penalties": 2,
                "total_penalty_yards": 20,
            }
        },
    }
    (team_dir / "game_1.json").write_text(json.dumps(payload))
    penalties._load_raw_game_penalty_totals.cache_clear()
    monkeypatch.setattr(penalties, "_raw_game_briefs_root", lambda: tmp_path)

    totals = penalties._load_raw_game_penalty_totals("sample-team", "Indiana")

    assert totals["2025-08-30"]["total_count"] == 2
    assert totals["2025-08-30"]["total_yards"] == 20
    penalties._load_raw_game_penalty_totals.cache_clear()


def test_aggregate_recovers_accepted_penalties_after_declined_clauses() -> None:
    team = {
        "slug": "michigan",
        "display_name": "Michigan",
        "penalty_totals_by_game": {
            "date:2025-11-08": {"total_count": 4, "total_yards": 39},
        },
        "pbp_entry": {
            "abbr": "UM",
            "abbr_aliases": ["MICH", "UM", "UOM", "U-M"],
            "games": [
                {
                    "game_number": 11,
                    "date": "2025-11-08",
                    "opponent": "OPP",
                    "opponent_abbr": "OPP",
                    "play_tree": [
                        {
                            "quarter": 2,
                            "drives": [
                                {
                                    "plays": [
                                        {
                                            "quarter": 2,
                                            "offense": "OPP",
                                            "description": "Pass incomplete PENALTY MICH Offside declined MICH Personal Foul (Pierce,Trey) 15 yards from OPP27 to OPP42, 1ST DOWN. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 4,
                                            "offense": "OPP",
                                            "description": "Pass deep right complete PENALTY UM Offsides on BARHAM, Jaishawn declined UM Targeting on HILLMAN, Brandyn enforced half the distance from the goal, 2 yards from the end of the play at the UM3 to the UM1 and results in automatic 1ST DOWN.",
                                            "is_no_play": False,
                                        },
                                        {
                                            "quarter": 3,
                                            "offense": "OPP",
                                            "description": "Pass incomplete PENALTY UOM Offside declined UOM Pass Interference (Hill,Jyaire) 7 yards from UOM09 to UOM02, 1ST DOWN. NO PLAY.",
                                            "is_no_play": True,
                                        },
                                        {
                                            "quarter": 1,
                                            "offense": "UM",
                                            "description": "PENALTY UM Unsportsmanlike Conduct on LINK, Evan enforced 15 yards from the UM12 to the UM27, clock 09:49.",
                                            "is_no_play": True,
                                        },
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
            "stats": {
                "penalties": {
                    "TEAM": {
                        "games": 1,
                        "total_penalties": 4,
                        "total_penalty_yards": 39,
                    }
                }
            },
        },
    }

    agg = penalties._aggregate(team)

    assert agg["total"] == 4
    assert agg["yards"] == 39
    assert agg["pi_allowed"] == 1
    assert agg["season_unattributed_count"] == 0
    assert agg["season_unattributed_yards"] == 0
    assert agg["per_game"][0]["count"] == 4
    assert agg["per_game"][0]["yards"] == 39
    assert agg["per_game"][0]["official_count"] is None
    assert agg["per_game"][0]["official_yards"] is None
    assert agg["per_game"][0]["delta_count"] == 0
    assert agg["per_game"][0]["delta_yards"] == 0


def test_aggregate_ignores_penalties_inside_original_play_review_notes() -> None:
    team = {
        "pbp_entry": {
            "abbr": "IND",
            "abbr_aliases": ["IND"],
            "games": [
                {
                    "game_number": 9,
                    "date": "2025-11-01",
                    "opponent": "UMD",
                    "opponent_abbr": "UMD",
                    "play_tree": [
                        {
                            "quarter": 4,
                            "drives": [
                                {
                                    "plays": [
                                        {
                                            "quarter": 4,
                                            "offense": "UMD",
                                            "description": "After official review, the ruling on the field was overturned: Fumble (Original Play: (00:54) No Huddle-Shotgun #12 K.Martin pass complete short right to #81 J.Powell-Wonson caught at IND40, for 10 yards to the IND40 (#16 J.Boyd; #38 K.McConnell), 1ST DOWN, PENALTY IND Personal Foul (#33 G.Reese) 15 yards from IND40 to IND25, 1ST DOWN).",
                                            "is_no_play": False,
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    }

    agg = penalties._aggregate(team)

    assert agg["total"] == 0
    assert agg["yards"] == 0
    assert agg["per_game"][0]["count"] == 0
    assert agg["per_game"][0]["yards"] == 0
