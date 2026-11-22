#!/usr/bin/env python3
"""Library name for a finished book: "Surname - Year - Short title".

Used for both the EPUB file name in Dropbox (books/NAME.epub) and its
dc:title, because the Boox library shows the metadata title.

  one author      Goddard - 2010 - Indivisible Territory
  two authors     Goddard & Pressman / ינון ופרידמן
  three or more   Goddard et al. / שני גולן ואחרים
  no year         Goddard - Indivisible Territory (never guess a year)
  no author       2017 - הילכו השונים יחדיו

The surname is the last word of each author name; pass surnames yourself for
compound ones ("שני גולן"). The short title is the part before ":".

Usage: book_name.py "TITLE" "AUTHOR, AUTHOR" [YEAR] [--surname "S1, S2"] [--short "T"]
"""
import argparse
import re
import sys

HEBREW = re.compile(r"[֐-׿]")
UNSAFE = re.compile(r'[\\/:*?"<>|״“”]')  # not allowed in file names


def surnames(authors):
    return [a.split()[-1] for a in re.split(r",| and | & ", authors) if a.strip()]


def author_part(names, hebrew):
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} ו{names[1]}" if hebrew else f"{names[0]} & {names[1]}"
    return f"{names[0]} ואחרים" if hebrew else f"{names[0]} et al."


def short_title(title):
    t = title.split(":")[0] if ":" in title.strip(":") else title
    t = UNSAFE.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" .,-–—'")


def book_name(title, authors="", year="", surname=None, short=None):
    hebrew = bool(HEBREW.search(title + authors))
    names = [s.strip() for s in surname.split(",")] if surname else surnames(authors)
    parts = [author_part(names, hebrew), str(year or "").strip(),
             short_title(short or title)]
    return " - ".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title")
    ap.add_argument("authors", nargs="?", default="")
    ap.add_argument("year", nargs="?", default="")
    ap.add_argument("--surname")
    ap.add_argument("--short")
    a = ap.parse_args()
    if a.year and not re.fullmatch(r"\d{4}", a.year):
        sys.exit(f"year must be 4 digits: {a.year!r}")
    print(book_name(a.title, a.authors, a.year, a.surname, a.short))


if __name__ == "__main__":
    main()
