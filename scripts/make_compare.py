#!/usr/bin/env python3
"""Stage 5 review aid: one self-contained HTML page with each scanned page next to its corrected text.

Usage: make_compare.py BOOK_DIR OUT_HTML --first-page 23
Uses BOOK_DIR/02_pages/*.png and BOOK_DIR/04_text_fixed/*.md.
"""
import argparse
import base64
import html
import io
import os
import re
import subprocess


def jpeg_b64(path, width=900):
    data = subprocess.run(["convert", path, "-resize", f"{width}x", "-quality", "70", "jpg:-"],
                          capture_output=True, check=True).stdout
    return base64.b64encode(data).decode()


def render(md):
    out = []
    for block in re.split(r"\n\s*\n", md.strip()):
        b = block.strip()
        if b == "+":
            continue
        if b.startswith("+\n"):
            out.append('<p class="cont">↩ המשך מהעמוד הקודם</p>')
            b = b[2:]
        cls = ""
        if b.startswith("[^"):
            cls = ' class="note"'
        t = html.escape(b)
        t = re.sub(r"\*([^*]+?)\*", r"<b>\1</b>", t)
        hm = re.match(r"^(#+) ", t)
        if hm:
            level = len(hm.group(1))
            label = {1: "כותרת ספר", 2: "כותרת פרק", 3: "כותרת משנה"}.get(level, "כותרת")
            out.append(f'<p class="h" data-l="{label}">{t[hm.end():]}</p>')
            continue
        out.append(f"<p{cls}>{t}</p>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("out_html")
    ap.add_argument("--first-page", type=int, default=1)
    args = ap.parse_args()
    rows = []
    for f in sorted(os.listdir(os.path.join(args.book_dir, "04_text_fixed"))):
        stem = f[:3]
        page = args.first_page + int(stem) - 1
        img = jpeg_b64(os.path.join(args.book_dir, "02_pages", stem + ".png"))
        md = open(os.path.join(args.book_dir, "04_text_fixed", f), encoding="utf-8").read()
        rows.append(f'<section id="p{page}"><h2>עמוד {page}</h2><div class="row">'
                    f'<img src="data:image/jpeg;base64,{img}" alt="סריקה עמוד {page}">'
                    f'<div class="text">{render(md)}</div></div></section>')
    nav = " ".join(f'<a href="#p{args.first_page + i}">{args.first_page + i}</a>' for i in range(len(rows)))
    doc = f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>השוואת סריקה וטקסט</title>
<style>
:root{{--bg:#ffffff;--fg:#1a1a1a;--muted:#666;--line:#d0d0d0;--link:#0b5cad}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#161616;--fg:#e8e8e8;--muted:#a0a0a0;--line:#3a3a3a;--link:#7ab7ff}}}}
:root[data-theme="dark"]{{--bg:#161616;--fg:#e8e8e8;--muted:#a0a0a0;--line:#3a3a3a;--link:#7ab7ff}}
body{{font-family:"David Libre","Frank Ruehl CLM",serif;margin:0 16px;background:var(--bg);color:var(--fg)}}
a{{color:var(--link)}}
nav{{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);line-height:2}}
nav a{{margin-inline-end:8px}}
.row{{display:flex;gap:16px;align-items:flex-start}}
.row img{{width:50%;max-width:600px;border:1px solid var(--line);background:#fff}}
.text{{flex:1;font-size:18px;line-height:1.6;min-width:0}}
.note{{font-size:15px;color:var(--muted);border-top:1px solid var(--line);padding-top:6px}}
.cont{{color:var(--muted);font-size:13px}}
.h{{font-weight:bold;text-align:center;margin:12px 0}}.h::before{{content:attr(data-l);display:block;font-size:12px;font-weight:normal;color:var(--muted)}}
@media (max-width:700px){{.row{{flex-direction:column}}.row img{{width:100%}}}}
</style></head><body><h1>השוואת סריקה וטקסט</h1><nav>{nav}</nav>{''.join(rows)}</body></html>"""
    with open(args.out_html, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print("wrote", args.out_html)


if __name__ == "__main__":
    main()
