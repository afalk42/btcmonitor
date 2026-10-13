import unittest

from btcmonitor.formatting import format_bytes, format_time_since_block, format_txid


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
        self.assertEqual(format_time_since_block(3725), "62:05")


if __name__ == "__main__":
    unittest.main()
