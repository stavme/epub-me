#!/usr/bin/env python3
"""Stage 5a: join corrected page files into one pandoc-ready Markdown book.

Page-file conventions (04_text_fixed/NNN.md):
  - A first line "+" means the first paragraph continues the previous page's
    last paragraph (joined with a space). A later block whose first line is
    "+" continues the last text paragraph on the page (used when an image or
    box interrupts a paragraph in the scan).
  - "[^*]" in text is a footnote reference; "[^*]:" starts its note.
    References and notes are matched in order and renumbered globally.
  - "[^+]:" continues the previous note in the same paragraph;
    "[^+p]:" continues it with a new paragraph.
  - Continuation paragraphs of a note are indented 4 spaces.
  - "*...*" is emphasis. Emphasis with no Hebrew letters becomes a
    [..]{.foreign} span (italic Latin/German); Hebrew emphasis stays <em>.
  - Headings: "#", "##", "###", "####".
  - Raw blocks are kept line by line (not joined into one paragraph):
    fenced divs "::: box" ... ":::" (may contain blank lines, lists, headings,
    footnote refs), pipe tables ("| ..."), table captions (": ..."),
    list blocks ("1. ..." on every line) and images ("![caption](img/x.jpg)").
    A page marker before a raw block becomes its own tiny paragraph.
  - A box that runs across pages: the part on the next page opens with
    "::: +" instead of "::: box" and is merged into the previous box. If its
    first line is "+", the box's last paragraph continues (no paragraph break).

Usage: assemble_book.py TEXT_DIR OUT_MD --first-page 23 [--page-markers]
"""
import argparse
import os
import re

HEB = re.compile(r"[א-ת]")


LIST = re.compile(r"^\d+\. ")


def is_raw(block):
    first = block[0]
    return (first.startswith(":::") or first.startswith("|") or first.startswith(": ")
            or first.startswith("![") or all(LIST.match(x) for x in block))


def split_page(raw):
    """Return (continues, body_blocks, note_blocks). note_blocks: list of (kind, [paras]).
    Raw blocks come back as strings that start with "\x00" and keep their newlines."""
    lines = raw.rstrip("\n").split("\n")
    continues = bool(lines) and lines[0].strip() == "+"
    if continues:
        lines = lines[1:]
    blocks, cur, in_div = [], [], False
    for ln in lines:
        if in_div:
            cur.append(ln)
            if ln.strip() == ":::":
                blocks.append(cur)
                cur, in_div = [], False
        elif ln.startswith("::: "):
            if cur:
                blocks.append(cur)
            cur, in_div = [ln], True
        elif ln.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(ln)
    if in_div:
        raise SystemExit("unclosed ::: div")
    if cur:
        blocks.append(cur)
    body, notes = [], []
    for b in blocks:
        if is_raw(b):
            body.append("\x00" + "\n".join(b))
            continue
        if b[0].strip() == "+" and len(b) > 1:  # mid-page: join the last text paragraph
            body.append("\x01" + " ".join(x.strip() for x in b[1:]))
            continue
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
    s = s.replace("<br>", "<br />")  # EPUB is XHTML: void tags must self-close
    if s.startswith("\x00"):
        out = []
        for ln in s[1:].split("\n"):
            if ln.startswith(":::") or re.fullmatch(r"\|[-|: ]+\|", ln) or ln.strip() == "":
                out.append(ln)
            else:
                out.append(inline(ln))
        return "\n".join(out)
    if s.strip() == "* * *":
        return '<p class="sep">✶</p>'
    # gershayim / geresh in abbreviations: X"Y inside a Hebrew word, X' after Hebrew
    def gersh(m):
        # an opening quote after prefix letters (ב"סכסוך ..." / ו"מהפכת ...") stays a quote
        before = re.search(r"[א-ת]+$", s[:m.start()]).group()
        if re.fullmatch(r"[בהוכלמש]{1,3}", before) and '"' in s[m.end():m.end() + 120]:
            return '"'
        return "״"
    s = re.sub(r'(?<=[א-ת])"(?=[א-ת])', gersh, s)
    s = re.sub(r"(?<=[א-ת])'", "׳", s)

    # "(1) ..." must stay literal text, not become a pandoc ordered list
    s = re.sub(r"^\((\d+)\) ", r"\\(\1) ", s)

    def em(m):
        inner = m.group(1)
        return f"*{inner}*" if HEB.search(inner) else f"[{inner}]{{.foreign}}"
    return re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", em, s)


def box_index(paras):
    for j in range(len(paras) - 1, -1, -1):
        if paras[j].startswith("\x00:::"):
            return j
    raise SystemExit('"::: +" with no box before it')


def merge_box(box, cont, marks):
    """Append the inside of continuation div CONT to raw div BOX (both "\x00:::...")."""
    head = box.rstrip("\n").split("\n")[:-1]          # drop the closing :::
    body = cont.rstrip("\n").split("\n")[1:-1]        # drop "::: +" and ":::"
    joined = bool(body) and body[0].strip() == "+"
    if joined:
        body = body[1:]
        if marks and body:
            body[0] = marks + body[0]
    else:
        body = ([marks, ""] if marks else []) + body
        head.append("")
    return "\n".join(head + body + [":::"])


def marker(n):
    return f'<span epub:type="pagebreak" role="doc-pagebreak" id="page-{n}" aria-label="{n}"></span>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text_dir")
    ap.add_argument("out_md")
    ap.add_argument("--first-page", type=int, default=1)
    ap.add_argument("--page-markers", action="store_true")
    ap.add_argument("--page-map", help='JSON {"NNN": book_page} for files whose page is not first_page + index (duplicates, gaps)')
    ap.add_argument("--no-marker", nargs="*", default=[], help="page files (NNN) that get no page marker")
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(args.text_dir) if f.endswith(".md"))
    import json
    page_map = json.load(open(args.page_map)) if args.page_map else {}
    paras = []          # body paragraphs
    notes = []          # list of lists of paragraphs
    pending_marks = []
    ref_n = 0
    def_n = 0

    for f in files:
        page = page_map.get(f[:3], args.first_page + int(f[:3]) - 1)
        raw = open(os.path.join(args.text_dir, f), encoding="utf-8").read()
        continues, body, pnotes = split_page(raw)
        if args.page_markers and f[:3] not in args.no_marker:
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
            if p.startswith("\x00::: +"):
                paras[box_index(paras)] = merge_box(paras[box_index(paras)], p, marks)
            elif p.startswith("\x01"):
                j = max(k for k, q in enumerate(paras) if not q.startswith("\x00"))
                paras[j] = paras[j] + " " + marks + p[1:]
            elif p.startswith("\x00"):
                if marks:
                    paras.append(marks)
                paras.append(p)
            elif i == 0 and continues and paras:
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
