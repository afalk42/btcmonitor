import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from btcmonitor.__main__ import build_config, parse_args
from btcmonitor.paths import discover_cookie_path, discover_default_datadir
from btcmonitor.rpc import BitcoinRPC


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



class DatadirTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.datadir = Path(tmp.name)

    def write_cookie(self, network_subdir, content="__cookie__:secret"):
        directory = self.datadir / network_subdir
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".cookie").write_text(content)

    def test_cookie_found_under_custom_datadir(self):
        self.write_cookie("")
        self.write_cookie("signet")
        self.assertEqual(discover_cookie_path("mainnet", self.datadir), self.datadir / ".cookie")
        self.assertEqual(discover_cookie_path("signet", self.datadir), self.datadir / "signet" / ".cookie")
        self.assertIsNone(discover_cookie_path("regtest", self.datadir))

    def test_datadir_option_reaches_rpc_auth(self):
        self.write_cookie("regtest")
        config = config_for("--network", "regtest", "--datadir", str(self.datadir))
        self.assertEqual(config.datadir, self.datadir)
        rpc = BitcoinRPC(config)
        expected = base64.b64encode(b"__cookie__:secret").decode()
        self.assertEqual(rpc._auth_header, {"Authorization": f"Basic {expected}"})

    def test_datadir_from_environment(self):
        config = config_for(env={"BITCOIN_DATADIR": str(self.datadir)})
        self.assertEqual(config.datadir, self.datadir)


if __name__ == "__main__":
    unittest.main()
