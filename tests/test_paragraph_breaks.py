"""Paragraph breaks in born-digital PDFs (check_pdf.line_breaks).

Line geometry below is copied from the Varon thesis (Hebrew, ragged left,
first-line indents on the right, indented block quotes) where every paragraph
used to split after its first line, and from a ragged-right English
bibliography page."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import check_pdf  # noqa: E402


def group(lines, right, left, rtl=True, justified=False):
    """Run line_breaks over (x0, x1) lines; return paragraphs as index lists."""
    out, para, geo = [], [], []
    for i, (x0, x1) in enumerate(lines):
        g = {"x0": x0, "x1": x1}
        starts, ends = check_pdf.line_breaks(g, geo, right, left, rtl, justified)
        if starts and para:
            out.append(para)
            para, geo = [], []
        para.append(i)
        geo.append(g)
        if ends:
            out.append(para)
            para, geo = [], []
    if para:
        out.append(para)
    return out


class HebrewIndents(unittest.TestCase):
    def test_indent_starts_paragraph(self):
        # Varon p.44: last line of a paragraph, an indented first line, body lines
        lines = [(42, 508), (314, 508), (31, 473), (26, 508), (53, 509), (360, 508), (66, 473), (35, 509)]
        self.assertEqual(group(lines, 509, 21), [[0, 1], [2, 3, 4, 5], [6, 7]])

    def test_block_quote_stays_whole(self):
        # Varon p.90: body line, a quote indented on both sides, body again
        lines = [(74, 487), (237, 459), (231, 459), (235, 459), (305, 459), (67, 487), (44, 487)]
        self.assertEqual(group(lines, 487, 34), [[0], [1, 2, 3, 4], [5, 6]])

    def test_english_quote_in_hebrew_page(self):
        # Varon p.60: a left-aligned English quote, ragged right
        lines = [(174, 346), (174, 382), (174, 358), (174, 356), (174, 329)]
        self.assertEqual(group(lines, 494, 29, rtl=False), [[0, 1, 2, 3, 4]])


class EnglishBibliography(unittest.TestCase):
    def test_ragged_right_entries(self):
        # Varon p.124: entries wrap at varying widths; short last lines end them
        lines = [(90, 504), (90, 197), (90, 482), (90, 506), (90, 147)]
        self.assertEqual(group(lines, 529, 90, rtl=False), [[0, 1], [2, 3, 4]])

    def test_justified_line_short_of_margin_ends(self):
        lines = [(50, 500), (50, 500), (50, 430), (50, 500)]
        self.assertEqual(group(lines, 500, 50, rtl=False, justified=True), [[0, 1, 2], [3]])

    def test_is_justified(self):
        geo = [{"x0": 50, "x1": 500}] * 5 + [{"x0": 50, "x1": 200}]
        self.assertTrue(check_pdf.is_justified(geo, 500, 50))
        ragged = [{"x0": 50, "x1": x} for x in (500, 430, 470, 410, 488)]
        self.assertFalse(check_pdf.is_justified(ragged, 500, 50))


if __name__ == "__main__":
    unittest.main()
