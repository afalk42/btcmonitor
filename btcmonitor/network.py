"""Network traffic rates and peer summaries"""

from __future__ import annotations

from collections import Counter, deque

# Short names for getpeerinfo's connection_type values
CONNECTION_TYPE_NAMES = {
    "outbound-full-relay": "full",
    "block-relay-only": "block",
    "manual": "manual",
    "addr-fetch": "addr",
    "feeler": "feeler",
    "inbound": "inbound",
}


class TrafficRate:
    """Receive and send rates (bytes/s) from getnettotals counters over a short rolling window"""

    def __init__(self, window_seconds: float = 10.0):
        self.window_seconds = window_seconds
        self._samples: deque[tuple[float, int, int]] = deque()

    def add(self, now: float, total_recv: int, total_sent: int) -> None:
        if self._samples and (total_recv < self._samples[-1][1] or now <= self._samples[-1][0]):
            # Counters reset (node restarted) or the clock went backwards: start over
            self._samples.clear()
        self._samples.append((now, total_recv, total_sent))
        while len(self._samples) > 2 and now - self._samples[1][0] >= self.window_seconds:
            self._samples.popleft()

    @property
    def rates(self) -> tuple[float, float] | None:
        """(receive, send) in bytes per second, once there are two samples"""
        if len(self._samples) < 2:
            return None
        (t0, r0, s0), (t1, r1, s1) = self._samples[0], self._samples[-1]
        return (r1 - r0) / (t1 - t0), (s1 - s0) / (t1 - t0)


def summarize_peers(peer_info: list[dict]) -> tuple[dict[str, int], int, list[tuple[str, int]]]:
    """(outbound connections by short type, peers on v2 transport, client versions by count)"""
    types = Counter(
        CONNECTION_TYPE_NAMES.get(peer.get("connection_type", ""), peer.get("connection_type", "?"))
        for peer in peer_info
        if not peer.get("inbound", False)
    )
    v2 = sum(1 for peer in peer_info if peer.get("transport_protocol_type") == "v2")
    clients = Counter(peer.get("subver", "").strip("/") or "?" for peer in peer_info)
    return dict(types.most_common()), v2, clients.most_common()
