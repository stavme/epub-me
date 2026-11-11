"""Tests for box continuation in assemble_book.py and for guess_first_page.py.

Run: python3 -m unittest discover -s tests
Schiff ch. 2: boxes that ran across pages came out as two boxes, and
--first-page was worked out by hand from a printed page number.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import guess_first_page  # noqa: E402

ASSEMBLE = os.path.join(ROOT, "scripts", "assemble_book.py")


def assemble(pages, *extra):
    with tempfile.TemporaryDirectory() as d:
        for i, text in enumerate(pages, 1):
            with open(os.path.join(d, f"{i:03d}.md"), "w", encoding="utf-8") as fh:
                fh.write(text)
        out = os.path.join(d, "book.md")
        subprocess.run([sys.executable, ASSEMBLE, d, out, *extra], check=True, capture_output=True)
        with open(out, encoding="utf-8") as fh:
            return fh.read()


class BoxContinuation(unittest.TestCase):
    def test_new_paragraph_merges_into_one_box(self):
        md = assemble(["טקסט.\n\n::: box\nפסקה ראשונה.\n:::\n", "::: +\nפסקה שנייה.\n:::\n\nאחרי.\n"])
        self.assertEqual(md.count("::: box"), 1)
        self.assertNotIn("::: +", md)
        self.assertIn("פסקה ראשונה.\n\nפסקה שנייה.\n:::", md)

    def test_plus_joins_the_last_paragraph(self):
        md = assemble(["::: box\nמשפט שנמשך\n:::\n", "::: +\n+\nבעמוד הבא.\n:::\n"])
        self.assertIn("משפט שנמשך\nבעמוד הבא.\n:::", md)

    def test_page_marker_lands_inside_the_box(self):
        md = assemble(["::: box\nא.\n:::\n", "::: +\nב.\n:::\n"], "--page-markers", "--first-page", "81")
        start, end = md.index("::: box"), md.rindex(":::")
        self.assertIn('id="page-82"', md[start:end])

    def test_continuation_without_box_fails(self):
        with self.assertRaises(subprocess.CalledProcessError):
            assemble(["::: +\nא.\n:::\n"])


class GuessFirstPage(unittest.TestCase):
    def test_majority_of_page_numbers(self):
        lines = ["001\tשיף", "020\t81", "021\t82", "022\t83", "030\t19"]  # 19: OCR noise
        self.assertEqual(guess_first_page.guess(lines), 62)

    def test_too_few_votes(self):
        self.assertIsNone(guess_first_page.guess(["020\t81", "021\t82"]))

    def test_running_headers_only(self):
        self.assertIsNone(guess_first_page.guess(["002\tניהול סכסוכים", "003\tניהול סכסוכים"]))


if __name__ == "__main__":
    unittest.main()
