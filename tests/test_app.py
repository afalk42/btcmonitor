import io
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
)


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


def data_with_transactions(count):
    transactions = [MempoolTransaction(f"tx{i}", 1.0, 0.0001, 2.0) for i in range(count)]
    return DashboardData(mempool=MempoolView(count, 1.0, 300.0, [], transactions))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        # 40 lines tall: 9 top + 15 mempool leaves a 16-line transactions panel showing 14 rows
        self.console = Console(file=self.output, width=120, height=40, color_system=None)
        self.dashboard = Dashboard(Mock(spec=Collector), console=self.console)

    def node_panel_text(self):
        self.console.print(self.dashboard.layout["node"])
        return self.output.getvalue()

    def test_q_quits(self):
        self.dashboard.handle_key("Q")
        self.assertTrue(self.dashboard.quit.is_set())

    def test_scroll_keys_stay_within_list(self):
        self.dashboard.update_layout(data_with_transactions(100))  # 14 visible rows -> max offset 86
        for key, expected in (
            (readchar.key.UP, 0),
            (readchar.key.DOWN, 1),
            (readchar.key.PAGE_DOWN, 11),
            (readchar.key.END, 86),
            (readchar.key.DOWN, 86),
            (readchar.key.PAGE_UP, 76),
            (readchar.key.HOME, 0),
        ):
            self.dashboard.handle_key(key)
            self.assertEqual(self.dashboard.scroll_offset, expected, key)

    def test_shrinking_list_pulls_scroll_offset_back(self):
        self.dashboard.update_layout(data_with_transactions(100))
        self.dashboard.handle_key(readchar.key.END)
        self.dashboard.update_layout(data_with_transactions(20))
        self.assertEqual(self.dashboard.scroll_offset, 6)

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
        self.assertEqual(self.dashboard.scroll_offset, 2)  # the DOWN after q was not handled

    def test_keyboard_failure_leaves_dashboard_running(self):
        self.dashboard.key_reader = key_reader(OSError("not a terminal"))
        self.dashboard._listen_keys()
        self.assertFalse(self.dashboard.quit.is_set())


if __name__ == "__main__":
    unittest.main()
