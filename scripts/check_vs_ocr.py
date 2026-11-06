#!/usr/bin/env python3
"""Cross-check corrected page files against raw OCR, word by word.

For each page, lists words in the corrected text (04_text_fixed/NNN.md) that
do not occur in the OCR output (03_ocr/NNN.txt) and are not within one edit of
any OCR word. These are either OCR misses (fine) or transcription typos (fix).
Usage: check_vs_ocr.py FIXED_DIR OCR_DIR [--map page_map.json]
"""
import os, re, sys

WORD = re.compile(r"[א-ת][א-ת\"'״׳]*[א-ת]|[A-Za-z]{3,}")

def words(t):
    t = re.sub(r"\(img/[^)]*\)|\{[^}]*\}|\[\^\*\]:?", " ", t)
    return [w.replace("״", '"') for w in WORD.findall(t)]

def near(w, vocab):
    if w in vocab: return True
    for i in range(len(w) + 1):
        for v in (w[:i] + w[i + 1:],):  # deletion
            if v in vocab: return True
    return any(len(v) == len(w) and sum(a != b for a, b in zip(v, w)) <= 1 or
               len(v) == len(w) + 1 and any(v[:i] + v[i + 1:] == w for i in range(len(v)))
               for v in vocab if abs(len(v) - len(w)) <= 1)

def main():
    fixed, ocr = sys.argv[1], sys.argv[2]
    total = 0
    for name in sorted(os.listdir(fixed)):
        if not name.endswith(".md"): continue
        stem = name[:-3]
        op = os.path.join(ocr, stem + ".txt")
        if not os.path.exists(op): continue
        vocab = set(words(open(op, encoding="utf-8").read()))
        bad = [w for w in dict.fromkeys(words(open(os.path.join(fixed, name), encoding="utf-8").read()))
               if len(w) >= 3 and not near(w, vocab)]
        total += len(bad)
        if bad: print(stem, " ".join(bad))
    print("total", total, file=sys.stderr)

if __name__ == "__main__":
    main()
