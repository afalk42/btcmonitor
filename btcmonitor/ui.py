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
from rich.box import SIMPLE

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
class BlockProjection:
    est_tx: int
    est_weight_vbytes: int
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
    return Panel(text, title="System", box=SIMPLE)


def get_node_panel(snap: Optional[NodeSnapshot], err: Optional[str]) -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", style="bold cyan")
    table.add_column()
    if err:
        return Panel(Text(err, style="bold red"), title="Bitcoin Core", box=SIMPLE)
    if not snap:
        return Panel(Text("Connecting..."), title="Bitcoin Core", box=SIMPLE)
    table.add_row("Chain", snap.chain)
    table.add_row("Height", str(snap.height))
    table.add_row("Headers", str(snap.headers))
    table.add_row("Verify", f"{snap.verification_progress*100:.2f}%")
    table.add_row("Peers", str(snap.peers))
    table.add_row("Mempool", f"{snap.mempool_tx} txs / {format_bytes(snap.mempool_bytes)}")
    table.add_row("Difficulty", f"{snap.difficulty:.4g}")
    return Panel(table, title="Bitcoin Core", box=SIMPLE)


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
        return Panel(Text("…"), title="Mempool", box=SIMPLE)
    text = Text()
    text.append(f"Total: {view.total_tx} txs / {format_bytes(view.total_vbytes)}\n\n")
    text.append(ascii_histogram(view.fee_buckets))
    return Panel(text, title="Mempool", box=SIMPLE)


def get_projection_panel(proj: Optional[BlockProjection]) -> Panel:
    if not proj:
        return Panel(Text("…"), title="Next Block (est)", box=SIMPLE)
    text = Text()
    text.append(f"Tx: ~{proj.est_tx}, Weight(vB): ~{proj.est_weight_vbytes}\n\n")
    text.append(ascii_histogram(proj.fee_buckets))
    return Panel(text, title="Next Block (est)", box=SIMPLE)


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
        # Projection: try getblocktemplate; fallback to fill with top fee buckets totaling ~ 1e6 vB
        proj: Optional[BlockProjection] = None
        try:
            gbt = rpc.get_block_template()
            # Estimate from transactions in template
            txs = gbt.get("transactions", [])
            total_vb = sum(tx.get("weight", 0) // 4 for tx in txs)
            est_tx = len(txs)
            # Build fee buckets from gbt if fee info present (not always); else reuse mempool buckets filtered
            proj_buckets = build_fee_buckets({t.get("txid", f"{i}"): {"vsize": t.get("weight", 0)//4, "fees": {"base": (t.get("fee", 0)/1e8)}} for i, t in enumerate(txs)})
            proj = BlockProjection(est_tx=est_tx, est_weight_vbytes=total_vb, fee_buckets=proj_buckets)
        except RPCError:
            # fallback: greedy include from highest fee bands
            sorted_buckets = sorted(fee_buckets, key=lambda x: int(x[0].split()[0].replace(">=", "").split("-")[0]), reverse=True)
            capacity = 1_000_000  # ~1M vbytes
            acc_vb = 0
            proj_buckets: List[Tuple[str, int]] = []
            for label, vb in sorted_buckets:
                if acc_vb >= capacity:
                    break
                take = min(vb, capacity - acc_vb)
                if take > 0:
                    proj_buckets.append((label, take))
                    acc_vb += take
            est_tx = int(view.total_tx * (acc_vb / max(1, view.total_vbytes))) if view.total_vbytes else 0
            proj = BlockProjection(est_tx=est_tx, est_weight_vbytes=acc_vb, fee_buckets=proj_buckets)
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

    with Live(layout, console=console, auto_refresh=False, screen=True):
        while True:
            snap, mem_view, proj, err = gather_snapshot(rpc)
            layout["sys"].update(get_system_panel())
            layout["node"].update(get_node_panel(snap, err))
            layout["mempool"].update(get_mempool_panel(mem_view))
            layout["projection"].update(get_projection_panel(proj))
            console.set_window_title("btcmonitor")
            console.refresh()
            time.sleep(max(0.1, 1.0 / refresh_hz))
