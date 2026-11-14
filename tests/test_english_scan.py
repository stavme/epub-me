"""English scans (retro on the three English PDFs, 2026-11-12): left-to-right
order everywhere, scanner-app PDFs treated as scans, Dropbox fetch by name."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import check_pdf  # noqa: E402
import dropbox_fetch  # noqa: E402

try:  # numpy + Pillow; CI may not have them
    import ocr_regions
    import review_queue
except ImportError:
    ocr_regions = review_queue = None
needs_imaging = unittest.skipIf(review_queue is None, "numpy/Pillow missing")


def word(text, x0, x1, line=(1, 1, 1), y=0):
    return {"text": text, "box": (x0, y, x1, y + 20), "line": line, "conf": 90}


@needs_imaging
class ReadingOrder(unittest.TestCase):
    def test_columns(self):
        left, right = (0, 0, 300, 100), (700, 0, 1000, 100)
        self.assertEqual(ocr_regions.reading_order([left, right], 1000), [right, left])
        self.assertEqual(ocr_regions.reading_order([right, left], 1000, rtl=False), [left, right])


@needs_imaging
class ReviewQueueDirection(unittest.TestCase):
    def tearDown(self):
        review_queue.set_lang("heb")

    def test_words_left_to_right_in_english(self):
        ws = [word("world", 120, 200), word("Hello", 10, 100)]
        review_queue.set_lang("eng")
        self.assertEqual([w["text"] for w in review_queue.lines_of(ws)[0]["words"]], ["Hello", "world"])
        review_queue.set_lang("heb")
        self.assertEqual([w["text"] for w in review_queue.lines_of(ws)[0]["words"]], ["world", "Hello"])

    def test_english_paragraphs(self):
        # full line, short last line, then an indented new paragraph
        lines = [{"box": (0, 0, 1000, 20)}, {"box": (0, 30, 400, 50)}, {"box": (80, 60, 1000, 80)},
                 {"box": (0, 90, 1000, 110)}]
        review_queue.set_lang("eng")
        self.assertEqual([len(p) for p in review_queue.paragraphs(lines, 1000)], [2, 2])

    def test_letters_follow_language(self):
        review_queue.set_lang("eng")
        self.assertEqual(review_queue.letters("Page 13"), "Page")
        review_queue.set_lang("heb")
        self.assertEqual(review_queue.letters("Page 13"), "")


class SpreadOrder(unittest.TestCase):
    def test_left_page_first_with_ltr(self):
        try:
            import numpy as np
            import prep_pages
        except ImportError:
            self.skipTest("cv2/numpy missing")
        gray = np.zeros((10, 20), dtype=np.uint8)
        self.assertEqual([s for s, _ in prep_pages.spread_halves(gray, 10)], ["right", "left"])
        self.assertEqual([s for s, _ in prep_pages.spread_halves(gray, 10, ltr=True)], ["left", "right"])


class ScannerAppPdf(unittest.TestCase):
    def test_full_page_picture_is_a_scan_despite_text_layer(self):
        text = "x" * 500
        self.assertEqual(check_pdf.scan_pages([text, text], [0.99, 0.1], 200), [1])
        self.assertEqual(check_pdf.scan_pages([text, ""], [], 200), [2])


class DropboxPick(unittest.TestCase):
    files = [{"name": "a.pdf"}, {"name": "b.pdf"}]

    def test_by_name(self):
        self.assertEqual(dropbox_fetch.pick(self.files, "b.pdf"), [{"name": "b.pdf"}])
        self.assertIsInstance(dropbox_fetch.pick(self.files, "c.pdf"), str)

    def test_refuses_several_without_name(self):
        self.assertIsInstance(dropbox_fetch.pick(self.files, None), str)
        self.assertEqual(dropbox_fetch.pick(self.files[:1], None), self.files[:1])
        self.assertIsInstance(dropbox_fetch.pick([], None), str)


if __name__ == "__main__":
    unittest.main()
