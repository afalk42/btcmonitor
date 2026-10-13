import io
import threading
import unittest
from unittest.mock import Mock, patch

import readchar
from rich.console import Console

from btcmonitor.app import Dashboard
from btcmonitor.collector import Collector
from btcmonitor.keyboard import KeyReader
from btcmonitor.models import (
    DashboardData,
    MempoolTransaction,
    MempoolView,
    NodeSnapshot,
    RecentBlock,
    SyncProgress,
    TransactionDetail,
)
from btcmonitor.rpc import RPCError


def key_reader(*keys):
    """A KeyReader stand-in that yields `keys`; an exception instance is raised instead of yielded"""
    reader = Mock(spec=KeyReader)

    def generate():
        for key in keys:
            if isinstance(key, BaseException):
                raise key
            yield key

    reader.keys.side_effect = generate
    return reader


def detail_of(txid):
    return TransactionDetail(txid, 141, 561, 0.00001, 1700000000, False, 0, 7.1, 0, 7.1, [], [], [], [])


def data_with_transactions(count):
    transactions = [MempoolTransaction(f"tx{i}", 1.0, 0.0001, 2.0) for i in range(count)]
    return DashboardData(mempool=MempoolView(count, 1.0, 300.0, [], transactions))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        # 40 lines tall: 9 top + 15 mempool leaves a 16-line transactions panel showing 14 rows
        self.console = Console(file=self.output, width=120, height=40, color_system=None)
        self.dashboard = Dashboard(Mock(spec=Collector, rpc=Mock()), console=self.console)

    def node_panel_text(self):
        self.console.print(self.dashboard.layout["node"])
        return self.output.getvalue()

    def test_q_quits(self):
        self.dashboard.handle_key("Q")
        self.assertTrue(self.dashboard.quit.is_set())

    def test_selection_moves_and_the_window_follows(self):
        self.dashboard.update_layout(data_with_transactions(100))  # 14 visible rows
        for key, selected, offset in (
            (readchar.key.UP, 0, 0),
            (readchar.key.DOWN, 1, 0),
            (readchar.key.PAGE_DOWN, 15, 2),
            (readchar.key.END, 99, 86),
            (readchar.key.DOWN, 99, 86),
            (readchar.key.PAGE_UP, 85, 85),
            (readchar.key.HOME, 0, 0),
        ):
            self.dashboard.handle_key(key)
            self.assertEqual((self.dashboard.selected, self.dashboard.scroll_offset), (selected, offset), repr(key))

    def test_selected_row_is_highlighted(self):
        self.dashboard.update_layout(data_with_transactions(5))
        self.dashboard.handle_key(readchar.key.DOWN)
        self.dashboard.update_layout(data_with_transactions(5))
        table = self.dashboard.layout["top_transactions"].renderable.renderable
        self.assertEqual([row.style for row in table.rows], [None, "reverse", None, None, None])

    def test_shrinking_list_pulls_selection_back(self):
        self.dashboard.update_layout(data_with_transactions(100))
        self.dashboard.handle_key(readchar.key.END)
        self.dashboard.update_layout(data_with_transactions(20))
        self.assertEqual((self.dashboard.selected, self.dashboard.scroll_offset), (19, 6))

    def test_sync_panel_replaces_mempool_panels_during_ibd(self):
        syncing = DashboardData(sync=SyncProgress(10, 900_000, 0.0001, None, None, None, None))
        self.dashboard.update_layout(syncing)
        self.assertTrue(self.dashboard.layout["sync"].visible)
        self.assertFalse(self.dashboard.layout["bottom"].visible)
        self.console.print(self.dashboard.layout)
        self.assertIn("Initial Block Download", self.output.getvalue())
        self.assertNotIn("Largest Transactions", self.output.getvalue())

        self.dashboard.update_layout(data_with_transactions(3))  # caught up
        self.assertFalse(self.dashboard.layout["sync"].visible)
        self.assertTrue(self.dashboard.layout["bottom"].visible)

    def test_recent_blocks_panel_below_next_block_panel(self):
        block = RecentBlock(971274, "aa", 1700000000, 4424, 1609728, 0.02, "F2Pool")
        self.dashboard.update_layout(DashboardData(recent_blocks=[block]))
        self.console.print(self.dashboard.layout)
        output = self.output.getvalue()
        self.assertLess(output.index("Next Block Template"), output.index("Recent Blocks"))
        self.assertIn("F2Pool", output)

    def test_top_row_shows_all_bitcoin_core_rows_and_network_panel(self):
        snap = NodeSnapshot(840000, 840001, 0.99999, "main", 10, 2, 8, 2048, 7, 8.3e13)
        self.dashboard.update_layout(DashboardData(node=snap))
        self.console.print(self.dashboard.layout)
        output = self.output.getvalue()
        self.assertIn("Network", output)
        self.assertIn("Difficulty", output)  # used to be cut off by a too-short top row

    def open_detail(self, fetch, rows=3, moves=1):
        self.dashboard._fetch_detail = fetch
        self.dashboard.update_layout(data_with_transactions(rows))
        for _ in range(moves):
            self.dashboard.handle_key(readchar.key.DOWN)
        self.dashboard.handle_key("\n")

    def test_enter_opens_details_of_the_selected_transaction(self):
        looked_up = []

        def fetch(rpc, txid):
            looked_up.append(txid)
            return detail_of(txid)

        self.open_detail(fetch)
        self.dashboard.detail_thread.join(timeout=5)
        self.assertEqual(looked_up, ["tx1"])
        self.dashboard.update_layout(data_with_transactions(3))
        self.assertTrue(self.dashboard.layout["detail"].visible)
        self.assertFalse(self.dashboard.layout["bottom"].visible)
        self.console.print(self.dashboard.layout)
        self.assertIn("Transaction tx1", self.output.getvalue())

        self.dashboard.handle_key(readchar.key.ESC)
        self.dashboard.update_layout(data_with_transactions(3))
        self.assertFalse(self.dashboard.layout["detail"].visible)
        self.assertTrue(self.dashboard.layout["bottom"].visible)

    def test_keys_other_than_back_are_ignored_in_detail_view(self):
        self.open_detail(lambda rpc, txid: detail_of(txid))
        self.dashboard.handle_key(readchar.key.DOWN)
        self.assertEqual((self.dashboard.detail_txid, self.dashboard.selected), ("tx1", 1))

    def test_transaction_gone_from_mempool(self):
        def fetch(rpc, txid):
            raise RPCError("{'code': -5, 'message': 'Transaction not in mempool'}")

        self.open_detail(fetch)
        self.dashboard.detail_thread.join(timeout=5)
        self.assertIn("No longer in the mempool", self.dashboard.detail_error)

    def test_result_for_a_closed_view_is_dropped(self):
        release = threading.Event()

        def slow_fetch(rpc, txid):
            release.wait(5)
            return detail_of(txid)

        self.open_detail(slow_fetch)
        thread = self.dashboard.detail_thread
        self.dashboard.handle_key(readchar.key.ESC)
        release.set()
        thread.join(timeout=5)
        self.assertIsNone(self.dashboard.detail)
        self.assertIsNone(self.dashboard.detail_txid)

    def test_enter_on_empty_list_does_nothing(self):
        self.dashboard.update_layout(DashboardData())
        self.dashboard.handle_key("\n")
        self.assertIsNone(self.dashboard.detail_txid)

    def test_node_error_is_shown(self):
        self.dashboard.update_layout(DashboardData(error="connection refused"))
        self.assertIn("connection refused", self.node_panel_text())

    def test_failing_panel_is_reported_in_node_panel(self):
        with patch("btcmonitor.app.get_system_panel", side_effect=OSError("psutil failed")):
            self.dashboard.update_layout(DashboardData())
        self.assertIn("Unexpected error: OSError: psutil failed", self.node_panel_text())

    def test_ctrl_c_in_keyboard_thread_quits(self):
        # On Windows readchar raises KeyboardInterrupt in the thread that reads keys, not in the main thread
        self.dashboard.key_reader = key_reader(KeyboardInterrupt())
        self.dashboard._listen_keys()
        self.assertTrue(self.dashboard.quit.is_set())

    def test_keys_are_handled_until_quit(self):
        self.dashboard.update_layout(data_with_transactions(100))
        self.dashboard.key_reader = key_reader(readchar.key.DOWN, readchar.key.DOWN, "q", readchar.key.DOWN)
        self.dashboard._listen_keys()
        self.assertTrue(self.dashboard.quit.is_set())
        self.assertEqual(self.dashboard.selected, 2)  # the DOWN after q was not handled

    def test_keyboard_failure_leaves_dashboard_running(self):
        self.dashboard.key_reader = key_reader(OSError("not a terminal"))
        self.dashboard._listen_keys()
        self.assertFalse(self.dashboard.quit.is_set())


if __name__ == "__main__":
    unittest.main()
