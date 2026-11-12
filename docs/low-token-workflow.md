# Low-token workflow

Goal: spend tokens only where a human eye is needed. Scripts do everything
else from disk, and page images never enter the main conversation.

## Where tokens went before

- Every page image was opened in the main conversation and stayed in context
  for the rest of it, so it was paid for again on every later step.
- Every page was retyped in full (output tokens are the expensive ones).
- Each book re-derived setup (apt proxy, tessdata, epubcheck) and debugged scripts.
- Visual QA of the comparison page and the EPUB.

## Short version: two commands

```
scripts/convert.sh start  SOURCE BOOK [--lang en]   # PDF, photo folder, or "dropbox:FILE NAME"
# scans only: helper agent (Sonnet) writes BOOK/03_queue/fixes.txt
# structure pass on BOOK/04_text_fixed (step 6; subagents for long chapters)
scripts/convert.sh finish BOOK "TITLE" "AUTHOR" NAME [--first-page N] [--lang en] [--upload]
```

English book (scan or text PDF): pass `--lang en` to both commands. With
several files in the Dropbox inbox, name the file: `start "dropbox:Adobe Scan
8 Nov 2026.pdf" BOOK`; plain `dropbox` is refused unless the inbox holds one
file, because it would fetch (and move to `/inbox/done`) every file.

Every tool call re-reads the whole conversation (over 95% of a thread's
tokens on 2026-11-06), so a conversion thread should be a handful of calls:
start, helper agent, a few structure edits, finish. Don't debug or extend the
scripts inside a conversion thread; note the problem and fix it separately.

## Steps

- **Intake**: don't attach scans to the conversation (an attachment is read
  into context). Drop them in Dropbox `Apps/EpubMe/inbox` and run
  `dropbox_fetch.py BOOK/00_src --name FILE`; the file moves to `/inbox/done`
  afterwards. `dropbox_fetch.py --list` (or `--keep`) to only look.
0. **Text or scan?** `check_pdf.py FILE.pdf BOOK/04_text_fixed`. If the PDF
   already has a text layer (born-digital), it writes the page files directly
   and steps 2-5 and 7 are skipped: go to structure (6) and build (8) after a
   look at one page's word order. A "scan" or "mixed" result runs the full
   pipeline (for "mixed", only the listed pages need OCR).
   With pdfplumber installed (setup_env.sh does it), the text pages also get
   structure from the PDF itself: paragraph breaks from line gaps and short
   lines, `#`/`##`/`###` from type size, `**bold**` from bold fonts (word by
   word), `+` when a page starts mid-paragraph, and Latin/number runs put back
   in logical order (`(diversity)`, `ב־184`, `(עזר, 2004)`). Running headers and page
   numbers are dropped (the script prints which lines), ruled tables become pipe
   tables, and charts/images are rendered to `BOOK/img/` and referenced as
   `![caption](img/...)`. English book: `finish ... --lang en` (LTR build + `check_en.py`).
   Never OCR a PDF that has a text layer.
1. **Setup** (once per container, ~20 s): `scripts/setup_env.sh`.
   It can also be pasted into the cloud environment's setup script.
2. **Prep**: rotate to upright (`tesseract --psm 0`), then
   `prep_pages.py 01_upright BOOK`. If it prints a gutter WARNING, look at a
   500 px thumbnail of that spread only and rerun with `--gutter FILE=X`.
3. **OCR + queue**: `review_queue.py BOOK/02_pages_ocr BOOK/03_queue --tessdata ~/.epub-tools/tessdata`.
   Mechanical fixes (maqaf, dashes, spaces before punctuation) are applied
   automatically; running headers and page numbers go to `headers.txt`.
4. **Fixes by a helper agent**: start a subagent (Sonnet is enough) with the
   prompt below. It views `sheets/*.png` (about 1.3K tokens each, 40 words per
   sheet) and `queue.txt`, and writes `fixes.txt`. The main conversation never
   sees an image; it only gets back "N fixes, M guesses".
5. **Apply**: `apply_fixes.py BOOK/03_queue BOOK/03_queue/fixes.txt BOOK/04_text_fixed`.
   `?` guesses land in `uncertain.txt` for the reader.
6. **Structure**: headings, boxes, footnotes `[^*]`, page continuation `+`,
   emphasis, tables, figures. A few pages: do it yourself with Edit on the
   small spots, text only. More than ~10 pages: one Sonnet subagent per 12
   pages with the structure-agent prompt below. Never retype a page.
7. **Sample check**: `sample_check.py BOOK/02_pages BOOK/04_text_fixed BOOK/03_queue BOOK/sample --n 2`
   and look at only those two 700 px scans against their text.
