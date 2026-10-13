"""Fee-rate bucketing and next-block projection"""

from __future__ import annotations

from .models import BlockProjection, FeeBuckets, Transaction

# Lower bounds of the fee-rate bands, in sat/vB
FEE_BANDS = [1, 2, 3, 5, 10, 20, 50, 100, 500, 1000]

BLOCK_CAPACITY_VBYTES = 1_000_000
SYNTHETIC_TX_VBYTES = 250  # size of the stand-in transactions the mempool fallback draws


def build_fee_buckets(mempool: dict[str, dict]) -> FeeBuckets:
    """Total vbytes per fee band for getrawmempool-verbose-shaped entries"""
    vbytes_per_band = [0 for _ in FEE_BANDS]
    for tx in mempool.values():
        # round() rather than int(): BTC floats like 0.00000059 * 1e8 come out just below the whole sat
        fee_sat = round(tx.get("fees", {}).get("base", 0) * 1e8)
        vsize = tx.get("vsize") or tx.get("weight", 0) // 4
        fr = fee_sat / max(1, vsize)
        # find band index; a rate equal to a band's lower bound belongs to that band ("2+" includes 2)
        idx = 0
        while idx < len(FEE_BANDS) - 1 and fr >= FEE_BANDS[idx + 1]:
            idx += 1
        vbytes_per_band[idx] += int(vsize)

    # First band reads "< 2  sat/vB", the others "2+ sat/vB", "3+ sat/vB", ..., "1000+ sat/vB"
    labels = [f"< {FEE_BANDS[1]}  sat/vB"] + [f"{lo}+ sat/vB" for lo in FEE_BANDS[1:]]
    return list(zip(labels, vbytes_per_band, strict=True))


def bucket_fee_rate(label: str) -> float:
    """Return a representative sat/vB rate for a build_fee_buckets label."""
    if label.lstrip().startswith("<"):
        # The lowest band (< 2 sat/vB) uses 1 sat/vB for estimation/coloring.
        return 1.0
    return float(label.split()[0].rstrip("+"))


def project_block_from_template(template: dict) -> BlockProjection:
    """Next block as proposed by getblocktemplate"""
    transactions = []
    # Same shape as getrawmempool verbose entries, so build_fee_buckets can bucket the template
    template_entries: dict[str, dict] = {}
    for i, tx in enumerate(template.get("transactions", [])):
        vbytes = tx.get("weight", 0) // 4
        fee_btc = tx.get("fee", 0) / 1e8
        fee_rate = (fee_btc * 1e8) / max(1, vbytes)  # sat/vB
        txid = tx.get("txid", f"tx_{i}")

        transactions.append(Transaction(fee_rate=fee_rate, vbytes=vbytes, txid=txid))
        template_entries[txid] = {"vsize": vbytes, "fees": {"base": fee_btc}}

    return BlockProjection(
        est_tx=len(transactions),
        est_weight_vbytes=sum(tx.vbytes for tx in transactions),
        transactions=transactions,
        fee_buckets=build_fee_buckets(template_entries),
    )


def project_block_from_buckets(fee_buckets: FeeBuckets, capacity: int = BLOCK_CAPACITY_VBYTES) -> BlockProjection:
    """Estimate the next block by filling it greedily from the highest fee band down.

    Used when getblocktemplate is unavailable (initial block download, no peers). The block is
    drawn with synthetic transactions of SYNTHETIC_TX_VBYTES each.
    """
    sorted_buckets = sorted(fee_buckets, key=lambda bucket: bucket_fee_rate(bucket[0]), reverse=True)
    acc_vb = 0
    proj_buckets: FeeBuckets = []
    transactions: list[Transaction] = []

    for label, vb in sorted_buckets:
        if acc_vb >= capacity:
            break
        take = min(vb, capacity - acc_vb)
        if take <= 0:
            continue
        proj_buckets.append((label, take))
        fee_rate = bucket_fee_rate(label)
        remaining = take
        for _ in range(max(1, take // SYNTHETIC_TX_VBYTES)):
            transactions.append(
                Transaction(
                    fee_rate=fee_rate,
                    vbytes=min(SYNTHETIC_TX_VBYTES, remaining),
                    txid=f"synthetic_{len(transactions)}",
                )
            )
            remaining -= SYNTHETIC_TX_VBYTES
            if remaining <= 0:
                break
        acc_vb += take

    return BlockProjection(
        est_tx=len(transactions), est_weight_vbytes=acc_vb, transactions=transactions, fee_buckets=proj_buckets
    )
