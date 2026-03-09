import inspect

from scripts.game_prep_brief import loaders


def test_convert_xml_bundle_team_backfills_game_rows_from_bundle_stats() -> None:
    payload = {
        "team_name": "Washington",
        "games_parsed": 1,
        "games": [
            {
                "week": 1,
                "game_date": "2025-09-01",
                "is_home": True,
                "opponent": "OSU",
                "opponent_abbr": "OSU",
                "points_for": 24,
                "points_against": 17,
                "total_plays": 61,
                "play_tree": [],
            }
        ],
        "stats": {
            "scoring": {"UW": {"games": 1}, "OSU": {"games": 1, "points_for": 24, "points_against": 17}},
            "total_yardage": {"UW": {"games": 1}, "OSU": {"games": 1, "total_offense_yards": 357}},
            "explosives": {
                "UW": {"games": 1},
                "OSU": {"games": 1, "explosive_pass": 3, "explosive_run": 2, "explosives": 5},
            },
            "negative_plays": {
                "UW": {"games": 1},
                "OSU": {"games": 1, "negative_plays": 4, "negative_plays_forced": 7},
            },
            "turnovers": {
                "UW": {"games": 1, "turnovers": 0, "turnovers_forced": 1},
                "OSU": {
                    "games": 1,
                    "turnovers": 1,
                    "turnovers_forced": 2,
                    "interceptions": 1,
                    "interceptions_forced": 1,
                    "fumbles_lost": 0,
                    "fumbles_recovered": 1,
                },
            },
            "points_off_turnovers": {
                "UW": {"games": 1},
                "OSU": {"games": 1, "points_off_turnovers": 7, "points_off_turnovers_allowed": 3},
            },
            "red_zone": {
                "UW": {"games": 1},
                "OSU": {"games": 1, "rz_trips": 3, "rz_tds": 2, "rz_fgs": 1, "rz_td_rate": 0.67},
            },
            "third_down": {"UW": {"games": 1}, "OSU": {"games": 1, "third_down_attempts": 10, "third_down_conversions": 5}},
            "fourth_down": {"UW": {"games": 1}, "OSU": {"games": 1, "attempts": 2, "conversions": 1}},
            "penalties": {
                "UW": {"games": 1, "total_penalties_pg": 5.0},
                "OSU": {
                    "games": 1,
                    "total_penalties": 5,
                    "total_penalty_yards": 45,
                    "offensive_penalties": 3,
                    "defensive_penalties": 2,
                },
            },
            "two_point": {
                "UW": {"games": 1},
                "OSU": {
                    "games": 1,
                    "two_point_attempts": 1,
                    "two_point_conversions": 1,
                    "two_point_allowed_attempts": 2,
                    "two_point_allowed_conversions": 1,
                },
            },
            "schedule": {"UW": {"games": 1}},
        },
    }

    converted = loaders._convert_xml_bundle_team("washington", payload)
    game = converted["games"][0]

    assert game["total_yards"] == 357
    assert game["explosive_passes"] == 3
    assert game["explosive_rushes"] == 2
    assert game["negative_plays"] == 4
    assert game["turnovers_lost"] == 1
    assert game["turnovers_gained"] == 2
    assert game["interceptions_lost"] == 1
    assert game["interceptions_gained"] == 1
    assert game["fumbles_gained"] == 1
    assert game["points_off_turnovers_for"] == 7
    assert game["points_off_turnovers_against"] == 3
    assert game["red_zone_trips"] == 3
    assert game["4th_down_attempts"] == 2
    assert game["4th_down_conversions"] == 1
    assert game["penalty_yards"] == 45
    assert game["penalties_offense"] == 3
    assert game["two_pt_attempts"] == 1
    assert game["opp_two_pt_attempts"] == 2


