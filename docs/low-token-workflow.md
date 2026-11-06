# Low-token workflow

Goal: spend tokens only where a human eye is needed. Scripts do everything
else from disk, and page images never enter the main conversation.

## Where tokens went before

- Every page image was opened in the main conversation and stayed in context
  for the rest of it, so it was paid for again on every later step.
- Every page was retyped in full (output tokens are the expensive ones).
- Each book re-derived setup (apt proxy, tessdata, epubcheck) and debugged scripts.
- Visual QA of the comparison page and the EPUB.

## Steps

0. **Text or scan?** `check_pdf.py FILE.pdf BOOK/04_text_fixed`. If the PDF
   already has a text layer (born-digital), it writes the page files directly
   and steps 2-5 and 7 are skipped: go to structure (6) and build (8) after a
   look at one page's word order. A "scan" or "mixed" result runs the full
   pipeline (for "mixed", only the listed pages need OCR).
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
6. **Structure** (text only, no images): headings, footnotes `[^*]`, page
   continuation `+`, emphasis. Edit the small spots with Edit; never retype a page.
7. **Sample check**: `sample_check.py BOOK/02_pages BOOK/04_text_fixed BOOK/03_queue BOOK/sample --n 2`
   and look at only those two 700 px scans against their text.
8. **Build and deliver**: `build_epub.sh`, epubcheck, `make_compare.py` (for
   the reader, not for Claude), `dropbox_upload.py`.

## Helper-agent prompt (fill in the paths and book description)

> You are proofreading Hebrew OCR. Work only with the files named here.
> queue.txt is tab-separated: n, page, primary (OCR), alt (second model), conf,
> why, context ([*] marks the item). why=missing: only the second model saw it;
> why=uncovered: ink no model read. sheets/sNN.png show n on the left and the
> printed line with the item boxed in red. Read queue.txt, then view every sheet.
> Write fixes.txt with one line per item whose primary reading is wrong:
> `n text` (exact print, maqaf ־, dash —), `n -` (junk), `n ?reconstruction`
> (cut or illegible; reconstruct from context). Skip correct items; ASCII "-"
> vs maqaf needs no line. Reply only with the number of lines and of '?' lines.

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
