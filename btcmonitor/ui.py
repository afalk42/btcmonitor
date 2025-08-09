from __future__ import annotations
import time
import math
import threading
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import urllib.request
import json

import psutil
import readchar
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
    usage_mb: float
    maxmempool_mb: float
    fee_buckets: List[Tuple[str, int]]  # label, vbytes
    top_transactions: List[MempoolTransaction]  # sorted by amount descending


@dataclass  
class Transaction:
    fee_rate: float  # sat/vB
    vbytes: int
    txid: str

@dataclass
class MempoolTransaction:
    txid: str
    amount_btc: float
    fee_btc: float
    fee_rate: float  # sat/vB

@dataclass
class BlockProjection:
    est_tx: int
    est_weight_vbytes: int
    transactions: List[Transaction]
    fee_buckets: List[Tuple[str, int]]  # label, vbytes

@dataclass
class BitcoinInfo:
    price_usd: Optional[float]
    current_subsidy: float
    blocks_until_halving: int
    estimated_halving_date: Optional[str]
    time_since_last_block: Optional[int]  # seconds since last block


def format_bytes(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024:
            return f"{num:.0f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"

def format_txid(txid: str) -> str:
    """Format transaction ID as first4...last4"""
    if len(txid) >= 8:
        return f"{txid[:4]}...{txid[-4:]}"
    return txid

def format_time_since_block(seconds: int) -> str:
    """Format seconds into minutes:seconds format"""
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}:{remaining_seconds:02d}"

def get_current_subsidy(block_height: int) -> float:
    """Calculate current block subsidy based on block height"""
    subsidy = 50.0  # Initial subsidy
    halvings = block_height // 210_000
    return subsidy / (2 ** halvings)

