import unittest
from unittest.mock import Mock, patch

from btcmonitor.collector import Collector
from btcmonitor.price import PriceFeed
from btcmonitor.rpc import BitcoinRPC, RPCError
from btcmonitor.transactions import TransactionTracker


class CollectorTestCase(unittest.TestCase):
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
        self.rpc.get_best_block_hash.return_value = "best"
        self.rpc.get_block.return_value = {"time": 1700000000}
        # Keep price HTTP requests and background transaction fetching offline.
        self.price_feed = Mock(spec=PriceFeed)
        self.price_feed.get.return_value = None
        self.tracker = Mock(spec=TransactionTracker)
        self.tracker.update.return_value = []
        self.tracker.loading = False
        self.collector = Collector(self.rpc, price_feed=self.price_feed, tracker=self.tracker)

    def collect(self):
        data = self.collector.collect()
        self.assertIsNone(data.error)
        for part in (data.node, data.mempool, data.bitcoin, data.projection):
            self.assertIsNotNone(part)
        return data


class BlockProjectionTests(CollectorTestCase):
    def projection(self):
        return self.collect().projection

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


class SnapshotContentTests(CollectorTestCase):
    def test_node_and_bitcoin_info(self):
        self.rpc.get_blockchain_info.return_value = {"blocks": 840000, "headers": 840001, "chain": "main"}
        self.rpc.get_connection_count.return_value = 3
        self.rpc.get_peer_info.return_value = [{"inbound": True}, {"inbound": False}, {"inbound": False}]
        self.price_feed.get.return_value = 65000.0
        data = self.collect()
        self.assertEqual((data.node.height, data.node.inbound_peers, data.node.outbound_peers), (840000, 1, 2))
        self.assertEqual(data.bitcoin.current_subsidy, 3.125)
        self.assertEqual(data.bitcoin.blocks_until_halving, 210000)
        self.assertEqual(data.bitcoin.price_usd, 65000.0)
        self.assertEqual(data.bitcoin.last_block_time, 1700000000)

    def test_peer_info_failure_counts_all_peers_as_outbound(self):
        self.rpc.get_connection_count.return_value = 4
        self.rpc.get_peer_info.side_effect = RPCError("boom")
        self.assertEqual(self.collect().node.outbound_peers, 4)

    def test_tracker_receives_mempool_and_height(self):
        self.rpc.get_raw_mempool.return_value = {"tx": {"vsize": 100, "fees": {"base": 0.000001}}}
        self.tracker.loading = True
        data = self.collect()
        self.tracker.update.assert_called_with({"tx": {"vsize": 100, "fees": {"base": 0.000001}}}, 100)
        self.assertTrue(data.mempool.loading_transactions)


class PollingCostTests(CollectorTestCase):
    def test_verbose_mempool_and_template_are_not_fetched_every_cycle(self):
        with patch("btcmonitor.collector.time.monotonic", return_value=1000.0):
            self.collect()
            self.collect()
        with patch("btcmonitor.collector.time.monotonic", return_value=1004.9):
            self.collect()
        self.assertEqual(self.rpc.get_raw_mempool.call_count, 1)
        self.assertEqual(self.rpc.get_block_template.call_count, 1)
        with patch("btcmonitor.collector.time.monotonic", return_value=1005.0):
            self.collect()
        self.assertEqual(self.rpc.get_raw_mempool.call_count, 2)

    def test_new_block_refreshes_mempool_immediately(self):
        with patch("btcmonitor.collector.time.monotonic", return_value=1000.0):
            self.collect()
            self.rpc.get_blockchain_info.return_value = {"blocks": 101}
            self.collect()
        self.assertEqual(self.rpc.get_raw_mempool.call_count, 2)

    def test_block_time_is_fetched_once_per_best_block(self):
        self.collect()
        self.collect()
        self.assertEqual(self.rpc.get_block.call_count, 1)
        self.rpc.get_blockchain_info.return_value = {"blocks": 101, "bestblockhash": "next"}
        self.rpc.get_block.return_value = {"time": 1700000600}
        self.assertEqual(self.collect().bitcoin.last_block_time, 1700000600)
        self.assertEqual(self.rpc.get_block.call_count, 2)
        # getbestblockhash is only a fallback when getblockchaininfo lacks bestblockhash
        self.assertEqual(self.rpc.get_best_block_hash.call_count, 2)


class InitialBlockDownloadTests(CollectorTestCase):
    def test_no_sync_data_once_caught_up(self):
        self.rpc.get_blockchain_info.return_value = {"blocks": 100, "headers": 100, "initialblockdownload": False}
        data = self.collect()
        self.assertIsNone(data.sync)
        self.assertFalse(data.node.initial_block_download)

    def test_sync_progress_and_rates_during_ibd(self):
        info = {
            "blocks": 100_000,
            "headers": 900_000,
            "verificationprogress": 0.2,
            "initialblockdownload": True,
            "time": 1300000000,
            "size_on_disk": 5_000_000_000,
            "pruned": True,
        }
        self.rpc.get_blockchain_info.return_value = info
        with patch("btcmonitor.collector.time.monotonic", return_value=1000.0):
            first = self.collect().sync
        self.assertEqual(
            (first.height, first.headers, first.tip_time, first.pruned), (100_000, 900_000, 1300000000, True)
        )
        self.assertIsNone(first.blocks_per_second)  # needs two samples

        self.rpc.get_blockchain_info.return_value = dict(info, blocks=101_000, verificationprogress=0.21)
        with patch("btcmonitor.collector.time.monotonic", return_value=1010.0):
            sync = self.collect().sync
        self.assertEqual(sync.blocks_per_second, 100.0)
        self.assertAlmostEqual(sync.eta_seconds, 790.0)  # 0.79 left at 0.001 per second

    def test_tip_time_falls_back_to_best_block_header(self):
        self.rpc.get_blockchain_info.return_value = {"blocks": 5, "headers": 10, "initialblockdownload": True}
        self.assertEqual(self.collect().sync.tip_time, 1700000000)


class UnexpectedErrorTests(CollectorTestCase):
    def test_rpc_error_is_reported(self):
        self.rpc.get_blockchain_info.side_effect = RPCError("connection refused")
        data = self.collector.collect()
        self.assertEqual(data.error, "connection refused")
        self.assertIsNone(data.node)

    def test_malformed_node_data_is_reported_not_raised(self):
        self.rpc.get_mempool_info.return_value = None
        data = self.collector.collect()
        self.assertIsNone(data.node)
        self.assertIn("Unexpected error: AttributeError", data.error)


if __name__ == "__main__":
    unittest.main()
