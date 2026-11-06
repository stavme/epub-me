#!/usr/bin/env python3
"""Stage 1 page prep: split spreads (right page first), deskew, crop, clean.

Input: a directory of upright page images (already rotated to reading orientation).
Output: 02_pages/NNN.png (grayscale, for review/comparison),
        02_pages_ocr/NNN.png (background-normalized, for OCR),
        pages.json manifest.

Usage: prep_pages.py IN_DIR OUT_ROOT [--spread-ratio 1.2]
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np


def ink_mask(gray):
    # Otsu threshold, ink = 1
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


def find_gutter(gray):
    """Column with least ink inside the middle 40%..60% band, smoothed."""
    h, w = gray.shape
    bw = ink_mask(gray)
    # ignore top/bottom 5% (scanner shadows)
    prof = bw[int(h * 0.05):int(h * 0.95)].sum(axis=0).astype(float)
    k = max(5, w // 100)
    prof = np.convolve(prof, np.ones(k) / k, mode="same")
    lo, hi = int(w * 0.40), int(w * 0.60)
    return lo + int(np.argmin(prof[lo:hi]))


def skew_angle(gray, max_deg=6.0, step=0.1):
    """Angle that maximizes the variance of the horizontal ink profile."""
    bw = ink_mask(gray)
    small = cv2.resize(bw, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    h, w = small.shape
    c = (w / 2, h / 2)
    best, best_a = -1, 0.0
    for a in np.arange(-max_deg, max_deg + 1e-9, step):
        m = cv2.getRotationMatrix2D(c, a, 1.0)
        r = cv2.warpAffine(small, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        s = np.var(r.sum(axis=1).astype(float))
        if s > best:
            best, best_a = s, float(a)
    return round(best_a, 2)


def rotate(gray, a):
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def content_bbox(gray, pad=40):
    """Bounding box of real content; drops thin edge artifacts (shadows, gutter lines)."""
    bw = ink_mask(gray)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    h, w = bw.shape
    # dilate to join letters into blocks, then keep blocks that are not hugging the edge
    blobs = cv2.dilate(bw, np.ones((25, 25), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(blobs)
    xs, ys, xe, ye = [], [], [], []
    for i in range(1, n):
        x, y, bw_, bh, area = st[i]
        if area < 1500:
            continue
        # long thin strips on the border are scan shadows
        thin_vertical = bw_ < w * 0.03 and bh > h * 0.3
        thin_horizontal = bh < h * 0.02 and bw_ > w * 0.5 and (y < h * 0.04 or y + bh > h * 0.96)
        touches = x <= 2 or y <= 2 or x + bw_ >= w - 2 or y + bh >= h - 2
        if (thin_vertical or thin_horizontal) and touches:
            continue
        xs.append(x); ys.append(y); xe.append(x + bw_); ye.append(y + bh)
    if not xs:
        return 0, 0, w, h
    return (max(0, min(xs) - pad), max(0, min(ys) - pad),
            min(w, max(xe) + pad), min(h, max(ye) + pad))


def normalize_bg(gray):
    """Flatten uneven lighting: divide by a heavily blurred background."""
    bg = cv2.medianBlur(gray, 51)
    norm = cv2.divide(gray, bg, scale=255)
    return norm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_dir")
    ap.add_argument("out_root")
    ap.add_argument("--spread-ratio", type=float, default=1.2)
    ap.add_argument("--gutter", nargs="*", default=[], metavar="FILE=X",
                    help="override the split column for a spread, e.g. 3.jpg=987")
    args = ap.parse_args()

    out_rev = os.path.join(args.out_root, "02_pages")
    out_ocr = os.path.join(args.out_root, "02_pages_ocr")
    os.makedirs(out_rev, exist_ok=True)
    os.makedirs(out_ocr, exist_ok=True)

    gut_over = {k: int(v) for k, v in (g.split("=") for g in args.gutter)}
    manifest = []
    seq = 0
    for name in sorted(os.listdir(args.in_dir)):
        if not name.lower().endswith((".png", ".tif", ".tiff", ".jpg")):
            continue
        gray = cv2.imread(os.path.join(args.in_dir, name), cv2.IMREAD_GRAYSCALE)
        h, w = gray.shape
        if w / h > args.spread_ratio:
            g = gut_over.get(name) or find_gutter(gray)
            if name not in gut_over and abs(g - w / 2) > 0.06 * w:
                print(f"WARNING {name}: gutter at {g}/{w} is far from the middle; check a "
                      f"500px thumbnail and rerun with --gutter {name}=X", file=sys.stderr)
            # Hebrew: right half is read first
            halves = [("right", gray[:, g:]), ("left", gray[:, :g])]
            gutter = g
        else:
            halves = [("single", gray)]
            gutter = None
        for side, img in halves:
            seq += 1
            a = skew_angle(img)
            img2 = rotate(img, a) if abs(a) >= 0.05 else img
            x0, y0, x1, y1 = content_bbox(img2)
            crop = img2[y0:y1, x0:x1]
            out = f"{seq:03d}.png"
            cv2.imwrite(os.path.join(out_rev, out), crop)
            cv2.imwrite(os.path.join(out_ocr, out), normalize_bg(crop))
            manifest.append({
                "page": seq, "file": out, "source": name, "side": side,
                "gutter_x": None if gutter is None else int(gutter), "skew_deg": a, "crop": [int(x0), int(y0), int(x1), int(y1)],
            })
            print(f"{out} <- {name} {side} skew={a} crop={x1-x0}x{y1-y0}", file=sys.stderr)

    with open(os.path.join(args.out_root, "pages.json"), "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
