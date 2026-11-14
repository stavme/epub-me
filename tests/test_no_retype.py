"""Tests for the never-retype-pages rule: the guard hook and replace_text.py.

Run: python3 -m unittest discover -s tests
A 23-page English scan failed twice with "Output blocked by content filtering
policy" after pages were retyped in model output; the hook blocks that and
replace_text.py fixes page files while printing only short lines.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import guard_page_edits as guard  # noqa: E402
import replace_text  # noqa: E402

GUARD = os.path.join(ROOT, "scripts", "guard_page_edits.py")
PAGE = "/work/book/04_text_fixed/007.md"
LONG = "מילה " * 200  # 1,000 characters, a third of a page


def event(tool, **inp):
    return {"tool_name": tool, "tool_input": inp}


class Guard(unittest.TestCase):
    def setUp(self):
        p = mock.patch.dict(os.environ, {}, clear=False)
        p.start()
        self.addCleanup(p.stop)
        for k in ("EPUBME_ALLOW_PAGE_WRITES", "EPUBME_EDIT_LIMIT", "EPUBME_BASH_LIMIT"):
            os.environ.pop(k, None)

    def test_blocks_writing_a_whole_page(self):
        self.assertTrue(guard.check(event("Write", file_path=PAGE, content=LONG)))

    def test_blocks_project_files_text_folder(self):
        path = "/mnt/project-files/kant/text/012.md"
        self.assertTrue(guard.check(event("Write", file_path=path, content=LONG)))

    def test_blocks_hand_written_book_md(self):
        path = "book/05_book_md/book.md"
        self.assertTrue(guard.check(event("Write", file_path=path, content=LONG)))

    def test_allows_tiny_new_page(self):
        self.assertIsNone(guard.check(event("Write", file_path=PAGE, content="+\n")))

    def test_allows_small_edit_blocks_big_one(self):
        self.assertIsNone(guard.check(event("Edit", file_path=PAGE, old_string="ina", new_string="in a")))
        self.assertTrue(guard.check(event("Edit", file_path=PAGE, old_string="x", new_string=LONG)))
        self.assertTrue(guard.check(event("Edit", file_path=PAGE, old_string=LONG, new_string="x")))

    def test_multiedit_checks_each_edit(self):
        edits = [{"old_string": "a", "new_string": "b"}, {"old_string": "c", "new_string": LONG}]
        self.assertTrue(guard.check(event("MultiEdit", file_path=PAGE, edits=edits)))

    def test_other_files_are_not_checked(self):
        for path in ("scripts/assemble_book.py", "docs/lessons.md", "book/03_queue/fixes.txt",
                     "book/04_text_fixed/uncertain.txt"):
            self.assertIsNone(guard.check(event("Write", file_path=path, content=LONG)), path)

    def test_bash_heredoc_into_pages_is_blocked(self):
        cmd = f"cat > book/04_text_fixed/007.md <<'EOF'\n{LONG}{LONG}\nEOF"
        self.assertTrue(guard.check(event("Bash", command=cmd)))

    def test_bash_short_or_unrelated_is_allowed(self):
        cmd = "python3 scripts/replace_text.py book/04_text_fixed book/fixes.tsv"
        self.assertIsNone(guard.check(event("Bash", command=cmd)))
        self.assertIsNone(guard.check(event("Bash", command="echo " + LONG * 2)))

    def test_override_env(self):
        os.environ["EPUBME_ALLOW_PAGE_WRITES"] = "1"
        self.assertIsNone(guard.check(event("Write", file_path=PAGE, content=LONG)))

    def test_hook_exit_codes(self):
        def run(ev):
            return subprocess.run([sys.executable, GUARD], input=json.dumps(ev), text=True,
                                  capture_output=True)
        r = run(event("Write", file_path=PAGE, content=LONG))
        self.assertEqual(r.returncode, 2)
        self.assertIn("replace_text.py", r.stderr)
        self.assertEqual(run(event("Write", file_path=PAGE, content="+\n")).returncode, 0)

    def test_settings_register_the_hook(self):
        with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as f:
            hooks = json.load(f)["hooks"]["PreToolUse"]
        entry = next(h for h in hooks if "guard_page_edits.py" in h["hooks"][0]["command"])
        for tool in ("Write", "Edit", "MultiEdit", "Bash"):
            self.assertIn(tool, entry["matcher"].split("|"))


class ReplaceText(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.pages = {1: "the cat sat ina box.\n", 2: "| said ina way.\n\nSecond para.\n",
                      3: "word word\n"}
        for p, t in self.pages.items():
            with open(os.path.join(self.dir, f"{p:03d}.md"), "w", encoding="utf-8") as f:
                f.write(t)

    def page(self, p):
        with open(os.path.join(self.dir, f"{p:03d}.md"), encoding="utf-8") as f:
            return f.read()

    def apply(self, tsv, dry_run=False):
        path = os.path.join(self.dir, "fixes.tsv")
        with open(path, "w", encoding="utf-8") as f:
            f.write(tsv)
        out = io.StringIO()
        code = replace_text.run(self.dir, path, dry_run, out)
        return code, out.getvalue()

    def test_page_range_and_star(self):
        code, out = self.apply("*\tina\tin a\n2\t| said\tI said\n")
        self.assertEqual(code, 0)
        self.assertEqual(self.page(1), "the cat sat in a box.\n")
        self.assertEqual(self.page(2), "I said in a way.\n\nSecond para.\n")
        self.assertIn("3 replacements, changed 2 pages, 0 problems", out)

    def test_newline_escape_wraps_a_box(self):
        self.apply("2\tSecond para.\t::: box\\nSecond para.\\n:::\n")
        self.assertIn("::: box\nSecond para.\n:::", self.page(2))

    def test_ambiguous_and_missing_are_reported_not_applied(self):
        code, out = self.apply("3\tword\tWORD\n1-2\tnothing here\tx\n")
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS", out)
        self.assertIn("NOT FOUND", out)
        self.assertEqual(self.page(3), "word word\n")

    def test_all_prefix_replaces_every_occurrence(self):
        self.apply("all:3\tword\tWORD\n")
        self.assertEqual(self.page(3), "WORD WORD\n")

    def test_dry_run_writes_nothing(self):
        self.apply("*\tina\tin a\n", dry_run=True)
        self.assertEqual(self.page(1), self.pages[1])

    def test_output_never_echoes_a_page(self):
        long_line = "x" * 300 + " tail"
        with open(os.path.join(self.dir, "004.md"), "w", encoding="utf-8") as f:
            f.write(long_line)
        _, out = self.apply(f"4\t{long_line}\tshort\n")
        self.assertTrue(all(len(line) < 120 for line in out.splitlines()), out)


if __name__ == "__main__":
    unittest.main()
