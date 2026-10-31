#!/usr/bin/env python3
"""Stage 4: automated checks on corrected Hebrew page files.

Usage: check_text.py TEXT_DIR [--hunspell he_IL] [--first-page 23]

Reports one line per finding: page, check, snippet. Exit code 0 always;
this is a review queue, not a gate.
"""
import argparse
import collections
import os
import re
import subprocess
import unicodedata

HEB = "א-ת"
FINALS = "ךםןףץ"
NONFINAL_OF = {"כ": "ך", "מ": "ם", "נ": "ן", "פ": "ף", "צ": "ץ"}
WORD = re.compile(rf"[{HEB}־'\"״׳]+")


def strip_markup(s):
    s = re.sub(r"\[\^[*+]\]:?", "", s)
    s = re.sub(r"^#+ ", "", s, flags=re.M)
    return s.replace("*", "")


def heb_words(s):
    for m in WORD.finditer(s):
        for part in m.group().split("־"):
            yield part


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text_dir")
    ap.add_argument("--hunspell", default="he_IL")
    ap.add_argument("--first-page", type=int, default=1)
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.text_dir) if f.endswith(".md"))
    findings = []
    all_words = collections.Counter()
    word_pages = collections.defaultdict(set)
    refs = defs = 0

    def add(page, check, snippet):
        findings.append((page, check, snippet))

    lengths = {}
    for f in files:
        page = args.first_page + int(f[:3]) - 1
        raw = open(os.path.join(args.text_dir, f), encoding="utf-8").read()
        if unicodedata.normalize("NFC", raw) != raw:
            add(page, "not-NFC", "")
        refs += raw.count("[^*]") - raw.count("[^*]:")
        defs += raw.count("[^*]:")
        text = strip_markup(raw)
        lengths[page] = len(text.split())
        for m in re.finditer(rf"[{HEB}][{FINALS}][{HEB}]", text):
            add(page, "final-letter-mid-word", text[max(0, m.start()-8):m.end()+8])
        for w in heb_words(text):
            core = w.strip("'\"״׳")
            if not core or "'" in w or '"' in w or "״" in w or "׳" in w:
                pass
            elif len(core) > 1 and core[-1] in NONFINAL_OF:
                add(page, "nonfinal-at-word-end", w)
            all_words[core] += 1
            word_pages[core].add(page)
        for m in re.finditer(rf"[{HEB}][A-Za-z0-9]|[A-Za-z0-9][{HEB}]", text):
            add(page, "latin-or-digit-touching-hebrew", text[max(0, m.start()-8):m.end()+8])
        for m in re.finditer(rf"[{HEB}]-[{HEB}]", text):
            add(page, "hyphen-not-maqaf", text[max(0, m.start()-8):m.end()+8])
        for m in re.finditer(r"\b(\S+) \1\b", text):
            add(page, "doubled-word", m.group())
        for m in re.finditer(rf"(?<![{HEB}'])[{HEB}](?![{HEB}'\"])", text):
            ch = m.group()
            if ch not in "וה":  # single ו/ה can be legit only rarely; flag the rest
                add(page, "lone-letter", text[max(0, m.start()-8):m.end()+8])
        if re.search(r"[^\s\w.,;:!?()\[\]\"'״׳—\-־*^+…%/]", text.replace("־", "")):
            odd = set(re.findall(r"[^\s\w.,;:!?()\[\]\"'״׳—\-־*^+…%/]", text))
            add(page, "unusual-chars", " ".join(sorted(odd)))
        if text.count('"') % 2:
            add(page, "odd-number-of-quotes", "")
        if re.search(r"\s[,.;:]", text):
            for m in re.finditer(r"\S+\s[,.;:]", text):
                add(page, "space-before-punct", m.group())

    # parentheses balance across the whole book (pages can split a parenthesis)
    book = "".join(strip_markup(open(os.path.join(args.text_dir, f)).read()) for f in files)
    for o, c in ("()", "[]"):
        if book.count(o) != book.count(c):
            add("book", "unbalanced", f"{o}{c}: {book.count(o)} vs {book.count(c)}")
    if refs != defs:
        add("book", "footnote-ref-def-mismatch", f"refs={refs} defs={defs}")

    # unusually short/long pages
    vals = sorted(lengths.values())
    med = vals[len(vals) // 2]
    for p, n in lengths.items():
        if n < med * 0.4 or n > med * 1.6:
            add(p, "unusual-length", f"{n} words (median {med})")

    # dictionary check, try with common prefixes stripped
    try:
        words = sorted(all_words)
        out = subprocess.run(["hunspell", "-d", args.hunspell, "-l"], input="\n".join(words),
                             capture_output=True, text=True).stdout.split()
        unknown = set(out)
        for w in sorted(unknown, key=lambda w: -all_words[w]):
            stripped = re.sub(r"^[ובלכמשה]{1,3}", "", w)
            if stripped != w and stripped not in unknown and stripped in all_words:
                continue
            add(",".join(map(str, sorted(word_pages[w]))), "not-in-dictionary", w)
    except FileNotFoundError:
        add("book", "hunspell-missing", "")

    for page, check, snip in findings:
        print(f"{page}\t{check}\t{snip}")


if __name__ == "__main__":
    main()
