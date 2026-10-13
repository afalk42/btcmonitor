"""Rich renderables for each dashboard panel"""

from __future__ import annotations

import time

import psutil
from rich.box import ROUNDED
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .fees import bucket_fee_rate
from .formatting import format_bytes, format_time_since_block, format_txid
from .models import BitcoinInfo, BlockProjection, FeeBuckets, MempoolView, NodeSnapshot, Transaction

# Colors for fee rates, highest threshold (sat/vB) first; anything lower is blue
FEE_COLORS = [
    (100, "bright_red"),
    (50, "red"),
    (20, "bright_yellow"),
    (10, "yellow"),
    (5, "bright_green"),
    (2, "green"),
]

# Hide the Fee US$ column when the terminal is narrower than this
FEE_USD_MIN_TERMINAL_WIDTH = 114


def get_fee_color(fee_rate: float) -> str:
    """Get color for fee rate visualization"""
    for threshold, color in FEE_COLORS:
        if fee_rate >= threshold:
            return color
    return "blue"


def get_bitcoin_info_panel(info: BitcoinInfo | None, now: float | None = None) -> Panel:
    if not info:
        return Panel(Text("Loading...", style="dim"), title="Bitcoin", box=ROUNDED)

    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold orange1")
    table.add_column()
    table.add_row("Price", f"${info.price_usd:,.0f}" if info.price_usd else "N/A")
    table.add_row("Block Subsidy", f"{info.current_subsidy:.3f} BTC")
    table.add_row("To Next Halving", f"{info.blocks_until_halving:,} blocks")
    table.add_row("Est. Date", info.estimated_halving_date or "Unknown")

    # Computed at render time so the clock keeps ticking between data refreshes
    if info.last_block_time is not None:
        seconds = int((now if now is not None else time.time()) - info.last_block_time)
        table.add_row("Since Last Block", format_time_since_block(seconds))
    else:
        table.add_row("Since Last Block", "N/A")

    return Panel(table, title="Bitcoin", box=ROUNDED)


