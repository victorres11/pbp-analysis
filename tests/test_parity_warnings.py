from scripts.game_prep_brief import loaders


def test_third_down_parity_gap_surfaces_small_remaining_delta() -> None:
    pbp_entry = {
        "games": [
            {
                "third_down_attempts": 199,
                "third_down_conversions": 113,
            }
        ],
        "cfbstats": {
            "rankings": {
                "all": {
                    "third_down": {
                        "value": "56.50",
                    }
                }
            }
        },
    }

    warning = loaders._third_down_parity_gap("Indiana", pbp_entry)

    assert warning == "Indiana: 3rd-down parity delta +0.3 pts (PBP 113/199=56.8% vs CFBStats 56.5%)"
