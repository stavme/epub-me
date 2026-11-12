#!/usr/bin/env python3
"""Apply small text fixes to page files without retyping them.

FIXES is a TSV with one fix per line:  PAGE<TAB>OLD<TAB>NEW
  PAGE  a page number (7 or 007), a range (3-5), or * for every page
  OLD   exact text to find; it must occur exactly once per page it applies to
        unless the line starts with "all:" before PAGE (all:*  ina  in a)
  NEW   replacement; empty deletes OLD
  \\n in OLD or NEW stands for a line break, \\t for a tab.
Lines starting with # and blank lines are ignored.

Usage: replace_text.py PAGES_DIR FIXES [--dry-run]

Prints one short line per fix (page, count, and the change cut to 40
characters) and a total, never whole pages, so the output is cheap to read
and book text is not echoed back. Exits 1 if any fix found nothing or was
ambiguous; the other fixes are still written (unless --dry-run).
"""
import argparse
import os
import re
import sys

SNIP = 40


def short(s):
    s = s.replace("\n", "⏎")
    return s if len(s) <= SNIP else s[:SNIP - 1] + "…"


def unescape(s):
    return s.replace("\\n", "\n").replace("\\t", "\t")


def pages_for(spec, all_pages):
    if spec == "*":
        return all_pages
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", spec)
    if not m:
        raise ValueError(f"bad page spec {spec!r}")
    lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
    return [p for p in all_pages if lo <= p <= hi]


def parse(path):
    fixes = []
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            sys.exit(f"{path}:{i}: need PAGE<TAB>OLD<TAB>NEW, got {len(parts)} fields")
        spec, old, new = parts
        every = spec.startswith("all:")
        if every:
            spec = spec[4:]
        if not old:
            sys.exit(f"{path}:{i}: OLD is empty")
        fixes.append((i, spec, unescape(old), unescape(new), every))
    return fixes


def run(pages_dir, fixes_path, dry_run=False, out=sys.stdout):
    names = {int(n[:3]): n for n in os.listdir(pages_dir) if re.fullmatch(r"\d{3}\.md", n)}
    texts = {p: open(os.path.join(pages_dir, n), encoding="utf-8").read() for p, n in names.items()}
    changed, bad, total = set(), 0, 0
    for line_no, spec, old, new, every in parse(fixes_path):
        hits = 0
        for p in pages_for(spec, sorted(texts)):
            c = texts[p].count(old)
            if c == 0:
                continue
            if c > 1 and not every:
                print(f"AMBIGUOUS\tline {line_no}\t{p:03d}\t{c}x\t{short(old)}", file=out)
                bad += 1
                hits = -1
                break
            texts[p] = texts[p].replace(old, new)
            changed.add(p)
            hits += c
            print(f"{p:03d}\t{c}x\t{short(old)} → {short(new)}", file=out)
        if hits == 0:
            print(f"NOT FOUND\tline {line_no}\t{spec}\t{short(old)}", file=out)
            bad += 1
        total += max(hits, 0)
    if not dry_run:
        for p in changed:
            with open(os.path.join(pages_dir, names[p]), "w", encoding="utf-8") as f:
                f.write(texts[p])
    verb = "would change" if dry_run else "changed"
    print(f"{total} replacements, {verb} {len(changed)} pages, {bad} problems", file=out)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pages_dir")
    ap.add_argument("fixes")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.pages_dir, a.fixes, a.dry_run))


if __name__ == "__main__":
    main()
