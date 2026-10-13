import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from btcmonitor.__main__ import build_config, parse_args
from btcmonitor.conf import read_bitcoin_conf
from btcmonitor.paths import discover_cookie_path, discover_default_datadir
from btcmonitor.rpc import BitcoinRPC


def config_for(*argv, env=None, base_datadir=Path("/nonexistent/btcmonitor-test")):
    # Point the default data directory away from any real ~/.bitcoin so tests are hermetic
    with (
        patch.dict(os.environ, env or {}, clear=True),
        patch("btcmonitor.__main__.default_base_datadir", return_value=base_datadir),
    ):
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
        with (
            patch("btcmonitor.paths.Path.home", return_value=Path("/home/u")),
            patch("btcmonitor.paths.sys.platform", "linux"),
        ):
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


class BitcoinConfTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def write_conf(self, text, name="bitcoin.conf"):
        path = self.base / name
        path.write_text(text)
        return path

    def test_reads_sections_prefixes_and_comments(self):
        path = self.write_conf(
            "# comment\n"
            "rpcuser=alice   # trailing comment\n"
            "rpcpassword=pw1\n"
            "rpcport=1111\n"
            "rpcpassword=ignored-second-value\n"
            "signet.rpcport=3333\n"
            "[regtest]\n"
            "rpcport=2222\n"
            "rpcuser=bob\n"
        )
        self.assertEqual(
            read_bitcoin_conf(path, "mainnet"), {"rpcuser": "alice", "rpcpassword": "pw1", "rpcport": "1111"}
        )
        # Top-level rpcport is mainnet-only; section values win over top-level ones
        self.assertEqual(
            read_bitcoin_conf(path, "regtest"), {"rpcuser": "bob", "rpcpassword": "pw1", "rpcport": "2222"}
        )
        self.assertEqual(read_bitcoin_conf(path, "signet")["rpcport"], "3333")
        self.assertNotIn("rpcport", read_bitcoin_conf(path, "testnet4"))

    def test_missing_file_has_no_settings(self):
        self.assertEqual(read_bitcoin_conf(self.base / "absent.conf", "mainnet"), {})

    def test_credentials_and_port_come_from_default_conf(self):
        self.write_conf("rpcuser=alice\nrpcpassword=secret\nrpcport=8999\n")
        config = config_for(base_datadir=self.base)
        self.assertEqual((config.user, config.password, config.port), ("alice", "secret", 8999))

    def test_command_line_wins_over_conf(self):
        self.write_conf("rpcuser=alice\nrpcpassword=secret\nrpcport=8999\n")
        config = config_for("--rpc-user", "carol", "--rpc-password", "pw", "--rpc-port", "7000", base_datadir=self.base)
        self.assertEqual((config.user, config.password, config.port), ("carol", "pw", 7000))

    def test_explicit_conf_path(self):
        path = self.write_conf("[signet]\nrpcport=39999\n", name="other.conf")
        self.assertEqual(config_for("--network", "signet", "--conf", str(path)).port, 39999)

    def test_datadir_and_cookie_file_from_conf(self):
        node_dir = self.base / "node"
        (node_dir / "regtest").mkdir(parents=True)
        (node_dir / "regtest" / "my.cookie").write_text("__cookie__:abc")
        self.write_conf(f"datadir={node_dir}\nrpccookiefile=my.cookie\n")
        config = config_for("--network", "regtest", base_datadir=self.base)
        self.assertEqual(config.datadir, node_dir)
        self.assertEqual(config.cookie_file, node_dir / "regtest" / "my.cookie")
        expected = base64.b64encode(b"__cookie__:abc").decode()
        self.assertEqual(BitcoinRPC(config)._auth_header, {"Authorization": f"Basic {expected}"})


if __name__ == "__main__":
    unittest.main()
