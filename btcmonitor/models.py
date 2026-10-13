"""Plain data objects passed from the collector to the panels"""

from __future__ import annotations

from dataclasses import dataclass

# (label, vbytes) pairs as produced by fees.build_fee_buckets
FeeBuckets = list[tuple[str, int]]


@dataclass
class NodeSnapshot:
    height: int
    headers: int
    verification_progress: float
    chain: str
    peers: int
    inbound_peers: int
    outbound_peers: int
    mempool_bytes: int
    mempool_tx: int
    difficulty: float
    initial_block_download: bool = False


@dataclass
class SyncProgress:
    """Initial block download status; rates and ETA are None until enough samples exist"""

    height: int
    headers: int
    verification_progress: float  # 0..1, Bitcoin Core's estimate by transaction count
    blocks_per_second: float | None
    eta_seconds: float | None
    tip_time: int | None  # unix timestamp of the most recent validated block
    size_on_disk: int | None
    pruned: bool = False


@dataclass
class MempoolTransaction:
    txid: str
    amount_btc: float
    fee_btc: float
    fee_rate: float  # sat/vB


@dataclass
class MempoolView:
    total_tx: int
    usage_mb: float
    maxmempool_mb: float
    fee_buckets: FeeBuckets
    top_transactions: list[MempoolTransaction]  # sorted by amount descending
    loading_transactions: bool = False  # background lookups for top_transactions still running


@dataclass
class Transaction:
    fee_rate: float  # sat/vB
    vbytes: int
    txid: str


@dataclass
class BlockProjection:
    est_tx: int
    est_weight_vbytes: int
    transactions: list[Transaction]
    fee_buckets: FeeBuckets


@dataclass
class BitcoinInfo:
    price: float | None  # in `currency`
    current_subsidy: float
    blocks_until_halving: int
    estimated_halving_date: str | None
    last_block_time: int | None  # unix timestamp of the best block
    currency: str | None = "usd"  # None when price lookups are turned off
    price_unsupported: bool = False  # the price source does not quote `currency`


@dataclass
class RecentBlock:
    height: int
    hash: str
    time: int  # unix timestamp from the block header
    tx_count: int  # including the coinbase
    size: int  # bytes
    total_fee_btc: float
    miner: str  # best-effort pool name from the coinbase tag


@dataclass
class DashboardData:
    """Everything one collection cycle produced; `error` is set instead when the node could not be read"""

    node: NodeSnapshot | None = None
    mempool: MempoolView | None = None
    projection: BlockProjection | None = None
    bitcoin: BitcoinInfo | None = None
    sync: SyncProgress | None = None  # set only during initial block download
    # sat/vB per confirmation target in blocks; None where the node has too little data
    fee_estimates: dict[int, float | None] | None = None
    recent_blocks: list[RecentBlock] | None = None  # newest first
    error: str | None = None
