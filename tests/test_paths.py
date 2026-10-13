import os
import unittest
from pathlib import Path
from unittest.mock import patch

from btcmonitor.paths import DEFAULT_RPC_PORTS, NETWORK_SUBDIRS, default_base_datadir, discover_default_datadir

HOME = Path("/home/u")


def base_datadir_on(platform, env=None):
    with (
        patch("btcmonitor.paths.sys.platform", platform),
        patch("btcmonitor.paths.Path.home", return_value=HOME),
        patch.dict(os.environ, env or {}, clear=True),
    ):
        return default_base_datadir()


class DatadirTests(unittest.TestCase):
    def test_platform_default_datadirs(self):
        self.assertEqual(base_datadir_on("linux"), HOME / ".bitcoin")
        self.assertEqual(base_datadir_on("darwin"), HOME / "Library" / "Application Support" / "Bitcoin")
        self.assertEqual(
            base_datadir_on("win32", {"APPDATA": "C:/Users/u/AppData/Roaming"}),
            Path("C:/Users/u/AppData/Roaming") / "Bitcoin",
        )
        self.assertEqual(base_datadir_on("win32"), HOME / "AppData" / "Roaming" / "Bitcoin")

    def test_network_subdirectories(self):
        for network, subdir in (
            ("mainnet", ""),
            ("testnet", "testnet3"),
            ("testnet4", "testnet4"),
            ("signet", "signet"),
            ("regtest", "regtest"),
        ):
            with self.subTest(network=network):
                expected = Path("/data") / subdir if subdir else Path("/data")
                self.assertEqual(discover_default_datadir(network, Path("/data")), expected)

    def test_every_network_has_a_port_and_subdir(self):
        self.assertEqual(set(DEFAULT_RPC_PORTS), set(NETWORK_SUBDIRS))


if __name__ == "__main__":
    unittest.main()
