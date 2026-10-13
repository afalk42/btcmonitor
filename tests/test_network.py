import unittest

from btcmonitor.network import TrafficRate, summarize_peers


class TrafficRateTests(unittest.TestCase):
    def test_needs_two_samples(self):
        rate = TrafficRate()
        self.assertIsNone(rate.rates)
        rate.add(0, 1000, 500)
        self.assertIsNone(rate.rates)
        rate.add(2, 5000, 700)
        self.assertEqual(rate.rates, (2000.0, 100.0))

    def test_rolling_window(self):
        rate = TrafficRate(window_seconds=10)
        rate.add(0, 0, 0)
        rate.add(1, 1_000_000, 0)  # an early burst
        for t in range(2, 30):
            rate.add(t, 1_000_000 + (t - 1) * 100, 0)
        self.assertAlmostEqual(rate.rates[0], 100.0)

    def test_counter_reset_starts_over(self):
        rate = TrafficRate()
        rate.add(0, 10_000, 10_000)
        rate.add(5, 50, 20)  # node restarted
        self.assertIsNone(rate.rates)


class SummarizePeersTests(unittest.TestCase):
    def test_summary(self):
        peers = [
            {"connection_type": "outbound-full-relay", "transport_protocol_type": "v2", "subver": "/Satoshi:31.1.0/"},
            {"connection_type": "outbound-full-relay", "transport_protocol_type": "v2", "subver": "/Satoshi:31.1.0/"},
            {"connection_type": "block-relay-only", "transport_protocol_type": "v1", "subver": "/Satoshi:30.2.0/"},
            {"connection_type": "inbound", "inbound": True, "transport_protocol_type": "v2", "subver": "/Knots:29/"},
        ]
        types, v2, clients = summarize_peers(peers)
        self.assertEqual(types, {"full": 2, "block": 1})  # inbound peers are not outbound types
        self.assertEqual(v2, 3)
        self.assertEqual(clients[0], ("Satoshi:31.1.0", 2))

    def test_missing_fields_from_older_nodes(self):
        types, v2, clients = summarize_peers([{"inbound": False}])
        self.assertEqual((types, v2, clients), ({"?": 1}, 0, [("?", 1)]))


if __name__ == "__main__":
    unittest.main()
