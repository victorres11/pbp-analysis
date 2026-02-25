from scripts.game_prep_brief import loaders
from scripts.game_prep_brief.sections import zones


def test_derive_game_detail_stats_green_zone_is_inside_30() -> None:
    play_tree = [
        {
            "drives": [
                {
                    "plays": [
                        {
                            "offense": "TEAM",
                            "is_scrimmage_play": True,
                            "is_no_play": False,
                            "spot": "OPP35",
                            "description": "Rush for 5 yards",
                            "down_distance": "1st and 10",
                        }
                    ]
                },
                {
                    "plays": [
                        {
                            "offense": "TEAM",
                            "is_scrimmage_play": True,
                            "is_no_play": False,
                            "spot": "OPP20",
                            "description": "Pass complete for touchdown",
                            "down_distance": "1st and 10",
                        }
                    ]
                },
            ]
        }
    ]

    stats = loaders._derive_game_detail_stats(play_tree, "TEAM", "OPP")
    assert stats["green_zone_trips"] == 1
    assert stats["red_zone_trips"] == 1
    assert stats["tight_red_zone_trips"] == 0


def test_team_zone_stats_xml_efficiency_uses_displayed_counts() -> None:
    team = {
        "pbp_entry": {
            "xml_source": True,
            "xml_stats": {
                "red_zone": {
                    "TEAM": {
                        "games": 1,
                        "rz_trips": 10,
                        "rz_tds": 6,
                        "rz_fgs": 2,
                        "rz_td_rate": 0.6,
                        "rz_conversion_rate": 0.1,
                    }
                }
            },
            "games": [],
        }
    }

    stats = zones._team_zone_stats(team)
    assert stats["rz_td_pct"] == 60.0
    assert stats["rz_eff"] == 80.0


def test_scoring_zone_display_order_is_green_red_tight() -> None:
    team = {
        "display_name": "Team A",
        "has_pbp": True,
        "stats": {},
        "last_n": {"actual_n": 0, "required_n": 3},
        "pbp_entry": {
            "games": [
                {
                    "green_zone_trips": 3,
                    "green_zone_tds": 2,
                    "green_zone_fgs": 1,
                    "green_zone_failed": 0,
                    "red_zone_trips": 2,
                    "red_zone_tds": 1,
                    "red_zone_fgs": 1,
                    "tight_red_zone_trips": 1,
                    "tight_red_zone_tds": 1,
                    "tight_red_zone_fgs": 0,
                }
            ]
        },
    }
    opponent = {
        "display_name": "Team B",
        "has_pbp": False,
        "stats": {},
        "last_n": {"actual_n": 0, "required_n": 3},
    }

    section = zones.build(team, opponent)
    html = section["html_content"]
    assert html.find("<h4>Green Zone (Inside 30)</h4>") < html.find("<h4>Red Zone</h4>")
    assert html.find("<h4>Red Zone</h4>") < html.find("<h4>Tight Red Zone (Inside 10)</h4>")
