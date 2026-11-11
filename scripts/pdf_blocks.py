"""Page-level structure for born-digital PDFs (used by check_pdf.py).

  running_bands(pages)  -> per page (top, bottom) of the area left after removing
                           running headers/footers (a line that repeats on many
                           pages in the top/bottom band, page numbers included)
  find_tables(page)     -> tables ruled with horizontal rules (booktabs style or
                           full grids); cells are read with pdftotext per cell
  find_figures(page)    -> images and clusters of vector graphics (charts); each
                           is rendered to a PNG and referenced as ![caption](img/..)
  split_page(page)      -> the page as ordered blocks: text spans, tables, figures

Limits: one table per run of rules; spanning cells are assigned to the column
where they start; figures are found by "many drawing objects close together",
so a chart made only of text is not seen.
"""
import collections
import re
import subprocess

CAPTION = re.compile(r"^\s*(Table|Tab\.|טבלה|לוח)\s*\d", re.I)
FIG_CAPTION = re.compile(r"^\s*(Figure|Fig\.|Chart|Graph|איור|תרשים|גרף)\s*\d", re.I)
HEB = re.compile(r"[א-ת]")


def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", t.lower())).strip()


def running_bands(pages, band=0.10, share=0.4):
    """Lines in the top/bottom `band` of the page whose digit-normalised text appears
    on at least `share` of the pages are running headers/footers. Returns
    (list of (y0, y1) content limits per page, set of dropped texts)."""
    n = len(pages)
    per = []
    for pg in pages:
        h = pg.height
        per.append([(norm(l["text"]), l["top"], l["bottom"]) for l in pg.extract_text_lines(layout=False)
                    if l["bottom"] < h * band * 1.5 or l["top"] > h * (1 - band * 1.5)])
    cnt = collections.Counter(k for items in per for k in {i[0] for i in items if i[0]})
    rep = {k for k, c in cnt.items() if n >= 4 and c >= max(3, share * n)}
    limits = []
    for pg, items in zip(pages, per):
        y0, y1 = 0, pg.height
        for k, top, bottom in items:
            if k in rep:
                if top < pg.height / 2:
                    y0 = max(y0, bottom + 1)
                else:
                    y1 = min(y1, top - 1)
        limits.append((y0, y1))
    return limits, rep


def _rules(page):
    out = []
    for r in list(page.rects) + list(page.lines):
        if r["bottom"] - r["top"] <= 2.5 and r["x1"] - r["x0"] > 20:
            out.append(r)
    groups = []
    for r in sorted(out, key=lambda r: r["top"]):
        if groups and abs(groups[-1]["top"] - r["top"]) <= 2:
            groups[-1]["segs"].append((r["x0"], r["x1"]))
        else:
            groups.append(dict(top=r["top"], segs=[(r["x0"], r["x1"])]))
    return [g for g in groups if sum(b - a for a, b in g["segs"]) > page.width * 0.35]


def _col_bounds(page, y0, y1, rules):
    """Column edges: where one rule segment ends and the next begins; else gaps in
    the words' horizontal coverage."""
    segs = sorted(s for g in rules for s in g["segs"])
    x_lo, x_hi = min(a for a, b in segs), max(b for a, b in segs)
    edges = sorted({round(b) for g in rules for (a, b), (c, d) in zip(sorted(g["segs"]), sorted(g["segs"])[1:])
                    if abs(b - c) < 3})
    if edges:
        return [x_lo - 2] + edges + [x_hi + 2]
    words = page.crop((0, y0, page.width, y1)).extract_words()
    cover = sorted((w["x0"], w["x1"]) for w in words)
    gaps, end = [], None
    for a, b in cover:
        if end is not None and a - end >= 10:
            gaps.append((end + a) / 2)
        end = b if end is None else max(end, b)
    return [x_lo - 2] + gaps + [x_hi + 2]


def _cell(pdf, n, box):
    t = subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), "-r", "72", "-x", str(int(box[0])), "-y", str(int(box[1])),
                        "-W", str(int(box[2] - box[0]) + 1), "-H", str(int(box[3] - box[1]) + 1), "-enc", "UTF-8", pdf, "-"],
                       capture_output=True, text=True, check=True).stdout
    return t


