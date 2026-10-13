"""Details of one mempool transaction for the detail view"""

from __future__ import annotations

from .models import TransactionDetail, TxInput, TxOutput
from .rpc import BitcoinRPC, RPCError

# Each input needs its own lookup, so very large transactions are only partly resolved
MAX_INPUT_LOOKUPS = 50


def _spent_coin(rpc: BitcoinRPC, txid: str, vout: int) -> tuple[str | None, float | None]:
    """(address, amount) of the coin an input spends.

    For a mempool transaction Bitcoin Core does not report what its inputs spend, so look the
    coin up: a confirmed coin through gettxout (excluding the mempool, where it already counts
    as spent), an unconfirmed parent through getrawtransaction, which finds mempool
    transactions without -txindex.
    """
    try:
        coin = rpc.get_tx_out(txid, vout, False)
        if coin:
            return coin.get("scriptPubKey", {}).get("address"), float(coin["value"])
        output = rpc.get_raw_transaction(txid, True)["vout"][vout]
        return output.get("scriptPubKey", {}).get("address"), float(output["value"])
    except (RPCError, LookupError, TypeError, ValueError):
        return None, None


def fetch_transaction_detail(rpc: BitcoinRPC, txid: str) -> TransactionDetail:
    """Raises RPCError if the transaction is no longer in the mempool"""
    entry = rpc.get_mempool_entry(txid)
    tx = rpc.get_raw_transaction(txid, True)

    inputs = []
    vin = tx.get("vin", [])
    for spent in vin[:MAX_INPUT_LOOKUPS]:
        address, amount = _spent_coin(rpc, spent["txid"], spent["vout"])
        inputs.append(TxInput(prev=f"{spent['txid']}:{spent['vout']}", address=address, amount_btc=amount))

    outputs = [
        TxOutput(
            address=out.get("scriptPubKey", {}).get("address"),
            script_type=out.get("scriptPubKey", {}).get("type", "?"),
            amount_btc=float(out.get("value", 0)),
        )
        for out in tx.get("vout", [])
    ]

    fees = entry.get("fees", {})
    vsize = int(entry.get("vsize", tx.get("vsize", 0)))
    return TransactionDetail(
        txid=txid,
        vsize=vsize,
        weight=int(entry.get("weight", tx.get("weight", 0))),
        fee_btc=float(fees.get("base", 0.0)),
        entry_time=int(entry.get("time", 0)),
        replaceable=entry.get("bip125-replaceable"),
        # Bitcoin Core counts the transaction itself among its ancestors and descendants
        ancestor_count=max(0, int(entry.get("ancestorcount", 1)) - 1),
        ancestor_fee_rate=float(fees.get("ancestor", 0.0)) * 1e8 / max(1, int(entry.get("ancestorsize", vsize))),
        descendant_count=max(0, int(entry.get("descendantcount", 1)) - 1),
        descendant_fee_rate=float(fees.get("descendant", 0.0)) * 1e8 / max(1, int(entry.get("descendantsize", vsize))),
        parents=list(entry.get("depends", [])),
        children=list(entry.get("spentby", [])),
        inputs=inputs,
        outputs=outputs,
        inputs_not_looked_up=max(0, len(vin) - MAX_INPUT_LOOKUPS),
    )