def get_system_panel() -> Panel:
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Get additional system info
    try:
        uptime_hours = int((time.time() - psutil.boot_time()) // 3600)
        uptime_days, uptime_hours = divmod(uptime_hours, 24)
        # Try to get load average (Unix/Linux/macOS)
        try:
            load_info = f"Load: {psutil.getloadavg()[0]:.2f}"  # 1-minute load average
        except (AttributeError, OSError):
            # Fallback for systems without load average
            load_info = f"Procs: {len(psutil.pids())}"
    except Exception:
        uptime_days = uptime_hours = 0
        load_info = "N/A"

    text = Text()
    text.append(f"CPU: {cpu:5.1f}%\n")
    text.append(f"RAM: {mem.percent:5.1f}% of {format_bytes(mem.total)}\n")
    text.append(f"SWP: {swap.percent:5.1f}% of {format_bytes(swap.total)}\n")
    text.append(f"Uptime: {uptime_days}d {uptime_hours}h\n")
    text.append(f"{load_info}\n")
    return Panel(text, title="System", box=ROUNDED)


def get_node_panel(snap: NodeSnapshot | None, err: str | None) -> Panel:
    if err:
        return Panel(Text(err, style="bold red"), title="Bitcoin Core", box=ROUNDED)
    if not snap:
        return Panel(Text("Connecting..."), title="Bitcoin Core", box=ROUNDED)

    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold cyan")
    table.add_column()
    table.add_row("Chain", snap.chain)
    table.add_row("Height", str(snap.height))
    table.add_row("Headers", str(snap.headers))
    table.add_row("Verify", f"{snap.verification_progress * 100:.2f}%")
    table.add_row("Peers", f"{snap.peers} (In: {snap.inbound_peers} / Out: {snap.outbound_peers})")
    table.add_row("Mempool", f"{snap.mempool_tx} txs / {format_bytes(snap.mempool_bytes)}")
    table.add_row("Difficulty", f"{snap.difficulty:.4g}")
    return Panel(table, title="Bitcoin Core", box=ROUNDED)


def ascii_histogram(buckets: FeeBuckets, max_width: int = 40) -> Text:
    text = Text()
    max_vb = max((vb for _, vb in buckets), default=1)
    for label, vb in buckets:
        # Non-zero values get at least one block
        bar_len = 0 if vb == 0 else 1 + int((vb / max_vb) * max_width)
        text.append(f"{label:>14} | ")
        text.append("█" * bar_len, style=get_fee_color(bucket_fee_rate(label)))
        text.append(f" {vb}\n")
    return text


def get_mempool_panel(view: MempoolView | None) -> Panel:
    if not view:
        return Panel(Text("…"), title="Mempool", box=ROUNDED)
    text = Text()
    text.append(f"Total: {view.total_tx} txs | Memory Usage: {view.usage_mb:.2f} MB / {view.maxmempool_mb:.2f} MB\n\n")
    text.append(ascii_histogram(view.fee_buckets))
    return Panel(text, title="Mempool", box=ROUNDED)


def visible_transaction_rows(panel_height: int | None) -> int:
    """Table rows that fit in the transactions panel (its title and header take two lines)"""
    return max(1, (panel_height or 20) - 2)


def max_transaction_scroll(view: MempoolView | None, panel_height: int | None) -> int:
    if not view:
        return 0
    return max(0, len(view.top_transactions) - visible_transaction_rows(panel_height))


def get_top_transactions_panel(
    view: MempoolView | None,
    bitcoin_price: float | None,
    terminal_width: int | None = None,
    panel_height: int | None = None,
    scroll_offset: int = 0,
) -> Panel:
    title = "Largest Transactions"
    if not view:
        return Panel(Text("Loading..."), title=title, box=ROUNDED)

    if not view.top_transactions:
        if view.loading_transactions:
            message = "Loading transaction data in background...\nOther panels remain functional"
        else:
            message = f"No transaction data available\n(Total mempool txs: {view.total_tx})"
        return Panel(Text(message), title=title, box=ROUNDED)

    show_fee_usd_column = terminal_width is None or terminal_width >= FEE_USD_MIN_TERMINAL_WIDTH
    visible_rows = visible_transaction_rows(panel_height)
    total_transactions = len(view.top_transactions)
    start_idx = max(0, min(scroll_offset, max_transaction_scroll(view, panel_height)))
    end_idx = min(start_idx + visible_rows, total_transactions)

    table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    table.add_column("TxID", style="yellow", width=12)
    table.add_column("BTC", style="orange1", justify="right", width=10)
    table.add_column("US$", style="bright_green", justify="right", width=15)
    table.add_column("sat/vB", style="orange1", justify="right", width=8)
    if show_fee_usd_column:
        table.add_column("Fee US$", style="bright_green", justify="right", width=10)

    for tx in view.top_transactions[start_idx:end_idx]:
        if bitcoin_price:
            amount_usd = f"${tx.amount_btc * bitcoin_price:,.0f}"
            fee_usd = f"${tx.fee_btc * bitcoin_price:,.2f}"
        else:
            amount_usd = fee_usd = "N/A"
        row = [format_txid(tx.txid), f"{tx.amount_btc:.4f}", amount_usd, f"{tx.fee_rate:.1f}"]
        if show_fee_usd_column:
            row.append(fee_usd)
        table.add_row(*row)

    if total_transactions > visible_rows:
        title += f" ({start_idx + 1}-{end_idx} of {total_transactions})"
    return Panel(table, title=title, box=ROUNDED)


def render_block_grid(transactions: list[Transaction], width: int, height: int) -> Text:
    """Render block as a visual grid like mempool.space, `width` x `height` cells"""
    text = Text()
    if not transactions:
        text.append("No transactions", style="dim")
        return text

    # Sort transactions by fee rate (highest first)
    sorted_txs = sorted(transactions, key=lambda t: t.fee_rate, reverse=True)

    # With more transactions than cells, each cell stands for several; the first `remainder` cells take one extra
    total_cells = width * height
    if len(sorted_txs) > total_cells:
        tx_per_cell, remainder = divmod(len(sorted_txs), total_cells)
    else:
        tx_per_cell, remainder = 1, 0

    cell_idx = 0
    for row in range(height):
        for col in range(width):
            if cell_idx < len(sorted_txs):
                text.append("█", style=get_fee_color(sorted_txs[cell_idx].fee_rate))
                cell_idx += tx_per_cell + (1 if row * width + col < remainder else 0)
            else:
                # Empty space in block
                text.append("░", style="dim")
        text.append("\n")
    return text


def block_grid_size(terminal_width: int, terminal_height: int) -> tuple[int, int]:
    """Grid cells that fit the projection panel: about half the width and 2/3 of the height,
    less room for borders, the summary lines and the legend"""
    width = max(20, min(80, (terminal_width // 2) - 6))
    height = max(6, min(40, (2 * terminal_height // 3) - 8))
    return width, height


def get_projection_panel(proj: BlockProjection | None, terminal_width: int, terminal_height: int) -> Panel:
    if not proj:
        return Panel(Text("…"), title="Next Block Template", box=ROUNDED)

    text = Text()
    text.append(f"Transactions: {proj.est_tx:,} | Size: {format_bytes(proj.est_weight_vbytes)}\n")

    if proj.transactions:
        fee_rates = [tx.fee_rate for tx in proj.transactions]
        avg_fee = sum(fee_rates) / len(fee_rates)
        text.append(f"Fee: {min(fee_rates):.1f}-{max(fee_rates):.1f} (avg: {avg_fee:.1f}) sat/vB\n\n")
        text.append(render_block_grid(proj.transactions, *block_grid_size(terminal_width, terminal_height)))

        text.append("\nFee Legend: ")
        for threshold, color in FEE_COLORS:
            text.append("█", style=color)
            text.append(f"{threshold}+ ")
        text.append("█", style="blue")
        text.append("<2 sat/vB")
    else:
        text.append("\nNo transaction data available")

    return Panel(text, title="Next Block Template", box=ROUNDED)
