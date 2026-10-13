from __future__ import annotations

import argparse
import os

from .paths import DEFAULT_RPC_PORTS
from .rpc import BitcoinRPC, RPCConfig
from .ui import render_dashboard


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="btcmonitor", 
        description="Terminal Bitcoin Core monitor. Use arrow keys to scroll transactions. Press 'q' to quit or use Ctrl-C."
    )
    p.add_argument("--rpc-host", default=os.getenv("BITCOIN_RPC_HOST", "127.0.0.1"))
    env_port = os.getenv("BITCOIN_RPC_PORT")
    p.add_argument("--rpc-port", type=int, default=int(env_port) if env_port else None,
                   help="RPC port (default: the network's standard port, e.g. 8332 for mainnet)")
    p.add_argument("--rpc-user", default=os.getenv("BITCOIN_RPC_USER"))
    p.add_argument("--rpc-password", default=os.getenv("BITCOIN_RPC_PASSWORD"))
    p.add_argument("--network", default=os.getenv("BITCOIN_NETWORK", "mainnet"), choices=list(DEFAULT_RPC_PORTS))
    p.add_argument("--refresh", type=float, default=2.0, help="Refresh rate in Hz (default 2)")
    return p.parse_args(argv)


def build_config(args) -> RPCConfig:
    return RPCConfig(
        host=args.rpc_host,
        port=args.rpc_port if args.rpc_port is not None else DEFAULT_RPC_PORTS[args.network],
        user=args.rpc_user,
        password=args.rpc_password,
        network=args.network,
    )


def main(argv=None):
    args = parse_args(argv)
    rpc = BitcoinRPC(build_config(args))
    try:
        render_dashboard(rpc, refresh_hz=args.refresh)
    except KeyboardInterrupt:
        pass
    print("Exiting…")


if __name__ == "__main__":
    main()
