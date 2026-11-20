import os, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from book_name import book_name  # noqa: E402


class BookName(unittest.TestCase):
    def test_one_author(self):
        self.assertEqual(
            book_name("Indivisible Territory and the Politics of Legitimacy", "Stacie E. Goddard", "2010"),
            "Goddard - 2010 - Indivisible Territory and the Politics of Legitimacy")

    def test_subtitle_dropped_and_et_al(self):
        self.assertEqual(
            book_name("Counter-peace: From isolated blockages", "Sandra Pogodda, Oliver P. Richmond, Gëzim Visoka", "2023"),
            "Pogodda et al. - 2023 - Counter-peace")

    def test_two_authors(self):
        self.assertEqual(book_name("Time", "Stacie E. Goddard, Jeremy Pressman", "2008"),
                         "Goddard & Pressman - 2008 - Time")
        self.assertEqual(book_name("מדוע מצליחים בני הקיבוצים בצבא?", "יואל ינון, נילי פרידמן", "1975"),
                         "ינון ופרידמן - 1975 - מדוע מצליחים בני הקיבוצים בצבא")

    def test_hebrew_many_compound_surname(self):
        self.assertEqual(
            book_name("״אני לא יודעת, בוא תספר לי אתה״: מודל לדיאלוג", "א, ב, ג", surname="שני גולן, יולזרי, שמר"),
            "שני גולן ואחרים - אני לא יודעת, בוא תספר לי אתה")

    def test_no_year_no_author_unsafe_chars(self):
        self.assertEqual(book_name('לויתן — פרק י"ג', "תומס הובס"), "הובס - לויתן — פרק יג")
        self.assertEqual(book_name("הילכו השונים יחדיו? בין רב תרבותיות", "", "2017",
                                   short="הילכו השונים יחדיו"), "2017 - הילכו השונים יחדיו")

    def test_cli_rejects_bad_year(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/book_name.py"), "T", "A B", "c. 1900"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
