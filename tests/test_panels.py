import io
import unittest

from rich.console import Console

from btcmonitor.models import BitcoinInfo, BlockProjection, MempoolTransaction, MempoolView, NodeSnapshot, Transaction
from btcmonitor.panels import (
    ascii_histogram,
    get_bitcoin_info_panel,
    get_fee_color,
    get_mempool_panel,
    get_node_panel,
    get_projection_panel,
    get_top_transactions_panel,
    max_transaction_scroll,
    render_block_grid,
)


def render(renderable, width=120):
    console = Console(file=io.StringIO(), width=width, record=True, color_system=None)
    console.print(renderable)
    return console.export_text()


def mempool_view(count=0, loading=False):
    transactions = [
        MempoolTransaction(txid=f"{i:064x}", amount_btc=100.0 - i, fee_btc=0.0001, fee_rate=2.5) for i in range(count)
    ]
    return MempoolView(
        total_tx=count,
        usage_mb=1.5,
        maxmempool_mb=300.0,
        fee_buckets=[("< 2  sat/vB", 0), ("2+ sat/vB", 500)],
        top_transactions=transactions,
        loading_transactions=loading,
    )


class FeeColorTests(unittest.TestCase):
    def test_thresholds(self):
        for rate, color in (
            (1, "blue"),
            (2, "green"),
            (5, "bright_green"),
            (10, "yellow"),
            (20, "bright_yellow"),
            (50, "red"),
            (100, "bright_red"),
            (5000, "bright_red"),
        ):
            with self.subTest(rate=rate):
                self.assertEqual(get_fee_color(rate), color)

    def test_histogram_preserves_fee_colors(self):
        histogram = ascii_histogram([("< 2  sat/vB", 250), ("2+ sat/vB", 250), ("1000+ sat/vB", 250)])
        bar_styles = [span.style for span in histogram.spans if "█" in histogram.plain[span.start : span.end]]
        self.assertEqual(bar_styles, ["blue", "green", "bright_red"])

    def test_histogram_bars_scale_and_empty_bands_have_none(self):
        lines = ascii_histogram([("2+ sat/vB", 0), ("3+ sat/vB", 50), ("5+ sat/vB", 100)], max_width=10).plain
        self.assertEqual([line.count("█") for line in lines.splitlines()], [0, 6, 11])


class TopTransactionsPanelTests(unittest.TestCase):
    def test_loading_and_empty_messages(self):
        self.assertIn("Loading transaction data", render(get_top_transactions_panel(mempool_view(loading=True), None)))
        self.assertIn("No transaction data available", render(get_top_transactions_panel(mempool_view(), None)))

    def test_rows_scroll_window_and_usd_values(self):
        text = render(get_top_transactions_panel(mempool_view(30), 50000.0, 120, panel_height=12, scroll_offset=5))
        self.assertIn("Largest Transactions (6-15 of 30)", text)
        self.assertIn("95.0000", text)  # sixth transaction
        self.assertIn("$4,750,000", text)
        self.assertIn("Fee US$", text)
        self.assertNotIn("100.0000", text)  # scrolled past the first

    def test_scroll_offset_is_clamped(self):
        view = mempool_view(30)
        self.assertEqual(max_transaction_scroll(view, panel_height=12), 20)
        text = render(get_top_transactions_panel(view, None, 120, panel_height=12, scroll_offset=999))
        self.assertIn("(21-30 of 30)", text)

    def test_fee_usd_column_hidden_on_narrow_terminals(self):
        self.assertNotIn("Fee US$", render(get_top_transactions_panel(mempool_view(3), 50000.0, terminal_width=113)))

    def test_without_price_usd_shows_na(self):
        self.assertIn("N/A", render(get_top_transactions_panel(mempool_view(1), None)))


class OtherPanelTests(unittest.TestCase):
    def test_bitcoin_info_time_since_last_block_ticks_at_render_time(self):
        info = BitcoinInfo(
            price_usd=65000.0,
            current_subsidy=3.125,
            blocks_until_halving=1234,
            estimated_halving_date="2028-04-12",
            last_block_time=1000,
        )
        text = render(get_bitcoin_info_panel(info, now=1125))
        self.assertIn("$65,000", text)
        self.assertIn("1,234 blocks", text)
        self.assertIn("2:05", text)

    def test_bitcoin_info_without_block_time(self):
        info = BitcoinInfo(None, 3.125, 1, None, None)
        text = render(get_bitcoin_info_panel(info))
        self.assertEqual(text.count("N/A"), 2)  # price and time since last block
        self.assertIn("Unknown", text)

    def test_node_panel_shows_error_or_snapshot(self):
        self.assertIn("connection refused", render(get_node_panel(None, "connection refused")))
        snap = NodeSnapshot(840000, 840001, 0.99999, "main", 10, 2, 8, 2048, 7, 8.3e13)
        text = render(get_node_panel(snap, None))
        self.assertIn("10 (In: 2 / Out: 8)", text)
        self.assertIn("7 txs / 2 KB", text)
        self.assertIn("100.00%", text)

    def test_mempool_panel(self):
        text = render(get_mempool_panel(mempool_view(3)))
        self.assertIn("Total: 3 txs | Memory Usage: 1.50 MB / 300.00 MB", text)
        self.assertIn("2+ sat/vB", text)

    def test_projection_panel_summary_and_legend(self):
        proj = BlockProjection(
            est_tx=2,
            est_weight_vbytes=500,
            transactions=[Transaction(10.0, 250, "a"), Transaction(2.0, 250, "b")],
            fee_buckets=[],
        )
        text = render(get_projection_panel(proj, terminal_width=120, terminal_height=40))
        self.assertIn("Transactions: 2 | Size: 500 B", text)
        self.assertIn("Fee: 2.0-10.0 (avg: 6.0) sat/vB", text)
        self.assertIn("100+ ", text)
        self.assertIn("<2 sat/vB", text)


class BlockGridTests(unittest.TestCase):
    def test_fewer_transactions_than_cells_leaves_empty_cells(self):
        grid = render_block_grid([Transaction(5.0, 250, "a"), Transaction(50.0, 250, "b")], width=4, height=2)
        self.assertEqual(grid.plain, "██░░\n░░░░\n")
        self.assertEqual([span.style for span in grid.spans[:2]], ["red", "bright_green"])  # highest fee first

    def test_more_transactions_than_cells_fills_every_cell(self):
        transactions = [Transaction(float(i), 250, str(i)) for i in range(25)]
        self.assertEqual(render_block_grid(transactions, width=4, height=2).plain, "████\n████\n")

    def test_no_transactions(self):
        self.assertEqual(render_block_grid([], width=4, height=2).plain, "No transactions")


if __name__ == "__main__":
    unittest.main()
