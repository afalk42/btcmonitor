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
class NetworkInfo:
    recv_rate: float | None  # bytes/s; None until two samples exist
    send_rate: float | None
    total_recv: int  # bytes since the node started
    total_sent: int
    inbound: int
    outbound: int
    outbound_types: dict[str, int]  # short connection type -> count, e.g. {"full": 8, "block": 2}
    v2_peers: int  # peers on BIP324 encrypted (v2) transport
    clients: list[tuple[str, int]]  # user agents by count, most common first


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
class TxInput:
    prev: str  # "txid:vout" of the coin being spent
    address: str | None  # None when the spent coin could not be looked up
    amount_btc: float | None


@dataclass
class TxOutput:
    address: str | None  # None for outputs without an address, e.g. OP_RETURN
    script_type: str
    amount_btc: float


@dataclass
class TransactionDetail:
    txid: str
    vsize: int
    weight: int
    fee_btc: float
    entry_time: int  # when the transaction entered this node's mempool
    replaceable: bool | None  # BIP125 signalling, if the node reports it
    ancestor_count: int  # unconfirmed ancestors, not counting this transaction
    ancestor_fee_rate: float  # sat/vB of this transaction together with its ancestors
    descendant_count: int
    descendant_fee_rate: float
    parents: list[str]  # direct unconfirmed parents
    children: list[str]  # direct unconfirmed children
    inputs: list[TxInput]
    outputs: list[TxOutput]
    inputs_not_looked_up: int = 0  # inputs beyond the lookup limit

    @property
    def fee_rate(self) -> float:
        return self.fee_btc * 1e8 / max(1, self.vsize)


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
    network: NetworkInfo | None = None
    error: str | None = None
