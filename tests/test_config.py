import os
import unittest
from pathlib import Path
from unittest.mock import patch

from btcmonitor.__main__ import build_config, parse_args
from btcmonitor.paths import discover_default_datadir


def config_for(*argv, env=None):
    with patch.dict(os.environ, env or {}, clear=True):
        return build_config(parse_args(list(argv)))


class NetworkDefaultsTests(unittest.TestCase):
    def test_rpc_port_follows_network(self):
        for network, port in (
            ("mainnet", 8332),
            ("testnet", 18332),
            ("testnet3", 18332),
            ("testnet4", 48332),
            ("signet", 38332),
            ("regtest", 18443),
        ):
            with self.subTest(network=network):
                self.assertEqual(config_for("--network", network).port, port)

    def test_network_from_environment_sets_port(self):
        self.assertEqual(config_for(env={"BITCOIN_NETWORK": "signet"}).port, 38332)

    def test_explicit_port_wins(self):
        self.assertEqual(config_for("--network", "regtest", "--rpc-port", "9999").port, 9999)
        self.assertEqual(config_for("--network", "regtest", env={"BITCOIN_RPC_PORT": "9998"}).port, 9998)

    def test_testnet4_uses_its_own_datadir(self):
        with patch("btcmonitor.paths.Path.home", return_value=Path("/home/u")), \
                patch("btcmonitor.paths.sys.platform", "linux"):
            self.assertEqual(discover_default_datadir("testnet4"), Path("/home/u/.bitcoin/testnet4"))
            self.assertEqual(discover_default_datadir("testnet3"), Path("/home/u/.bitcoin/testnet3"))
            self.assertEqual(discover_default_datadir("mainnet"), Path("/home/u/.bitcoin"))


if __name__ == "__main__":
    unittest.main()
