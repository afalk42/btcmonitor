"""The full-screen dashboard: layout, keyboard handling and the render loop"""

from __future__ import annotations

import threading
from collections.abc import Callable

import readchar
from rich.console import Console
from rich.layout import Layout
from rich.live import Live

from .collector import Collector
from .keyboard import KeyReader
from .models import DashboardData, TransactionDetail
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
    get_transaction_detail_panel,
    visible_transaction_rows,
)
from .price import PriceFeed
from .rpc import BitcoinRPC, RPCError
from .txdetail import fetch_transaction_detail

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
        # Replaces "bottom" while a transaction's details are open
        Layout(name="detail", visible=False),
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


# Keys that open the detail view of the selected transaction, and that close it again
OPEN_DETAIL_KEYS = {"\r", "\n"}
CLOSE_DETAIL_KEYS = {"\r", "\n", readchar.key.ESC, readchar.key.LEFT, readchar.key.BACKSPACE}


class Dashboard:
    def __init__(
        self,
        collector: Collector,
        refresh_hz: float = 2.0,
        console: Console | None = None,
        key_reader: KeyReader | None = None,
        fetch_detail: Callable[[BitcoinRPC, str], TransactionDetail] = fetch_transaction_detail,
    ):
        self.collector = collector
        self.key_reader = key_reader or KeyReader()
        self.refresh_interval = max(0.1, 1.0 / refresh_hz)
        self.console = console or Console()
        self.layout = build_layout()
        self.quit = threading.Event()
        self._redraw = threading.Event()  # set by a keypress to redraw without waiting for the next tick
        # Guards the selection and detail state, which the keyboard thread, the render loop and
        # the detail lookup thread all touch
        self._lock = threading.Lock()
        self.selected = 0  # index into the largest-transactions list
        self.scroll_offset = 0  # first visible row
        self._txids: list[str] = []  # the list as last rendered, so Enter opens what is on screen
        self._visible_rows = 1
        # Detail view: open while detail_txid is set; detail or detail_error fill in once looked up
        self._fetch_detail = fetch_detail
        self.detail_txid: str | None = None
        self.detail: TransactionDetail | None = None
        self.detail_error: str | None = None
        self._detail_generation = 0  # results of a lookup for a view that was since closed are dropped
        self.detail_thread: threading.Thread | None = None

    def handle_key(self, key: str) -> None:
        if key.lower() == "q":
            self.quit.set()
            self._redraw.set()
            return
        with self._lock:
            if self.detail_txid is not None:
                if key in CLOSE_DETAIL_KEYS:
                    self.detail_txid = self.detail = self.detail_error = None
                    self._detail_generation += 1
            elif key in OPEN_DETAIL_KEYS:
                if self.selected < len(self._txids):
                    self._open_detail(self._txids[self.selected])
            else:
                page = self._visible_rows
                moves = {
                    readchar.key.UP: -1,
                    readchar.key.DOWN: 1,
                    readchar.key.PAGE_UP: -page,
                    readchar.key.PAGE_DOWN: page,
                    readchar.key.HOME: -len(self._txids),
                    readchar.key.END: len(self._txids),
                }
                self.selected += moves.get(key, 0)
                self._follow_selection()
        self._redraw.set()

    def _follow_selection(self) -> None:
        """Keep the selection inside the list and the visible window around it (caller holds the lock)"""
        self.selected = max(0, min(self.selected, len(self._txids) - 1))
        if self.selected < self.scroll_offset:
            self.scroll_offset = self.selected
        elif self.selected >= self.scroll_offset + self._visible_rows:
            self.scroll_offset = self.selected - self._visible_rows + 1
        self.scroll_offset = max(0, min(self.scroll_offset, len(self._txids) - self._visible_rows))

    def _open_detail(self, txid: str) -> None:
        """Show the detail view for `txid` and look it up in the background (caller holds the lock)"""
        self._detail_generation += 1
        self.detail_txid, self.detail, self.detail_error = txid, None, None
        self.detail_thread = threading.Thread(
            target=self._look_up_detail, args=(txid, self._detail_generation), daemon=True
        )
        self.detail_thread.start()

    def _look_up_detail(self, txid: str, generation: int) -> None:
        detail, error = None, None
        try:
            detail = self._fetch_detail(self.collector.rpc, txid)
        except RPCError as e:
            not_in_mempool = "not in mempool" in str(e).lower()
            error = "No longer in the mempool: confirmed or replaced." if not_in_mempool else str(e)
        except Exception as e:
            error = f"Unexpected error: {type(e).__name__}: {e}"
        with self._lock:
            if generation == self._detail_generation:
                self.detail, self.detail_error = detail, error
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
            with self._lock:
                self._txids = [tx.txid for tx in data.mempool.top_transactions] if data.mempool else []
                self._visible_rows = visible_transaction_rows(transactions_height)
                self._follow_selection()
                scroll_offset, selected = self.scroll_offset, self.selected
                detail_txid, detail, detail_error = self.detail_txid, self.detail, self.detail_error

            self.layout["sys"].update(get_system_panel())
            self.layout["bitcoin_info"].update(get_bitcoin_info_panel(data.bitcoin))
            self.layout["node"].update(get_node_panel(data.node, data.error))
            self.layout["network"].update(get_network_panel(data.network))
            self.layout["mempool"].update(get_mempool_panel(data.mempool))
            price = data.bitcoin.price if data.bitcoin else None
            currency = data.bitcoin.currency if data.bitcoin else None
            self.layout["top_transactions"].update(
                get_top_transactions_panel(
                    data.mempool, price, width, transactions_height, scroll_offset, currency, selected
                )
            )
            projection_height = height - TOP_ROW_HEIGHT - RECENT_BLOCKS_PANEL_HEIGHT
            self.layout["projection"].update(
                get_projection_panel(data.projection, width // 2, projection_height, data.fee_estimates)
            )
            self.layout["recent_blocks"].update(get_recent_blocks_panel(data.recent_blocks))

            # The lower half shows one of: the sync view, a transaction's details, or the usual panels
            syncing = data.sync is not None
            showing_detail = detail_txid is not None and not syncing
            self.layout["sync"].visible = syncing
            self.layout["detail"].visible = showing_detail
            self.layout["bottom"].visible = not syncing and not showing_detail
            if syncing:
                self.layout["sync"].update(get_sync_panel(data.sync, width))
            elif showing_detail:
                detail_panel = get_transaction_detail_panel(
                    detail_txid, detail, detail_error, price, currency, width, height - TOP_ROW_HEIGHT
                )
                self.layout["detail"].update(detail_panel)
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