def calculate_halving_info(block_height: int) -> Tuple[int, Optional[str]]:
    """Calculate blocks until next halving and estimated date"""
    HALVING_INTERVAL = 210_000
    BLOCK_TIME_MINUTES = 10  # Average block time
    
    next_halving_block = ((block_height // HALVING_INTERVAL) + 1) * HALVING_INTERVAL
    blocks_until_halving = next_halving_block - block_height
    
    # Estimate date (approximate)
    minutes_until_halving = blocks_until_halving * BLOCK_TIME_MINUTES
    estimated_date = datetime.now() + timedelta(minutes=minutes_until_halving)
    date_str = estimated_date.strftime("%Y-%m-%d")
    
    return blocks_until_halving, date_str

# Global price cache
_price_cache: Dict[str, float] = {}
_last_price_fetch = 0.0
PRICE_CACHE_DURATION = 60.0  # 60 seconds

def fetch_bitcoin_price() -> Optional[float]:
    """Fetch Bitcoin price from a public API with caching"""
    global _price_cache, _last_price_fetch
    
    current_time = time.time()
    
    # Check if we have a cached price that's less than 60 seconds old
    if (current_time - _last_price_fetch) < PRICE_CACHE_DURATION and "btc_usd" in _price_cache:
        return _price_cache["btc_usd"]
    
    try:
        # Using CoinGecko API (no auth required)
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read())
            price = float(data["bitcoin"]["usd"])
            
            # Update cache
            _price_cache["btc_usd"] = price
            _last_price_fetch = current_time
            
            return price
    except Exception:
        # If API fails, return cached price if available
        return _price_cache.get("btc_usd", None)


def get_bitcoin_info_panel(info: Optional[BitcoinInfo]) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold orange1")
    table.add_column()
    
    if not info:
        return Panel(Text("Loading...", style="dim"), title="Bitcoin", box=ROUNDED)
    
    price_str = f"${info.price_usd:,.0f}" if info.price_usd else "N/A"
    table.add_row("Price", price_str)
    table.add_row("Block Subsidy", f"{info.current_subsidy:.3f} BTC")
    table.add_row("To Next Halving", f"{info.blocks_until_halving:,} blocks")
    halving_date = info.estimated_halving_date or "Unknown"
    table.add_row("Est. Date", halving_date)
    
    time_since_str = format_time_since_block(info.time_since_last_block) if info.time_since_last_block is not None else "N/A"
    table.add_row("Since Last Block", time_since_str)
    
    return Panel(table, title="Bitcoin", box=ROUNDED)

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
    bands = [1, 2, 3, 5, 10, 20, 50, 100, 500, 1000]
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
        if i == 0:
            # First band: "< 2 sat/vB"
            label = f"< {bands[i + 1]}  sat/vB"
        elif i == len(bands) - 1:
            # Last band: "1000+ sat/vB"
            label = f"{lo}+ sat/vB"
        else:
            # Middle bands: "2+ sat/vB", "3+ sat/vB", etc.
            label = f"{lo}+ sat/vB"
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
        if vb == 0:
            bar_len = 0
        else:
            # Calculate bar length, then ensure minimum of 1 for non-zero values
            bar_len = 1 + int((vb / max_vb) * max_width)
        
        # Extract fee rate from label for coloring
        if label.startswith("<"):
            # Handle "< 2 sat/vB" format - use 1 as representative fee rate
            fee_rate = 1.0
        else:
            # Handle "2+ sat/vB", "3+ sat/vB", "1000+ sat/vB", etc. format
            fee_rate = float(label.split("+")[0])
        color = get_fee_color(fee_rate)
        
        bar = "█" * bar_len
        text.append(f"{label:>14} | ")
        text.append(bar, style=color)
        text.append(f" {vb}\n")
    return text


def get_mempool_panel(view: Optional[MempoolView]) -> Panel:
    if not view:
        return Panel(Text("…"), title="Mempool", box=ROUNDED)
    text = Text()
    text.append(f"Total: {view.total_tx} txs | Memory Usage: {view.usage_mb:.2f} MB / {view.maxmempool_mb:.2f} MB\n\n")
    text.append(ascii_histogram(view.fee_buckets))
    return Panel(text, title="Mempool", box=ROUNDED)

def get_top_transactions_panel(view: Optional[MempoolView], bitcoin_price: Optional[float]) -> Panel:
    if not view:
        return Panel(Text("Loading..."), title="Largest Transactions", box=ROUNDED)
    
    if not view.top_transactions:
        return Panel(Text(f"No transaction data available\n(Total mempool txs: {view.total_tx if view else 0})"), title="Largest Transactions", box=ROUNDED)
    
    # Create table with headers
    table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    table.add_column("TxID", style="yellow", width=12)
    table.add_column("BTC", style="bright_green", justify="right", width=10)
    table.add_column("USD", style="bright_green", justify="right", width=10)
    table.add_column("Fee", style="orange1", justify="right", width=8)
    
    # Show top 100 transactions (or fewer if available)
    for tx in view.top_transactions[:100]:
        txid_short = format_txid(tx.txid)
        amount_btc = f"{tx.amount_btc:.4f}"
        
        # Calculate USD amount if price available
        if bitcoin_price:
            amount_usd = f"${tx.amount_btc * bitcoin_price:,.0f}"
        else:
            amount_usd = "N/A"
            
        fee_btc = f"{tx.fee_btc:.6f}"
        
        table.add_row(txid_short, amount_btc, amount_usd, fee_btc)
    
    return Panel(table, title="Largest Transactions", box=ROUNDED)


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


def gather_snapshot(rpc: BitcoinRPC) -> Tuple[Optional[NodeSnapshot], Optional[MempoolView], Optional[BlockProjection], Optional[BitcoinInfo], Optional[str]]:
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
        usage_mb = mi.get("usage", 0) / (1000 * 1000)  # Convert bytes to MB
        maxmempool_mb = mi.get("maxmempool", 0) / (1000 * 1000)  # Convert bytes to MB
        
        # Extract ALL transactions and get their actual BTC output amounts
        top_transactions = []
        processed_count = 0
        error_count = 0
        total_count = len(mem_verbose)
        
        # Limit processing to avoid very long delays for huge mempools
        max_to_process = min(1000, total_count)  # Process up to 1000 transactions
        items_to_process = list(mem_verbose.items())[:max_to_process]
        
        for txid, tx_data in items_to_process:
            processed_count += 1
            fee_btc = tx_data.get("fees", {}).get("base", 0.0)
            vbytes = tx_data.get("vsize", tx_data.get("weight", 0) // 4)
            fee_rate = (fee_btc * 1e8) / max(1, vbytes) if vbytes > 0 else 0
            
            try:
                # Get actual transaction details
                tx_detail = rpc.get_raw_transaction(txid, True)
                # Sum all output values to get total BTC amount
                amount_btc = sum(float(vout.get("value", 0)) for vout in tx_detail.get("vout", []))
                
                if amount_btc > 0:
                    top_transactions.append(MempoolTransaction(
                        txid=txid,
                        amount_btc=amount_btc,
                        fee_btc=fee_btc,
                        fee_rate=fee_rate
                    ))
            except Exception as e:
                error_count += 1
                # If lookup fails, continue with next transaction
                continue
        
        # Sort by actual BTC output amount descending and take top 100
        top_transactions.sort(key=lambda x: x.amount_btc, reverse=True)
        top_transactions = top_transactions[:100]
        
        view = MempoolView(
            total_tx=len(mem_verbose),
            total_vbytes=sum(tx.get("vsize", tx.get("weight", 0) // 4) for tx in mem_verbose.values()),
            usage_mb=usage_mb,
            maxmempool_mb=maxmempool_mb,
            fee_buckets=fee_buckets,
            top_transactions=top_transactions,
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
        
        # Bitcoin info (price, subsidy, halving)
        block_height = int(bi.get("blocks", 0))
        current_subsidy = get_current_subsidy(block_height)
        blocks_until_halving, halving_date = calculate_halving_info(block_height)
        
        # Fetch Bitcoin price (async, might fail)
        bitcoin_price = fetch_bitcoin_price()
        
        # Get time since last block
        time_since_last_block = None
        try:
            best_hash = rpc.get_best_block_hash()
            block_info = rpc.get_block(best_hash)
            block_timestamp = block_info.get("time", 0)
            current_timestamp = int(time.time())
            time_since_last_block = current_timestamp - block_timestamp
        except (RPCError, Exception):
            pass  # If we can't get block time, just show N/A
        
        bitcoin_info = BitcoinInfo(
            price_usd=bitcoin_price,
            current_subsidy=current_subsidy,
            blocks_until_halving=blocks_until_halving,
            estimated_halving_date=halving_date,
            time_since_last_block=time_since_last_block
        )
        
        return snap, view, proj, bitcoin_info, None
    except RPCError as e:
        return None, None, None, None, str(e)


# Global flag for quit signal
_quit_requested = False

def keyboard_listener():
    """Background thread to listen for single keypress input"""
    global _quit_requested
    
    try:
        while not _quit_requested:
            try:
                # readchar.readkey() blocks until a key is pressed
                # but doesn't interfere with Rich's display
                key = readchar.readkey()
                if key.lower() == 'q':
                    _quit_requested = True
                    break
            except (KeyboardInterrupt, EOFError):
                # Handle Ctrl-C or EOF
                break
            except Exception:
                # Handle any other readchar exceptions
                break
    except Exception:
        # Silently handle any other exceptions
        pass


def render_dashboard(rpc: BitcoinRPC, refresh_hz: float = 2.0) -> None:
    global _quit_requested
    _quit_requested = False
    
    console = Console()
    layout = Layout()
    layout.split_column(
        Layout(name="top", size=7),
        Layout(name="bottom")
    )
    layout["top"].split_row(
        Layout(name="sys"),
        Layout(name="bitcoin_info"),
        Layout(name="node"),
    )
    layout["bottom"].split_row(
        Layout(name="left"),
        Layout(name="projection"),
    )
    # Split the left side into mempool (top) and top transactions (bottom)
    layout["left"].split_column(
        Layout(name="mempool"),
        Layout(name="top_transactions"),
    )

    # Start keyboard listener thread
    keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
    keyboard_thread.start()

    with Live(console=console, auto_refresh=False, screen=True, transient=False) as live:
        while True:
            # Check for quit signal
            if _quit_requested:
                break
                
            snap, mem_view, proj, bitcoin_info, err = gather_snapshot(rpc)
            layout["sys"].update(get_system_panel())
            layout["bitcoin_info"].update(get_bitcoin_info_panel(bitcoin_info))
            layout["node"].update(get_node_panel(snap, err))
            layout["mempool"].update(get_mempool_panel(mem_view))
            layout["top_transactions"].update(get_top_transactions_panel(mem_view, bitcoin_info.price_usd if bitcoin_info else None))
            layout["projection"].update(get_projection_panel(proj, console))
            console.set_window_title("btcmonitor")
            live.update(layout, refresh=True)
            time.sleep(max(0.1, 1.0 / refresh_hz))
