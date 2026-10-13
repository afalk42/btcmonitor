"""Initial block download speed and time-to-completion estimates"""

from __future__ import annotations

from collections import deque


class SyncRate:
    """Rolling sync speed from (time, height, verification progress) samples.

    The ETA extrapolates verification progress, which Bitcoin Core estimates from transaction
    counts, rather than block height: early blocks are tiny and recent ones are full, so a
    block-based estimate would be far too optimistic.
    """

    def __init__(self, window_seconds: float = 120.0, min_span_seconds: float = 5.0):
        self.window_seconds = window_seconds
        self.min_span_seconds = min_span_seconds  # shortest span a rate is computed over
        self._samples: deque[tuple[float, int, float]] = deque()

    def add(self, now: float, height: int, progress: float) -> None:
        if self._samples and (height < self._samples[-1][1] or now <= self._samples[-1][0]):
            # The node was restarted or reindexed, or the clock went backwards: start over
            self._samples.clear()
        self._samples.append((now, height, progress))
        while len(self._samples) > 2 and now - self._samples[1][0] >= self.window_seconds:
            self._samples.popleft()

    def _span(self) -> tuple[float, int, float] | None:
        """(seconds, blocks, progress) between the oldest and newest sample, if long enough"""
        if len(self._samples) < 2:
            return None
        (t0, h0, p0), (t1, h1, p1) = self._samples[0], self._samples[-1]
        if t1 - t0 < self.min_span_seconds:
            return None
        return t1 - t0, h1 - h0, p1 - p0

    @property
    def blocks_per_second(self) -> float | None:
        span = self._span()
        return span[1] / span[0] if span else None

    @property
    def eta_seconds(self) -> float | None:
        span = self._span()
        if not span or span[2] <= 0:
            return None
        progress = self._samples[-1][2]
        return max(0.0, 1.0 - progress) * span[0] / span[2]
