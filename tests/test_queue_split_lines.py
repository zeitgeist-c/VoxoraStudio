"""
txttoTTS - toplu üretim kuyruğu yardımcı testleri.

queue_split_lines pure helper'ı test eder.
"""
from __future__ import annotations

import unittest

from app.main_window import queue_split_lines


class QueueSplitLinesTests(unittest.TestCase):
    def test_empty_text_returns_empty_list(self):
        self.assertEqual(queue_split_lines(""), [])
        self.assertEqual(queue_split_lines("\n\n\n"), [])

    def test_single_line(self):
        self.assertEqual(queue_split_lines("Merhaba"), ["Merhaba"])

    def test_multiple_lines_with_blanks(self):
        text = "Birinci\n\nİkinci\n   \nÜçüncü\n"
        self.assertEqual(
            queue_split_lines(text),
            ["Birinci", "İkinci", "Üçüncü"],
        )

    def test_only_blank_lines(self):
        self.assertEqual(queue_split_lines("\n\n\n\n"), [])

    def test_leading_trailing_whitespace(self):
        text = "  Birinci  \n   İkinci\n"
        self.assertEqual(queue_split_lines(text), ["Birinci", "İkinci"])


if __name__ == "__main__":
    unittest.main()