#!/usr/bin/env python3
"""Flatten curved pages before OCR, page by page, only where it helps.

A book photographed open bends its lines near the spine; per-block deskew
can't straighten that. page-dewarp (pip) fits the page curve and writes a
flattened black-and-white page. It halves the errors on curved pages but
loses words on flat ones, so each page is judged by OCR + hunspell:

  1. OCR the page; pages with few unknown words (< --try-rate) are left alone.
  2. Otherwise flatten it, OCR again, and keep the flat version only when the
     unknown words drop by at least --gain (relative) and it keeps at least
     --keep-words of the words (page-dewarp crops margins).

A replaced page is kept as IN_DIR/orig/NNN.png. One line per page goes to
stdout and to OUT_LOG (default IN_DIR/../dewarp.txt).
Run on 02_pages_ocr (what review_queue reads); 02_pages stays as scanned.

Usage: dewarp_pages.py IN_DIR [--lang eng] [--try-rate 0.03] [--gain 0.3]
       [--keep-words 0.85] [--jobs 4]
"""
import argparse
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import tempfile

DICTS = {"eng": "en_US", "heb": "he_IL"}
WORD = {"eng": re.compile(r"^[A-Za-z]{2,}$"), "heb": re.compile(r"^[א-ת\"'־]{2,}$")}


def score(img, lang):
    """(words, unknown words) of one OCR'd page."""
    env = dict(os.environ, OMP_THREAD_LIMIT="1")  # parallel tesseracts crawl without it
    text = subprocess.run(["tesseract", img, "-", "-l", lang, "--psm", "3"], capture_output=True,
                          text=True, env=env).stdout
    words = [w.strip(".,;:!?()[]\"'“”‘’—-") for w in text.split()]
    words = [w for w in words if WORD[lang].match(w)]
    unknown = subprocess.run(["hunspell", "-i", "utf-8", "-d", DICTS[lang], "-l"], input="\n".join(words),
                             capture_output=True, text=True).stdout.split()
    return len(words), len(unknown)


def choose(orig, flat, try_rate=0.03, gain=0.3, keep_words=0.85):
    """True when the flattened page should replace the original.
    orig/flat are (words, unknown); flat may be None (not tried or failed)."""
    ow, ou = orig
    if not flat or not ow or ou / ow < try_rate:
        return False
    fw, fu = flat
    return fw >= keep_words * ow and fu <= (1 - gain) * ou


def flatten(img, tmp):
    stem = os.path.splitext(os.path.basename(img))[0]
    subprocess.run(["page-dewarp", "-o", tmp, img], capture_output=True, env=dict(os.environ, OMP_THREAD_LIMIT="1"))
    out = os.path.join(tmp, stem + "_thresh.png")
    return out if os.path.exists(out) else None


def page(img, a, tmp):
    orig = score(img, a.lang)
    flat_img, flat = None, None
    if orig[0] and orig[1] / orig[0] >= a.try_rate:
        flat_img = flatten(img, tmp)
        flat = score(flat_img, a.lang) if flat_img else None
    use = choose(orig, flat, a.try_rate, a.gain, a.keep_words)
    return img, orig, flat, flat_img if use else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_dir")
    ap.add_argument("--lang", default="eng", choices=sorted(DICTS))
    ap.add_argument("--try-rate", type=float, default=0.03, help="unknown-word share that makes a page a candidate")
    ap.add_argument("--gain", type=float, default=0.3, help="relative drop in unknown words needed")
    ap.add_argument("--keep-words", type=float, default=0.85, help="share of words the flat page must keep")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--log")
    a = ap.parse_args()
    if not shutil.which("page-dewarp"):
        sys.exit("page-dewarp not installed (pip install page-dewarp); pages left as they are")
    pages = sorted(os.path.join(a.in_dir, f) for f in os.listdir(a.in_dir) if f.endswith(".png"))
    log = a.log or os.path.join(os.path.dirname(os.path.abspath(a.in_dir)), "dewarp.txt")
    lines, n = [], 0
    with tempfile.TemporaryDirectory() as tmp, concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        for img, orig, flat, use in ex.map(lambda p: page(p, a, tmp), pages):
            name = os.path.basename(img)
            if use:
                os.makedirs(os.path.join(a.in_dir, "orig"), exist_ok=True)
                shutil.move(img, os.path.join(a.in_dir, "orig", name))
                shutil.copy(use, img)
                n += 1
            what = "flattened" if use else ("kept" if flat else "flat enough" if orig[0] else "no text")
            lines.append(f"{name}\t{what}\twords/unknown {orig[0]}/{orig[1]}"
                         + (f" -> {flat[0]}/{flat[1]}" if flat else ""))
    with open(log, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"dewarp: {n}/{len(pages)} pages flattened (details in {log})")


if __name__ == "__main__":
    main()
