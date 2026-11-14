#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block retyping book pages by hand.

Why: a 23-page English scan failed twice with "Output blocked by content
filtering policy" after whole pages were printed and retyped, and retyped
pages are the most expensive tokens in a conversion. Book text must stay in
files made by OCR or scripts and be fixed with small, targeted edits.

When it applies: only to page files, i.e. NNN.md under 04_text_fixed/ or a
text/ folder, and anything under 05_book_md/. Other files are never checked.

  Write  to a page file: blocked when the content is over LIMIT characters
         (a tiny new page such as "+" is fine).
  Edit / MultiEdit on a page file: blocked when old_string or new_string is
         over LIMIT characters. Wrap a box with two short edits (one for
         "::: box", one for ":::") instead of one edit holding the whole box.
  Bash   that names a page location: blocked when the command is over
         BASH_LIMIT characters (a heredoc or python -c holding page text).
         Long replacement lists go in a TSV file for replace_text.py.

LIMIT is 400 and BASH_LIMIT is 1500; EPUBME_EDIT_LIMIT and
EPUBME_BASH_LIMIT override them, and EPUBME_ALLOW_PAGE_WRITES=1 turns the
guard off (only for repo work on the scripts themselves, never in a
conversion). Exit code 2 blocks the call and shows the reason to Claude.
"""
import json
import os
import re
import sys

PAGE_FILE = re.compile(r"(^|/)((04_text_fixed|text)/[^/]*\d{3}\.md|05_book_md/[^/]+\.md)$")
PAGE_LOC = re.compile(r"04_text_fixed|05_book_md|(^|[\s/'\"])text/(\d{3}\.md|\*)")

HOW = ("Keep book text in the OCR/script output and fix it with small edits: "
       "Edit with a short unique anchor, or a TSV for scripts/replace_text.py "
       "(prints counts only). Never retype or print a whole page. "
       "See 'Never retype pages' in docs/low-token-workflow.md.")


def limits():
    env = os.environ
    return int(env.get("EPUBME_EDIT_LIMIT", 400)), int(env.get("EPUBME_BASH_LIMIT", 1500))


def check(event):
    """Return a reason to block, or None."""
    if os.environ.get("EPUBME_ALLOW_PAGE_WRITES") == "1":
        return None
    limit, bash_limit = limits()
    tool = event.get("tool_name", "")
    inp = event.get("tool_input") or {}
    if tool == "Bash":
        cmd = inp.get("command", "")
        if len(cmd) > bash_limit and PAGE_LOC.search(cmd):
            return f"Bash command of {len(cmd)} characters touches page files (limit {bash_limit})."
        return None
    path = inp.get("file_path", "")
    if not PAGE_FILE.search(path.replace("\\", "/")):
        return None
    if tool == "Write":
        n = len(inp.get("content", ""))
        if n > limit:
            return f"Writing {n} characters into page file {path} (limit {limit})."
    elif tool in ("Edit", "MultiEdit"):
        edits = inp.get("edits") or [inp]
        for e in edits:
            n = max(len(e.get("old_string", "")), len(e.get("new_string", "")))
            if n > limit:
                return f"Edit of {n} characters in page file {path} (limit {limit})."
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0  # not a hook event; never block on our own parse error
    reason = check(event)
    if reason:
        print(f"Blocked: {reason} {HOW}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
