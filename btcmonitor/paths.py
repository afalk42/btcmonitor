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


def discover_default_datadir(network: str = "mainnet") -> Path:
    home = Path.home()
    if sys.platform.startswith("darwin"):
        base = home / "Library" / "Application Support" / "Bitcoin"
    elif sys.platform.startswith("win"):
        base = Path(os.getenv("APPDATA", home / "AppData" / "Roaming")) / "Bitcoin"
    else:
        base = home / ".bitcoin"
    subdir = NETWORK_SUBDIRS.get(network, "")
    return base / subdir if subdir else base


def discover_cookie_path(network: str = "mainnet") -> Optional[Path]:
    datadir = discover_default_datadir(network)
    cookie = datadir / ".cookie"
    return cookie if cookie.exists() else None
