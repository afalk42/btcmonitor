# btcmonitor

A terminal dashboard (TUI) that monitors a local Bitcoin Core node using its JSON-RPC interface.

- Cross-platform: macOS and Ubuntu/Linux
- Uses cookie auth detection or `bitcoin.conf`
- Visualizes the following data about your bitcoin node in a dashboard:
  - Node health, blockchain height, peer information
  - Bitcoin price, block subsidy, # of blocks until next halving, time since last block
  - Mempool transaction count, memory size and fee histogram
  - Next block template as well as expected tx count, weight, and fee rate bands
  - Scrollable list of the 100 largest transactions in the mempool sorted by BTC output

![[screenshot.png]]

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

```bash
git clone https://github.com/afalk42/btcmonitor
python3 -m venv ~/.venv/
source ~/.venv/bin/activate
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

If `--rpc-user`/`--rpc-password` are omitted, cookie authentication will be attempted.

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
