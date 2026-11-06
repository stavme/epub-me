#!/usr/bin/env python3
"""Step 0: decide whether a PDF needs OCR at all.

Counts the Hebrew letters in each page's text layer (pdftotext). Pages with
at least --min letters count as "text"; the rest are scans.

  - All (or nearly all) pages are text: the PDF is born-digital. Skip prep,
    OCR, the queue and the helper agent: the text is written straight to
    OUT_DIR/NNN.md, ready for the structure step (headings, footnotes) and
    the EPUB build. Lines are joined into paragraphs; Hebrew that came out in
    visual order (reversed words, final letters at word starts) is flipped.
  - Otherwise: prints "scan" (or "mixed" with the scanned page numbers), and
    the normal OCR pipeline runs.

Usage: check_pdf.py FILE.pdf [OUT_DIR] [--min 200]
Exit code 0 = text written (or text but no OUT_DIR), 1 = scan/mixed.
"""
import argparse
import os
import re
import subprocess
import sys

HEB = re.compile(r"[א-ת]")
FINALS_AT_START = re.compile(r"(?:^|\s)[םןץףך][א-ת]")
FINALS_AT_END = re.compile(r"[א-ת][םןץףך](?:$|[\s.,;:!?])")


def page_count(pdf):
    info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, check=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))


def page_text(pdf, n):
    return subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), "-enc", "UTF-8", pdf, "-"],
                          capture_output=True, text=True, check=True).stdout


BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def fix_order(text):
    """Drop bidi control marks; flip lines whose Hebrew is in visual (reversed) order."""
    text = BIDI.sub("", text)
    if len(FINALS_AT_START.findall(text)) <= len(FINALS_AT_END.findall(text)):
        return text
    return "\n".join(line[::-1] for line in text.splitlines())


def to_paragraphs(text):
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    # bidi reordering can leave ". word" where the print has "word. word"
    paras = [re.sub(r"\s([.,;:!?])(?=[א-ת])", r"\1 ", p) for p in paras]
    return "\n\n".join(p for p in paras if p) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--min", type=int, default=200, help="Hebrew letters for a page to count as text")
    a = ap.parse_args()
    n = page_count(a.pdf)
    texts = [page_text(a.pdf, i) for i in range(1, n + 1)]
    scanned = [i + 1 for i, t in enumerate(texts) if len(HEB.findall(t)) < a.min]
    if len(scanned) > max(1, n // 10):  # a blank or picture page or two is fine
        kind = "scan" if len(scanned) == n else "mixed"
        print(f"{kind}: {len(scanned)}/{n} pages have no text layer -> run the OCR pipeline"
              + (f" (scanned pages: {scanned})" if kind == "mixed" else ""))
        sys.exit(1)
    print(f"text: {n - len(scanned)}/{n} pages have a text layer -> skip OCR")
    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        for i, t in enumerate(texts, 1):
            with open(os.path.join(a.out_dir, f"{i:03d}.md"), "w", encoding="utf-8") as f:
                f.write(to_paragraphs(fix_order(t)))
        print(f"wrote {n} page files to {a.out_dir}; spot-check one page's word order")


if __name__ == "__main__":
    main()
