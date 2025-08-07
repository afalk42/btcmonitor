from __future__ import annotations
import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .paths import discover_cookie_path


class RPCError(Exception):
    pass


@dataclass
class RPCConfig:
    host: str = "127.0.0.1"
    port: int = 8332
    user: Optional[str] = None
    password: Optional[str] = None
    network: str = "mainnet"
    timeout: float = 5.0


class BitcoinRPC:
    def __init__(self, config: RPCConfig):
        self.config = config
        self._url = f"http://{config.host}:{config.port}"
        self._auth_header = self._build_auth_header()

    def _build_auth_header(self) -> Dict[str, str]:
        if self.config.user and self.config.password:
            token = base64.b64encode(f"{self.config.user}:{self.config.password}".encode()).decode()
            return {"Authorization": f"Basic {token}"}
        # cookie auth
        cookie_path = discover_cookie_path(self.config.network)
        if cookie_path and cookie_path.exists():
            # Format is: user:token in one line
            content = Path(cookie_path).read_text().strip()
            token = base64.b64encode(content.encode()).decode()
            return {"Authorization": f"Basic {token}"}
        return {}

    def call(self, method: str, *params: Any) -> Any:
        payload = {"jsonrpc": "2.0", "id": "btcmonitor", "method": method, "params": list(params)}
        try:
            resp = requests.post(self._url, headers={"Content-Type": "application/json", **self._auth_header}, data=json.dumps(payload), timeout=self.config.timeout)
        except requests.RequestException as e:
            raise RPCError(str(e))
        if resp.status_code == 401:
            raise RPCError("Unauthorized: check RPC credentials or cookie")
        if resp.status_code >= 400:
            raise RPCError(f"HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        if data.get("error"):
            raise RPCError(str(data["error"]))
        return data.get("result")

    # Convenience wrappers
    def get_blockchain_info(self) -> Dict[str, Any]:
        return self.call("getblockchaininfo")

    def get_mempool_info(self) -> Dict[str, Any]:
        return self.call("getmempoolinfo")

    def get_mempool_ancestors(self, txid: str, verbose: bool = False) -> Any:
        return self.call("getmempoolancestors", txid, verbose)

    def get_raw_mempool(self, verbose: bool = True) -> Any:
        return self.call("getrawmempool", verbose)

    def get_network_info(self) -> Dict[str, Any]:
        return self.call("getnetworkinfo")

    def get_connection_count(self) -> int:
        return self.call("getconnectioncount")

    def get_block_template(self) -> Dict[str, Any]:
        return self.call("getblocktemplate", {"rules": ["segwit"]})
