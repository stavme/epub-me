#!/usr/bin/env python3
"""Stage 5a: join corrected page files into one pandoc-ready Markdown book.

Page-file conventions (04_text_fixed/NNN.md):
  - A first line "+" means the first paragraph continues the previous page's
    last paragraph (joined with a space).
  - "[^*]" in text is a footnote reference; "[^*]:" starts its note.
    References and notes are matched in order and renumbered globally.
  - "[^+]:" continues the previous note in the same paragraph;
    "[^+p]:" continues it with a new paragraph.
  - Continuation paragraphs of a note are indented 4 spaces.
  - "*...*" is emphasis. Emphasis with no Hebrew letters becomes a
    [..]{.foreign} span (italic Latin/German); Hebrew emphasis stays <em>.
  - Headings: "#", "##", "###".

Usage: assemble_book.py TEXT_DIR OUT_MD --first-page 23 [--page-markers]
"""
import argparse
import os
import re

HEB = re.compile(r"[א-ת]")


def split_page(raw):
    """Return (continues, body_blocks, note_blocks). note_blocks: list of (kind, [paras])."""
    lines = raw.rstrip("\n").split("\n")
    continues = bool(lines) and lines[0].strip() == "+"
    if continues:
        lines = lines[1:]
    blocks, cur = [], []
    for ln in lines:
        if ln.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(ln)
    if cur:
        blocks.append(cur)
    body, notes = [], []
    for b in blocks:
        first = b[0]
        m = re.match(r"\[\^(\*|\+|\+p)\]:\s*(.*)", first)
        if m:
            notes.append((m.group(1), [" ".join([m.group(2)] + [x.strip() for x in b[1:]])]))
        elif first.startswith("    ") and notes:
            notes[-1][1].append(" ".join(x.strip() for x in b))
        else:
            body.append(" ".join(x.strip() for x in b))
    return continues, body, notes


def inline(s):
    if s.strip() == "* * *":
        return '<p class="sep">✶</p>'
    # gershayim / geresh in abbreviations: X"Y inside a Hebrew word, X' after Hebrew
    s = re.sub(r'(?<=[א-ת])"(?=[א-ת])', "״", s)
    s = re.sub(r"(?<=[א-ת])'", "׳", s)

    # "(1) ..." must stay literal text, not become a pandoc ordered list
    s = re.sub(r"^\((\d+)\) ", r"\\(\1) ", s)

    def em(m):
        inner = m.group(1)
        return f"*{inner}*" if HEB.search(inner) else f"[{inner}]{{.foreign}}"
    return re.sub(r"\*([^*\n]+?)\*", em, s)


def marker(n):
    return f'<span epub:type="pagebreak" role="doc-pagebreak" id="page-{n}" aria-label="{n}"></span>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text_dir")
    ap.add_argument("out_md")
    ap.add_argument("--first-page", type=int, default=1)
    ap.add_argument("--page-markers", action="store_true")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.text_dir) if f.endswith(".md"))
    paras = []          # body paragraphs
    notes = []          # list of lists of paragraphs
    pending_marks = []
    ref_n = 0
    def_n = 0

    for f in files:
        page = args.first_page + int(f[:3]) - 1
        raw = open(os.path.join(args.text_dir, f), encoding="utf-8").read()
        continues, body, pnotes = split_page(raw)
        if args.page_markers:
            pending_marks.append(marker(page))

        def renum_refs(text):
            nonlocal ref_n
            def r(_):
                nonlocal ref_n
                ref_n += 1
                return f"[^{ref_n}]"
            return re.sub(r"\[\^\*\]", r, text)

        for i, p in enumerate(body):
            p = renum_refs(p)
            marks = "".join(pending_marks)
            pending_marks = []
            if i == 0 and continues and paras:
                paras[-1] = paras[-1] + " " + marks + p if marks else paras[-1] + " " + p
            elif p.startswith("#"):
                hashes, _, title = p.partition(" ")
                paras.append(f"{hashes} {marks}{title}")
            else:
                paras.append(marks + p)

        for kind, ps in pnotes:
            if kind == "*":
                def_n += 1
                notes.append((def_n, list(ps)))
            elif kind == "+":
                notes[-1][1][-1] += " " + ps[0]
                notes[-1][1].extend(ps[1:])
            else:  # +p
                notes[-1][1].extend(ps)

    if pending_marks:
        paras.append("".join(pending_marks))
    if ref_n != def_n:
        raise SystemExit(f"footnote mismatch: {ref_n} refs, {def_n} notes")

    out = []
    for p in paras:
        out.append(inline(p))
    out.append("")
    for n, ps in notes:
        first, rest = ps[0], ps[1:]
        out.append(f"[^{n}]: " + inline(first))
        for r in rest:
            out.append("\n    " + inline(r))
        out.append("")
    with open(args.out_md, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(out).replace("\n\n\n\n    ", "\n\n    ") + "\n")
    print(f"{len(paras)} paragraphs, {def_n} footnotes")


if __name__ == "__main__":
    main()
