#!/usr/bin/env python3
"""Low-token OCR stage: OCR every page locally and queue only the doubtful words.

Claude (or a helper agent) never reads whole pages. It reads the small sheet
images in OUT/sheets/ (each row = one numbered word, cropped with a little
context and boxed) next to OUT/queue.txt, and writes a short fixes file that
apply_fixes.py merges into the drafts.

Per page (IN_DIR/NNN.png, already deskewed by prep_pages.py):
  1. Tesseract layout pass -> text blocks; each block is deskewed on its own
     (photos bend) and optionally upscaled (low-res photos OCR better at 2x).
  2. Each block is read by two models (tessdata_best and the distro fast heb).
  3. A word of the primary reading is queued when: its confidence is below
     --low, the other model reads something else at the same spot, the other
     model has no word there, or Hebrew is glued to a digit/Latin letter
     (footnote markers). Words only the second model saw are queued too.

Output in OUT_DIR:
  draft/NNN.md   primary text, paragraphs joined, queued words as {{n:word}}
  queue.txt      n<TAB>page<TAB>primary<TAB>alt<TAB>conf<TAB>why<TAB>context
  sheets/sNN.png numbered crops, ~40 per sheet (about 1.3K tokens each)
  blocks/        deskewed block images (for later crops)
  headers.txt    running headers / page numbers that were left out of the drafts
  stats.txt      words and queued words per page

Usage: review_queue.py IN_DIR OUT_DIR --tessdata DIR [--low 75] [--scale auto]
       [--per-sheet 40] [--lang heb]
"""
import argparse
import csv
import io
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ocr_regions import layout_blocks, merge, normalize, reading_order, skew_angle  # noqa: E402

GLUED = re.compile(r"[א-ת][0-9A-Za-z*+]|[0-9A-Za-z*+][א-ת]")


def tsv_words(path, tessdata, lang, psm=6):
    cmd = ["tesseract", path, "-", "-l", lang, "--oem", "1", "--psm", str(psm), "--dpi", "300", "tsv"]
    if tessdata:
        cmd[1:1] = ["--tessdata-dir", tessdata]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    words = []
    for r in csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE):
        if r["level"] == "5" and r["text"].strip():
            x, y, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
            words.append({"text": r["text"].strip(), "conf": float(r["conf"]),
                          "box": (x, y, x + w, y + h),
                          "line": (int(r["par_num"]), int(r["line_num"]))})
    return words


def overlap(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if not inter:
        return 0.0
    return inter / min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))


def normalize_text(t):
    """Mechanical fixes that never need a look: maqaf, dashes, space before punctuation."""
    t = re.sub(r"(?<=[א-ת])-(?=[א-ת])", "־", t)
    t = re.sub(r"\s*--+\s*|\s+-\s+|\s+—\s+", " — ", t)
    t = re.sub(r"\s+([;:,.?!])", r"\1", t)
    t = re.sub(r"(?<=[א-ת])\.(?=[א-ת])", ". ", t)
    return t


def uncovered(img, boxes, min_h):
    """Horizontal ink strips not covered by any OCR word box (dropped lines/words)."""
    import numpy as np
    a = np.asarray(img) < 128
    cov = np.zeros_like(a)
    for x0, y0, x1, y1 in boxes:
        cov[max(0, y0 - 4):y1 + 4, max(0, x0 - 6):x1 + 6] = True
    left = a & ~cov
    rows = left.sum(axis=1) > max(8, img.width * 0.02)
    out, y = [], 0
    while y < len(rows):
        if rows[y]:
            y1 = y
            while y1 < len(rows) and rows[y1]:
                y1 += 1
            if y1 - y >= min_h:
                xs = np.where(left[y:y1].any(axis=0))[0]
                if len(xs) and xs[-1] - xs[0] > 3 * min_h:
                    out.append((int(xs[0]), y, int(xs[-1]) + 1, y1))
            y = y1
        else:
            y += 1
    return out


def letters(w):
    return re.sub(r"[^א-ת]", "", w)


def norm_word(w):
    return w.replace("״", '"').replace("׳", "'")


def lines_of(words):
    lines = {}
    for w in words:
        lines.setdefault(w["line"], []).append(w)
    out = []
    for ws in lines.values():
        ws.sort(key=lambda w: -w["box"][2])  # RTL: rightmost word first
        box = (min(w["box"][0] for w in ws), min(w["box"][1] for w in ws),
               max(w["box"][2] for w in ws), max(w["box"][3] for w in ws))
        out.append({"words": ws, "box": box})
    out.sort(key=lambda l: l["box"][1])
    return out


def paragraphs(lines, block_w):
    """Join lines; a short last line (left end far from the block's left edge) ends a paragraph."""
    if not lines:
        return []
    left = min(l["box"][0] for l in lines)
    right = max(l["box"][2] for l in lines)
    paras, cur = [], []
    for i, l in enumerate(lines):
        indented = l["box"][2] < right - 0.04 * block_w
        if cur and indented:
            paras.append(cur)
            cur = []
        cur.append(l)
        if l["box"][0] > left + 0.12 * block_w:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    return paras


