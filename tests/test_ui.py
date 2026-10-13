import io
import unittest
from unittest.mock import Mock, patch

from rich.console import Console

from btcmonitor.rpc import BitcoinRPC, RPCError
from btcmonitor.ui import (
    ascii_histogram,
    bucket_fee_rate,
    build_fee_buckets,
    build_layout,
    gather_snapshot,
    update_layout,
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

    def test_histogram_preserves_fee_colors(self):
        histogram = ascii_histogram([("< 2  sat/vB", 250), ("2+ sat/vB", 250), ("1000+ sat/vB", 250)])
        bar_styles = [span.style for span in histogram.spans if "█" in histogram.plain[span.start : span.end]]
        self.assertEqual(bar_styles, ["blue", "green", "bright_red"])


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


class SnapshotTestCase(unittest.TestCase):
    def setUp(self):
        self.rpc = Mock(spec=BitcoinRPC)
        self.rpc.get_blockchain_info.return_value = {
            "blocks": 100,
            "headers": 900000,
            "verificationprogress": 0.001,
            "chain": "main",
            "initialblockdownload": True,
        }
        self.rpc.get_mempool_info.return_value = {}
        self.rpc.get_connection_count.return_value = 1
        self.rpc.get_peer_info.return_value = [{"inbound": False}]
        self.rpc.get_raw_mempool.return_value = {}
        self.rpc.get_block_template.side_effect = RPCError(
            "{'code': -10, 'message': 'Bitcoin Core is in initial sync and waiting for blocks...'}"
        )
        self.rpc.get_block.return_value = {"time": 1700000000}
        # Keep price HTTP requests and background transaction fetching offline.
        for target, result in (
            ("btcmonitor.ui.fetch_bitcoin_price", None),
            ("btcmonitor.ui.fetch_top_transactions", []),
        ):
            patcher = patch(target, return_value=result)
            patcher.start()
            self.addCleanup(patcher.stop)


class BlockProjectionTests(SnapshotTestCase):
    def projection(self):
        snapshot, view, projection, bitcoin_info, error = gather_snapshot(self.rpc)
        self.assertIsNone(error)
        self.assertIsNotNone(snapshot)
        self.assertIsNotNone(view)
        self.assertIsNotNone(bitcoin_info)
        self.assertIsNotNone(projection)
        return projection

    def test_ibd_with_empty_mempool_returns_empty_projection(self):
        projection = self.projection()
        self.assertEqual(projection.est_tx, 0)
        self.assertEqual(projection.est_weight_vbytes, 0)
        self.assertEqual(projection.transactions, [])
        self.assertEqual(projection.fee_buckets, [])

    def test_ibd_projects_every_generated_bucket_in_descending_fee_order(self):
        # One 250-vbyte transaction inside each band, away from boundaries.
        self.rpc.get_raw_mempool.return_value = {
            str(index): {"vsize": 250, "fees": {"base": fee_btc}}
            for index, fee_btc in enumerate(
                [0.0000025, 0.00000625, 0.00001, 0.00002, 0.0000375, 0.000075, 0.0001875, 0.000625, 0.001875, 0.00375]
            )
        }
        projection = self.projection()
        self.assertEqual(
            [tx.fee_rate for tx in projection.transactions],
            [1000, 500, 100, 50, 20, 10, 5, 3, 2, 1],
        )
        self.assertEqual(projection.est_tx, 10)
        self.assertEqual(projection.est_weight_vbytes, 2500)
        self.assertEqual(projection.fee_buckets[-1], ("< 2  sat/vB", 250))

    def test_ibd_prioritizes_higher_fees_when_block_is_full(self):
        self.rpc.get_raw_mempool.return_value = {
            "low": {"vsize": 500000, "fees": {"base": 0.005}},
            "medium": {"vsize": 500000, "fees": {"base": 0.02}},
            "high": {"vsize": 750000, "fees": {"base": 0.15}},
        }
        projection = self.projection()
        self.assertEqual(projection.est_weight_vbytes, 1000000)
        self.assertEqual(
            projection.fee_buckets,
            [("20+ sat/vB", 750000), ("3+ sat/vB", 250000)],
        )
        self.assertEqual(projection.est_tx, 4000)
        self.assertEqual(
            [tx.fee_rate for tx in projection.transactions],
            [20] * 3000 + [3] * 1000,
        )

    def test_successful_block_template_uses_real_transactions(self):
        self.rpc.get_block_template.side_effect = None
        self.rpc.get_block_template.return_value = {
            "transactions": [{"txid": "template-tx", "weight": 1000, "fee": 1250}]
        }
        projection = self.projection()
        self.assertEqual(projection.est_tx, 1)
        self.assertEqual(projection.est_weight_vbytes, 250)
        self.assertEqual(projection.transactions[0].txid, "template-tx")
        self.assertEqual(projection.transactions[0].fee_rate, 5)

    def test_block_template_fee_buckets_use_real_fees(self):
        self.rpc.get_block_template.side_effect = None
        self.rpc.get_block_template.return_value = {
            "transactions": [
                {"txid": "a", "weight": 800, "fee": 10000},  # 200 vB at 50 sat/vB
                {"txid": "b", "weight": 400, "fee": 300},  # 100 vB at 3 sat/vB
            ]
        }
        buckets = dict(self.projection().fee_buckets)
        self.assertEqual(buckets["50+ sat/vB"], 200)
        self.assertEqual(buckets["3+ sat/vB"], 100)
        self.assertEqual(sum(buckets.values()), 300)


class UnexpectedErrorTests(SnapshotTestCase):
    def test_malformed_node_data_is_reported_not_raised(self):
        self.rpc.get_mempool_info.return_value = None
        snapshot, view, projection, bitcoin_info, error = gather_snapshot(self.rpc)
        self.assertIsNone(snapshot)
        self.assertIn("Unexpected error: AttributeError", error)

    def test_failing_panel_is_reported_in_node_panel(self):
        console = Console(file=io.StringIO(), width=120, height=40)
        layout = build_layout()
        with patch("btcmonitor.ui.get_system_panel", side_effect=OSError("psutil failed")):
            update_layout(layout, self.rpc, console)
        console.print(layout["node"])
        self.assertIn("Unexpected error: OSError: psutil failed", console.file.getvalue())


if __name__ == "__main__":
    unittest.main()
