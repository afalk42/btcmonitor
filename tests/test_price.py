import io
import json
import unittest
from unittest.mock import patch

from btcmonitor.price import PriceFeed


def response(price):
    return io.BytesIO(json.dumps({"bitcoin": {"usd": price}}).encode())


class PriceFeedTests(unittest.TestCase):
    def setUp(self):
        self.feed = PriceFeed(cache_seconds=60)
        self.clock = 1000.0
        for target, kwargs in (
            ("btcmonitor.price.time.monotonic", {"side_effect": lambda: self.clock}),
            ("btcmonitor.price.urllib.request.urlopen", {}),
        ):
            patcher = patch(target, **kwargs)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
        self.urlopen = mock

    def test_other_currency(self):
        feed = PriceFeed("EUR", cache_seconds=60)
        self.urlopen.return_value = io.BytesIO(b'{"bitcoin": {"eur": 74507}}')
        self.assertEqual(feed.get(), 74507.0)
        self.assertIn("vs_currencies=eur", self.urlopen.call_args.args[0])

    def test_unsupported_currency_is_not_asked_again(self):
        feed = PriceFeed("xyz", cache_seconds=60)
        self.urlopen.return_value = io.BytesIO(b'{"bitcoin": {}}')
        self.assertIsNone(feed.get())
        self.assertTrue(feed.unsupported)
        self.clock += 600
        self.assertIsNone(feed.get())
        self.assertEqual(self.urlopen.call_count, 1)

    def test_disabled_feed_makes_no_requests(self):
        self.assertIsNone(PriceFeed(enabled=False).get())
        self.urlopen.assert_not_called()

    def test_price_is_cached_for_the_period(self):
        self.urlopen.return_value = response(65000)
        self.assertEqual(self.feed.get(), 65000.0)
        self.clock += 59
        self.urlopen.return_value = response(70000)
        self.assertEqual(self.feed.get(), 65000.0)
        self.clock += 1
        self.assertEqual(self.feed.get(), 70000.0)
        self.assertEqual(self.urlopen.call_count, 2)

    def test_failure_keeps_last_price_and_waits_before_retrying(self):
        self.urlopen.return_value = response(65000)
        self.feed.get()
        self.clock += 60
        self.urlopen.side_effect = OSError("network down")
        self.assertEqual(self.feed.get(), 65000.0)
        self.clock += 30
        self.assertEqual(self.feed.get(), 65000.0)
        self.assertEqual(self.urlopen.call_count, 2)  # no retry within the period

    def test_no_price_before_first_success(self):
        self.urlopen.side_effect = ValueError("bad JSON")
        self.assertIsNone(self.feed.get())


if __name__ == "__main__":
    unittest.main()
