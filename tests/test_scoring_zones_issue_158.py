from scripts.game_prep_brief.sections import zones


def test_team_zone_stats_uses_bundle_game_row_fields_without_play_tree_derivation() -> None:
    team = {
        "pbp_entry": {
            "games": [
                {
                    "green_zone_trips": 1,
                    "green_zone_tds": 1,
                    "green_zone_fgs": 0,
                    "green_zone_failed": 0,
                    "red_zone_trips": 1,
                    "red_zone_tds": 1,
                    "red_zone_fgs": 0,
                    "tight_red_zone_trips": 0,
                    "tight_red_zone_tds": 0,
                    "tight_red_zone_fgs": 0,
                    # The play tree intentionally lacks enough context to derive
                    # the same zone counts. Section output should trust bundle rows.
                    "play_tree": [],
                }
            ]
        }
    }

    stats = zones._team_zone_stats(team)
    assert stats["gz_trips"] == 1
    assert stats["rz_trips"] == 1
    assert stats["trz_trips"] == 0


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
