# btcmonitor

A terminal dashboard (TUI) that monitors a local Bitcoin Core node using its JSON-RPC interface.

- Cross-platform using Python3 and [Rich](https://github.com/Textualize/rich): tested on macOS, Ubuntu, Windows
- Reads RPC credentials from the auth cookie or `bitcoin.conf`, with optional command-line overrides
- Visualizes the following data about your bitcoin node in a dashboard:
  - Node health, blockchain height, peer information
  - Bitcoin price, block subsidy, # of blocks until next halving, time since last block
  - Mempool transaction count, memory size and fee histogram
  - Next block template as well as expected tx count, weight, and fee rate bands
  - Fee estimates from Bitcoin Core for confirmation within 2, 3 and 6 blocks and one day
  - Scrollable list of the 100 largest transactions in the mempool sorted by BTC output
  - While the node is syncing: progress, blocks per second and estimated time to completion

![Screenshot](/screenshot.png)

## Installation

### Prerequisites

The following are needed for a successful installation:

- Python 3.11+
- PIP Python Package Manager
- Python3 virtual environments support

If you don't have them already available, you can use these commands on Linux to install the prerequisites (Ubuntu 24.04 and later ship Python 3.12; on older releases install a newer Python first):

```bash
sudo apt install python3 python3-pip python3-venv
```

### Installation

#### On macOS and Ubuntu/Linux

On both macOS and Ubuntu using pip in Python3 requires the use of a venv virtual environment.

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
- Python 3.11+ with pip and venv support
- A running `bitcoind` with JSON-RPC enabled (default on loopback)

## Features
- Node summary: block height, headers, verification progress, peers, mempool bytes/txs, difficulty
- System stats: CPU, memory, swap, uptime, load average
- Mempool visualization: fee buckets with ASCII bars
- Next block projection: approximate composition derived from `getblocktemplate` or mempool fees
- Fee estimates: `estimatesmartfee` for 2, 3 and 6 blocks and one day (144 blocks), in sat/vB; Bitcoin Core's shortest target is 2 blocks
- Bitcoin price, block subsidy, # of blocks until next halving, time since last block
- Scrollable list of the 100 largest transactions in the mempool sorted by BTC output
- Initial block download view: replaces the mempool panels while the node syncs, with progress, blocks remaining, blocks per second, estimated time left (extrapolated from verification progress over the last two minutes), the date of the block being validated and size on disk

## Keys
- `↑`/`↓`, `PgUp`/`PgDn`, `Home`/`End`: scroll the largest-transactions list
- `q` or `Ctrl+C`: quit

## Refresh rate
`--refresh` sets how often the display redraws and the node is polled (default 2 Hz). The mempool histogram and the next-block projection, which require fetching the whole mempool and a block template, are refreshed every 5 seconds and whenever a new block arrives. The largest-transactions list looks up new mempool transactions in the background about once a minute.

## Tests and linting

After installing the project with its development extras in your virtual environment, run:

```bash
pip install -e ".[dev]"
python -m unittest discover -v
ruff check .
ruff format --check .
```

The tests run offline and do not require a Bitcoin Core node.

## Project layout

| Module | Purpose |
| --- | --- |
| `__main__.py`, `conf.py`, `paths.py` | Command line, `bitcoin.conf` and data directory discovery |
| `rpc.py` | JSON-RPC client with cookie and password authentication |
| `collector.py` | Polls the node on a background thread and assembles `DashboardData` |
| `transactions.py` | Background lookups for the largest-transactions list |
| `price.py` | Cached BTC/USD price |
| `fees.py`, `chain.py`, `formatting.py` | Pure calculations: fee buckets, next-block projection, subsidy and halving, text formatting |
| `models.py` | Data classes passed from the collector to the panels |
| `panels.py`, `app.py`, `keyboard.py` | Rendering, layout, render loop and keyboard input | GitHub Actions runs the same checks on every push and pull request.
