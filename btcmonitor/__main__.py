from __future__ import annotations
import argparse
import os
import sys

from .rpc import BitcoinRPC, RPCConfig
from .ui import render_dashboard


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="btcmonitor", 
        description="Terminal Bitcoin Core monitor. Use arrow keys to scroll transactions. Press 'q' to quit or use Ctrl-C."
    )
    p.add_argument("--rpc-host", default=os.getenv("BITCOIN_RPC_HOST", "127.0.0.1"))
    p.add_argument("--rpc-port", type=int, default=int(os.getenv("BITCOIN_RPC_PORT", 8332)))
    p.add_argument("--rpc-user", default=os.getenv("BITCOIN_RPC_USER"))
    p.add_argument("--rpc-password", default=os.getenv("BITCOIN_RPC_PASSWORD"))
    p.add_argument("--network", default=os.getenv("BITCOIN_NETWORK", "mainnet"), choices=["mainnet", "testnet", "testnet3", "signet", "regtest"]) 
    p.add_argument("--refresh", type=float, default=2.0, help="Refresh rate in Hz (default 2)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    rpc = BitcoinRPC(RPCConfig(
        host=args.rpc_host,
        port=args.rpc_port,
        user=args.rpc_user,
        password=args.rpc_password,
        network=args.network,
    ))
    try:
        render_dashboard(rpc, refresh_hz=args.refresh)
    except KeyboardInterrupt:
        pass
    print("Exiting…")


if __name__ == "__main__":
    main()
