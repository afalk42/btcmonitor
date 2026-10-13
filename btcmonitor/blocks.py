"""The most recent blocks, with the mining pool read from each coinbase"""

from __future__ import annotations

import re

from .models import RecentBlock
from .rpc import BitcoinRPC

# Pool names as they appear in coinbase tags, checked in order, with the name to show
KNOWN_POOLS = (
    ("Foundry USA", "Foundry USA"),
    ("AntPool", "AntPool"),
    ("F2Pool", "F2Pool"),
    ("ViaBTC", "ViaBTC"),
    ("MARA", "MARA Pool"),
    ("SpiderPool", "SpiderPool"),
    ("Binance", "Binance Pool"),
    ("Luxor", "Luxor"),
    ("SECPOOL", "SECPOOL"),
    ("OCEAN", "OCEAN"),
    ("Braiins", "Braiins"),
    ("slush", "Braiins"),
    ("btccom", "BTC.com"),
    ("BTC.com", "BTC.com"),
    ("Poolin", "Poolin"),
    ("SBICrypto", "SBI Crypto"),
    ("EMCD", "EMCD"),
    ("WhitePool", "WhitePool"),
    ("NiceHash", "NiceHash"),
    ("ULTIMUS", "ULTIMUSPOOL"),
    ("KuCoin", "KuCoin Pool"),
)
MAX_TAG_LENGTH = 16
_PRINTABLE_RUN = re.compile(rb"[\x20-\x7e]{4,}")
_SLASH_TAG = re.compile(r"/([^/]{3,})/")


def miner_tag(coinbase_hex: str) -> str:
    """Best-effort pool name from a coinbase input's script, e.g. "Foundry USA"; "?" if none.

    Pools write a tag such as "/F2Pool/" or "Mined by AntPool" between binary fields, so known
    names are matched first, then a /slash-delimited/ tag, then the longest readable text.
    """
    try:
        raw = bytes.fromhex(coinbase_hex)
    except ValueError:
        return "?"
    runs = [run.decode("ascii").strip() for run in _PRINTABLE_RUN.findall(raw)]
    text = " ".join(runs)
    for needle, name in KNOWN_POOLS:
        if needle in text:
            return name
    slash = _SLASH_TAG.search(text)
    if slash:
        return slash.group(1).split("#")[0].strip()[:MAX_TAG_LENGTH]
    longest = max(runs, key=len, default="")
    return longest[:MAX_TAG_LENGTH] or "?"


class RecentBlocks:
    """The last `count` blocks, fetched when the tip changes and cached by hash"""

    STATS = ["blockhash", "height", "time", "txs", "total_size", "totalfee"]

    def __init__(self, rpc: BitcoinRPC, count: int = 5):
        self._rpc = rpc
        self.count = count
        self._cache: dict[str, RecentBlock] = {}
        self._tip: str | None = None
        self._blocks: list[RecentBlock] = []

    def update(self, tip_hash: str, height: int) -> list[RecentBlock]:
        if tip_hash == self._tip:
            return self._blocks
        blocks = []
        for h in range(height, max(-1, height - self.count), -1):
            block_hash = tip_hash if h == height else self._rpc.get_block_hash(h)
            if block_hash not in self._cache:
                self._cache[block_hash] = self._fetch(h)
            blocks.append(self._cache[block_hash])
        # Keep only what is shown; a reorged-out block is simply not looked up again
        self._cache = {block.hash: block for block in blocks}
        self._tip, self._blocks = tip_hash, blocks
        return blocks

    def _fetch(self, height: int) -> RecentBlock:
        stats = self._rpc.get_block_stats(height, self.STATS)
        block_hash = stats["blockhash"]
        coinbase_txid = self._rpc.get_block(block_hash)["tx"][0]
        coinbase = self._rpc.get_raw_transaction(coinbase_txid, True, block_hash)
        return RecentBlock(
            height=int(stats["height"]),
            hash=block_hash,
            time=int(stats["time"]),
            tx_count=int(stats["txs"]),
            size=int(stats["total_size"]),
            total_fee_btc=int(stats["totalfee"]) / 1e8,
            miner=miner_tag(coinbase["vin"][0].get("coinbase", "")),
        )
