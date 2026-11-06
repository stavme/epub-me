#!/usr/bin/env python3
"""Merge a short fixes list into the drafts made by review_queue.py.

FIXES has one line per queued word that needs a change:
  17 מדינה          replace word 17 (may be several words)
  17 -              delete it
  17 ?מדינה         best guess, also listed in uncertain.txt
Words not listed keep the primary OCR reading; "missing" and "uncovered"
items that are not listed are dropped. Lines starting with # are ignored.

Usage: apply_fixes.py QUEUE_DIR FIXES OUT_DIR
Writes OUT_DIR/NNN.md (clean text, no markers) and OUT_DIR/uncertain.txt.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from review_queue import normalize_text  # noqa: E402

MARK = re.compile(r"\{\{(\d+):([^}]*)\}\}")


def main():
    qdir, fixes_path, out = sys.argv[1:4]
    fixes = {}
    for line in open(fixes_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"(\d+)[\s:.)-]+(.*)$", line)
        if not m:
            sys.exit(f"bad fixes line: {line!r}")
        fixes[int(m.group(1))] = m.group(2).strip()
    os.makedirs(out, exist_ok=True)
    uncertain, used = [], set()
    draft = os.path.join(qdir, "draft")
    for name in sorted(os.listdir(draft)):
        text = open(os.path.join(draft, name), encoding="utf-8").read()

        def sub(m):
            n = int(m.group(1))
            if n not in fixes:
                return m.group(2)
            used.add(n)
            v = fixes[n]
            if v == "-":
                return ""
            if v.startswith("?"):
                v = v[1:]
                uncertain.append(f"{name[:-3]}: {v}")
            return v

        text = MARK.sub(sub, text)
        paras = [normalize_text(re.sub(r"[ \t]+", " ", p).strip()) for p in text.split("\n\n")]
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write("\n\n".join(p for p in paras if p) + "\n")
    unknown = sorted(set(fixes) - used)
    if unknown:
        print("warning: fixes for unknown items:", unknown, file=sys.stderr)
    with open(os.path.join(out, "uncertain.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(uncertain) + ("\n" if uncertain else ""))
    print(f"applied {len(used)} fixes, {len(uncertain)} uncertain")


if __name__ == "__main__":
    main()
