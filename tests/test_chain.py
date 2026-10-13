import unittest
from datetime import datetime

from btcmonitor.chain import calculate_halving_info, get_current_subsidy


class SubsidyTests(unittest.TestCase):
    def test_subsidy_halves_every_210000_blocks(self):
        for height, subsidy in (
            (0, 50.0),
            (209_999, 50.0),
            (210_000, 25.0),
            (630_000, 6.25),
            (840_000, 3.125),
            (1_049_999, 3.125),
            (1_050_000, 1.5625),
        ):
            with self.subTest(height=height):
                self.assertEqual(get_current_subsidy(height), subsidy)


class HalvingTests(unittest.TestCase):
    def test_blocks_until_next_halving(self):
        now = datetime(2026, 1, 1)
        self.assertEqual(calculate_halving_info(840_000, now)[0], 210_000)
        self.assertEqual(calculate_halving_info(1_049_999, now)[0], 1)

    def test_estimated_date_assumes_ten_minute_blocks(self):
        # 144 blocks a day: 1440 blocks is ten days
        self.assertEqual(calculate_halving_info(1_050_000 - 1440, datetime(2026, 1, 1))[1], "2026-01-11")


if __name__ == "__main__":
    unittest.main()
