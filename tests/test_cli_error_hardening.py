import json
import tempfile
import unittest
from pathlib import Path

from mcp_ward.report import render_text
from mcp_ward.diff import Finding, DiffReport


class CliErrorTextTests(unittest.TestCase):
    def test_error_renderer_neutralizes_control_sequences(self):
        from mcp_ward.report import safe_error

        text = safe_error("\x1b]0;spoof\x07\x9d0;c1\x9c\u202e\u2066")
        for char in ("\x1b", "\x07", "\x9b", "\x9d", "\x9c", "\u202e", "\u2066"):
            self.assertNotIn(char, text)


if __name__ == "__main__":
    unittest.main()
