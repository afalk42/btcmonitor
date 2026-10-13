from __future__ import annotations

import argparse
import os
from pathlib import Path

from .conf import read_bitcoin_conf
from .paths import DEFAULT_RPC_PORTS, default_base_datadir, discover_default_datadir
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
    p.add_argument("--datadir", type=Path, default=os.getenv("BITCOIN_DATADIR"),
                   help="Bitcoin Core data directory, used to find the auth cookie (default: platform default)")
    p.add_argument("--conf", type=Path, default=os.getenv("BITCOIN_CONF"),
                   help="bitcoin.conf to read rpcuser, rpcpassword, rpcport, rpccookiefile and datadir from "
                        "(default: bitcoin.conf in the data directory)")
    p.add_argument("--refresh", type=float, default=2.0, help="Refresh rate in Hz (default 2)")
    return p.parse_args(argv)


def build_config(args) -> RPCConfig:
    """Resolve settings: command line and environment first, then bitcoin.conf, then defaults"""
    datadir = Path(args.datadir).expanduser() if args.datadir else None
    conf_path = Path(args.conf).expanduser() if args.conf else (datadir or default_base_datadir()) / "bitcoin.conf"
    conf = read_bitcoin_conf(conf_path, args.network)
    if datadir is None and conf.get("datadir"):
        datadir = Path(conf["datadir"]).expanduser()

    port = args.rpc_port
    if port is None and conf.get("rpcport", "").isdigit():
        port = int(conf["rpcport"])
    if port is None:
        port = DEFAULT_RPC_PORTS[args.network]

    cookie_file = None
    if conf.get("rpccookiefile"):
        # Bitcoin Core resolves a relative rpccookiefile against the network's data directory
        cookie_file = discover_default_datadir(args.network, datadir) / Path(conf["rpccookiefile"]).expanduser()

    return RPCConfig(
        host=args.rpc_host,
        port=port,
        user=args.rpc_user or conf.get("rpcuser"),
        password=args.rpc_password or conf.get("rpcpassword"),
        network=args.network,
        datadir=datadir,
        cookie_file=cookie_file,
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