def find_tables(page, pdf, n, fix, tidy, limits):
    """Returns [(y0, y1, markdown)]."""
    rules = [g for g in _rules(page) if limits[0] <= g["top"] <= limits[1]]
    if len(rules) < 2:
        return []
    # split runs of rules that are far apart (text between them)
    runs, cur = [], [rules[0]]
    for g in rules[1:]:
        if g["top"] - cur[-1]["top"] > page.height * 0.6:
            runs.append(cur); cur = [g]
        else:
            cur.append(g)
    runs.append(cur)
    out = []
    for run in runs:
        if len(run) < 2:
            continue
        top, bottom = run[0]["top"], run[-1]["top"] + 3
        cols = _col_bounds(page, top, bottom, run)
        ncol = len(cols) - 1
        if ncol < 2:
            continue
        # caption: "Table N" line above the first rule and the lines after it
        lines = page.extract_text_lines(layout=False)
        above = [l for l in lines if l["bottom"] <= top + 1 and l["top"] >= top - 70]
        cap_i = next((i for i, l in enumerate(above) if CAPTION.match(l["text"])), None)
        cap_top = above[cap_i]["top"] - 1 if cap_i is not None else top
        cap = ""
        if cap_i is not None:
            c = _cell(pdf, n, (0, cap_top, page.width, top))
            cap = tidy(" ".join(fix(c).split()))
        # rows from the line tops of all columns
        spans = []  # (top, bottom) of every text line in every column
        for a, b in zip(cols, cols[1:]):
            for l in page.crop((a, top, b, bottom + 4)).extract_text_lines(layout=False):
                spans.append((l["top"], l["bottom"]))
        spans.sort()
        if not spans:
            continue
        col_gaps = []
        for a, b in zip(cols, cols[1:]):
            ts = sorted(l["top"] for l in page.crop((a, top, b, bottom + 4)).extract_text_lines(layout=False))
            col_gaps += [y - x for x, y in zip(ts, ts[1:]) if y - x > 1]
        line_gap = min(col_gaps) if col_gaps else 12
        head_bottom = run[1]["top"] + 1 if len(run) >= 3 else None
        rows, cur = [], [spans[0]]
        for s in spans[1:]:
            new_row = s[0] - cur[-1][0] > line_gap * 1.3 and s[0] - cur[-1][1] > -0.5 and \
                      s[0] - max(c[0] for c in cur) > line_gap * 1.3
            if head_bottom and cur[-1][1] <= head_bottom < s[0] + 1:
                new_row = True
            if new_row:
                rows.append(cur); cur = [s]
            else:
                cur.append(s)
        rows.append(cur)
        table = []
        for r in rows:
            y0 = min(s[0] for s in r) - 0.5
            y1 = max(s[1] for s in r) + 0.5
            cells = []
            for a, b in zip(cols, cols[1:]):
                t = tidy(" ".join(fix(_cell(pdf, n, (a, y0, b, y1))).split()))
                cells.append(t.replace("|", "\\|"))
            table.append(cells)
        hebrew = len(HEB.findall(" ".join(c for r in table for c in r))) > 20
        if hebrew:  # RTL table: first column is the rightmost
            table = [r[::-1] for r in table]
            cols = [cols[0]] + [b for a, b in zip(cols, cols[1:])]
            widths = [b - a for a, b in zip(cols, cols[1:])][::-1]
        else:
            widths = [b - a for a, b in zip(cols, cols[1:])]
        body = table[1:] or table
        filled = sum(sum(bool(c) for c in r) >= 2 for r in body)
        if len(table) < 3 or filled < 0.6 * len(body):  # decorative rules, not a table
            continue
        total = sum(widths)
        dashes = ["-" * max(3, round(60 * w / total)) for w in widths]
        md = ["| " + " | ".join(table[0]) + " |", "|" + "|".join(dashes) + "|"]
        md += ["| " + " | ".join(r) + " |" for r in table[1:]]
        if cap:
            md += ["", ": " + cap]
        out.append((cap_top, bottom, "\n".join(md)))
    return out


