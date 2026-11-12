#!/usr/bin/env python3
"""Stage 3 OCR with per-region deskew (needs only numpy + Pillow + tesseract).

Phone photos of a book page bend: the main column, the margin-note column and
framed boxes often sit at slightly different angles. Deskewing the whole page
leaves some regions tilted, which hurts OCR. So:

  1. Tesseract layout pass (psm 3) on the page -> text blocks (block_num bbox).
  2. Merge overlapping/adjacent blocks of the same column.
  3. Each block is cropped with padding, deskewed on its own (projection
     variance search), and OCR'd with psm 6.

Output per page in OUT_DIR:
  NNN.txt       blocks in reading order (right column first), separated by
                "=== block i x0,y0,x1,y1 skew=a ===" lines
  NNN.regions.json  block boxes + skew angles

Usage: ocr_regions.py IN_DIR OUT_DIR [--tessdata DIR] [--lang heb+eng]
"""
import argparse
import csv
import io
import json
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageFilter, ImageOps


def tess(path, psm, tessdata, lang, fmt=None):
    cmd = ["tesseract", path, "-", "-l", lang, "--oem", "1", "--psm", str(psm), "--dpi", "300"]
    if tessdata:
        cmd[1:1] = ["--tessdata-dir", tessdata]
    if fmt:
        cmd.append(fmt)
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def normalize(gray):
    """Flatten lighting and fade bleed-through: divide by blurred background."""
    a = np.asarray(gray, dtype=np.float32)
    bg = np.asarray(gray.filter(ImageFilter.GaussianBlur(25)), dtype=np.float32)
    n = np.clip(a / np.maximum(bg, 1) * 255, 0, 255)
    # push light grey (show-through) to white
    n = np.clip((n - 120) * (255 / (235 - 120)), 0, 255)
    return Image.fromarray(n.astype(np.uint8))


def otsu(a):
    hist = np.bincount(a.ravel(), minlength=256).astype(float)
    p = hist / hist.sum()
    w = np.cumsum(p)
    mu = np.cumsum(p * np.arange(256))
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (mu[-1] * w - mu) ** 2 / (w * (1 - w))
    return int(np.nanargmax(s))


def skew_angle(img, max_deg=5.0, step=0.1):
    small = img.resize((max(1, img.width // 2), max(1, img.height // 2)))
    a = np.asarray(small)
    ink = Image.fromarray(((a < otsu(a)) * 255).astype(np.uint8))
    best, best_a = -1.0, 0.0
    for ang in np.arange(-max_deg, max_deg + 1e-9, step):
        r = np.asarray(ink.rotate(float(ang), resample=Image.NEAREST, fillcolor=0))
        s = float(np.var(r.sum(axis=1)))
        if s > best:
            best, best_a = s, float(ang)
    return round(best_a, 2)


def layout_blocks(path, tessdata, lang):
    tsv = tess(path, 3, tessdata, lang, "tsv")
    rows = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    boxes = {}
    for r in rows:
        if r["level"] != "5" or not r["text"].strip():
            continue
        b = int(r["block_num"])
        x, y, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
        x0, y0, x1, y1 = boxes.get(b, (x, y, x + w, y + h))
        boxes[b] = (min(x0, x), min(y0, y), max(x1, x + w), max(y1, y + h))
    return list(boxes.values())


def merge(boxes, gap=40):
    """Merge boxes that overlap horizontally a lot and are vertically close."""
    boxes = sorted(boxes, key=lambda b: (b[1], -b[2]))
    changed = True
    while changed:
        changed = False
        out = []
        for b in boxes:
            for i, o in enumerate(out):
                hov = min(b[2], o[2]) - max(b[0], o[0])
                if hov > 0.6 * min(b[2] - b[0], o[2] - o[0]) and b[1] - o[3] < gap and o[1] - b[3] < gap:
                    out[i] = (min(b[0], o[0]), min(b[1], o[1]), max(b[2], o[2]), max(b[3], o[3]))
                    changed = True
                    break
            else:
                out.append(b)
        boxes = out
    return boxes


def reading_order(boxes, width, rtl=True):
    """Sort blocks by column, then top. Hebrew (rtl): right column first;
    English (rtl=False): left column first."""
    def key(b):
        col = round((b[0] + b[2]) / 2 / (width / 3))
        return (-col if rtl else col, b[1])
    return sorted(boxes, key=key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--tessdata")
    ap.add_argument("--lang", default="heb+eng")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    for name in sorted(os.listdir(args.in_dir)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in (".png", ".jpg", ".jpeg", ".tif") or (args.only and stem not in args.only):
            continue
        gray = ImageOps.grayscale(Image.open(os.path.join(args.in_dir, name)))
        norm = normalize(gray)
        with tempfile.TemporaryDirectory() as td:
            pp = os.path.join(td, "p.png")
            norm.save(pp)
            boxes = reading_order(merge(layout_blocks(pp, args.tessdata, args.lang)), norm.width,
                                  rtl=args.lang.startswith("heb"))
            parts, meta = [], []
            for i, (x0, y0, x1, y1) in enumerate(boxes):
                if (x1 - x0) * (y1 - y0) < 4000:
                    continue
                pad = 30
                crop = norm.crop((max(0, x0 - pad), max(0, y0 - pad), min(norm.width, x1 + pad), min(norm.height, y1 + pad)))
                a = skew_angle(crop)
                if abs(a) >= 0.1:
                    crop = crop.rotate(a, resample=Image.BICUBIC, expand=True, fillcolor=255)
                cp = os.path.join(td, f"b{i}.png")
                crop.save(cp)
                txt = tess(cp, 6, args.tessdata, args.lang).strip()
                if not txt:
                    continue
                parts.append(f"=== block {i} {x0},{y0},{x1},{y1} skew={a} ===\n{txt}")
                meta.append({"box": [x0, y0, x1, y1], "skew": a})
        with open(os.path.join(args.out_dir, stem + ".txt"), "w") as f:
            f.write("\n\n".join(parts) + "\n")
        with open(os.path.join(args.out_dir, stem + ".regions.json"), "w") as f:
            json.dump(meta, f)
        print(stem, len(meta), "blocks", [m["skew"] for m in meta], flush=True)


if __name__ == "__main__":
    main()
