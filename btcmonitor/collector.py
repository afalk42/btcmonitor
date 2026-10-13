"""Polling the node for dashboard data on a background thread"""

from __future__ import annotations

import threading
import time

from .chain import calculate_halving_info, get_current_subsidy
from .fees import (
    FEE_ESTIMATE_TARGETS,
    build_fee_buckets,
    estimate_to_sat_per_vbyte,
    project_block_from_buckets,
    project_block_from_template,
)
from .models import BitcoinInfo, BlockProjection, DashboardData, FeeBuckets, MempoolView, NodeSnapshot, SyncProgress
from .price import PriceFeed
from .rpc import BitcoinRPC, RPCError
from .sync import SyncRate
from .transactions import TransactionTracker


class Collector:
    """Polls the node on its own thread, so slow RPC calls never stall the display.

    Cheap calls run every `interval` seconds. The verbose mempool and the block template grow with
    the mempool (tens of MB and noticeable node CPU when it is full), so they are refreshed every
    `mempool_seconds`, or as soon as a new block arrives.
    """

    def __init__(
        self,
        rpc: BitcoinRPC,
        interval: float = 0.5,
        mempool_seconds: float = 5.0,
        price_feed: PriceFeed | None = None,
        tracker: TransactionTracker | None = None,
    ):
        self.rpc = rpc
        self.interval = interval
        self.mempool_seconds = mempool_seconds
        self.price_feed = price_feed or PriceFeed()
        self.tracker = tracker or TransactionTracker(rpc)
        self.sync_rate = SyncRate()
        # Replaced wholesale after each cycle; readers on other threads just take the reference
        self.latest = DashboardData()

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._mempool: dict[str, dict] = {}
        self._fee_buckets: FeeBuckets = []
        self._projection: BlockProjection | None = None
        self._fee_estimates: dict[int, float | None] = {}
        self._mempool_fetched_at: float | None = None
        self._mempool_height: int | None = None
        self._best_hash: str | None = None
        self._best_time: int | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.latest = self.collect()
            self._stop.wait(self.interval)

    def collect(self) -> DashboardData:
        """One polling cycle; failures are returned as `error` rather than raised"""
        try:
            return self._collect()
        except RPCError as e:
            return DashboardData(error=str(e))
        except Exception as e:
            # Unexpected data from the node must not take down the dashboard; show it and keep polling
            return DashboardData(error=f"Unexpected error: {type(e).__name__}: {e}")

    def _collect(self) -> DashboardData:
        bi = self.rpc.get_blockchain_info()
        mi = self.rpc.get_mempool_info()
        peers = int(self.rpc.get_connection_count())
        height = int(bi.get("blocks", 0))

        # Get detailed peer information for inbound/outbound breakdown
        try:
            peer_info = self.rpc.get_peer_info()
            inbound_count = sum(1 for peer in peer_info if peer.get("inbound", False))
            outbound_count = len(peer_info) - inbound_count
        except Exception:
            inbound_count, outbound_count = 0, peers

        node = NodeSnapshot(
            height=height,
            headers=int(bi.get("headers", 0)),
            verification_progress=float(bi.get("verificationprogress", 0.0)),
            chain=str(bi.get("chain", "")),
            peers=peers,
            inbound_peers=inbound_count,
            outbound_peers=outbound_count,
            mempool_bytes=int(mi.get("bytes", 0)),
            mempool_tx=int(mi.get("size", 0)),
            difficulty=float(bi.get("difficulty", 0.0)),
            initial_block_download=bool(bi.get("initialblockdownload", False)),
        )

        now = time.monotonic()
        self.sync_rate.add(now, height, node.verification_progress)
        if (
            self._mempool_fetched_at is None
            or now - self._mempool_fetched_at >= self.mempool_seconds
            or height != self._mempool_height
        ):
            self._refresh_mempool(height)
            self._mempool_fetched_at = now

        mempool = MempoolView(
            total_tx=len(self._mempool),
            usage_mb=mi.get("usage", 0) / (1000 * 1000),
            maxmempool_mb=mi.get("maxmempool", 0) / (1000 * 1000),
            fee_buckets=self._fee_buckets,
            top_transactions=self.tracker.update(self._mempool, height),
            loading_transactions=self.tracker.loading,
        )

        blocks_until_halving, halving_date = calculate_halving_info(height)
        bitcoin = BitcoinInfo(
            price_usd=self.price_feed.get(),
            current_subsidy=get_current_subsidy(height),
            blocks_until_halving=blocks_until_halving,
            estimated_halving_date=halving_date,
            last_block_time=self._last_block_time(bi),
        )
        sync = None
        if node.initial_block_download:
            sync = SyncProgress(
                height=height,
                headers=node.headers,
                verification_progress=node.verification_progress,
                blocks_per_second=self.sync_rate.blocks_per_second,
                eta_seconds=self.sync_rate.eta_seconds,
                tip_time=bi.get("time") or bitcoin.last_block_time,
                size_on_disk=bi.get("size_on_disk"),
                pruned=bool(bi.get("pruned", False)),
            )
        return DashboardData(
            node=node,
            mempool=mempool,
            projection=self._projection,
            bitcoin=bitcoin,
            sync=sync,
            fee_estimates=self._fee_estimates,
        )

    def _refresh_mempool(self, height: int) -> None:
        self._mempool = self.rpc.get_raw_mempool(True)
        self._mempool_height = height
        self._fee_buckets = build_fee_buckets(self._mempool)
        try:
            self._projection = project_block_from_template(self.rpc.get_block_template())
        except RPCError:
            # No template during initial block download or without peers: estimate from the mempool
            self._projection = project_block_from_buckets(self._fee_buckets)
        self._fee_estimates = {target: self._estimate_fee(target) for target in FEE_ESTIMATE_TARGETS}

    def _estimate_fee(self, target: int) -> float | None:
        try:
            return estimate_to_sat_per_vbyte(self.rpc.estimate_smart_fee(target))
        except RPCError:
            return None

    def _last_block_time(self, blockchain_info: dict) -> int | None:
        """Timestamp of the best block, fetched only when the best block changes"""
        try:
            best_hash = blockchain_info.get("bestblockhash") or self.rpc.get_best_block_hash()
            if best_hash != self._best_hash:
                self._best_time = int(self.rpc.get_block(best_hash)["time"])
                self._best_hash = best_hash
        except Exception:
            pass  # keep the previous value; the panel shows N/A if there never was one
        return self._best_time
