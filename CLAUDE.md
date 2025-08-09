# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Installation & Setup
```bash
# Create and activate virtual environment
python3 -m venv ~/.venv/
source ~/.venv/bin/activate

# Install in development mode
pip install -e .
```

### Running the Application
```bash
# Run with default settings (auto-discovers Bitcoin Core datadir and cookie)
btcmonitor

# Run with custom RPC settings
btcmonitor --network mainnet --rpc-host 127.0.0.1 --rpc-port 8332 --rpc-user user --rpc-password pass

# Run with different refresh rate
btcmonitor --refresh 1.5

# Get help
btcmonitor --help
```

### Testing & Quality
The project uses a simple setup.py-based build system with setuptools. There are no explicit test commands or linting tools configured in the project files.

## Architecture Overview

### Core Components

**btcmonitor/**: Main package directory
- `__main__.py`: CLI entry point with argument parsing and main loop initialization
- `rpc.py`: Bitcoin Core JSON-RPC client with authentication handling (cookie + basic auth)
- `ui.py`: Terminal UI rendering using Rich library for dashboard layout
- `paths.py`: Cross-platform Bitcoin datadir and cookie file discovery

### Key Architecture Patterns

**Authentication Strategy**: The RPC client (`BitcoinRPC`) implements a fallback authentication system:
1. First attempts basic auth if user/password provided
2. Falls back to cookie authentication by auto-discovering `.cookie` file
3. Supports network-specific datadir discovery (mainnet, testnet, signet, regtest)

**Dashboard Architecture**: Uses Rich library's Layout system with 5 panels:
- **Top row**: System stats, Bitcoin info (price/halving), Node status
- **Bottom row**: Mempool visualization, Next block template projection

**Data Flow**: 
1. `gather_snapshot()` in ui.py:712 collects all data via RPC calls
2. Transforms raw RPC responses into structured dataclasses
3. Updates all UI panels in render loop

**Block Template Handling**: Dual approach for next block projection:
1. Primary: Uses `getblocktemplate` RPC for accurate block composition
2. Fallback: Synthetic estimation from mempool fee buckets when RPC unavailable

### External Dependencies
- `requests`: HTTP client for JSON-RPC calls
- `rich`: Terminal UI framework for layouts, panels, and text styling
- `psutil`: System monitoring (CPU, memory stats)
- CoinGecko API: Bitcoin price fetching (with 60s caching)

### Network Configuration
Default ports by network:
- mainnet: 8332
- testnet: 18332  
- signet: 38332
- regtest: 18443

The application auto-detects network-specific datadirs and cookie files across macOS, Windows, and Linux.