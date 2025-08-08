from __future__ import annotations
import time
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psutil
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.progress import BarColumn, Progress, TextColumn
from rich.text import Text
from rich.box import ROUNDED

from .rpc import BitcoinRPC, RPCError


@dataclass
class NodeSnapshot:
    height: int
    headers: int
    verification_progress: float
    chain: str
    peers: int
    mempool_bytes: int
    mempool_tx: int
    difficulty: float


@dataclass
class MempoolView:
    total_tx: int
    total_vbytes: int
    fee_buckets: List[Tuple[str, int]]  # label, vbytes


@dataclass  
class Transaction:
    fee_rate: float  # sat/vB
    vbytes: int
    txid: str

@dataclass
class BlockProjection:
    est_tx: int
    est_weight_vbytes: int
    transactions: List[Transaction]
    fee_buckets: List[Tuple[str, int]]  # label, vbytes


def format_bytes(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return f"{num:.0f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def get_system_panel() -> Panel:
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    text = Text()
    text.append(f"CPU: {cpu:5.1f}%\n")
    text.append(f"RAM: {mem.percent:5.1f}% of {format_bytes(mem.total)}\n")
    text.append(f"SWP: {swap.percent:5.1f}% of {format_bytes(swap.total)}\n")
    return Panel(text, title="System", box=ROUNDED)


def get_node_panel(snap: Optional[NodeSnapshot], err: Optional[str]) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold cyan")
    table.add_column()
    if err:
        return Panel(Text(err, style="bold red"), title="Bitcoin Core", box=ROUNDED)
    if not snap:
        return Panel(Text("Connecting..."), title="Bitcoin Core", box=ROUNDED)
    table.add_row("Chain", snap.chain)
    table.add_row("Height", str(snap.height))
    table.add_row("Headers", str(snap.headers))
    table.add_row("Verify", f"{snap.verification_progress*100:.2f}%")
    table.add_row("Peers", str(snap.peers))
    table.add_row("Mempool", f"{snap.mempool_tx} txs / {format_bytes(snap.mempool_bytes)}")
    table.add_row("Difficulty", f"{snap.difficulty:.4g}")
    return Panel(table, title="Bitcoin Core", box=ROUNDED)


def build_fee_buckets(mempool: Dict[str, Dict]) -> List[Tuple[str, int]]:
    # Fee rate buckets in sat/vB
    bands = [1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 80, 100, 150, 200, 300, 500, 800, 1000]
    vbytes_per_band = [0 for _ in bands]
    for tx in mempool.values():
        fee_sat = int(tx.get("fees", {}).get("base", 0) * 1e8)
        vsize = tx.get("vsize") or tx.get("weight", 0) // 4
        fr = fee_sat / max(1, vsize)
        # find band index
        idx = 0
        while idx < len(bands) - 1 and fr > bands[idx + 1]:
            idx += 1
        vbytes_per_band[idx] += int(vsize)
    labels: List[Tuple[str, int]] = []
    for i, vb in enumerate(vbytes_per_band):
        lo = bands[i]
        hi = (bands[i + 1] - 1) if i + 1 < len(bands) else lo
        label = f"{lo}-{hi} sat/vB" if i + 1 < len(bands) else f">= {lo} sat/vB"
        labels.append((label, vb))
    return labels


def get_fee_color(fee_rate: float) -> str:
    """Get color for fee rate visualization"""
    if fee_rate >= 100:
        return "bright_red"
    elif fee_rate >= 50:
        return "red"
    elif fee_rate >= 20:
        return "bright_yellow"
    elif fee_rate >= 10:
        return "yellow"
    elif fee_rate >= 5:
        return "bright_green"
    elif fee_rate >= 2:
        return "green"
    else:
        return "blue"

def render_block_grid(transactions: List[Transaction], console: Console, panel_width: int = None, panel_height: int = None) -> Text:
    """Render block as a visual grid like mempool.space with dynamic sizing"""
    text = Text()
    
    if not transactions:
        text.append("No transactions", style="dim")
        return text
    
    # Calculate available dimensions
    if panel_width is None or panel_height is None:
        # Get terminal size and estimate panel size
        term_width = console.size.width
        term_height = console.size.height
        # Projection panel is roughly 1/2 width, and takes up roughly 2/3 of the bottom half
        # Account for borders, title, legend, etc.
        width = max(20, min(80, (term_width // 2) - 6))  # Leave space for borders
        height = max(6, min(40, (2 * term_height // 3) - 8))  # Leave space for text + legend
    else:
        width = max(20, min(80, panel_width - 6))
        height = max(6, min(40, panel_height - 8))
    
    # Sort transactions by fee rate (highest first)
    sorted_txs = sorted(transactions, key=lambda t: t.fee_rate, reverse=True)
    
    # Calculate grid dimensions - distribute transactions across cells
    total_cells = width * height
    if len(sorted_txs) > total_cells:
        # More transactions than cells - multiple transactions per cell
        tx_per_cell = len(sorted_txs) // total_cells
        remainder = len(sorted_txs) % total_cells
    else:
        # Fewer transactions than cells - one transaction per cell
        tx_per_cell = 1
        remainder = 0
    
    cell_idx = 0
    for row in range(height):
        for col in range(width):
            if cell_idx < len(sorted_txs):
                tx = sorted_txs[cell_idx]
                color = get_fee_color(tx.fee_rate)
                text.append("█", style=color)
                # Skip ahead based on transactions per cell
                skip = tx_per_cell
                if remainder > 0 and (row * width + col) < remainder:
                    skip += 1  # Distribute remainder across first cells
                cell_idx += skip
            else:
                # Empty space in block
                text.append("░", style="dim")
        text.append("\n")
    
    return text

def ascii_histogram(buckets: List[Tuple[str, int]], max_width: int = 40) -> Text:
    text = Text()
    max_vb = max((vb for _, vb in buckets), default=1)
    for label, vb in buckets:
        bar_len = 0 if max_vb == 0 else int((vb / max_vb) * max_width)
        bar = "#" * bar_len
        text.append(f"{label:>14} | {bar} {vb}\n")
    return text


def get_mempool_panel(view: Optional[MempoolView]) -> Panel:
    if not view:
        return Panel(Text("…"), title="Mempool", box=ROUNDED)
    text = Text()
    text.append(f"Total: {view.total_tx} txs / {format_bytes(view.total_vbytes)}\n\n")
    text.append(ascii_histogram(view.fee_buckets))
    return Panel(text, title="Mempool", box=ROUNDED)


def get_projection_panel(proj: Optional[BlockProjection], console: Console) -> Panel:
    if not proj:
        return Panel(Text("…"), title="Next Block Template", box=ROUNDED)
    
    text = Text()
    text.append(f"Transactions: {proj.est_tx:,} | Size: {format_bytes(proj.est_weight_vbytes)}\n")
    
    if proj.transactions:
        # Show fee rate statistics
        fee_rates = [tx.fee_rate for tx in proj.transactions]
        min_fee = min(fee_rates)
        max_fee = max(fee_rates)
        avg_fee = sum(fee_rates) / len(fee_rates)
        text.append(f"Fee: {min_fee:.1f}-{max_fee:.1f} (avg: {avg_fee:.1f}) sat/vB\n\n")
        
        # Render the visual block grid with dynamic sizing
        text.append(render_block_grid(proj.transactions, console))
        
        # Add fee rate legend
        text.append("\nFee Legend: ")
        text.append("█", style="bright_red")
        text.append("100+ ")
        text.append("█", style="red") 
        text.append("50+ ")
        text.append("█", style="bright_yellow")
        text.append("20+ ")
        text.append("█", style="yellow")
        text.append("10+ ")
        text.append("█", style="bright_green")
        text.append("5+ ")
        text.append("█", style="green")
        text.append("2+ ")
        text.append("█", style="blue")
        text.append("<2 sat/vB")
    else:
        text.append("\nNo transaction data available")
        
    return Panel(text, title="Next Block Template", box=ROUNDED)


def gather_snapshot(rpc: BitcoinRPC) -> Tuple[Optional[NodeSnapshot], Optional[MempoolView], Optional[BlockProjection], Optional[str]]:
    try:
        bi = rpc.get_blockchain_info()
        mi = rpc.get_mempool_info()
        peers = rpc.get_connection_count()
        mem_verbose = rpc.get_raw_mempool(True)
        snap = NodeSnapshot(
            height=int(bi.get("blocks", 0)),
            headers=int(bi.get("headers", 0)),
            verification_progress=float(bi.get("verificationprogress", 0.0)),
            chain=str(bi.get("chain", "")),
            peers=int(peers),
            mempool_bytes=int(mi.get("bytes", 0)),
            mempool_tx=int(mi.get("size", 0)),
            difficulty=float(bi.get("difficulty", 0.0)),
        )
        fee_buckets = build_fee_buckets(mem_verbose)
        view = MempoolView(
            total_tx=len(mem_verbose),
            total_vbytes=sum(tx.get("vsize", tx.get("weight", 0) // 4) for tx in mem_verbose.values()),
            fee_buckets=fee_buckets,
        )
        # Projection: try getblocktemplate; fallback to mempool estimation
        proj: Optional[BlockProjection] = None
        try:
            gbt = rpc.get_block_template()
            txs = gbt.get("transactions", [])
            
            # Create Transaction objects from block template
            transactions = []
            for i, tx in enumerate(txs):
                vbytes = tx.get("weight", 0) // 4
                fee_btc = tx.get("fee", 0) / 1e8
                fee_rate = (fee_btc * 1e8) / max(1, vbytes)  # sat/vB
                
                transactions.append(Transaction(
                    fee_rate=fee_rate,
                    vbytes=vbytes,
                    txid=tx.get("txid", f"tx_{i}")
                ))
            
            total_vb = sum(tx.vbytes for tx in transactions)
            proj_buckets = build_fee_buckets({t.txid: {"vsize": t.vbytes, "fees": {"base": t.fee_rate/1e8}} for t in transactions})
            proj = BlockProjection(
                est_tx=len(transactions), 
                est_weight_vbytes=total_vb, 
                transactions=transactions,
                fee_buckets=proj_buckets
            )
            
        except RPCError:
            # Fallback: estimate from mempool using greedy algorithm
            sorted_buckets = sorted(fee_buckets, key=lambda x: int(x[0].split()[0].replace(">=", "").split("-")[0]), reverse=True)
            capacity = 1_000_000  # ~1M vbytes
            acc_vb = 0
            proj_buckets: List[Tuple[str, int]] = []
            transactions = []
            
            # Create synthetic transactions from fee buckets
            tx_id = 0
            for label, vb in sorted_buckets:
                if acc_vb >= capacity:
                    break
                take = min(vb, capacity - acc_vb)
                if take > 0:
                    proj_buckets.append((label, take))
                    # Parse fee rate from label 
                    fee_rate = int(label.split()[0].replace(">=", "").split("-")[0])
                    # Create synthetic transactions (group by ~250 vbytes each)
                    tx_size = 250
                    num_txs = max(1, take // tx_size)
                    for _ in range(num_txs):
                        transactions.append(Transaction(
                            fee_rate=fee_rate,
                            vbytes=min(tx_size, take),
                            txid=f"synthetic_{tx_id}"
                        ))
                        tx_id += 1
                        take -= tx_size
                        if take <= 0:
                            break
                    acc_vb += min(vb, capacity - acc_vb)
            
            est_tx = len(transactions)
            proj = BlockProjection(
                est_tx=est_tx, 
                est_weight_vbytes=acc_vb, 
                transactions=transactions,
                fee_buckets=proj_buckets
            )
        return snap, view, proj, None
    except RPCError as e:
        return None, None, None, str(e)


def render_dashboard(rpc: BitcoinRPC, refresh_hz: float = 2.0) -> None:
    console = Console()
    layout = Layout()
    layout.split_column(
        Layout(name="top", size=7),
        Layout(name="bottom")
    )
    layout["top"].split_row(
        Layout(name="sys"),
        Layout(name="node"),
    )
    layout["bottom"].split_row(
        Layout(name="mempool"),
        Layout(name="projection"),
    )

    with Live(console=console, auto_refresh=False, screen=True, transient=False) as live:
        while True:
            snap, mem_view, proj, err = gather_snapshot(rpc)
            layout["sys"].update(get_system_panel())
            layout["node"].update(get_node_panel(snap, err))
            layout["mempool"].update(get_mempool_panel(mem_view))
            layout["projection"].update(get_projection_panel(proj, console))
            console.set_window_title("btcmonitor")
            live.update(layout, refresh=True)
            time.sleep(max(0.1, 1.0 / refresh_hz))
