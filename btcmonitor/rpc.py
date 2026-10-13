from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .paths import discover_cookie_path


class RPCError(Exception):
    pass


@dataclass
class RPCConfig:
    host: str = "127.0.0.1"
    port: int = 8332
    user: str | None = None
    password: str | None = None
    network: str = "mainnet"
    timeout: float = 5.0
    datadir: Path | None = None
    cookie_file: Path | None = None  # rpccookiefile from bitcoin.conf; overrides the datadir's .cookie


class BitcoinRPC:
    def __init__(self, config: RPCConfig):
        self.config = config
        self._url = f"http://{config.host}:{config.port}"
        self._cookie_path: Path | None = None
        self._auth_header = self._build_auth_header()

    def _find_cookie(self) -> Path | None:
        if self.config.cookie_file is not None:
            return self.config.cookie_file if self.config.cookie_file.exists() else None
        return discover_cookie_path(self.config.network, self.config.datadir)

    def _read_cookie_header(self) -> dict[str, str]:
        """Auth header from the current cookie file, or {} if there is none"""
        self._cookie_path = self._find_cookie()
        if not self._cookie_path:
            return {}
        try:
            # Format is: user:token in one line
            content = self._cookie_path.read_text().strip()
        except OSError:
            return {}
        token = base64.b64encode(content.encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def _build_auth_header(self) -> dict[str, str]:
        if self.config.user and self.config.password:
            token = base64.b64encode(f"{self.config.user}:{self.config.password}".encode()).decode()
            return {"Authorization": f"Basic {token}"}
        return self._read_cookie_header()

    def _post(self, payload: dict[str, Any], auth_header: dict[str, str]) -> requests.Response:
        try:
            return requests.post(
                self._url,
                headers={"Content-Type": "application/json", **auth_header},
                data=json.dumps(payload),
                timeout=self.config.timeout,
            )
        except requests.RequestException as e:
            raise RPCError(str(e)) from e

    def call(self, method: str, *params: Any) -> Any:
        payload = {"jsonrpc": "2.0", "id": "btcmonitor", "method": method, "params": list(params)}
        resp = self._post(payload, self._auth_header)
        if resp.status_code == 401:
            # bitcoind writes a new cookie each time it starts, and it may not have existed when we
            # started, so re-read it and retry once (also the fallback when user/password are rejected)
            cookie_header = self._read_cookie_header()
            if cookie_header and cookie_header != self._auth_header:
                resp = self._post(payload, cookie_header)
                if resp.status_code != 401:
                    self._auth_header = cookie_header
        if resp.status_code == 401:
            target = f"http://{self.config.host}:{self.config.port}"
            cookie_note = (
                f" cookie at {self._cookie_path}"
                if (self._cookie_path and self._cookie_path.exists())
                else " cookie (not found)"
            )
            raise RPCError(
                f"Unauthorized to {target}: check rpcuser/rpcpassword or rpcauth, or{cookie_note} for this network ({self.config.network})."
            )
        if resp.status_code >= 400:
            raise RPCError(f"HTTP {resp.status_code}: {resp.text}")
        try:
            data = resp.json()
        except ValueError as e:
            raise RPCError(f"Invalid JSON from {self._url}: {resp.text[:200]!r}") from e
        if not isinstance(data, dict):
            raise RPCError(f"Unexpected JSON-RPC response from {self._url}: {str(data)[:200]}")
        if data.get("error"):
            raise RPCError(str(data["error"]))
        return data.get("result")

    # Convenience wrappers
    def get_blockchain_info(self) -> dict[str, Any]:
        return self.call("getblockchaininfo")

    def get_mempool_info(self) -> dict[str, Any]:
        return self.call("getmempoolinfo")

    def get_mempool_ancestors(self, txid: str, verbose: bool = False) -> Any:
        return self.call("getmempoolancestors", txid, verbose)

    def get_raw_mempool(self, verbose: bool = True) -> Any:
        return self.call("getrawmempool", verbose)

    def get_network_info(self) -> dict[str, Any]:
        return self.call("getnetworkinfo")

    def get_connection_count(self) -> int:
        return self.call("getconnectioncount")

    def get_block_template(self) -> dict[str, Any]:
        return self.call("getblocktemplate", {"rules": ["segwit"]})

    def get_best_block_hash(self) -> str:
        return self.call("getbestblockhash")

    def get_block(self, block_hash: str, verbosity: int = 1) -> dict[str, Any]:
        return self.call("getblock", block_hash, verbosity)

    def get_raw_transaction(self, txid: str, verbose: bool = False) -> Any:
        return self.call("getrawtransaction", txid, verbose)

    def get_peer_info(self) -> Any:
        return self.call("getpeerinfo")
