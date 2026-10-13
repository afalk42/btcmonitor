import unittest
from unittest.mock import Mock, patch

from btcmonitor.rpc import BitcoinRPC, RPCError
from btcmonitor.txdetail import fetch_transaction_detail

ENTRY = {
    "vsize": 189,
    "weight": 753,
    "time": 1791910491,
    "ancestorcount": 2,
    "ancestorsize": 300,
    "descendantcount": 1,
    "descendantsize": 189,
    "fees": {"base": 0.0000338, "ancestor": 0.0000450, "descendant": 0.0000338},
    "depends": ["parent"],
    "spentby": [],
    "bip125-replaceable": True,
}
TX = {
    "vin": [{"txid": "confirmed", "vout": 1}, {"txid": "parent", "vout": 0}],
    "vout": [
        {"value": 0.0050438, "scriptPubKey": {"address": "bc1qdest", "type": "witness_v0_scripthash"}},
        {"value": 0.0, "scriptPubKey": {"type": "nulldata"}},
    ],
}


def fake_rpc(mempool_parents=True):
    rpc = Mock(spec=BitcoinRPC)
    rpc.get_mempool_entry.return_value = ENTRY
    coins = {("confirmed", 1): {"value": 0.0040726, "scriptPubKey": {"address": "bc1qconfirmed"}}}
    rpc.get_tx_out.side_effect = lambda txid, n, include_mempool: coins.get((txid, n))
    mempool = {"parent": {"vout": [{"value": 0.001005, "scriptPubKey": {"address": "bc1qparent"}}]}}

    def raw_transaction(txid, verbose):
        if txid == "tx":
            return TX
        if mempool_parents and txid in mempool:
            return mempool[txid]
        raise RPCError("No such mempool or blockchain transaction")

    rpc.get_raw_transaction.side_effect = raw_transaction
    return rpc


class FetchTransactionDetailTests(unittest.TestCase):
    def test_details_and_spent_coins(self):
        detail = fetch_transaction_detail(fake_rpc(), "tx")
        self.assertEqual((detail.vsize, detail.weight, detail.replaceable), (189, 753, True))
        self.assertAlmostEqual(detail.fee_rate, 17.88, places=2)
        self.assertEqual((detail.ancestor_count, detail.descendant_count), (1, 0))  # not counting itself
        self.assertAlmostEqual(detail.ancestor_fee_rate, 15.0)
        self.assertEqual(detail.parents, ["parent"])
        # A confirmed coin comes from gettxout, an unconfirmed parent's from the mempool
        self.assertEqual(
            [(i.prev, i.address, i.amount_btc) for i in detail.inputs],
            [("confirmed:1", "bc1qconfirmed", 0.0040726), ("parent:0", "bc1qparent", 0.001005)],
        )
        self.assertEqual(
            [(o.address, o.script_type) for o in detail.outputs],
            [("bc1qdest", "witness_v0_scripthash"), (None, "nulldata")],
        )
        spent = sum(i.amount_btc for i in detail.inputs)
        self.assertAlmostEqual(spent - sum(o.amount_btc for o in detail.outputs), detail.fee_btc)

    def test_coin_that_cannot_be_found_is_unknown(self):
        detail = fetch_transaction_detail(fake_rpc(mempool_parents=False), "tx")
        self.assertEqual((detail.inputs[1].address, detail.inputs[1].amount_btc), (None, None))

    def test_input_lookups_are_capped(self):
        rpc = fake_rpc()
        many = dict(TX, vin=[{"txid": "confirmed", "vout": 1}] * 5)
        rpc.get_raw_transaction.side_effect = lambda txid, verbose: many
        with patch("btcmonitor.txdetail.MAX_INPUT_LOOKUPS", 3):
            detail = fetch_transaction_detail(rpc, "tx")
        self.assertEqual((len(detail.inputs), detail.inputs_not_looked_up), (3, 2))
        self.assertEqual(rpc.get_tx_out.call_count, 3)

    def test_not_in_mempool_raises(self):
        rpc = fake_rpc()
        rpc.get_mempool_entry.side_effect = RPCError("{'code': -5, 'message': 'Transaction not in mempool'}")
        with self.assertRaises(RPCError):
            fetch_transaction_detail(rpc, "tx")


if __name__ == "__main__":
    unittest.main()
