#!/usr/bin/env python3
"""Step 0: decide whether a PDF needs OCR at all.

Counts the Hebrew letters in each page's text layer (pdftotext). Pages with
at least --min letters count as "text"; the rest are scans. A page covered by
one picture (>= 85% of its area) is a scan too, whatever its text layer says:
scanner apps (Adobe Scan, CamScanner) add their own OCR layer, which is noisy
and has no structure, and the page must go through our OCR instead.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pdf_blocks  # noqa: E402

HEB = re.compile(r"[A-Za-zא-ת]")  # any letters: English PDFs count too
FINALS_AT_START = re.compile(r"(?:^|\s)[םןץףך][א-ת]")
FINALS_AT_END = re.compile(r"[א-ת][םןץףך](?:$|[\s.,;:!?])")


def page_count(pdf):
    info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, check=True).stdout
    return int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))


def page_text(pdf, n, crop=None):
    """pdftotext of page n; crop=(x0, y0, x1, y1) in points limits it to that box."""
    box = []
    if crop:
        x0, y0, x1, y1 = crop
        box = ["-x", str(int(x0)), "-y", str(int(y0)), "-W", str(int(x1 - x0) + 1), "-H", str(int(y1 - y0) + 1)]
    return subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), "-r", "72", *box, "-enc", "UTF-8", pdf, "-"],
                          capture_output=True, text=True, check=True).stdout


BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
LTR_RUN = re.compile("\u202a([^\u202a-\u202c]*)\u202c")
CORE = re.compile(r"^(\W*?)(\w.*\w|\w)?(\W*)$", re.S)


def fix_ltr_run(m):
    """pdftotext gives an embedded LTR run (Latin, numbers) in visual order, so
    the neutrals at its edges sit on the wrong side: ' 184' is '184 ', ')2004' is
    '2004)', ' 600 -' is '- 600 '. Move them across the core."""
    lead, core, trail = CORE.match(m.group(1)).groups()
    return trail[::-1] + (core or "") + lead[::-1]


MIRROR = str.maketrans("()[]", ")(][")


def fix_order(text):
    """Fix embedded LTR runs, drop bidi control marks, and flip lines whose
    Hebrew is in visual (reversed) order."""
    text = LTR_RUN.sub(fix_ltr_run, text)
    text = BIDI.sub("", text)
    if len(FINALS_AT_START.findall(text)) <= len(FINALS_AT_END.findall(text)):
        return text
    return "\n".join(line[::-1].translate(MIRROR) for line in text.splitlines())


NOTE_THEN_LATIN = re.compile(r"^(\[[^\[\]]*[א-ת][^\[\]]*\]) \)(.*[A-Za-z0-9].*)$")
NOTE_AFTER_NUMBERS = re.compile(r"\[ \)([0-9a-z:,.\- ]*?)([א-ת][^\[\]]*)\]")


def _numbers_in_order(run):
    """'816 :2018 ,' (visual) -> ', 2018: 816'; leading punctuation moves to the end."""
    out = []
    for tok in reversed(run.split()):
        m = re.match(r"^([:,.]*)(.*)$", tok)
        out.append(m.group(2) + m.group(1))
    return " ".join(t for t in out if t)


def fix_note_after_quote(line):
    """A Hebrew note in brackets ("[ההדגשה שלי]") after a citation's closing
    paren comes out of pdftotext in the wrong run order:
      "[ההדגשה שלי] )achieve that. (Rice, 2011:601"  (last line of an English quote)
        -> "achieve that. (Rice, 2011:601) [ההדגשה שלי]"
      "(אולמרט[ )816 :2018 ,ההדגשה שלי]"  (Hebrew quote)
        -> "(אולמרט, 2018: 816) [ההדגשה שלי]"
    When it applies: born-digital Hebrew PDFs with English or Hebrew quotes
    that end in "(source) [note]" (Varon thesis, 2026-11-22). Lines without
    that shape are returned unchanged."""
    m = NOTE_THEN_LATIN.match(line.strip())
    if m:
        return f"{m.group(2).strip()}) {m.group(1)}"

    def fix(m):
        nums = _numbers_in_order(m.group(1))
        return (nums + ") " if nums else ") ") + "[" + m.group(2).strip() + "]"

    return NOTE_AFTER_NUMBERS.sub(fix, line)


def _parens_ok(t):
    depth = 0
    for c in t:
        depth += (c == "(") - (c == ")")
        if depth < 0:
            return False
    return depth == 0


OPEN_AS_CLOSE = re.compile(r"(?<=[A-Za-z0-9.])\((?![A-Za-z0-9])")  # "2015(." "MHS(,"
CLOSE_AS_OPEN = re.compile(r"(?<![A-Za-z0-9.;:!?…])\)(?=[A-Za-z0-9])")  # "בסכסוך)Jackson" ")2013:23"


REVERSED_PAIR = re.compile(r"(?<![A-Za-z0-9.;:!?…])\)([A-Za-z0-9][^()\n]{0,120}?[A-Za-z0-9.])\((?![A-Za-z0-9])")


# an English quote whose citation's ")" landed at the end of the quote's first
# line: "it is the)skillful ... (Nye & Armitage, 2007 [note]" -> "... 2007) [note]"
QUOTE_CLOSER = re.compile(r"^([^()]*?[A-Za-z,.…])\)([A-Za-z\"“][^()]*?\([^()]*?[A-Za-z0-9.])(\s*\[[^\[\]]*\])?\s*$")


def _unmatched(t):
    depth = bad = 0
    for c in t:
        if c == "(":
            depth += 1
        elif c == ")":
            if depth:
                depth -= 1
            else:
                bad += 1
    return bad + depth


def fix_parens(p):
    """Mirror parens that pdftotext left facing the wrong way around Latin
    citations in Hebrew text: "בסכסוך)Jackson, 1952(" -> "בסכסוך(Jackson, 1952)",
    "הדדי")MHS(" -> "הדדי"(MHS)".
    Candidates: ")" glued to the Latin or digits after it, "(" glued to the
    Latin or digits before it. A candidate pair (a ")" and the next "(") or a
    single candidate is flipped only if that leaves fewer unmatched parens, so
    a paragraph whose parens already balance never changes.
    When it applies: born-digital Hebrew PDFs (Varon thesis, 2026-11-22)."""
    if _parens_ok(p):
        return p
    # whole reversed pairs first: ")MHS(" ")Rice, 2011(" -> "(MHS)" "(Rice, 2011)";
    # volume(issue) in Hebrew references: ",)3(11." -> ", 11(3)." and "19)4)" -> "19(4)"
    whole = re.sub(r",\)(\d+)\((\d+)", r", \2(\1)", p)
    whole = re.sub(r"\b(\d+)\)(\d+)\)", r"\1(\2)", whole)
    whole = REVERSED_PAIR.sub(lambda m: "(" + m.group(1) + ")", whole)
    whole = QUOTE_CLOSER.sub(r"\1 \2)\3", whole)
    if _unmatched(whole) <= _unmatched(p):
        p0, p = p, whole
    else:
        p0 = p
    s = list(p)
    opens = [m.start() for m in CLOSE_AS_OPEN.finditer(p)]
    closes = [m.start() for m in OPEN_AS_CLOSE.finditer(p)]
    moves = []
    for i in opens:
        later = [j for j in closes if j > i]
        if later:
            moves.append((i, later[0]))
    moves += [(i,) for i in opens] + [(j,) for j in closes]
    for mv in moves:
        if _parens_ok("".join(s)):
            break
        t = s[:]
        for k in mv:
            t[k] = "(" if t[k] == ")" else ")"
        if _unmatched("".join(t)) < _unmatched("".join(s)):
            s = t
    q = "".join(s)
    p = p0
    if q != p:  # the flipped parens lost their spaces: "word(Name", "2015)word"
        q = re.sub(r"(?<=[א-ת])\((?=[A-Za-z0-9])", " (", q)
        q = re.sub(r"\)(?=[א-ת])", ") ", q)
        q = re.sub(r"(?<=[א-ת]),\((?=[A-Za-z0-9])", ", (", q)
    return q


def tidy(p):
    p = re.sub(r"\s+", " ", p).strip()
    p = re.sub(r"\s([.,;:!?])(?=[א-ת\"(])", r"\1 ", p)  # ". word" -> "word. word"
    p = re.sub(r"(?<=\b[בהוכלמש])- (?=\d)", "־", p)  # "ה- 70" -> "ה־70"
    p = re.sub(r"\( +", "(", p)
    p = re.sub(r" +\)", ")", p)
    p = re.sub(r"(?<=[א-ת])\((?= ?[A-Za-z0-9])", " (", p)  # "word(Name" -> "word (Name"
    p = re.sub(r" +([.,;:])", r"\1", p)
    return re.sub(r"\s{2,}", " ", p).strip()


def to_paragraphs(text):
    paras = [fix_parens(tidy(p)) for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paras if p) + "\n"


def mark_bold(t, boldw):
    """Wrap the words of line t that the PDF sets in a bold font in **...**."""
    if not boldw:
        return t
    boldw = boldw.copy()
    out, run = [], []

    def end_run():
        tail = []
        while run and not any(ch.isalnum() for ch in run[-1]):
            tail.insert(0, run.pop())  # bare punctuation after the run stays plain
        if run:
            out.append("**" + " ".join(run) + "**")
        out.extend(tail)
        run.clear()

    for tok in t.split(" "):
        k = "".join(sorted(ch for ch in tok if ch.isalnum()))
        if k and boldw[k] > 0:
            boldw[k] -= 1
            run.append(tok)
        elif not k and run:
            run.append(tok)
        else:
            end_run()
            out.append(tok)
    end_run()
    return " ".join(out)


def page_stats(geo):
    """Body type size, right and left text edges, typical line step of a page."""
    import collections
    body = collections.Counter(g["size"] for g in geo).most_common(1)[0][0]
    right = max(g["x1"] for g in geo if g["size"] == body)
    left = min(g["x0"] for g in geo if g["size"] == body)
    tops = sorted(g["top"] for g in geo if g["size"] == body)
    steps = [b - a for a, b in zip(tops, tops[1:]) if b > a]
    step = sorted(steps)[len(steps) // 2] if steps else body * 1.4
    return body, right, left, step


HEB_ONLY = re.compile(r"[א-ת]")
LATIN = re.compile(r"[A-Za-z]")


def line_breaks(g, para, right, left, rtl, justified=False):
    """(starts, ends): does printed line g start a new paragraph, or end one?
    para holds the geometry of the lines already in the open paragraph;
    justified says most lines of the page reach both margins.

    Measured from the side where lines start (the right in Hebrew, the left
    in English; rtl says which, by the line's own letters):
      - a line that starts in from the paragraph's (or page's) start edge is
        a first-line indent: a new paragraph starts there;
      - a line that starts further out than the paragraph's lines (body text
        after an indented block quote) starts a new paragraph too, except
        the line after an indented first line;
      - a line shorter than 60% of the block's width ends the paragraph; the
        first line of a block only when it starts at the page margin (an
        indented quote line is short but goes on);
      - justified text: a body line that stops short of the far margin ends
        the paragraph (in ragged text most lines do, so not there).
    Hebrew indents used to count as ends, which split every paragraph after
    its first line (Varon thesis, 2026-11-22)."""
    width = right - left
    tol = width * 0.05
    if rtl:
        start, stop = (lambda x: x["x1"]), (lambda x: x["x0"])
        inward = lambda a, b: b - a  # how far a starts in from b
    else:
        start, stop = (lambda x: x["x0"]), (lambda x: x["x1"])
        inward = lambda a, b: a - b
    margin, far = (right, left) if rtl else (left, right)
    at_margin = inward(start(g), margin) <= tol
    short_of_far = justified and at_margin and inward(far, stop(g)) > tol
    if not para:
        starts = not at_margin
        ends = at_margin and g["x1"] - g["x0"] < width * 0.6 or short_of_far
        return starts, ends
    edge = [start(x) for x in para[1:]] or [start(para[0])]
    edge = max(edge) if rtl else min(edge)
    first_indented = len(para) == 1 and inward(start(para[0]), margin) > tol and at_margin
    starts = inward(start(g), edge) > tol or (inward(edge, start(g)) > tol and not first_indented)
    if starts:
        return True, line_breaks(g, [], right, left, rtl, justified)[1]
    lo = min([x["x0"] for x in para] + [g["x0"]])
    hi = max([x["x1"] for x in para] + [g["x1"]])
    ends = g["x1"] - g["x0"] < (hi - lo) * 0.6 or short_of_far
    return starts, ends


def is_justified(geo, right, left):
    """Most full-size lines reach both margins (within 5% of the width)."""
    tol = (right - left) * 0.05
    both = [g for g in geo if g["x1"] - g["x0"] > (right - left) * 0.6]
    return bool(both) and sum(right - g["x1"] <= tol and g["x0"] - left <= tol
                              for g in both) >= 0.8 * len(both)


def line_direction(t, g, para, para_rtl, tol):
    """True when printed line t (geometry g) reads right to left. para holds the
    open paragraph's lines, para_rtl the direction of the previous line.
      - a "[note]" in brackets does not count;
      - a line with no letters ("7(1): 69-91.") keeps the previous direction;
      - a mixed line (Hebrew with a Latin citation) inside a paragraph keeps
        the paragraph's direction, and so does a Latin-only line that ends
        flush right with a right-to-left paragraph (a citation on its own line);
      - otherwise the script with more letters wins."""
    bare = re.sub(r"\[[^\[\]]*\]", "", t)
    heb, lat = len(HEB_ONLY.findall(bare)), len(LATIN.findall(bare))
    if not heb and not lat:
        return para_rtl
    rtl = para_rtl if (para and heb and lat) else heb >= lat
    if para and para_rtl and abs(g["x1"] - para[-1]["x1"]) <= tol:
        rtl = True
    return rtl


def layout_page(pdf_path, page, n, crop=None, stats=None):
    """With pdfplumber: use line geometry and fonts for structure. A vertical gap
    or a short line ends a paragraph; very large type is a heading (# for the
    biggest on the first page, ## otherwise); bold lines become **bold**.
    Lines are matched to pdftotext's (logical-order) lines by letter content."""
    import collections
    raw = page_text(pdf_path, n, crop)
    if crop:
        page = page.crop(crop)
    lines = [fix_note_after_quote(l) for l in fix_order(raw).splitlines() if l.strip()]
    geo = []
    for l in page.extract_text_lines(layout=False):
        ch = [c for c in l["chars"] if c["text"].strip()]
        if not ch:
            continue
        size = collections.Counter(round(c["size"]) for c in ch).most_common(1)[0][0]
        bold = sum("Bold" in c["fontname"] or "Bol" in c["fontname"] for c in ch) / len(ch)
        geo.append(dict(x0=l["x0"], x1=l["x1"], top=l["top"], size=size, bold=bold,
                        c=collections.Counter(c["text"] for c in ch if c["text"].isalnum())))
    if not geo:
        return to_paragraphs(fix_order(raw))
    key = lambda w: "".join(sorted(ch for ch in w if ch.isalnum()))
    for g in geo:
        g["boldw"] = collections.Counter()
    for w in page.extract_words(extra_attrs=["fontname"]):
        if "Bol" in w["fontname"] and key(w["text"]):
            min(geo, key=lambda g: abs(g["top"] - w["top"]))["boldw"][key(w["text"])] += 1
    body, right, left, step = stats or page_stats(geo)
    j, rows = 0, []
    for t in lines:
        c = collections.Counter(ch for ch in t if ch.isalnum())
        tot = max(1, sum(c.values()))
        ov = lambda k: sum((c & geo[k]["c"]).values())
        cand = range(max(0, j - 1), min(j + 12, len(geo))) or [len(geo) - 1]
        best = max(cand, key=lambda k: (ov(k) / max(tot, sum(geo[k]["c"].values())), -abs(k - j)))
        if ov(best) / max(tot, sum(geo[best]["c"].values())) > 0.6:
            j = best + 1
        else:  # a fragment (table cell, column): find its printed line nearby, don't advance
            near = range(max(0, j - 3), min(j + 2, len(geo))) or [len(geo) - 1]
            best = max(near, key=lambda k: (ov(k) / tot, -abs(k - j)))
        # several pdftotext lines on one printed line = table cells or columns
        cell = bool(rows) and rows[-1][1] is geo[best]
        rows.append((t.strip(), geo[best], cell))
    justified = is_justified(geo, right, left)
    out, para, para_bold, para_geo, prev, para_rtl = [], [], [], [], None, True

    def flush():
        if para:
            # consecutive bold lines become one **span**
            parts, i = [], 0
            while i < len(para):
                k = i
                while k < len(para) and para_bold[k] == para_bold[i]:
                    k += 1
                chunk = tidy(" ".join(para[i:k]))
                parts.append(f"**{chunk}**" if para_bold[i] else chunk)
                i = k
            out.append(fix_parens(" ".join(parts).replace("** **", " ")))
        para.clear(); para_bold.clear(); para_geo.clear()

    for t, g, cell in rows:
        if cell and para:
            para[-1] += " | " + t  # keep cells together; tidy the table by hand
            continue
        if g["size"] < body * 0.85 and re.fullmatch(r"[-–\d\s]+", t):
            continue  # page number
        if g["size"] >= body * 1.4:
            flush()
            level = "#" if n == 1 and g["size"] >= body * 3 else "##"
            if out and out[-1].startswith(level + " ") and prev and prev["size"] == g["size"]:
                out[-1] += " " + t  # heading that wraps
            elif out and out[-1].startswith("# ") and level == "##" and n == 1:
                out.append(f"### {t}")  # subtitle
            else:
                out.append(f"{level} {t}")
            prev = g
            continue
        if prev and (g["top"] - prev["top"] > step * 1.5 or prev["size"] >= body * 1.4):
            flush()
        rtl = line_direction(t, g, para_geo, para_rtl, (right - left) * 0.05)
        para_rtl = rtl
        starts, ends = line_breaks(g, para_geo, right, left, rtl, justified)
        if starts:
            flush()
        para_geo.append(g)
        para.append(mark_bold(t, g["boldw"])); para_bold.append(False)
        if ends:
            flush()
        prev = g
    flush()
    return "\n\n".join(out) + "\n"


def geo_all(page):
    import collections
    out = []
    for l in page.extract_text_lines(layout=False):
        ch = [c for c in l["chars"] if c["text"].strip()]
        if ch:
            size = collections.Counter(round(c["size"]) for c in ch).most_common(1)[0][0]
            out.append(dict(top=l["top"], bottom=l["bottom"], x0=l["x0"], x1=l["x1"], size=size))
    return out


def image_coverage(pdf):
    """Per page, the largest share of the page area one image covers (0..1).
    Empty list when pdfplumber is missing."""
    try:
        import pdfplumber
    except ImportError:
        return []
    out = []
    with pdfplumber.open(pdf) as doc:
        for pg in doc.pages:
            area = float(pg.width * pg.height) or 1.0
            best = 0.0
            for im in pg.images:
                w = min(im["x1"], pg.width) - max(im["x0"], 0)
                h = min(im["bottom"], pg.height) - max(im["top"], 0)
                best = max(best, max(0.0, w) * max(0.0, h) / area)
            out.append(best)
    return out


def scan_pages(texts, coverage, min_letters, full=0.85):
    """1-based numbers of the pages that need OCR: too few letters in the text
    layer, or a full-page picture (a scanner app's OCR layer is not trusted)."""
    return [i + 1 for i, t in enumerate(texts)
            if len(HEB.findall(t)) < min_letters or (i < len(coverage) and coverage[i] >= full)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--min", type=int, default=200, help="Hebrew letters for a page to count as text")
    a = ap.parse_args()
    n = page_count(a.pdf)
    texts = [page_text(a.pdf, i) for i in range(1, n + 1)]
    scanned = scan_pages(texts, image_coverage(a.pdf), a.min)
    if len(scanned) > max(1, n // 10):  # a blank or picture page or two is fine
        kind = "scan" if len(scanned) == n else "mixed"
        print(f"{kind}: {len(scanned)}/{n} pages have no text layer or are one full-page picture"
              " -> run the OCR pipeline"
              + (f" (scanned pages: {scanned})" if kind == "mixed" else ""))
        sys.exit(1)
    print(f"text: {n - len(scanned)}/{n} pages have a text layer -> skip OCR")
    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        try:
            import pdfplumber
            pages = pdfplumber.open(a.pdf).pages
        except ImportError:
            pages = None
            print("pdfplumber missing: paragraphs follow pdftotext only (pip install pdfplumber)")
        prev_md = ""
        limits, dropped = ([(0, p.height) for p in pages], set()) if not pages else pdf_blocks.running_bands(pages)
        if dropped:
            print("dropped running header/footer lines: " + "; ".join(sorted(dropped))[:300])
        img_dir = os.path.join(os.path.dirname(os.path.abspath(a.out_dir)), "img")
        n_tab = n_fig = 0
        for i, t in enumerate(texts, 1):
            if pages:
                pg = pages[i - 1]
                full = [g for g in geo_all(pg) if limits[i - 1][0] <= g["top"] and g["bottom"] <= limits[i - 1][1] + 1]
                stats = page_stats(full) if full else None
                parts = []
                for r in pdf_blocks.split_page(pg, a.pdf, i, fix_order, tidy, limits[i - 1], img_dir):
                    if r[0] == "md":
                        parts.append(r[3]); n_tab += r[3].startswith("|"); n_fig += r[3].startswith("![")
                    else:
                        s_ = layout_page(a.pdf, pg, i, (0, r[1], pg.width, r[2]), stats)
                        if s_.strip():
                            parts.append(s_.strip())
                md = "\n\n".join(parts) + "\n"
                # a short paragraph that is all bold with no final period is a heading
                md = re.sub(r"(?m)^\*\*([^*\n]{2,100}[^.*\n:])\*\*$", r"### \1", md)
            else:
                md = to_paragraphs(fix_order(t))
            # a page that starts mid-paragraph continues the previous one ("+")
            if prev_md and not re.search(r"[.?!:\")*]\s*$", prev_md) and not md.startswith(("#", "|", "![")):
                md = "+\n" + md
            prev_md = md
            with open(os.path.join(a.out_dir, f"{i:03d}.md"), "w", encoding="utf-8") as f:
                f.write(md)
        print(f"tables: {n_tab}, figures: {n_fig} (PNG in {img_dir})")
        print(f"wrote {n} page files to {a.out_dir}; spot-check one page's word order")


if __name__ == "__main__":
    main()
