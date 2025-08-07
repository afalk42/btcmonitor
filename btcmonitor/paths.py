import os
import sys
from pathlib import Path
from typing import Optional


def discover_default_datadir(network: str = "mainnet") -> Path:
    home = Path.home()
    if sys.platform.startswith("darwin"):
        base = home / "Library" / "Application Support" / "Bitcoin"
    elif sys.platform.startswith("win"):
        base = Path(os.getenv("APPDATA", home / "AppData" / "Roaming")) / "Bitcoin"
    else:
        base = home / ".bitcoin"
    if network == "testnet" or network == "testnet3":
        return base / "testnet3"
    if network == "signet":
        return base / "signet"
    if network == "regtest":
        return base / "regtest"
    return base


def discover_cookie_path(network: str = "mainnet") -> Optional[Path]:
    datadir = discover_default_datadir(network)
    cookie = datadir / ".cookie"
    return cookie if cookie.exists() else None