8. **Build and deliver**: `build_epub.sh`, epubcheck, `make_compare.py` (for
   the reader, not for Claude), `dropbox_upload.py`.

## Helper-agent prompt (fill in the paths and book description)

> You are proofreading Hebrew OCR (for an English book: English OCR; skip the
> maqaf rule). Work only with the files named here.
> queue.txt is tab-separated: n, page, primary (OCR), alt (second model), conf,
> why, context ([*] marks the item). why=missing: only the second model saw it;
> why=uncovered: ink no model read. sheets/sNN.png show n on the left and the
> printed line with the item boxed in red. Read queue.txt, then view every sheet.
> Write fixes.txt with one line per item whose primary reading is wrong:
> `n text` (exact print, maqaf ־, dash —), `n -` (junk), `n ?reconstruction`
> (cut or illegible; reconstruct from context). Skip correct items; ASCII "-"
> vs maqaf needs no line. Reply only with the number of lines and of '?' lines.

## Structure-agent prompt (fill in BOOK, the page range, and the book description)

Each rule says when it applies. A rule whose condition doesn't hold on a page
is skipped, and a case that fits no rule goes to the doubts list, not to a guess.

> You are adding structure to Hebrew page files of a scanned book. Work only on
> BOOK/04_text_fixed/NNN.md for pages FROM-TO; the scan of each is
> BOOK/02_pages/NNN.png (view each once). The page-file format is the docstring
> of scripts/assemble_book.py. Change only the spots below with Edit; the
> wording is already proofread, so never retype a page.
>
> - **Headings**: `#`..`####`. With numbered sections (1.2.3), the level is the
>   depth of the number; otherwise use type size relative to the other headings.
>   A level you guessed goes to the doubts list.
> - **Footnotes**: a note marked `*` (margin or foot of page) becomes
>   `[^*]` + `[^*]:`. A digit or letter marker whose note text is not on these
>   pages (an endnote outside the excerpt) is deleted. Digit or letter notes
>   whose text *is* on the page are kept as `[^*]` too.
> - **Letter-spaced words** (ר ו ו ח between letters) become `**bold**` when
>   letter-spacing is the book's emphasis style: the spaced word sits inside
>   normally set running text. Spacing that only fills a justified short line,
>   or the design of a heading or title, stays as normal text.
> - **Boxes**: a framed or shaded box is `::: box` ... `:::`, placed where it
>   sits in the reading order. When a box runs onto the next page, open the
>   part on the next page with `::: +` (first line `+` if a paragraph is cut
>   mid-sentence). Numbered lists inside boxes are plain `1. ` lines; the build
>   sets RTL.
> - **Tables**: a ruled grid in the scan becomes a pipe table with `: caption`.
>   Text set in columns without a grid stays paragraphs.
> - **Figures**: photos, cartoons and charts are cropped from the original
>   color render BOOK/00_src (not 02_pages) into BOOK/img/pNNN-K.png and written
>   as `![printed caption](img/pNNN-K.png)`. A paragraph the figure interrupts
>   continues after it with a `+` line.
> - **Running headers and page numbers** that survived OCR: delete a line that
>   repeats the book or chapter title at the top or bottom edge of many pages.
>   A real heading that happens to sit at the top of a page stays.
> - **Latin citations** printed reversed inside Hebrew text
>   (`(Richmond, 2005 ;2001`) are put in logical order. Hebrew is untouched.
> - **English text only**: a lone `|` where the language has no use for one
>   (running prose, not a table, formula or code) is `I`; glued words like
>   `ina`/`ofthe` are split. `finish --lang en` lists them via check_en.py.
>
> Done when every page in the range has been opened next to its scan and every
> box, heading, note, table and figure on the scan is in the file. Reply with
> one line of counts (headings, boxes, notes, tables, figures) and a list of
> doubts as `NNN: what and why`.

## Measured on Hobbes ch. 13 (7 pages, 1,480 words), 2026-11-06

- Queue: 325 of 1,560 OCR words (~46 per page) on 9 sheets. It holds about
  85% of the OCR errors; the rest are letters the photocopier cut off and
  words OCR dropped at line edges.
- Helper agent (Sonnet, 12 tool calls, ~94K tokens counted across its calls,
  mostly cached re-reads; the 9 sheets themselves are ~13K image tokens).
  The main conversation received one line back.
- Word errors against the hand-corrected text: 209 in raw OCR, 108 after the
  fixes. What remains is mostly reconstruction of cut letters and a few lines
  out of order on the worst page; the hand-corrected run fixed those by reading
  full pages. On a clean scan this gap should be much smaller; the sample
  check (step 7) is where it gets caught.
