"""The full-screen dashboard: layout, keyboard handling and the render loop"""

from __future__ import annotations

import threading

import readchar
from rich.console import Console
from rich.layout import Layout
from rich.live import Live

from .collector import Collector
from .keyboard import KeyReader
from .models import DashboardData
from .panels import (
    get_bitcoin_info_panel,
    get_mempool_panel,
    get_network_panel,
    get_node_panel,
    get_projection_panel,
    get_recent_blocks_panel,
    get_sync_panel,
    get_system_panel,
    get_top_transactions_panel,
    max_transaction_scroll,
)
from .price import PriceFeed
from .rpc import BitcoinRPC

TOP_ROW_HEIGHT = 9  # seven rows (the Bitcoin Core panel's) + borders
MEMPOOL_PANEL_HEIGHT = 15  # title + histogram + borders
RECENT_BLOCKS_PANEL_HEIGHT = 8  # header + five blocks + borders


def build_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="top", size=TOP_ROW_HEIGHT),
        Layout(name="bottom"),
        # Replaces "bottom" during initial block download, when the mempool panels have nothing to show
        Layout(name="sync", visible=False),
    )
    layout["top"].split_row(
        Layout(name="sys"),
        Layout(name="bitcoin_info"),
        Layout(name="node"),
        Layout(name="network"),
    )
    layout["bottom"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    layout["right"].split_column(
        Layout(name="projection"),
        Layout(name="recent_blocks", size=RECENT_BLOCKS_PANEL_HEIGHT),
    )
    # Mempool has fixed content; the transactions list takes the remaining height
    layout["left"].split_column(
        Layout(name="mempool", size=MEMPOOL_PANEL_HEIGHT),
        Layout(name="top_transactions"),
    )
    return layout


class Dashboard:
    def __init__(
        self,
        collector: Collector,
        refresh_hz: float = 2.0,
        console: Console | None = None,
        key_reader: KeyReader | None = None,
    ):
        self.collector = collector
        self.key_reader = key_reader or KeyReader()
        self.refresh_interval = max(0.1, 1.0 / refresh_hz)
        self.console = console or Console()
        self.layout = build_layout()
        self.scroll_offset = 0
        self.quit = threading.Event()
        self._redraw = threading.Event()  # set by a keypress to redraw without waiting for the next tick
        self._scroll_lock = threading.Lock()  # the keyboard thread and render loop both adjust scroll_offset
        self._max_scroll = 0

    def handle_key(self, key: str) -> None:
        if key.lower() == "q":
            self.quit.set()
        with self._scroll_lock:
            if key == readchar.key.UP:
                self.scroll_offset -= 1
            elif key == readchar.key.DOWN:
                self.scroll_offset += 1
            elif key == readchar.key.PAGE_UP:
                self.scroll_offset -= 10
            elif key == readchar.key.PAGE_DOWN:
                self.scroll_offset += 10
            elif key == readchar.key.HOME:
                self.scroll_offset = 0
            elif key == readchar.key.END:
                self.scroll_offset = self._max_scroll
            self.scroll_offset = max(0, min(self.scroll_offset, self._max_scroll))
        self._redraw.set()

    def _listen_keys(self) -> None:
        try:
            for key in self.key_reader.keys():
                self.handle_key(key)
                if self.quit.is_set():
                    break
        except KeyboardInterrupt:
            # On Windows readchar reports Ctrl+C here, in the reading thread, rather than in the main thread
            self.quit.set()
        except Exception:
            # No usable keyboard (e.g. stdin is not a terminal); keep displaying without it
            pass
        self._redraw.set()

    def update_layout(self, data: DashboardData) -> None:
        """Refresh every panel; an unexpected error is shown in the node panel instead of ending the program"""
        try:
            width, height = self.console.size
            transactions_height = height - TOP_ROW_HEIGHT - MEMPOOL_PANEL_HEIGHT
            with self._scroll_lock:
                self._max_scroll = max_transaction_scroll(data.mempool, transactions_height)
                self.scroll_offset = min(self.scroll_offset, self._max_scroll)
                scroll_offset = self.scroll_offset

            self.layout["sys"].update(get_system_panel())
            self.layout["bitcoin_info"].update(get_bitcoin_info_panel(data.bitcoin))
            self.layout["node"].update(get_node_panel(data.node, data.error))
            self.layout["network"].update(get_network_panel(data.network))
            self.layout["mempool"].update(get_mempool_panel(data.mempool))
            price = data.bitcoin.price if data.bitcoin else None
            currency = data.bitcoin.currency if data.bitcoin else None
            self.layout["top_transactions"].update(
                get_top_transactions_panel(data.mempool, price, width, transactions_height, scroll_offset, currency)
            )
            projection_height = height - TOP_ROW_HEIGHT - RECENT_BLOCKS_PANEL_HEIGHT
            self.layout["projection"].update(
                get_projection_panel(data.projection, width // 2, projection_height, data.fee_estimates)
            )
            self.layout["recent_blocks"].update(get_recent_blocks_panel(data.recent_blocks))

            syncing = data.sync is not None
            self.layout["bottom"].visible = not syncing
            self.layout["sync"].visible = syncing
            if syncing:
                self.layout["sync"].update(get_sync_panel(data.sync, width))
        except Exception as e:
            self.layout["node"].update(get_node_panel(None, f"Unexpected error: {type(e).__name__}: {e}"))

    def run(self) -> None:
        self.collector.start()
        try:
            with self.key_reader, Live(console=self.console, auto_refresh=False, screen=True, transient=False) as live:
                threading.Thread(target=self._listen_keys, daemon=True).start()
                while not self.quit.is_set():
                    self.update_layout(self.collector.latest)
                    self.console.set_window_title("btcmonitor")
                    live.update(self.layout, refresh=True)
                    self._redraw.wait(self.refresh_interval)
                    self._redraw.clear()
        finally:
            self.collector.stop()


def run_dashboard(rpc: BitcoinRPC, refresh_hz: float = 2.0, price_feed: PriceFeed | None = None) -> None:
    collector = Collector(rpc, interval=max(0.1, 1.0 / refresh_hz), price_feed=price_feed)
    Dashboard(collector, refresh_hz).run()
