from __future__ import annotations

import unittest
from types import SimpleNamespace

from generate_data import should_count_explosive_play


def make_play(
    description: str,
    *,
    offense: str = "ASU",
    yards: int | None = 0,
    is_no_play: bool = False,
):
    return SimpleNamespace(
        description=description,
        offense=offense,
        yards=yards,
        is_no_play=is_no_play,
    )


class TestExplosivePlayFilters(unittest.TestCase):
    def test_excludes_nullified_by_penalty_without_no_play_marker(self) -> None:
        play = make_play(
            "No Huddle-Shotgun #10 S.Leavitt pass complete short right to #3 R.Brown "
            "caught at ASU20, for 75 yards to the NAU00 TOUCHDOWN nullified by penalty, "
            "clock 08:02 PENALTY ASU Holding (#12",
            yards=75,
            is_no_play=False,
        )
        self.assertFalse(should_count_explosive_play(play, "ASU"))

    def test_keeps_valid_explosive_play(self) -> None:
        play = make_play(
            "No Huddle-Shotgun #10 S.Leavitt pass complete short right to #3 R.Brown "
            "caught at ASU20, for 75 yards to the NAU00 TOUCHDOWN.",
            yards=75,
            is_no_play=False,
        )
        self.assertTrue(should_count_explosive_play(play, "ASU"))


if __name__ == "__main__":
    unittest.main()
