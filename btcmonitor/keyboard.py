"""Keyboard input that does not drop keys while the dashboard redraws"""

from __future__ import annotations

import codecs
import os
import re
import select
import sys
from collections.abc import Iterator
from typing import TextIO

import readchar

# Other sequences terminals send for these keys, mapped to readchar's constants
_ALIASES = {
    "\x1bOA": readchar.key.UP,
    "\x1bOB": readchar.key.DOWN,
    "\x1bOH": readchar.key.HOME,
    "\x1b[1~": readchar.key.HOME,
    "\x1b[7~": readchar.key.HOME,
    "\x1bOF": readchar.key.END,
    "\x1b[4~": readchar.key.END,
    "\x1b[8~": readchar.key.END,
}
_KEY = re.compile(r"\x1b\[[0-9;]*[A-Za-z~]|\x1bO[A-Za-z]|.", re.DOTALL)
_PARTIAL_ESCAPE = re.compile(r"\x1b(\[[0-9;]*|O)?\Z")
ESCAPE_WAIT_SECONDS = 0.05  # how long to wait for the rest of an escape sequence split across reads


def split_keys(text: str) -> list[str]:
    """Split raw terminal input into keys, e.g. "\\x1b[B\\x1b[Bq" -> [DOWN, DOWN, "q"]"""
    return [_ALIASES.get(key, key) for key in _KEY.findall(text)]


class KeyReader:
    """Reads key presses from a terminal for the duration of a `with` block.

    On POSIX the terminal stays in cbreak mode for the whole block. readchar instead switches
    modes around every character with TCSAFLUSH, which discards keys typed while the previous
    one is being handled, and turns Ctrl+C into an exception in the reading thread. In cbreak
    mode Ctrl+C still raises KeyboardInterrupt in the main thread. Elsewhere (Windows) readchar
    is used as is.
    """

    def __init__(self, stream: TextIO | None = None):
        self._stream = stream or sys.stdin
        self._fd: int | None = None
        self._saved_mode: list | None = None

    def __enter__(self) -> KeyReader:
        if os.name == "posix" and self._stream.isatty():
            import termios
            import tty

            self._fd = self._stream.fileno()
            self._saved_mode = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._saved_mode is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_mode)
            self._saved_mode = None

    def keys(self) -> Iterator[str]:
        """Yield keys as they are pressed; blocks between keys and ends when input closes"""
        if self._saved_mode is None:
            while True:
                yield readchar.readkey()

        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            data = os.read(self._fd, 64)
            if not data:
                return
            text = decoder.decode(data)
            # An escape sequence can arrive in pieces (e.g. over SSH); give the rest a moment
            while _PARTIAL_ESCAPE.search(text) and select.select([self._fd], [], [], ESCAPE_WAIT_SECONDS)[0]:
                more = os.read(self._fd, 64)
                if not more:
                    break
                text += decoder.decode(more)
            yield from split_keys(text)
