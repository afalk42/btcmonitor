import sys
import time
import unittest
from unittest.mock import Mock, patch

from btcmonitor import ui
from btcmonitor.rpc import BitcoinRPC


def reset_transaction_cache():
    ui._transaction_cache = []
    ui._last_transaction_fetch = 0.0
    ui._transaction_data_cache = {}
    ui._known_txids = set()
    ui._last_block_height = 0
    ui._initial_cache_loading = False
    ui._cache_loading_thread = None


def mempool_of(count):
    return {f"tx{i}": {"vsize": 200, "fees": {"base": 0.00001}} for i in range(count)}


def fake_rpc():
    rpc = Mock(spec=BitcoinRPC)
    rpc.get_raw_transaction.side_effect = lambda txid, verbose: {"vout": [{"value": int(txid[2:]) + 1}]}
    return rpc


class TransactionCacheTests(unittest.TestCase):
    def setUp(self):
        reset_transaction_cache()
        self.addCleanup(reset_transaction_cache)

    def wait_for_background_load(self):
        thread = ui._cache_loading_thread
        if thread is not None:
            thread.join(timeout=30)
            self.assertFalse(thread.is_alive())

    def test_reading_while_background_load_runs_does_not_crash(self):
        # Switch threads as often as possible so the reader overlaps the loader's writes
        interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        self.addCleanup(sys.setswitchinterval, interval)
        rpc = fake_rpc()
        mempool = mempool_of(20000)
        ui.fetch_top_transactions(rpc, mempool, 1)
        deadline = time.monotonic() + 10
        while ui._initial_cache_loading and time.monotonic() < deadline:
            ui.fetch_top_transactions(rpc, mempool, 1)
        self.wait_for_background_load()
        self.assertEqual(len(ui.fetch_top_transactions(rpc, mempool, 1)), 100)

    def test_every_transaction_in_a_large_mempool_is_looked_up(self):
        # More transactions than the old 20,000 initial-load cap, which silently skipped the rest
        rpc = fake_rpc()
        mempool = mempool_of(30000)
        with patch.object(ui, "TRANSACTION_CACHE_DURATION", 0):
            ui.fetch_top_transactions(rpc, mempool, 1)
            self.wait_for_background_load()
            ui.fetch_top_transactions(rpc, mempool, 1)
            self.wait_for_background_load()
            top = ui.fetch_top_transactions(rpc, mempool, 1)
        self.assertEqual(rpc.get_raw_transaction.call_count, 30000)
        self.assertEqual(top[0].txid, "tx29999")

    def test_transactions_arriving_later_are_looked_up_once(self):
        rpc = fake_rpc()
        with patch.object(ui, "TRANSACTION_CACHE_DURATION", 0):
            ui.fetch_top_transactions(rpc, mempool_of(10), 1)
            self.wait_for_background_load()
            ui.fetch_top_transactions(rpc, mempool_of(15), 1)
            self.wait_for_background_load()
            top = ui.fetch_top_transactions(rpc, mempool_of(15), 1)
        self.assertEqual(rpc.get_raw_transaction.call_count, 15)
        self.assertEqual([tx.txid for tx in top[:2]], ["tx14", "tx13"])


if __name__ == "__main__":
    unittest.main()
