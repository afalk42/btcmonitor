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
    price_usd: float | None
    current_subsidy: float
    blocks_until_halving: int
    estimated_halving_date: str | None
    last_block_time: int | None  # unix timestamp of the best block


@dataclass
class DashboardData:
    """Everything one collection cycle produced; `error` is set instead when the node could not be read"""

    node: NodeSnapshot | None = None
    mempool: MempoolView | None = None
    projection: BlockProjection | None = None
    bitcoin: BitcoinInfo | None = None
    error: str | None = None
