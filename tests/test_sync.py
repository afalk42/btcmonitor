import unittest

from btcmonitor.sync import SyncRate


class SyncRateTests(unittest.TestCase):
    def test_no_estimate_until_samples_span_long_enough(self):
        rate = SyncRate(min_span_seconds=5)
        self.assertIsNone(rate.blocks_per_second)
        rate.add(0, 100, 0.10)
        rate.add(4, 140, 0.11)
        self.assertIsNone(rate.blocks_per_second)
        self.assertIsNone(rate.eta_seconds)
        rate.add(5, 150, 0.12)
        self.assertEqual(rate.blocks_per_second, 10.0)

    def test_eta_extrapolates_verification_progress_not_blocks(self):
        rate = SyncRate()
        rate.add(0, 100_000, 0.20)
        rate.add(100, 110_000, 0.30)  # 0.1 progress per 100 s
        self.assertEqual(rate.blocks_per_second, 100.0)
        self.assertAlmostEqual(rate.eta_seconds, 700.0)  # 0.7 left

    def test_window_keeps_only_recent_samples(self):
        rate = SyncRate(window_seconds=60)
        rate.add(0, 0, 0.0)  # fast early blocks
        rate.add(10, 10_000, 0.1)
        for t in range(20, 200, 10):
            rate.add(t, 10_000 + (t - 10) * 2, 0.1 + (t - 10) * 0.001)
        self.assertAlmostEqual(rate.blocks_per_second, 2.0)

    def test_stalled_progress_has_no_eta(self):
        rate = SyncRate()
        rate.add(0, 100, 0.5)
        rate.add(60, 100, 0.5)
        self.assertEqual(rate.blocks_per_second, 0.0)
        self.assertIsNone(rate.eta_seconds)

    def test_height_going_backwards_starts_over(self):
        rate = SyncRate()
        rate.add(0, 100_000, 0.5)
        rate.add(60, 50, 0.0)  # reindex
        self.assertIsNone(rate.blocks_per_second)
        rate.add(120, 6_050, 0.01)
        self.assertEqual(rate.blocks_per_second, 100.0)


if __name__ == "__main__":
    unittest.main()
