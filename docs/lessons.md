# Lessons from the first manual run (Kant, "Perpetual Peace", 13 PDF pages → 24 book pages)

## Stage 1: page prep
- `pdfimages -list` showed each PDF page is built from 2-3 JPEG strips (~170 ppi), so extracting images is useless; render the page with `pdftoppm -r 300` instead.
- `pdftotext` returned nothing: no text layer.
- Tesseract OSD (`--psm 0`) detected orientation correctly on all pages. "Rotate: 270" means rotate 270° clockwise = ImageMagick `-rotate 270`. (I first applied 90 and got upside-down pages.)
- Spread detection by aspect ratio > 1.2 worked; gutter = minimum ink column in the 40-60% band.
- Each half had a different skew (−0.9° to 4°), confirming split-before-deskew. Skew search range must be ≥ ±6°; ±3° clipped.
- Page-number OCR on the bottom 7% strip (`-l eng --psm 6`) is a cheap sequence check: 23..46 continuous.
- Approval PDF: PNG pages gave 31 MB; JPEG q80 pages gave 9 MB.

## Stage 3: OCR
- Ubuntu's `tesseract-ocr-heb` is the fast model (0.9 MB). `tessdata_best/heb.traineddata` (3.7 MB) downloads from raw.githubusercontent.com (github.com/…/raw is blocked by the session proxy).
- With `--tessdata-dir`, copy `configs/` and `tessconfigs/` next to the model, or `tsv` output silently falls back to txt.
- **Do not use `preserve_interword_spaces=1` for Hebrew**: it drops the space between the last two words of every line ("אינםיכולים").
- psm 4 vs 6 and best vs fast gave nearly identical mean confidences (~85-90) and a similar error count (~5 per page) on the pilot, but the two models make *different* errors, so their word-level disagreements are a good review queue.
- Superscript footnote markers come out as stray letters/digits (ז, 1, +) glued to the word: always flag them.
- Hebrew text OCR was good (~5 errors/page); Latin/German words in parentheses came out as garbage with `-l heb` and had to be typed from the image. Next time try OCR-ing those spans separately with `-l eng` (or `deu`).
- Footnotes run across pages, sometimes for whole pages (31, 33, 35 were all footnote continuation). The tell is a short rule at the *top* of the page. Check every page top for it.
- Footnote markers seen: `*` (Kant's notes, kept), superscript digits and Hebrew letters (editor's endnotes, not in the excerpt, dropped).

## Page-file format (04_text_fixed/NNN.md)
See the docstring of `scripts/assemble_book.py`. Key rules: first line `+` = paragraph continues from previous page; `[^*]` ref / `[^*]:` note; `[^+]:` continues the previous note, `[^+p]:` continues it as a new paragraph; a word split across pages goes wholly on the earlier page; `* * *` = section break.

## Stage 4: checks
- hunspell he_IL flagged ~90 words, all legitimate (old spellings like היתה, foreign names). Useful mainly as a queue; no real errors left after manual correction.
- Doubled words "הוא הוא" / "היא היא" are idiomatic here.

## Stage 5: EPUB
- pandoc 3.1: pass metadata with `--metadata-file` (a YAML given as an input file is ignored). Use `-f markdown-smart` so " stays " instead of English curly quotes.
- "(1) text" at paragraph start becomes an ordered list in pandoc; escape as `\(1)`.
- pandoc sets lang="he" but not dir="rtl" on `<html>`; `fix_epub_rtl.py` adds it. CSS `direction` is forbidden by epubcheck.
- epubcheck 5.1.0 (from GitHub releases) passes with 0 errors.
- Font: David Libre (OFL) from raw.githubusercontent.com/google/fonts, embedded.
