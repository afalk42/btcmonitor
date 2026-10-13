"""Tracking of the largest mempool transactions by total output value"""

from __future__ import annotations

import threading
import time

from .models import MempoolTransaction
from .rpc import BitcoinRPC


class TransactionTracker:
    """Keeps the largest mempool transactions by total output value.

    A transaction's outputs need one getrawtransaction call (a millisecond or two each), so every
    transaction is looked up once, on a background thread, and kept while it stays in the mempool.
    New transactions are picked up every `refresh_seconds`, or right away after a new block.
    """

    def __init__(self, rpc: BitcoinRPC, refresh_seconds: float = 60.0, top_n: int = 100):
        self._rpc = rpc
        self.refresh_seconds = refresh_seconds
        self.top_n = top_n
        self._cache: dict[str, MempoolTransaction] = {}  # txid -> looked-up transaction
        self._lock = threading.Lock()  # guards _cache, which the loader writes while update() reads it
        # Transactions handed to the loader; only these count as seen, so none are skipped
        self._known: set[str] = set()
        self._loader: threading.Thread | None = None
        self._last_refresh: float | None = None
        self._last_height = 0

    @property
    def loading(self) -> bool:
        return self._loader is not None and self._loader.is_alive()

    def wait(self, timeout: float | None = None) -> None:
        """Block until the current background lookups finish"""
        if self._loader is not None:
            self._loader.join(timeout)

    def update(self, mempool: dict[str, dict], block_height: int) -> list[MempoolTransaction]:
        """Start lookups for unseen transactions if due, and return the current top list"""
        current = set(mempool)
        now = time.monotonic()
        if block_height > self._last_height:
            # A new block confirmed transactions and changed the mempool; refresh now
            self._last_height = block_height
            self._last_refresh = None

        due = self._last_refresh is None or now - self._last_refresh >= self.refresh_seconds
        if due and not self.loading:
            self._known &= current
            with self._lock:
                for txid in set(self._cache) - current:
                    del self._cache[txid]
            new_txids = list(current - self._known)
            if new_txids:
                self._known.update(new_txids)
                self._loader = threading.Thread(target=self._load, args=(new_txids, mempool), daemon=True)
                self._loader.start()
            self._last_refresh = now

        with self._lock:
            valid = [tx for txid, tx in self._cache.items() if txid in current]
        valid.sort(key=lambda tx: tx.amount_btc, reverse=True)
        return valid[: self.top_n]

    def _load(self, txids: list[str], mempool: dict[str, dict]) -> None:
        for txid in txids:
            entry = mempool[txid]
            fee_btc = entry.get("fees", {}).get("base", 0.0)
            vbytes = entry.get("vsize", entry.get("weight", 0) // 4)
            fee_rate = (fee_btc * 1e8) / vbytes if vbytes > 0 else 0
            try:
                tx_detail = self._rpc.get_raw_transaction(txid, True)
                # Sum all output values to get total BTC amount
                amount_btc = sum(float(vout.get("value", 0)) for vout in tx_detail.get("vout", []))
            except Exception:
                # The transaction may have left the mempool since; skip it
                continue
            if amount_btc > 0:
                with self._lock:
                    self._cache[txid] = MempoolTransaction(
                        txid=txid, amount_btc=amount_btc, fee_btc=fee_btc, fee_rate=fee_rate
                    )
