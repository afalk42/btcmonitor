"""Bitcoin price lookup with caching"""

from __future__ import annotations

import json
import time
import urllib.request

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"


class PriceFeed:
    """BTC/USD price from CoinGecko (no auth required), fetched at most once per `cache_seconds`"""

    def __init__(self, cache_seconds: float = 60.0, timeout: float = 3.0):
        self.cache_seconds = cache_seconds
        self.timeout = timeout
        self._price: float | None = None
        self._attempted_at: float | None = None

    def get(self) -> float | None:
        """Current price, or the last known price (None if never fetched) when the API fails"""
        now = time.monotonic()
        if self._attempted_at is not None and now - self._attempted_at < self.cache_seconds:
            return self._price
        # Count failed attempts too, so an unreachable API costs one timeout per period, not one per refresh
        self._attempted_at = now
        try:
            with urllib.request.urlopen(COINGECKO_URL, timeout=self.timeout) as response:
                self._price = float(json.loads(response.read())["bitcoin"]["usd"])
        except Exception:
            pass
        return self._price
