import os
import threading
import time
import unittest

import readchar

from btcmonitor.keyboard import KeyReader, split_keys


class SplitKeysTests(unittest.TestCase):
    def test_several_keys_in_one_read(self):
        k = readchar.key
        raw = k.UP + k.DOWN + k.DOWN + k.PAGE_UP + k.PAGE_DOWN + k.HOME + k.END + "q"
        self.assertEqual(split_keys(raw), [k.UP, k.DOWN, k.DOWN, k.PAGE_UP, k.PAGE_DOWN, k.HOME, k.END, "q"])

    def test_alternative_sequences_map_to_readchar_keys(self):
        for raw, key in (
            ("\x1bOA", readchar.key.UP),
            ("\x1bOB", readchar.key.DOWN),
            ("\x1b[1~", readchar.key.HOME),
            ("\x1bOH", readchar.key.HOME),
            ("\x1b[4~", readchar.key.END),
            ("\x1bOF", readchar.key.END),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(split_keys(raw), [key])

    def test_plain_characters_and_lone_escape(self):
        self.assertEqual(split_keys("aQ\x1b"), ["a", "Q", "\x1b"])


@unittest.skipUnless(os.name == "posix", "terminal modes are POSIX-only")
class KeyReaderTests(unittest.TestCase):
    def setUp(self):
        import pty

        master, slave = pty.openpty()
        self.master = master
        self.terminal = os.fdopen(slave, "r")
        self.addCleanup(os.close, master)
        self.addCleanup(self.terminal.close)

    def read_keys(self, count, chunks, delay=0.0, handling_time=0.0):
        """Write `chunks` to the terminal, pausing `delay` between them, and collect `count` keys,
        spending `handling_time` on each key as the dashboard would on a redraw"""
        keys = []

        def consume(reader):
            for key in reader.keys():
                keys.append(key)
                time.sleep(handling_time)
                if len(keys) == count:
                    return

        with KeyReader(self.terminal) as reader:
            reading = threading.Thread(target=consume, args=(reader,), daemon=True)
            reading.start()
            for chunk in chunks:
                os.write(self.master, chunk)
                time.sleep(delay)
            reading.join(timeout=5)
        return keys

    def test_keys_typed_while_one_is_handled_are_not_lost(self):
        # readchar flushed input that arrived between reads; with this timing it lost about half the keys
        keys = self.read_keys(10, [b"\x1b[B"] * 10, delay=0.03, handling_time=0.05)
        self.assertEqual(keys, [readchar.key.DOWN] * 10)

    def test_escape_sequence_split_across_reads(self):
        keys = self.read_keys(2, [b"\x1b[", b"Bq"], delay=0.01)
        self.assertEqual(keys, [readchar.key.DOWN, "q"])

    def test_terminal_mode_is_restored(self):
        import termios

        before = termios.tcgetattr(self.terminal.fileno())
        with KeyReader(self.terminal):
            self.assertNotEqual(termios.tcgetattr(self.terminal.fileno()), before)
        self.assertEqual(termios.tcgetattr(self.terminal.fileno()), before)


if __name__ == "__main__":
    unittest.main()
