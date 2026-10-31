#!/usr/bin/env python3
"""Stage 3 OCR: run two Hebrew models per page and flag where they disagree.

The primary reading comes from tessdata_best heb. A second reading from the
distro (fast) heb model is diffed word by word; disagreements and words with
low confidence are what a human (or Claude) checks against the image.

Output per page in OUT_DIR:
  NNN.txt      primary text
  NNN.tsv      primary word boxes + confidences
  NNN.alt.txt  second-model text
  NNN.flags.txt  primary text with [[primary|alt]] at disagreements and
                 {{word}} at low-confidence words

Usage: ocr_pages.py IN_DIR OUT_DIR --best-tessdata DIR [--psm 6] [--low 70]
"""
import argparse
import csv
import difflib
import os
import subprocess


def tess(img, tessdata, psm, fmt=None):
    cmd = ["tesseract", img, "-", "-l", "heb", "--oem", "1", "--psm", str(psm),
           "--dpi", "300"]
    if tessdata:
        cmd[1:1] = ["--tessdata-dir", tessdata]
    if fmt:
        cmd.append(fmt)
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def low_conf_words(tsv_text, thresh):
    rows = csv.DictReader(tsv_text.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE)
    out = []
    for r in rows:
        if r["level"] == "5" and r["text"].strip():
            out.append((r["text"], float(r["conf"])))
    return out


def flag_line(a_line, b_line, low):
    a, b = a_line.split(), b_line.split()
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.extend("{{%s}}" % w if w in low else w for w in a[i1:i2])
        else:
            out.append("[[%s|%s]]" % (" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--best-tessdata", required=True)
    ap.add_argument("--psm", type=int, default=6)
    ap.add_argument("--low", type=float, default=70)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    for name in sorted(os.listdir(args.in_dir)):
        if not name.endswith(".png"):
            continue
        stem = name[:-4]
        img = os.path.join(args.in_dir, name)
        txt = tess(img, args.best_tessdata, args.psm)
        tsv = tess(img, args.best_tessdata, args.psm, "tsv")
        alt = tess(img, None, args.psm)
        words = low_conf_words(tsv, args.low)
        low = {w for w, c in words if c < args.low}
        a_lines = [l for l in txt.splitlines() if l.strip()]
        b_lines = [l for l in alt.splitlines() if l.strip()]
        # align lines first, then words inside aligned lines
        sm = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)
        flagged, n_dis = [], 0
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                flagged.extend(flag_line(l, l, low) for l in a_lines[i1:i2])
            elif op == "replace" and (i2 - i1) == (j2 - j1):
                for la, lb in zip(a_lines[i1:i2], b_lines[j1:j2]):
                    flagged.append(flag_line(la, lb, low))
            else:
                flagged.extend("[[%s|]]" % l for l in a_lines[i1:i2])
                flagged.extend("[[|%s]]" % l for l in b_lines[j1:j2])
        n_dis = sum(l.count("[[") for l in flagged)
        n_low = sum(l.count("{{") for l in flagged)
        for ext, data in ((".txt", txt), (".tsv", tsv), (".alt.txt", alt),
                          (".flags.txt", "\n".join(flagged) + "\n")):
            with open(os.path.join(args.out_dir, stem + ext), "w") as f:
                f.write(data)
        print(f"{stem}: words={len(words)} disagreements={n_dis} lowconf={n_low}")


if __name__ == "__main__":
    main()
