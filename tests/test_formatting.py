import unittest

from btcmonitor.formatting import (
    fiat_label,
    format_age,
    format_bytes,
    format_duration,
    format_fiat,
    format_time_since_block,
    format_txid,
)


class FormattingTests(unittest.TestCase):
    def test_format_bytes(self):
        for num, expected in (
            (0, "0 B"),
            (1023, "1023 B"),
            (1024, "1 KB"),
            (1536 * 1024, "2 MB"),
            (5 * 1024**3, "5 GB"),
            (3 * 1024**4, "3.0 TB"),
        ):
            with self.subTest(num=num):
                self.assertEqual(format_bytes(num), expected)

    def test_format_txid(self):
        self.assertEqual(format_txid("abcdef0123456789"), "abcd...6789")
        self.assertEqual(format_txid("short"), "short")

    def test_format_time_since_block(self):
        self.assertEqual(format_time_since_block(0), "0:00")
        self.assertEqual(format_time_since_block(125), "2:05")
        self.assertEqual(format_time_since_block(3599), "59:59")
        self.assertEqual(format_time_since_block(3725), "1h 02m")
        self.assertEqual(format_time_since_block(8253680 * 60), "5731d 17h")

    def test_format_fiat(self):
        self.assertEqual(format_fiat(1234567.4, "usd"), "$1,234,567")
        self.assertEqual(format_fiat(0.425, "eur", decimals=2), "€0.42")
        self.assertEqual(format_fiat(1234, "sek"), "1,234 SEK")
        self.assertEqual((fiat_label("usd"), fiat_label("eur")), ("US$", "EUR"))

    def test_format_age(self):
        for seconds, expected in ((5, "<1m"), (59.9, "<1m"), (60, "1m"), (3599, "59m"), (3725, "1h 02m")):
            with self.subTest(seconds=seconds):
                self.assertEqual(format_age(seconds), expected)

    def test_format_duration(self):
        for seconds, expected in (
            (0, "0s"),
            (45.9, "45s"),
            (750, "12m 30s"),
            (4 * 3600 + 300, "4h 05m"),
            (2 * 86400 + 3 * 3600 + 59 * 60, "2d 3h"),
        ):
            with self.subTest(seconds=seconds):
                self.assertEqual(format_duration(seconds), expected)


if __name__ == "__main__":
    unittest.main()
