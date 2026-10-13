# Roadmap

Candidate features for btcmonitor, roughly in order of value. Each item is meant to become its own pull request; completed items are marked ✅ with the date they were merged.

## Features

1. **Initial block download view.** While `getblockchaininfo` reports `initialblockdownload`, show sync progress, blocks per second and an estimated time to completion instead of the mostly empty mempool panels. This is a natural follow-up to PR #1, which stopped the dashboard from crashing during IBD.

2. **Fee estimates.** Show `estimatesmartfee` results for 1, 3, 6 and 144 blocks, so the dashboard answers "what fee should I pay right now?".

3. **Recent blocks panel.** List the last few blocks with height, age, transaction count, size, total fees and the miner tag from the coinbase.

4. **Price privacy and currency options.** The price lookup sends a request to CoinGecko from the node's IP address about once a minute, which node operators may not want. Add `--no-price` to turn it off, and a currency option for non-USD prices.

5. **Networking details.** Bandwidth from `getnettotals`, plus peer client versions and connection types (including BIP324 v2 transport) from `getpeerinfo`.

6. **Transaction detail view.** Press Enter on a row in the largest-transactions list to see inputs, outputs, fee, ancestors and descendants for that transaction.

7. **PyPI release.** Publish the package so it can be installed with `pipx install btcmonitor`, replacing the manual virtual environment steps in the README.

## Maintenance

- ✅ *2026-10-13* — **Minimum Python raised to 3.11.** Python 3.9 reached end of life in October 2025; 3.11 is supported until October 2027.
