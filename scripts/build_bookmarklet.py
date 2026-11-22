#!/usr/bin/env python3
"""Build the browser button (bookmarklet) from browser/epub-me.js.

Usage: build_bookmarklet.py [--check]
Writes browser/bookmarklet.txt: one line, "javascript:" plus the URL-encoded script.
The script is only trimmed (leading block comment, whole-line // comments,
indentation and blank lines); newlines are kept, so no minifier is needed and the
code runs exactly as written. --check exits 1 if bookmarklet.txt is out of date.
"""
import os
import re
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "browser", "epub-me.js")
OUT = os.path.join(ROOT, "browser", "bookmarklet.txt")


def build(src_text):
    code = re.sub(r"\A\s*/\*.*?\*/", "", src_text, count=1, flags=re.S)
    lines = []
    for line in code.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        lines.append(line)
    return "javascript:" + urllib.parse.quote("\n".join(lines), safe="!~*'();,/?:@&=+$")


def main():
    text = build(open(SRC, encoding="utf-8").read()) + "\n"
    if "--check" in sys.argv:
        old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if old != text:
            raise SystemExit("browser/bookmarklet.txt is out of date: run scripts/build_bookmarklet.py")
        return
    open(OUT, "w", encoding="utf-8").write(text)
    print(f"wrote {os.path.relpath(OUT, ROOT)} ({len(text)} chars)")


if __name__ == "__main__":
    main()
