#!/usr/bin/env python3
"""Turn an open-access journal article page (HTML) into page files for the book build.

Usage: html_article.py SOURCE BOOK_DIR
  SOURCE: an https URL or a saved .html file.
Writes BOOK/04_text_fixed/001.md (the whole article as one "page file", format in
assemble_book.py), the figures to BOOK/img/, and BOOK/source.url (its presence makes
`convert.sh finish` skip page markers and page-number guessing). Prints the
TITLE and AUTHOR to pass to `convert.sh finish`.

Understands the Cambridge Core article layout (citation_* meta tags, `div.abstract`,
`div.sec` sections, `div.fig-ada` figures, numbered footnotes in `#footnotes-list`).
For other pages it falls back to <article>/<main> with h2/h3, p, lists and figure
elements, and no footnotes. Never OCR: the text comes from the page itself.
"""
import os
import re
import subprocess
import sys
import urllib.parse

from bs4 import BeautifulSoup, NavigableString, Tag


def fetch(url):
    r = subprocess.run(["curl", "-sSL", "--fail", "-m", "90", "-A", "Mozilla/5.0", url],
                       capture_output=True)
    if r.returncode:
        raise SystemExit(f"download failed ({r.returncode}): {url}\n{r.stderr.decode()[:200]}")
    return r.stdout


def esc(t):
    t = re.sub(r"([\\\[\]<_*])", r"\\\1", t)
    t = re.sub(r"\s+", " ", t)
    return t


def inline(node):
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            if c.__class__.__name__ in ("Comment", "Doctype"):
                continue
            out.append(esc(str(c)))
        elif isinstance(c, Tag):
            cls = c.get("class") or []
            if "show-for-sr" in cls or c.name in ("script", "style"):
                continue
            if c.name == "a" and "fn" in cls:
                out.append("[^*]")
            elif c.name in ("em", "i"):
                inner = inline(c).strip()
                out.append(f" *{inner}* " if inner else "")
            elif c.name in ("strong", "b"):
                inner = inline(c).strip()
                out.append(f" **{inner}** " if inner else "")
            elif c.name == "br":
                out.append(" ")
            else:
                out.append(inline(c))
    s = "".join(out)
    # " *x* " added spaces around emphasis: drop them next to punctuation or edges
    s = re.sub(r" (\*+)([^*]+?)(\*+) (?=[\s.,;:!?)’”\]'\"]|$)", r" \1\2\3", s)
    s = re.sub(r"(?<=[(‘“\[]) (\*+)", r"\1", s)
    return re.sub(r" {2,}", " ", s)


def para(node):
    s = inline(node).strip()
    s = re.sub(r"^([+\-#>|:!]|\d+\.)", r"\\\1", s)  # keep it a plain paragraph
    return s


def fig_block(fig, imgdir, base):
    cap = fig.select_one(".caption")
    label = cap.select_one(".label") if cap else None
    text = ""
    if cap:
        text = re.sub(r"\s+", " ", cap.get_text(" ", strip=True))
    img = fig.find("img")
    src = img and (img.get("data-src") or img.get("src"))
    if not src or src.startswith("data:"):
        return None
    src = urllib.parse.urljoin(base, src)
    clean = urllib.parse.urlunparse(urllib.parse.urlparse(src)._replace(query=""))
    m = re.search(r"_(fig\d+)\.(\w+)$", clean)
    name = f"{m.group(1)}.{m.group(2)}" if m else os.path.basename(clean)
    os.makedirs(imgdir, exist_ok=True)
    open(os.path.join(imgdir, name), "wb").write(fetch(src if "pub-status" in src else clean))
    alt = text.replace("[", "(").replace("]", ")") or "Figure"
    return f"![{alt}](img/{name})"


