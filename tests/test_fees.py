import unittest

from btcmonitor.fees import (
    bucket_fee_rate,
    build_fee_buckets,
    project_block_from_buckets,
    project_block_from_template,
)


class FeeBucketTests(unittest.TestCase):
    def test_parses_bucket_labels_with_variable_whitespace(self):
        for label, expected in (
            ("< 2 sat/vB", 1.0),
            ("< 2  sat/vB", 1.0),
            ("  < 2 sat/vB  ", 1.0),
            ("2+ sat/vB", 2.0),
            ("  3+\t sat/vB ", 3.0),
            ("1000+ sat/vB", 1000.0),
        ):
            with self.subTest(label=label):
                self.assertEqual(bucket_fee_rate(label), expected)

    def test_every_generated_label_parses(self):
        rates = [bucket_fee_rate(label) for label, _ in build_fee_buckets({})]
        self.assertEqual(rates, [1, 2, 3, 5, 10, 20, 50, 100, 500, 1000])


class BuildFeeBucketsTests(unittest.TestCase):
    @staticmethod
    def bucket_of(fee_sat, vsize=100):
        buckets = build_fee_buckets({"tx": {"vsize": vsize, "fees": {"base": fee_sat / 1e8}}})
        return next(label for label, vbytes in buckets if vbytes)

    def test_rate_on_band_boundary_belongs_to_that_band(self):
        for rate, expected in (
            (1, "< 2  sat/vB"),
            (2, "2+ sat/vB"),
            (3, "3+ sat/vB"),
            (5, "5+ sat/vB"),
            (10, "10+ sat/vB"),
            (20, "20+ sat/vB"),
            (50, "50+ sat/vB"),
            (100, "100+ sat/vB"),
            (500, "500+ sat/vB"),
            (1000, "1000+ sat/vB"),
        ):
            with self.subTest(rate=rate):
                self.assertEqual(self.bucket_of(rate * 100), expected)

    def test_rate_just_below_boundary_stays_in_lower_band(self):
        self.assertEqual(self.bucket_of(199), "< 2  sat/vB")
        self.assertEqual(self.bucket_of(1999), "10+ sat/vB")

    def test_btc_float_conversion_does_not_lose_a_satoshi(self):
        # 59 sat is 0.00000059 BTC, and 0.00000059 * 1e8 == 58.99999999999999
        self.assertEqual(self.bucket_of(59 * 2, vsize=59), "2+ sat/vB")

    def test_vsize_falls_back_to_weight(self):
        buckets = dict(build_fee_buckets({"tx": {"weight": 800, "fees": {"base": 0.00001}}}))
        self.assertEqual(buckets["5+ sat/vB"], 200)


class ProjectionTests(unittest.TestCase):
    def test_template_projection_counts_vbytes_and_rates(self):
        projection = project_block_from_template({"transactions": [{"txid": "a", "weight": 1000, "fee": 1250}]})
        self.assertEqual((projection.est_tx, projection.est_weight_vbytes), (1, 250))
        self.assertEqual(projection.transactions[0].fee_rate, 5)

    def test_bucket_projection_draws_whole_synthetic_transactions(self):
        projection = project_block_from_buckets([("5+ sat/vB", 600)])
        self.assertEqual([tx.vbytes for tx in projection.transactions], [250, 250])
        self.assertEqual(projection.est_weight_vbytes, 600)

    def test_bucket_projection_respects_capacity(self):
        projection = project_block_from_buckets([("2+ sat/vB", 800), ("10+ sat/vB", 800)], capacity=1000)
        self.assertEqual(projection.fee_buckets, [("10+ sat/vB", 800), ("2+ sat/vB", 200)])
        self.assertEqual(projection.est_weight_vbytes, 1000)


if __name__ == "__main__":
    unittest.main()
