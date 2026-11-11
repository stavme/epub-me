#!/usr/bin/env python3
"""Checks for English page files (born-digital or OCR): the slips Stav found in Hofstede.

  - a lone "|" or "l"/"1" where "I" is meant:  "What | have", "| think"
  - two words glued together:  "ina" for "in a", "ofthe", "tothe" (needs hunspell en_US;
    without it only the short list below is checked)
  - running headers that slipped through: a line that repeats on many page files
  - leftover table cells: " | " outside real tables

Usage: check_en.py TEXT_DIR            Exit code 0 always: a review list, not a gate.
"""
import collections
import os
import re
import shutil
import subprocess
import sys

GLUE = {"ina", "ofthe", "tothe", "inthe", "onthe", "forthe", "andthe", "isa", "ofa", "toa", "asa", "atthe", "bythe", "withthe"}


def main():
    d = sys.argv[1]
    files = sorted(f for f in os.listdir(d) if f.endswith(".md"))
    seen = collections.Counter()
    text = {}
    for f in files:
        t = open(os.path.join(d, f), encoding="utf-8").read()
        text[f] = t
        for line in set(t.splitlines()):
            if len(line) > 12 and not line.startswith("|"):
                seen[re.sub(r"\d+", "#", line.strip())] += 1
    for line, c in seen.items():
        if c >= max(3, len(files) * 0.4):
            print(f"header?\t{c} pages\t{line[:70]}")
    words = set()
    for f, t in text.items():
        for i, line in enumerate(t.splitlines(), 1):
            if line.startswith("|"):
                continue
            for m in re.finditer(r"(?<![|\\])\s\|\s|\s\|(?=[a-z])", line):
                print(f"pipe\t{f}:{i}\t…{line[max(0, m.start() - 25):m.end() + 25]}…")
            for m in re.finditer(r"[A-Za-z]+", line):
                w = m.group().lower()
                if w in GLUE:
                    print(f"glued\t{f}:{i}\t…{line[max(0, m.start() - 25):m.end() + 25]}…")
                words.add(w)
    if shutil.which("hunspell"):
        r = subprocess.run(["hunspell", "-d", "en_US", "-l"], input="\n".join(sorted(words)), capture_output=True, text=True)
        bad = set(r.stdout.split())
        for w in sorted(bad):
            for i in range(1, len(w)):  # unknown word that is two known words: "ina" -> "in a"
                if w[:i] not in bad and w[i:] not in bad and (i >= 2 or w[:i] in ("a", "i")) and (len(w) - i >= 2 or w[i:] in ("a", "i")):
                    print(f"glued?\t{w}\t{w[:i]} {w[i:]}")
                    break
    else:
        print("note: hunspell not installed, glued-word check is the short list only")


if __name__ == "__main__":
    main()
