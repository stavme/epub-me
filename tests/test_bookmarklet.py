import json, os, shutil, subprocess, sys, tempfile, unittest, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_bookmarklet  # noqa: E402


def have_playwright():
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


class Bookmarklet(unittest.TestCase):
    def test_in_sync_with_source(self):
        with open(os.path.join(ROOT, "browser", "epub-me.js"), encoding="utf-8") as f:
            src = f.read()
        with open(os.path.join(ROOT, "browser", "bookmarklet.txt"), encoding="utf-8") as f:
            built = f.read()
        self.assertEqual(built, build_bookmarklet.build(src) + "\n",
                         "run scripts/build_bookmarklet.py after editing browser/epub-me.js")
        self.assertNotIn("#", built)       # '#' would cut a javascript: URL in some browsers

    def test_build_keeps_code_lines(self):
        out = build_bookmarklet.build("/* head */\n  var a = 'x://y'; // c\n  // gone\n\n  b();\n")
        self.assertEqual(out, "javascript:var%20a%20=%20'x://y';%20//%20c%0Ab();")


# CI sets REQUIRE_BROWSER_TESTS=1 so these fail instead of skipping there
@unittest.skipUnless(have_playwright() or os.environ.get("REQUIRE_BROWSER_TESTS") == "1",
                     "needs node with playwright")
class BookmarkletInBrowser(unittest.TestCase):
    def run_page(self, page, *mode):
        out = os.path.join(tempfile.mkdtemp(), "out.epub")
        r = subprocess.run(["node", os.path.join(ROOT, "tests", "bookmarklet_e2e.js"), page, out, *mode],
                           capture_output=True, text=True, timeout=180)
        self.assertEqual(r.returncode, 0, r.stderr)
        z = zipfile.ZipFile(out)
        return json.loads(r.stdout.strip().splitlines()[-1]), z

    def test_cambridge_layout(self):
        s, z = self.run_page("cambridge.html")
        first = z.infolist()[0]
        self.assertEqual((first.filename, first.compress_type), ("mimetype", zipfile.ZIP_STORED))
        self.assertEqual(z.testzip(), None)
        self.assertEqual((s["notes"], s["figures"], s["lostFigures"], s["rtl"]), (2, 1, 1, False))
        t = z.read("EPUB/text.xhtml").decode()
        self.assertEqual(t.count('epub:type="noteref"'), 3)        # note 1 cited twice
        self.assertEqual(t.count('epub:type="footnote"'), 2)
        self.assertIn('<p class="byline">Ann One, Bo Two</p>', t)
        self.assertIn("<strong>Keywords:</strong> Peace, War", t)
        self.assertIn('<ul class="labelled">', t)                   # "(i)" items get no second number
        self.assertIn("<em>book title</em>", t)
        self.assertIn('src="img/fig1.png"', t)
        self.assertIn("[Figure not downloaded]", t)
        self.assertIn("<th>Level</th>", t)
        for gone in ("Footnote", "Information", "Cookie", "Login"):
            self.assertNotIn(gone, t)
        nav = z.read("EPUB/nav.xhtml").decode()
        self.assertIn('<ol><li><a href="text.xhtml#s3">A subsection</a></li></ol>', nav)
        opf = z.read("EPUB/content.opf").decode()
        self.assertIn("<dc:creator>Ann One, Bo Two</dc:creator>", opf)
        self.assertNotIn("page-progression-direction", opf)
        # library name, as scripts/book_name.py: surnames, year, title before ":"
        self.assertIn("<dc:title>One &amp; Two - 2023 - A Test Article</dc:title>", opf)
        self.assertEqual(s["name"], "One & Two - 2023 - A Test Article.epub")

    def test_hebrew_generic_page(self):
        s, z = self.run_page("hebrew.html")
        self.assertEqual((s["notes"], s["figures"], s["rtl"]), (2, 1, True))
        t = z.read("EPUB/text.xhtml").decode()
        self.assertIn('lang="he"', t)
        self.assertIn('dir="rtl"', t.split("<head>")[0])
        self.assertIn('<li dir="rtl">', t)
        self.assertIn("<p>טקסט חופשי בתוך div בלי פסקה.</p>", t)
        self.assertNotIn("↩", t)
        self.assertNotIn("דף הבית", t)
        self.assertEqual(t.count("<h1"), 1)                         # page h1 is the title
        opf = z.read("EPUB/content.opf").decode()
        self.assertIn('page-progression-direction="rtl"', opf)
        self.assertIn("<dc:title>ישראלי - הילכו שניים יחדיו</dc:title>", opf)  # no date: no year

    def test_wordpress_post(self):
        s, z = self.run_page("wordpress.html")
        t = z.read("EPUB/text.xhtml").decode()
        opf = z.read("EPUB/content.opf").decode()
        self.assertIn("<dc:title>כותבת - 2025 - כותרת המאמר</dc:title>", opf)  # site name dropped
        self.assertIn('<h1 id="title">כותרת המאמר</h1>', t)          # the page keeps the full title
        self.assertIn("<dc:creator>ישראלה כותבת</dc:creator>", opf)  # bold first line, not the login
        self.assertNotIn("wsr_site", t + opf)
        self.assertEqual(t.count("ישראלה כותבת"), 1)                 # only as the byline
        heads = [(h, x) for h, x in __import__("re").findall(r"<h([23]) id=\"s\d+\">([^<]+)<", t)]
        self.assertEqual(heads, [("2", "פתיחה"), ("3", "כותרת משנה"), ("2", "חלק א'"),
                                 ("3", "נושא ראשון"), ("3", "נושא שני")])
        self.assertIn("<p>משפט קצר שנגמר בנקודה.</p>", t)
        self.assertIn('<span class="missing">', t)                  # lost inline image: no <p> in <p>
        for gone in (">מאמר<", "•", "שיתוף", "פוסט אחר"):
            self.assertNotIn(gone, t)

    def test_iphone_uses_share_sheet(self):
        # iPhone Safari names blob downloads with a random id, so the box offers Share
        s, z = self.run_page("hebrew.html", "ios")
        self.assertEqual(s["shared"], {"name": "ישראלי - הילכו שניים יחדיו.epub", "type": "application/epub+zip"})
        self.assertEqual(z.infolist()[0].filename, "mimetype")


if __name__ == "__main__":
    unittest.main()
