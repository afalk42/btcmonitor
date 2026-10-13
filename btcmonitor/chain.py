"""Consensus arithmetic: block subsidy and halving schedule"""

from __future__ import annotations

from datetime import datetime, timedelta

HALVING_INTERVAL = 210_000
INITIAL_SUBSIDY_BTC = 50.0
BLOCK_TIME_MINUTES = 10  # Average block time


def get_current_subsidy(block_height: int) -> float:
    """Calculate current block subsidy based on block height"""
    halvings = block_height // HALVING_INTERVAL
    return INITIAL_SUBSIDY_BTC / (2**halvings)


def calculate_halving_info(block_height: int, now: datetime | None = None) -> tuple[int, str]:
    """Return blocks until the next halving and its estimated date (YYYY-MM-DD)"""
    next_halving_block = ((block_height // HALVING_INTERVAL) + 1) * HALVING_INTERVAL
    blocks_until_halving = next_halving_block - block_height

    # Estimate date (approximate)
    estimated_date = (now or datetime.now()) + timedelta(minutes=blocks_until_halving * BLOCK_TIME_MINUTES)
    return blocks_until_halving, estimated_date.strftime("%Y-%m-%d")