def find_figures(page, avoid, limits, min_objs=8):
    """Boxes (x0, y0, x1, y1) of images and vector-drawn charts outside `avoid` y-ranges."""
    W, H = page.width, page.height
    boxes = []
    for im in page.images:
        w, h = im["x1"] - im["x0"], im["bottom"] - im["top"]
        if h >= 60 and w >= 60 and w * h >= 0.05 * W * H:
            boxes.append((im["x0"], im["top"], im["x1"], im["bottom"], 99))

    def inside(o):
        return any(a - 1 <= o["top"] and o["bottom"] <= b + 1 for a, b in avoid)

    objs = [o for o in list(page.curves) + list(page.rects) + list(page.lines)
            if not inside(o) and (o["bottom"] - o["top"] > 2.5 or o["x1"] - o["x0"] > 2.5)
            and not (o["x1"] - o["x0"] > W * 0.95 and o["bottom"] - o["top"] > H * 0.9)  # page background
            and not (o["bottom"] - o["top"] <= 2.5 and o["x1"] - o["x0"] > W * 0.5)]     # a rule
    clusters = []
    for o in sorted(objs, key=lambda o: o["top"]):
        b = [o["x0"], o["top"], o["x1"], o["bottom"], 1]
        merged = True
        while merged:
            merged = False
            for c in clusters:
                if b[0] - 8 <= c[2] and c[0] - 8 <= b[2] and b[1] - 8 <= c[3] and c[1] - 8 <= b[3]:
                    b = [min(b[0], c[0]), min(b[1], c[1]), max(b[2], c[2]), max(b[3], c[3]), b[4] + c[4]]
                    clusters.remove(c)
                    merged = True
                    break
        clusters.append(b)
    for c in clusters:
        if c[4] >= min_objs and c[2] - c[0] >= 80 and c[3] - c[1] >= 50:
            boxes.append(tuple(c))
    return [b[:4] for b in boxes if limits[0] <= b[1] and b[3] <= limits[1] + 1]


def render(pdf, n, box, out_png, dpi=150):
    k = dpi / 72
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile", "-f", str(n), "-l", str(n),
                    "-x", str(int(box[0] * k)), "-y", str(int(box[1] * k)),
                    "-W", str(int((box[2] - box[0]) * k) + 1), "-H", str(int((box[3] - box[1]) * k) + 1),
                    pdf, out_png[:-4]], check=True)


def split_page(page, pdf, n, fix, tidy, limits, img_dir):
    """Ordered regions of the page: ("text", y0, y1), ("md", y0, y1, markdown).
    Figures are rendered into img_dir and come back as "md" regions."""
    import os
    W = page.width
    tables = find_tables(page, pdf, n, fix, tidy, limits)
    regions = [("md", a, b, md) for a, b, md in tables]
    figs = find_figures(page, [(a, b) for a, b, _ in tables], limits)
    lines = page.extract_text_lines(layout=False)
    for k, box in enumerate(sorted(figs, key=lambda b: b[1]), 1):
        x0, y0, x1, y1 = box
        x0, x1 = max(0, x0 - 12), min(W, x1 + 12)
        y0, y1 = max(limits[0], y0 - 12), min(limits[1], y1 + 12)
        cap = ""
        for l in lines:  # a "Figure N" caption just below or above travels with the image
            if FIG_CAPTION.match(l["text"]) and (0 <= l["top"] - y1 < 30 or 0 <= y0 - l["bottom"] < 30):
                cap = tidy(" ".join(fix(_cell(pdf, n, (0, l["top"] - 1, W, l["bottom"] + 1))).split()))
                y0, y1 = min(y0, l["top"] - 2), max(y1, l["bottom"] + 2)
        os.makedirs(img_dir, exist_ok=True)
        name = f"fig-p{n:02d}-{k}.png"
        render(pdf, n, (0, y0, W, y1) if False else (x0, y0, x1, y1), os.path.join(img_dir, name))
        regions.append(("md", y0, y1, f"![{cap or 'Figure'}](img/{name})"))
    regions.sort(key=lambda r: r[1])
    out, pos = [], limits[0]
    for r in regions:
        if r[1] - pos > 6:
            out.append(("text", pos, r[1] - 1))
        out.append(r)
        pos = r[2] + 1
    if limits[1] - pos > 6:
        out.append(("text", pos, limits[1]))
    return out
