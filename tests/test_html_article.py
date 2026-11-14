import os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import html_article  # noqa: E402

PAGE = b"""<html><head>
<meta name="citation_title" content="A Title: Sub">
<meta name="citation_author" content="Ann One"><meta name="citation_author" content="Bo Two">
</head><body>
<div class="abstract"><p>Abstract text <em>here</em>.</p></div>
<div class="keywords"><h2>Keywords</h2><a>Peace</a><a>War</a></div>
<div class="sec" id="sec1"><h2>Intro</h2>
<p class="p">First claim.<a class="xref fn" href="#fn1"><span class="show-for-sr">Footnote </span><sup>1</sup></a>
 More with * star and [bracket].</p>
<ol><li class="list-item"><p class="p"><span class="label">(i)</span> item one;</p></li></ol>
<p class="p">Second<a class="xref fn" href="#fn2"><sup>2</sup></a> and again<a class="xref fn" href="#fn1"><sup>1</sup></a>.</p>
</div>
<div id="footnotes-list"><h2>Footnotes</h2>
<div id="fn1"><p class="p"><span class="label"><sup>1</sup></span> Note <em>one</em>.</p></div>
<div id="fn2"><p class="p"><span class="label"><sup>2</sup></span> Note two.</p></div>
</div></body></html>"""


class HtmlArticle(unittest.TestCase):
    def build(self, page=PAGE):
        d = tempfile.mkdtemp()
        title, authors, nrefs, stats, nnotes = html_article.build(page, "file:///x.html", d)
        text = open(f"{d}/04_text_fixed/001.md", encoding="utf-8").read()
        return d, title, authors, nrefs, text

    def test_text_notes_and_meta(self):
        _, title, authors, nrefs, text = self.build()
        self.assertEqual(title, "A Title: Sub")
        self.assertEqual(authors, "Ann One, Bo Two")
        self.assertEqual(nrefs, 3)                      # a repeated note is repeated
        self.assertEqual(text.count("[^*]:"), 3)
        self.assertEqual(text.count("[^*]"), 6)         # 3 refs + 3 note starts
        self.assertIn("## Abstract", text)
        self.assertIn("**Keywords:** Peace, War", text)
        self.assertIn("*here*.", text)
        self.assertIn("[^*]: Note *one*.", text)
        self.assertIn("\\* star and \\[bracket\\]", text)
        self.assertIn("(i) item one;", text)
        self.assertNotIn("Footnote ", text)             # screen-reader label dropped

    def test_missing_note_fails(self):
        bad = PAGE.replace(b'<div id="fn2">', b'<div id="zz">')
        with self.assertRaises(SystemExit):
            self.build(bad)

    def test_assembles(self):
        d, *_ = self.build()
        out = subprocess.run([sys.executable, f"{ROOT}/scripts/assemble_book.py",
                              f"{d}/04_text_fixed", f"{d}/book.md"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("3 footnotes", out)


if __name__ == "__main__":
    unittest.main()
