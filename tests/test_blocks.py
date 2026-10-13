import unittest
from unittest.mock import Mock

from btcmonitor.blocks import RecentBlocks, miner_tag
from btcmonitor.rpc import BitcoinRPC

# Coinbase scripts of mainnet blocks 971267-971274
REAL_COINBASES = {
    "F2Pool": (
        "0305d20e2cfabe6d6d2343e7f86cd932cc70ff31c29327addb35bec10f9735cb65e24ee1743c66c45710000000f09f909f092f4632506f6f6c2f6500000000000000000000000000000000000000000000000000000000000000000000000500e3b403a8"
    ),
    "MARA Pool": (
        "0309d20e04e15ace6a7c204d415241204d61646520696e2055534120f09f87baf09f87b8207c763035148fdd6bf30000000000ffffffff"
    ),
    "AntPool": (
        "0304d20e194d696e656420627920416e74506f6f6c207800720113e0dca3fabe6d6dc17cfa5c58e843987bfe41039e782a063828ffdd4db4542d1931ecd4892d56f4100000000000000000011e40b5feba6ac29c787b"
    ),
    "BTC.com": (
        "0303d20e0e627463636f6d7d00420412b9edbffabe6d6d6b416a8ac23f34b673d918c97bee0e34bcb701a8519ec8d8449ada149356747510000000000000000000a2f1ab65000000000000"
    ),
    "Foundry USA": (
        "0307d20e049dc577592f466f756e6472792055534120506f6f6c202364726f70676f6c642f160a76560000177ad4040100"
    ),
}


def tag_hex(*parts: bytes) -> str:
    return b"".join(parts).hex()


class MinerTagTests(unittest.TestCase):
    def test_real_coinbases(self):
        for pool, coinbase in REAL_COINBASES.items():
            with self.subTest(pool=pool):
                self.assertEqual(miner_tag(coinbase), pool)

    def test_unknown_pool_slash_tag(self):
        self.assertEqual(miner_tag(tag_hex(b"\x03\x01\x02\x03", b"\x10/SomeNewPool #42/\x00")), "SomeNewPool")

    def test_unknown_pool_falls_back_to_longest_text(self):
        self.assertEqual(miner_tag(tag_hex(b"\x03abc\x00", b"hello miner\x00\xff")), "hello miner")

    def test_nothing_readable(self):
        self.assertEqual(miner_tag(tag_hex(b"\x03\x01\x02\x03\xff")), "?")
        self.assertEqual(miner_tag("not hex"), "?")


def fake_rpc(chain):
    """An RPC stand-in for a chain given as a list of block hashes by height"""
    rpc = Mock(spec=BitcoinRPC)
    rpc.get_block_hash.side_effect = lambda height: chain[height]
    rpc.get_block_stats.side_effect = lambda height, stats: {
        "blockhash": chain[height],
        "height": height,
        "time": 1700000000 + height * 600,
        "txs": 100 + height,
        "total_size": 1000 * height,
        "totalfee": 50_000 * height,
    }
    rpc.get_block.side_effect = lambda block_hash: {"tx": [f"coinbase-of-{block_hash}"]}
    rpc.get_raw_transaction.side_effect = lambda txid, verbose, block_hash: {
        "vin": [{"coinbase": tag_hex(b"\x03\x01\x02\x03/F2Pool/")}]
    }
    return rpc


class RecentBlocksTests(unittest.TestCase):
    def test_last_blocks_newest_first(self):
        chain = [f"h{i}" for i in range(10)]
        blocks = RecentBlocks(fake_rpc(chain), count=3).update("h9", 9)
        self.assertEqual([b.height for b in blocks], [9, 8, 7])
        self.assertEqual((blocks[0].tx_count, blocks[0].size, blocks[0].miner), (109, 9000, "F2Pool"))
        self.assertAlmostEqual(blocks[0].total_fee_btc, 0.0045)

    def test_new_block_fetches_only_the_new_one(self):
        chain = [f"h{i}" for i in range(10)]
        rpc = fake_rpc(chain)
        recent = RecentBlocks(rpc, count=3)
        recent.update("h8", 8)
        recent.update("h8", 8)  # unchanged tip: nothing fetched
        self.assertEqual(rpc.get_block_stats.call_count, 3)
        recent.update("h9", 9)
        self.assertEqual(rpc.get_block_stats.call_count, 4)

    def test_reorg_refetches_replaced_blocks(self):
        chain = [f"h{i}" for i in range(10)]
        rpc = fake_rpc(chain)
        recent = RecentBlocks(rpc, count=3)
        recent.update("h9", 9)
        chain[8], chain[9] = "x8", "x9"
        blocks = recent.update("x9", 9)
        self.assertEqual([b.hash for b in blocks], ["x9", "x8", "h7"])
        self.assertEqual(rpc.get_block_stats.call_count, 5)

    def test_short_chain(self):
        blocks = RecentBlocks(fake_rpc(["g", "h1"]), count=5).update("h1", 1)
        self.assertEqual([b.height for b in blocks], [1, 0])


if __name__ == "__main__":
    unittest.main()
