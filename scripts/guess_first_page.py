#!/usr/bin/env python3
"""Guess --first-page (the printed page number of page file 001) for a scan.

review_queue.py writes the page numbers it drops to 03_queue/headers.txt as
"NNN<TAB>text". Each line that is only a number votes for number - NNN + 1;
the most common vote wins if at least 3 pages agree and they are a majority
of the votes. Prints the number, or nothing (exit 1) when the evidence is weak.

Usage: guess_first_page.py BOOK/03_queue/headers.txt
"""
import collections
import re
import sys


def guess(lines):
    votes = collections.Counter()
    for ln in lines:
        stem, _, text = ln.rstrip("\n").partition("\t")
        m = re.fullmatch(r"\s*(\d{1,4})\s*", text)
        if re.fullmatch(r"\d{3}", stem) and m:
            votes[int(m.group(1)) - int(stem) + 1] += 1
    if not votes:
        return None
    first, n = votes.most_common(1)[0]
    if n >= 3 and n * 2 > sum(votes.values()) and first >= 1:
        return first
    return None


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        g = guess(fh)
    if g is None:
        sys.exit(1)
    print(g)
