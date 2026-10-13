# btcmonitor

A terminal dashboard (TUI) that monitors a local Bitcoin Core node using its JSON-RPC interface.

- Cross-platform using Python3 and [Rich](https://github.com/Textualize/rich): tested on macOS, Ubuntu, Windows
- Reads RPC credentials from the auth cookie or `bitcoin.conf`, with optional command-line overrides
- Visualizes the following data about your bitcoin node in a dashboard:
  - Node health, blockchain height, peer information
  - Bitcoin price, block subsidy, # of blocks until next halving, time since last block
  - Mempool transaction count, memory size and fee histogram
  - Next block template as well as expected tx count, weight, and fee rate bands
  - Scrollable list of the 100 largest transactions in the mempool sorted by BTC output

![Screenshot](/screenshot.png)

## Installation

### Prerequisites

The following are needed for a successful installation:

- Python 3.9+
- PIP Python Package Mangager
- Python3 virtual environments support

If you don't have them already available, you can used these commands on Linux to install the prerequisites:

```bash
sudo apt install python3 python3-pip python3-venv
```

### Installation

#### On MacOS and Ubuntu/Linux

On both MacOS and Ubunut using pip in Python3 requires the use of a venv virtual environment.

```bash
git clone https://github.com/afalk42/btcmonitor
python3 -m venv ~/.venv/
source ~/.venv/bin/activate
cd btcmonitor
pip install -e .
```

#### On Windows 11

It appears that using a Python venv is not required on Windows.

```bash
git clone https://github.com/afalk42/btcmonitor
cd btcmonitor
pip install -e .
```

## Usage

```bash
btcmonitor --help
```

By default it auto-discovers the datadir and cookie file for the default network (`mainnet`). You can override:

```bash
btcmonitor --network mainnet --rpc-host 127.0.0.1 --rpc-port 8332 --rpc-user user --rpc-password pass
```

Settings are resolved in this order: command-line options (or the `BITCOIN_*` environment variables), then `bitcoin.conf`, then defaults. From `bitcoin.conf` btcmonitor reads `rpcuser`, `rpcpassword`, `rpcport`, `rpccookiefile` and `datadir`, honoring network sections such as `[signet]`. It looks for `bitcoin.conf` in the data directory; use `--conf` to point elsewhere.

If no user and password are configured, cookie authentication will be attempted. If your node uses a non-default data directory, pass it with `--datadir` (or `BITCOIN_DATADIR`) so the cookie can be found.

`--network` accepts `mainnet`, `testnet` (alias `testnet3`), `testnet4`, `signet` and `regtest`. Unless `--rpc-port` is given, the network's standard RPC port is used (8332, 18332, 48332, 38332 and 18443 respectively).

## Requirements
- Python 3.9+ with pip and venv support
- A running `bitcoind` with JSON-RPC enabled (default on loopback)

## Features
- Node summary: block height, headers, verification progress, peers, mempool bytes/txs, uptime
- System stats: CPU, memory, I/O
- Mempool visualization: fee buckets with ASCII bars
- Next block projection: approximate composition derived from `getblocktemplate` or mempool fees
- Bitcoin price, block subsidy, # of blocks until next halving, time since last block
- Scrollable list of the 100 largest transactions in the mempool sorted by BTC output

## Quit
- Press `q` or `Ctrl+C`

## Tests and linting

After installing the project with its development extras in your virtual environment, run:

```bash
pip install -e ".[dev]"
python -m unittest discover -v
ruff check .
```

The tests run offline and do not require a Bitcoin Core node. GitHub Actions runs the same checks on every push and pull request.
