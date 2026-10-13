import os
import sys
from pathlib import Path
from typing import Optional

# Subdirectory of the data directory that Bitcoin Core uses for each network
NETWORK_SUBDIRS = {
    "mainnet": "",
    "testnet": "testnet3",
    "testnet3": "testnet3",
    "testnet4": "testnet4",
    "signet": "signet",
    "regtest": "regtest",
}

# Bitcoin Core's default RPC port for each network
DEFAULT_RPC_PORTS = {
    "mainnet": 8332,
    "testnet": 18332,
    "testnet3": 18332,
    "testnet4": 48332,
    "signet": 38332,
    "regtest": 18443,
}


def default_base_datadir() -> Path:
    """Bitcoin Core's default data directory for this platform (without the network subdirectory)"""
    home = Path.home()
    if sys.platform.startswith("darwin"):
        return home / "Library" / "Application Support" / "Bitcoin"
    if sys.platform.startswith("win"):
        return Path(os.getenv("APPDATA", home / "AppData" / "Roaming")) / "Bitcoin"
    return home / ".bitcoin"


def discover_default_datadir(network: str = "mainnet", datadir: Optional[Path] = None) -> Path:
    """Network-specific data directory, under `datadir` if given, else under the platform default"""
    base = Path(datadir).expanduser() if datadir else default_base_datadir()
    subdir = NETWORK_SUBDIRS.get(network, "")
    return base / subdir if subdir else base


def discover_cookie_path(network: str = "mainnet", datadir: Optional[Path] = None) -> Optional[Path]:
    cookie = discover_default_datadir(network, datadir) / ".cookie"
    return cookie if cookie.exists() else None
