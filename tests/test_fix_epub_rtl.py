"""Regression tests for scripts/fix_epub_rtl.py and the stylesheets.

Run: python3 -m unittest discover -s tests
Bug (Schiff ch. 2): the tag regex matched "<li" inside "<link", producing
<li dir="rtl"nk ...> and an unparseable nav.xhtml; epubcheck also rejects
CSS "direction" (CSS-001), so the dir="rtl" attributes must do that job.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.dom import minidom

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "fix_epub_rtl.py")

XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="he">
<head><title>t</title>
  <link rel="stylesheet" type="text/css" href="styles/stylesheet1.css" />
</head>
<body><section class="box"><ol><li>a</li><li>b</li></ol>
<table><tr><td>x</td></tr></table></section><p>text</p></body>
</html>
"""


def run_fix(xhtml):
    with tempfile.TemporaryDirectory() as d:
        epub = os.path.join(d, "b.epub")
        with zipfile.ZipFile(epub, "w") as z:
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z.writestr("EPUB/nav.xhtml", xhtml)
        subprocess.run([sys.executable, SCRIPT, epub], check=True, capture_output=True)
        with zipfile.ZipFile(epub) as z:
            assert z.namelist()[0] == "mimetype"
            return z.read("EPUB/nav.xhtml").decode("utf-8")


class FixEpubRtl(unittest.TestCase):
    def test_link_is_not_mistaken_for_li(self):
        out = run_fix(XHTML)
        self.assertIn('<link rel="stylesheet"', out)
        self.assertNotIn('<li dir="rtl"nk', out)

    def test_output_is_well_formed_xml(self):
        minidom.parseString(run_fix(XHTML).encode("utf-8"))

    def test_dir_added_to_block_elements(self):
        out = run_fix(XHTML)
        for tag in ("html", "section", "ol", "li", "table"):
            self.assertRegex(out, r'<%s dir="rtl"' % tag)
        self.assertEqual(out.count('<li dir="rtl"'), 2)

    def test_idempotent(self):
        once = run_fix(XHTML)
        self.assertEqual(run_fix(once), once)


class Stylesheets(unittest.TestCase):
    def test_no_direction_properties(self):
        for name in ("epub.css", "epub-ltr.css"):
            css = open(os.path.join(ROOT, "scripts", name), encoding="utf-8").read()
            css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
            self.assertNotRegex(css, r"\b(direction|unicode-bidi)\s*:", name)


if __name__ == "__main__":
    unittest.main()