def crop_item(img, word_box, line_box, height=44):
    lh = line_box[3] - line_box[1]
    x0 = max(0, word_box[0] - 3 * lh)
    x1 = min(img.width, word_box[2] + 3 * lh)
    y0 = max(0, line_box[1] - lh // 3)
    y1 = min(img.height, line_box[3] + lh // 3)
    c = img.crop((x0, y0, x1, y1)).convert("RGB")
    d = ImageDraw.Draw(c)
    d.rectangle((word_box[0] - x0 - 2, word_box[1] - y0 - 2, word_box[2] - x0 + 2, word_box[3] - y0 + 2),
                outline=(220, 0, 0), width=2)
    s = height / c.height
    return c.resize((max(1, int(c.width * s)), height))


def make_sheets(items, out_dir, per_sheet, width=560, row_h=48):
    os.makedirs(out_dir, exist_ok=True)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    paths = []
    for s in range(0, len(items), per_sheet):
        chunk = items[s:s + per_sheet]
        sheet = Image.new("RGB", (width, row_h * len(chunk)), "white")
        d = ImageDraw.Draw(sheet)
        for i, (n, crop) in enumerate(chunk):
            y = i * row_h
            d.text((4, y + 10), str(n), fill=(0, 0, 160), font=font)
            c = crop if crop.width <= width - 60 else crop.crop((crop.width - (width - 60), 0, crop.width, crop.height))
            sheet.paste(c, (width - c.width - 2, y + 2))  # right-aligned, like the text
            d.line((0, y + row_h - 1, width, y + row_h - 1), fill=(200, 200, 200))
        p = os.path.join(out_dir, f"s{s // per_sheet + 1:02d}.png")
        sheet.save(p, optimize=True)
        paths.append(p)
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("in_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--tessdata", required=True, help="dir with tessdata_best heb.traineddata")
    ap.add_argument("--lang", default="heb")
    ap.add_argument("--low", type=float, default=75, help="queue words below this confidence")
    ap.add_argument("--same-letters-conf", type=float, default=85,
                    help="ignore a punctuation-only disagreement when confidence is at least this")
    ap.add_argument("--scale", default="auto", help="'auto' (2x if page < 1800 px wide) or a number")
    ap.add_argument("--per-sheet", type=int, default=40)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    for sub in ("draft", "blocks"):
        os.makedirs(os.path.join(args.out_dir, sub), exist_ok=True)

    pages = []
    for name in sorted(os.listdir(args.in_dir)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in (".png", ".jpg", ".jpeg", ".tif") or (args.only and stem not in args.only):
            continue
        page = normalize(ImageOps.grayscale(Image.open(os.path.join(args.in_dir, name))))
        scale = (2.0 if page.width < 1800 else 1.0) if args.scale == "auto" else float(args.scale)
        if scale != 1.0:
            page = page.resize((int(page.width * scale), int(page.height * scale)), Image.LANCZOS)
        pp = os.path.join(args.out_dir, "blocks", f"{stem}_page.png")
        page.save(pp)
        found = merge(layout_blocks(pp, args.tessdata, args.lang))
        # ink the layout pass skipped (whole lines can go missing): add it as extra blocks
        extra = []
        for ub in uncovered(page, found, int(8 * scale)):
            if extra and ub[1] - extra[-1][3] < 30 * scale:
                e = extra[-1]
                extra[-1] = (min(e[0], ub[0]), e[1], max(e[2], ub[2]), ub[3])
            else:
                extra.append(ub)
        boxes = reading_order(merge(found + extra), page.width)
        os.remove(pp)
        page_paras, n_words = [], 0
        for bi, (x0, y0, x1, y1) in enumerate(boxes):
            if (x1 - x0) * (y1 - y0) < 4000 * scale * scale:
                continue
            pad = int(30 * scale)
            blk = page.crop((max(0, x0 - pad), max(0, y0 - pad), min(page.width, x1 + pad), min(page.height, y1 + pad)))
            a = skew_angle(blk)
            if abs(a) >= 0.1:
                blk = blk.rotate(a, resample=Image.BICUBIC, expand=True, fillcolor=255)
            bp = os.path.join(args.out_dir, "blocks", f"{stem}_b{bi}.png")
            blk.save(bp)
            best = tsv_words(bp, args.tessdata, args.lang)
            fast = tsv_words(bp, None, args.lang)
            used = set()
            for w in best:
                why, alt = [], ""
                hits = [(overlap(w["box"], f["box"]), i) for i, f in enumerate(fast)]
                hits = [h for h in hits if h[0] > 0.5]
                if hits:
                    idx = [i for _, i in sorted(hits, reverse=True)]
                    used.update(idx)
                    alt_words = sorted((fast[i] for i in idx), key=lambda f: -f["box"][2])
                    alt = " ".join(f["text"] for f in alt_words)
                    if norm_word(alt) != norm_word(w["text"]) and not (
                            letters(alt) == letters(w["text"]) and w["conf"] >= args.same_letters_conf):
                        why.append("alt")
                else:
                    why.append("noalt")
                if w["conf"] < args.low:
                    why.append("conf")
                if GLUED.search(w["text"]):
                    why.append("glued")
                w.update(why=why, alt=alt, img=blk)
            lines = lines_of(best)
            for l in lines:
                for w in l["words"]:
                    w["lbox"] = l["box"]
            # words only the second model saw (dropped by the primary)
            for i, f in enumerate(fast):
                if i in used or any(overlap(f["box"], w["box"]) > 0.2 for w in best):
                    continue
                f.update(why=["missing"], alt=f["text"], text="", img=blk, lbox=f["box"])
                lines.append({"words": [f], "box": f["box"]})
            # ink inside the block that no model read
            hs = sorted(w["box"][3] - w["box"][1] for w in best) or [20]
            for ub in uncovered(blk, [w["box"] for w in best + fast], hs[len(hs) // 2] // 2):
                u = {"text": "", "alt": "", "conf": 0, "why": ["uncovered"], "box": ub, "lbox": ub,
                     "img": blk, "strip": True}
                lines.append({"words": [u], "box": ub})
            lines.sort(key=lambda l: l["box"][1])
            n_words += len(best)
            page_paras.extend(paragraphs(lines, blk.width))
        pages.append((stem, page_paras, n_words))
        print(f"{stem}\twords={n_words}", flush=True)

    # dictionary pass over the whole book: an unknown word that occurs only once is suspect
    allw = [w for _, paras, _ in pages for para in paras for l in para for w in l["words"] if w["text"]]
    counts = {}
    for w in allw:
        counts[norm_word(w["text"])] = counts.get(norm_word(w["text"]), 0) + 1
    cand = sorted({re.sub(r"[^א-ת\"'־]", "", w["text"]) for w in allw if not w["why"]} - {""})
    unknown = set(subprocess.run(["hunspell", "-i", "utf-8", "-d", "he_IL", "-l"], input="\n".join(cand),
                                 capture_output=True, text=True).stdout.split()) if cand else set()
    for w in allw:
        if not w["why"] and counts[norm_word(w["text"])] == 1 and re.sub(r"[^א-ת\"'־]", "", w["text"]) in unknown:
            w["why"] = ["dict"]

    # running headers / page numbers: short first or last paragraph with a number, or repeated on other pages
    def ptext(para):
        return " ".join(w["text"] or w["alt"] for l in para for w in l["words"])
    edge = {}
    for stem, paras, _ in pages:
        for para in paras[:1] + paras[-1:]:
            edge.setdefault(letters(ptext(para)), set()).add(stem)
    headers = []
    for stem, paras, _ in pages:
        for para in [p for p in (paras[:1] + paras[-1:]) if p in paras]:
            t = ptext(para)
            if len(t.split()) <= 5 and (re.search(r"\d", t) or len(edge.get(letters(t), ())) > 1
                                        or not letters(t)):
                paras.remove(para)
                headers.append(f"{stem}\t{t}")

    items, queue, stats, n = [], [], [], 0
    for stem, paras, n_words in pages:
        md, nq = [], 0
        for para in paras:
            toks = []
            flat = [w for l in para for w in l["words"]]
            for l in para:
                for w in l["words"]:
                    if w["why"]:
                        k = flat.index(w)
                        ctx = " ".join(x["text"] for x in flat[max(0, k - 4):k]) + " [*] " + \
                            " ".join(x["text"] for x in flat[k + 1:k + 5])
                        n += 1
                        nq += 1
                        queue.append((n, stem, w["text"], w["alt"], int(w["conf"]), ",".join(w["why"]), ctx))
                        if w.get("strip"):
                            b = w["box"]
                            c = w["img"].crop((b[0], max(0, b[1] - 4), b[2], min(w["img"].height, b[3] + 4))).convert("RGB")
                            items.append((n, c.resize((max(1, int(c.width * 44 / c.height)), 44))))
                        else:
                            items.append((n, crop_item(w["img"], w["box"], w["lbox"])))
                        toks.append("{{%d:%s}}" % (n, w["text"]))
                    else:
                        toks.append(w["text"])
            md.append(normalize_text(" ".join(toks)))
        with open(os.path.join(args.out_dir, "draft", stem + ".md"), "w", encoding="utf-8") as f:
            f.write("\n\n".join(md) + "\n")
        stats.append(f"{stem}\twords={n_words}\tqueued={nq}")

    items.sort(key=lambda t: t[0])
    sheets = make_sheets(items, os.path.join(args.out_dir, "sheets"), args.per_sheet)
    with open(os.path.join(args.out_dir, "queue.txt"), "w", encoding="utf-8") as f:
        f.write("# n\tpage\tprimary\talt\tconf\twhy\tcontext ([*] = this word)\n")
        for q in queue:
            f.write("\t".join(str(x) for x in q) + "\n")
    with open(os.path.join(args.out_dir, "headers.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(headers) + "\n")
    with open(os.path.join(args.out_dir, "stats.txt"), "w") as f:
        f.write("\n".join(stats) + f"\ntotal queued={len(queue)} sheets={len(sheets)}\n")
    print(f"total queued={len(queue)} sheets={len(sheets)}")


if __name__ == "__main__":
    main()
