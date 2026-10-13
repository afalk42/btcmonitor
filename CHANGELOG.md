# Changelog

## 0.9.0

First release published to PyPI (`pipx install btcmonitor`).

### New
- Initial block download view with progress, blocks per second and estimated time left
- Fee estimates for 2, 3 and 6 blocks and one day
- Recent blocks panel with fees and mining pool
- Network panel: traffic rates and totals, connection types, encrypted v2 transport, peer clients
- Transaction detail view: select a transaction and press Enter
- `--no-price` to skip the CoinGecko request, `--currency` for non-USD prices
- RPC settings are read from `bitcoin.conf`; `--datadir`, `--conf` and testnet4 support; the RPC port follows `--network`
- `--version`

### Fixed
- Crash when no block template is available (initial block download, no peers)
- Fee bucket boundaries and block-template fee buckets
- Losing the connection after bitcoind restarts with a new auth cookie
- Crash from a race between the transaction loader and the display
- Largest-transactions list skipping transactions in mempools over 20,000 entries
- Unexpected errors ending the program instead of being shown
- Dropped key presses and Ctrl+C needing two presses
- Mempool and Difficulty rows cut off in the Bitcoin Core panel

### Changed
- Requires Python 3.11 or later
- The node is polled on a background thread; the full mempool and block template are fetched every 5 seconds instead of on every refresh
