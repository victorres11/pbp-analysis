from __future__ import annotations

import unittest
from types import SimpleNamespace

from generate_data import compute_two_point_stats


def make_play(
    description: str,
    *,
    offense: str,
    is_no_play: bool = False,
    is_scoring: bool = False,
    quarter: int = 4,
    clock: str = "",
):
    return SimpleNamespace(
        description=description,
        offense=offense,
        is_no_play=is_no_play,
        is_scoring=is_scoring,
        quarter=quarter,
        clock=clock,
    )


class TestTwoPointStats(unittest.TestCase):
    def test_counts_uns_kickoff_enforcement_no_play_as_success(self) -> None:
        play = make_play(
            "#15 K.Anderson pass attempt Successful. Arizona St. 21, Colorado 14. "
            "PENALTY COLO UNS: Unsportsmanlike Conduct 15 yards from ASU35 to ASU50. NO PLAY.",
            offense="ASU",
            is_no_play=True,
            is_scoring=True,
        )
        stats = compute_two_point_stats([play], "ASU", "COLO", "Colorado")
        self.assertEqual(stats["two_pt_attempts"], 1)
        self.assertEqual(stats["two_pt_conversions"], 1)
        self.assertEqual(stats["two_pt_pass_attempts"], 1)
        self.assertEqual(stats["two_pt_pass_conversions"], 1)

    def test_excludes_no_play_without_uns_kickoff_pattern(self) -> None:
        play = make_play(
            "#15 W.Hammond pass attempt failed PENALTY ASU Holding 2 yards from ASU03 to ASU01. NO PLAY.",
            offense="ASU",
            is_no_play=True,
            is_scoring=False,
        )
        stats = compute_two_point_stats([play], "ASU", "TTU", "Texas Tech")
        self.assertEqual(stats["two_pt_attempts"], 0)
        self.assertEqual(stats["two_pt_conversions"], 0)


if __name__ == "__main__":
    unittest.main()
