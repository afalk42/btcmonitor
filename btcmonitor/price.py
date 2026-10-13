"""Bitcoin price lookup with caching"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies={currency}"


class PriceFeed:
    """BTC price in `currency` from CoinGecko (no auth required), fetched at most once per `cache_seconds`.

    With `enabled=False` no request is ever made, for node operators who would rather not reveal
    their IP address to a third party.
    """

    def __init__(self, currency: str = "usd", enabled: bool = True, cache_seconds: float = 60.0, timeout: float = 3.0):
        self.currency = currency.lower()
        self.enabled = enabled
        self.cache_seconds = cache_seconds
        self.timeout = timeout
        self.unsupported = False  # CoinGecko does not quote this currency
        self._price: float | None = None
        self._attempted_at: float | None = None

    def get(self) -> float | None:
        """Current price, or the last known price (None if never fetched) when the API fails"""
        if not self.enabled or self.unsupported:
            return None
        now = time.monotonic()
        if self._attempted_at is not None and now - self._attempted_at < self.cache_seconds:
            return self._price
        # Count failed attempts too, so an unreachable API costs one timeout per period, not one per refresh
        self._attempted_at = now
        url = COINGECKO_URL.format(currency=urllib.parse.quote(self.currency))
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                quotes = json.loads(response.read())["bitcoin"]
            if self.currency not in quotes:
                # An unknown currency is answered with an empty object; asking again won't help
                self.unsupported = True
                return None
            self._price = float(quotes[self.currency])
        except Exception:
            pass
        return self._price
