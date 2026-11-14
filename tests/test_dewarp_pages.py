"""dewarp_pages.choose: flatten a page only when it clearly helps (23-page English scan, 2026-11-14)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from dewarp_pages import choose  # noqa: E402


class Choose(unittest.TestCase):
    def test_curved_page_flattened(self):  # page 004: 505 words, 44 unknown -> 457, 19
        self.assertTrue(choose((505, 44), (457, 19)))

    def test_flat_page_not_tried(self):  # page 003: 1.6% unknown
        self.assertFalse(choose((548, 9), (481, 34)))

    def test_worse_after_flattening(self):  # page 009
        self.assertFalse(choose((548, 28), (489, 37)))

    def test_too_many_words_lost(self):  # page 008 (map): fewer unknown words, but 129 of 182 words left
        self.assertFalse(choose((182, 51), (129, 16)))

    def test_no_flat_version_or_no_text(self):
        self.assertFalse(choose((500, 50), None))
        self.assertFalse(choose((0, 0), (10, 0)))


if __name__ == "__main__":
    unittest.main()