def meta(soup, name):
    return [m["content"].strip() for m in soup.find_all("meta", attrs={"name": name}) if m.get("content")]


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    title = (meta(soup, "citation_title") or [None])[0]
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else "Article")
    authors = ", ".join(meta(soup, "citation_author"))

    notes = {}
    fl = soup.select_one("#footnotes-list")
    if fl:
        for it in fl.select('[id^="fn"]'):
            p = it.select_one("p.p") or it
            lab = p.select_one(".label")
            if lab:
                lab.decompose()
            notes[it["id"]] = inline(p).strip()

    abstract = soup.select_one("div.abstract")
    kw = soup.select_one("div.keywords")
    secs = [d for d in soup.find_all("div", class_="sec")
            if re.fullmatch(r"sec\d+", d.get("id", "")) and d.get("id") != "sec0"]
    ack = soup.select_one("div.ack")
    roots = []
    if abstract:
        roots.append(("abstract", abstract))
    roots += [("sec", s) for s in secs]
    if ack:
        roots.append(("sec", ack))
    if not secs:  # generic page
        art = soup.find("article") or soup.find("main") or soup.body
        roots = [("sec", art)]

    return soup, title, authors, notes, roots, kw


def build(html, base, book):
    soup, title, authors, notes, roots, kw = parse(html)
    imgdir = os.path.join(book, "img")
    blocks, refs = [], []
    stats = {"figures": 0, "lists": 0}

    def walk(node):
        for c in node.children:
            if not isinstance(c, Tag):
                continue
            cls = c.get("class") or []
            if c.name in ("h2", "h3", "h4"):
                blocks.append("#" * (int(c.name[1])) + " " + inline(c).strip())
            elif c.name == "p":
                s = para(c)
                if s:
                    blocks.append(s)
                    refs.extend(a.get("href", "")[1:] for a in c.select("a.xref.fn"))
            elif c.name in ("ol", "ul"):
                stats["lists"] += 1
                for li in c.find_all("li", recursive=False):
                    s = para(li)
                    blocks.append(s)
                    refs.extend(a.get("href", "")[1:] for a in li.select("a.xref.fn"))
            elif "fig-ada" in cls:
                b = fig_block(c, imgdir, base)
                if b:
                    stats["figures"] += 1
                    blocks.append(b)
            elif c.name in ("div", "section", "article", "main", "figure"):
                walk(c)

    for kind, root in roots:
        if kind == "abstract":
            blocks.append("## Abstract")
        walk(root)
        if kind == "abstract" and kw:
            words = [esc(x.get_text(" ", strip=True)) for x in kw.find_all(["a", "li", "span"])
                     if not x.find(["a", "li", "span"]) and x.get_text(strip=True) and x.get_text(strip=True) != "Keywords"]
            if not words:
                words = [re.sub(r"^Keywords\s*", "", kw.get_text(" ", strip=True))]
            blocks.append("**Keywords:** " + ", ".join(dict.fromkeys(words)))

    missing = [r for r in refs if r not in notes]
    if missing:
        raise SystemExit(f"footnote references without a note: {missing[:5]}")
    out = list(blocks)
    for r in refs:
        out.append(f"[^*]: {notes[r]}")
    os.makedirs(os.path.join(book, "04_text_fixed"), exist_ok=True)
    text = "\n\n".join(out) + "\n"
    open(os.path.join(book, "04_text_fixed", "001.md"), "w", encoding="utf-8").write(text)
    return title, authors, len(refs), stats, len(notes)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src, book = sys.argv[1:]
    if re.match(r"https?://", src):
        html, base = fetch(src), src
    else:
        html, base = open(src, "rb").read(), "file://" + os.path.abspath(src)
    title, authors, nrefs, stats, nnotes = build(html, base, book)
    os.makedirs(book, exist_ok=True)
    open(os.path.join(book, "source.url"), "w").write(src + "\n")
    print(f"article: {nrefs} footnote refs ({nnotes} notes on page), {stats['figures']} figures, {stats['lists']} lists")
    print(f"TITLE: {title}")
    print(f"AUTHOR: {authors}")


if __name__ == "__main__":
    main()