def test_gather_team_data_uses_offline_cfbstats_artifacts() -> None:
    assert not hasattr(loaders, "_fetch_live_rankings")
    assert not hasattr(loaders, "_fetch_live_turnover_split")
    assert not hasattr(loaders, "_verify_cfbstats_metrics")
    assert not hasattr(loaders, "_rollup_game_from_play_tree")
    assert not hasattr(loaders, "_derive_game_detail_stats")
    assert not hasattr(loaders, "_derive_turnover_drive_stats")
    assert "allow_live_enrichment" not in inspect.signature(loaders.gather_team_data).parameters

    pbp_teams = {
        "washington": {
            "name": "Washington",
            "abbr": "UW",
            "abbr_aliases": ["UW"],
            "conference": "",
            "color": "#888888",
            "cfbstats": {"rankings": {"all": {}, "conf": {}, "nonconf": {}}, "two_point_totals": {}},
            "xml_rollups": {
                "turnovers": {"turnovers": 1, "turnovers_forced": 2, "interceptions": 1, "fumbles_lost": 0},
                "points_off_turnovers": {"points_off_turnovers": 7, "points_off_turnovers_allowed": 3},
            },
            "aggregates": {"turnover_margin": 1},
            "bye_weeks": [],
            "schedule": {"games": []},
            "games": [
                {
                    "game_number": 1,
                    "week": 1,
                    "date": "2025-09-01",
                    "is_home": True,
                    "opponent": "OSU",
                    "opponent_abbr": "OSU",
                    "points_for": 24,
                    "points_against": 17,
                    "total_plays": 61,
                    "total_yards": 357,
                    "turnovers_gained": 2,
                    "turnovers_lost": 1,
                    "interceptions_gained": 1,
                    "interceptions_lost": 1,
                    "fumbles_gained": 1,
                    "fumbles_lost": 0,
                    "points_off_turnovers_for": 7,
                    "points_off_turnovers_against": 3,
                    "post_turnover_drives": [],
                    "red_zone_trips": 3,
                    "red_zone_tds": 2,
                    "red_zone_fgs": 1,
                    "tight_red_zone_trips": 1,
                    "tight_red_zone_tds": 1,
                    "tight_red_zone_fgs": 0,
                    "green_zone_trips": 3,
                    "green_zone_tds": 2,
                    "green_zone_fgs": 1,
                    "green_zone_failed": 0,
                    "third_down_attempts": 10,
                    "third_down_conversions": 5,
                    "4th_down_attempts": 2,
                    "4th_down_conversions": 1,
                    "penalties": 5,
                    "penalty_yards": 45,
                    "penalties_offense": 3,
                    "penalties_defense": 2,
                    "penalties_special_teams": 0,
                    "two_pt_attempts": 1,
                    "two_pt_conversions": 1,
                    "opp_two_pt_attempts": 2,
                    "opp_two_pt_conversions": 1,
                    "play_tree": [],
                }
            ],
            "xml_stats": {"middle_eight": {}, "penalties": {}},
            "xml_source": True,
        }
    }
    snapshot = {
        "meta": {"artifact": "cfbstats_snapshot"},
        "teams": {
            "washington": {
                "team_name": "Washington",
                "team_slug": "washington",
                "conference": "Big Ten",
                "rankings": {
                    "all": {
                        "fourth_down": {"rank": 12, "value": "50.0", "conference": "Big Ten", "label": "fourth down", "total": 18}
                    },
                    "conf": {},
                    "nonconf": {},
                },
                "two_point_totals": {
                    "two_point_attempts": 3,
                    "two_point_conversions": 2,
                    "two_point_allowed_attempts": 4,
                    "two_point_allowed_conversions": 1,
                },
            }
        },
    }
    verification_report = {
        "meta": {"artifact": "cfbstats_bundle_verification_report"},
        "known_gaps": {
            "turnover_on_downs_definition_gap": {
                "id": "turnover_on_downs_definition_gap",
                "title": "Turnover-on-downs definition gap",
                "description": "Parser season totals include turnover-on-downs events.",
            }
        },
        "teams": {
            "washington": {
                "team_slug": "washington",
                "result": "warning",
                "summary": {"metric_results": {"pass": 1, "warning": 1, "fail": 0}},
                "metrics": {
                    "red_zone_td_pct": {
                        "label": "Red Zone TD%",
                        "status": "match",
                        "result": "pass",
                        "reason_id": None,
                        "comparison": {"parser_value": 66.7, "cfbstats_value": 66.7, "delta": 0.0, "tolerance": 0.11},
                    },
                    "turnover_margin": {
                        "label": "Turnover Margin",
                        "status": "special_case",
                        "result": "warning",
                        "reason_id": "turnover_on_downs_definition_gap",
                        "note": "parser counts turnover on downs",
                        "comparison": {"parser_value": 1.0, "cfbstats_value": 0.0, "delta": 1.0, "tolerance": 0.11},
                    },
                },
            }
        },
    }

    team = loaders.gather_team_data(
        pbp_teams,
        "Washington",
        2025,
        cfbstats_snapshot=snapshot,
        cfbstats_verification_report=verification_report,
    )

    assert team["conference"] == "Big Ten"
    assert team["pbp_entry"]["cfbstats"]["rankings"]["all"]["fourth_down"]["rank"] == 12
    assert team["pbp_entry"]["cfbstats"]["two_point_totals"]["two_point_conversions"] == 2
    assert team["cfbstats_verification"]["summary"]["match"] == 1
    assert team["cfbstats_verification"]["summary"]["special_case"] == 1
    assert team["cfbstats_verification"]["summary"]["warning"] == 1
    turnover_metric = next(metric for metric in team["cfbstats_verification"]["metrics"] if metric["key"] == "turnover_margin")
    assert turnover_metric["status"] == "special_case"
    assert turnover_metric["source"] == 0.0
    assert "Turnover-on-downs definition gap" in turnover_metric["note"]
