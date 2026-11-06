#!/usr/bin/env python3
"""Pick a small sample of pages for a final look, instead of reviewing every page.

Chooses N pages: the page with the most queued words (most likely to hide a
miss) plus random others (fixed seed, so reruns agree). For each it writes a
700 px wide JPEG of the scan (about 1K tokens to view) next to the path of
its corrected text. Compare the two for dropped lines, wrong order, headers
left in, and structure (headings, footnotes, paragraphs).

Usage: sample_check.py PAGES_DIR TEXT_DIR QUEUE_DIR OUT_DIR [--n 2] [--seed 1]
"""
import argparse
import os
import random
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages")
    ap.add_argument("text")
    ap.add_argument("queue")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    stems = sorted(f[:-3] for f in os.listdir(a.text) if f.endswith(".md"))
    counts = {}
    for line in open(os.path.join(a.queue, "queue.txt"), encoding="utf-8"):
        if not line.startswith("#"):
            p = line.split("\t")[1]
            counts[p] = counts.get(p, 0) + 1
    pick = [max(stems, key=lambda s: counts.get(s, 0))]
    rest = [s for s in stems if s not in pick]
    random.Random(a.seed).shuffle(rest)
    pick += rest[:max(0, a.n - 1)]
    os.makedirs(a.out, exist_ok=True)
    for s in sorted(pick):
        src = next(os.path.join(a.pages, f) for f in os.listdir(a.pages) if f.startswith(s + "."))
        dst = os.path.join(a.out, s + ".jpg")
        subprocess.run(["convert", src, "-resize", "700x", "-quality", "70", dst], check=True)
        print(f"{s}\tscan={dst}\ttext={os.path.join(a.text, s + '.md')}\tqueued={counts.get(s, 0)}")


if __name__ == "__main__":
    main()
