import os, shutil, subprocess, tempfile, unittest, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
class EnglishBuildEmbedsFonts(unittest.TestCase):
    def test_fonts_embedded_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(f"{d}/04_text_fixed")
            os.makedirs(f"{d}/05_book_md")
            os.makedirs(f"{d}/fonts")
            open(f"{d}/fonts/Test.ttf", "wb").write(b"\0" * 16)
            open(f"{d}/04_text_fixed/001.md", "w").write("## Title\n\nHello world.\n")
            open(f"{d}/05_book_md/meta.yaml", "w").write(
                '{"title": "T", "lang": "en", "dir": "ltr"}\n')
            subprocess.run([f"{ROOT}/scripts/build_epub.sh", d, "t", "1"],
                           check=True, capture_output=True)
            names = zipfile.ZipFile(f"{d}/06_epub/t.epub").namelist()
            self.assertTrue(any(n.endswith("fonts/Test.ttf") for n in names), names)


if __name__ == "__main__":
    unittest.main()
