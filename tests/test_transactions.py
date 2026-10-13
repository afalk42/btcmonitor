import sys
import time
import unittest
from unittest.mock import Mock, patch

from btcmonitor.rpc import BitcoinRPC, RPCError
from btcmonitor.transactions import TransactionTracker


def mempool_of(count, start=0):
    return {f"tx{i}": {"vsize": 200, "fees": {"base": 0.00001}} for i in range(start, count)}


def fake_rpc():
    rpc = Mock(spec=BitcoinRPC)
    # tx<N> has N + 1 BTC of outputs, so higher numbers are larger
    rpc.get_raw_transaction.side_effect = lambda txid, verbose: {"vout": [{"value": int(txid[2:]) + 1}]}
    return rpc


class TransactionTrackerTests(unittest.TestCase):
    def setUp(self):
        self.rpc = fake_rpc()
        self.tracker = TransactionTracker(self.rpc, refresh_seconds=0)

    def update(self, mempool, height=1):
        """One update, waiting for the lookups it starts, then the resulting top list"""
        self.tracker.update(mempool, height)
        self.tracker.wait(timeout=30)
        self.assertFalse(self.tracker.loading)
        return self.tracker.update(mempool, height)

    def test_reading_while_background_load_runs_does_not_crash(self):
        # Switch threads as often as possible so the reader overlaps the loader's writes
        interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        self.addCleanup(sys.setswitchinterval, interval)
        mempool = mempool_of(20000)
        self.tracker.update(mempool, 1)
        deadline = time.monotonic() + 10
        while self.tracker.loading and time.monotonic() < deadline:
            self.tracker.update(mempool, 1)
        self.tracker.wait(timeout=30)
        self.assertEqual(len(self.tracker.update(mempool, 1)), 100)

    def test_every_transaction_in_a_large_mempool_is_looked_up(self):
        # More transactions than the old 20,000 initial-load cap, which silently skipped the rest
        top = self.update(mempool_of(30000))
        self.assertEqual(self.rpc.get_raw_transaction.call_count, 30000)
        self.assertEqual(top[0].txid, "tx29999")

    def test_transactions_arriving_later_are_looked_up_once(self):
        self.update(mempool_of(10))
        top = self.update(mempool_of(15))
        self.assertEqual(self.rpc.get_raw_transaction.call_count, 15)
        self.assertEqual([tx.txid for tx in top[:2]], ["tx14", "tx13"])

    def test_confirmed_transactions_drop_out(self):
        self.update(mempool_of(10))
        top = self.update(mempool_of(10, start=5), height=2)
        self.assertEqual({tx.txid for tx in top}, {f"tx{i}" for i in range(5, 10)})

    def test_top_list_is_limited_and_sorted(self):
        tracker = TransactionTracker(self.rpc, refresh_seconds=0, top_n=3)
        tracker.update(mempool_of(10), 1)
        tracker.wait(timeout=30)
        self.assertEqual([tx.txid for tx in tracker.update(mempool_of(10), 1)], ["tx9", "tx8", "tx7"])

    def test_fee_details_come_from_mempool_entry(self):
        tx = self.update({"tx0": {"vsize": 200, "fees": {"base": 0.00001}}})[0]
        self.assertEqual((tx.amount_btc, tx.fee_btc), (1.0, 0.00001))
        self.assertAlmostEqual(tx.fee_rate, 5.0)

    def test_failed_lookups_are_skipped(self):
        self.rpc.get_raw_transaction.side_effect = RPCError("No such mempool transaction")
        self.assertEqual(self.update(mempool_of(3)), [])

    def test_new_transactions_wait_for_refresh_interval_unless_a_block_arrives(self):
        tracker = TransactionTracker(self.rpc, refresh_seconds=60)
        with patch("btcmonitor.transactions.time.monotonic", return_value=1000.0):
            tracker.update(mempool_of(5), 1)
            tracker.wait(timeout=30)
            tracker.update(mempool_of(8), 1)  # within the interval: no new lookups
            tracker.wait(timeout=30)
            self.assertEqual(self.rpc.get_raw_transaction.call_count, 5)
            tracker.update(mempool_of(8), 2)  # new block: refresh right away
            tracker.wait(timeout=30)
        self.assertEqual(self.rpc.get_raw_transaction.call_count, 8)


if __name__ == "__main__":
    unittest.main()
