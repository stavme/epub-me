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

## Second book: Schiff, "יישוב סכסוכים בזירה הבינלאומית" ch. 1 (textbook, 49 phone photos)
Textbook layout: margin notes, framed boxes, tables, photos, cartoons, charts, lists. What changed in the process:

### Environment
- apt in the cloud container ignores the proxy and uses http sources. Fix: `/etc/apt/apt.conf.d/99proxy` with `Acquire::http::Proxy` and `Acquire::https::Proxy` set to `$HTTPS_PROXY`, switch `/etc/apt/sources.list.d/ubuntu.sources` to https, and move docker.list aside. Then `apt-get install tesseract-ocr hunspell-he epubcheck` work. pypi stays blocked, so scripts use only numpy + Pillow (no opencv).
- Debian's `/usr/bin/epubcheck` is a jar: run `java -jar /usr/bin/epubcheck FILE`, and give it an ASCII file name (a Hebrew name fails with "File not found" under the default locale).
- Headless Chromium here paints a blank page for any document with `dir="rtl"`; drop the attribute when taking QA screenshots.

### OCR
- Phone photos bend: the main column, margin notes and boxes sit at different angles (e.g. 2.0°, -1.2°, 0.9° on one page). `ocr_regions.py` runs a Tesseract layout pass, deskews each block separately, then OCRs it with psm 6. Quality was good enough to correct from.
- Detect duplicate or missing photos by grepping running-header page numbers in the OCR output. Here one page was photographed twice (deleted) and the mapping is passed as `--page-map page_map.json` to `assemble_book.py` and `make_compare.py`.
- A photo can cut off a heading or the edge of a margin note. Mark it in the text (`[שם הסעיף נחתך בצילום]`) and list reconstructed words in `uncertain.txt` for the reader.
- `check_vs_ocr.py` lists corrected words that are not within one edit of any OCR word on that page: a fast typo queue. Boxes moved from the next page show up as expected noise.

### Structure (page-file additions)
- `::: box` ... `:::` for framed boxes; a box that runs across pages continues on the next page with `::: +` (assemble_book merges the parts; Schiff ch. 2 had them split into two boxes each).
- Margin notes with `*` become footnotes; caption-only margin text becomes the image caption.
- `![caption](img/NAME.jpg)` for figures; a later block that starts with `+` continues the last paragraph when a figure interrupts it.
- Pipe tables with `: caption`; list cells use `• item<br>` (assemble_book turns `<br>` into XHTML `<br />`, otherwise epubcheck fails).
- Citations printed in RTL come out reversed (`(Richmond, 2005 ;2001`); write them in logical order.
- pandoc turns a fenced div that starts with a heading into `<section class="level4 box">`, so CSS must target `.box`, not `div.box`.

### Figures
- Crop photos from the ORIGINAL images (`00_render`), not from the cleaned grayscale pages: the cleanup washes photos out and drops color (two cartoons and two photos here are in color). Coordinates in `figs_orig.txt` with a light `-level`; line art can come from `02_pages` with a stronger level (`crops.txt`).
- To find coordinates fast: 20% thumbnails with a 200 px grid, then a 25% preview montage of the crops.

## Delivery and intake (both books)
- Finished EPUBs go to Dropbox `Apps/EpubMe` with `scripts/dropbox_upload.py FILE [/dest]`. It needs DROPBOX_APP_KEY, DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN in the cloud environment, network access to api.dropboxapi.com and content.dropboxapi.com, and app scopes files.content.write/read. The Google Drive connector can't upload binary EPUBs.
- Check every upload with `file` (magic bytes) before choosing a pipeline. Course files come from a Moodle site; a link saved while logged out gives an HTML login page that still carries the expected name and extension (e.g. `.docx`).

## Feedback on Schiff ch. 1 and Hofstede (2026-11-10) and what changed in the scripts
- **RTL lists in boxes** (Schiff): numbers in the grey boxes' lists ran left-to-right on the Boox. `epub.css` now sets `direction: rtl` on lists, boxes, tables and asides, and `fix_epub_rtl.py` adds `dir="rtl"` to `ol/ul/li/table/section/aside/figure/blockquote`, because that reader doesn't inherit direction from `<html>`. After a build, open a page with a numbered list in a box. Not yet confirmed on the device; if numbers are still wrong, check there first.
- **Born-digital PDF: never OCR it, and never retype it.** Hofstede has a clean text layer, but the delivered EPUB had `ina` for `in a` and `|` for `I`: typical slips of OCR or of reading page images. `convert.sh start` now takes the text layer for any PDF (English too: letters of any script count). `check_en.py` (run by `finish --lang en`) lists lone `|`, glued words (`ina`, `ofthe`; with hunspell en_US also any unknown word that splits into two known ones) and repeated lines.
- **Running headers/footers** (publication name on every page): `pdf_blocks.running_bands` drops lines in the top/bottom 15% that repeat (digits ignored) on at least 40% of the pages, so page numbers and alternating even/odd headers go too. The script prints what it dropped; for a scan, `headers.txt` has the same job. Check that list: a real heading that repeats would be dropped too.
- **Tables stay tables.** For text PDFs, ruled tables (booktabs or full grid) become pandoc pipe tables with `: caption`; cells are read per cell, so wrapped cells stay whole; Hebrew tables get the column order reversed so the first column is on the right; column widths follow the dashes. Decorative rules (a cover page) are rejected when fewer than 60% of rows have two filled cells. For scans, keep writing pipe tables by hand (see Schiff above); never join cells with ` | ` in a paragraph.
- **Charts stay charts.** Images and clusters of 8+ vector objects are rendered at 150 dpi to `BOOK/img/fig-pNN-K.png` and written as `![caption](img/...)`; a "Figure/Chart/איור/תרשים N" caption next to it is included in the image and the alt text. A chart made only of text is not detected; check pages with `Figure` in the text. For scans, crop from the original photos (see Figures).
- **English books**: `convert.sh finish ... --lang en` builds LTR (no Hebrew font, `epub-ltr.css`, no `dir="rtl"`); the default stays Hebrew.
- Tested on the Hofstede PDF (26 pages): 6 of 6 tables, headers/footers gone, 0 figures (it has none); and on a hand-made PDF with a vector chart. The old EPUBs were not rebuilt (Stav: only the lessons are needed).

## English PDFs (2026-11-12): three phone scans from Adobe Scan, 7, 2 and 23 pages
What went wrong and what changed:
- **English scans went through Hebrew OCR.** `convert.sh start` had no language option: it ran `heb`, put words, columns and spread pages right to left, and gave 3,489 junk queue items on 7 pages. The threads OCR'd by hand with `tesseract -l eng` and skipped the queue, so there was no queue-based sample check either. Now `convert.sh start ... --lang en` runs eng OCR with left-to-right words, lines, paragraphs (indent at the left, short last line at the right), columns, spread order (`prep_pages.py --ltr`), sheet crops and the en_US dictionary pass. On the 7-page scan: 174 queue items on 5 sheets, ~2 minutes. `setup_env.sh` downloads tessdata_best `eng` (15 MB); without it review_queue warns and uses the distro model, so only low-confidence and dictionary words are queued.
- **Scanner-app PDFs carry an OCR text layer.** Adobe Scan (and CamScanner) put their own OCR text under the photo, so `check_pdf.py` called the 2-page PDF born-digital and took the noisy layer. A page covered by one picture (≥ 85% of its area) now counts as a scan. When it applies: any PDF whose pages are photos; a born-digital PDF with a full-page figure on a page or two stays "text" (up to 10% scanned pages are allowed).
- **Several inbox files.** `convert.sh start dropbox` downloaded every inbox file, moved them all to `/inbox/done`, and used the first, so parallel threads couldn't find their own book, and old books still in the inbox could be picked. Use `start "dropbox:NAME"` (`dropbox_fetch.py --name NAME`); plain `dropbox` is refused with more than one file.
- **Fixes made inside a conversion thread got lost.** The 23-page thread fixed the right-to-left word order for English in its own container and never pushed it. Script fixes go to a branch and a PR (or a note to the coordinator), never only into a conversion container.
- **Content filter.** The 23-page thread failed twice with "Output blocked by content filtering policy" after retyping pages; see "Never retype pages" in `low-token-workflow.md`.
- **Page numbers on English scans.** The running header line holds the page number with text ("14 Chapter 1"), so `headers.txt` stays empty and `finish` can't guess the first page: pass `--first-page` (the printed number of the first page). Leftover running headers are removed in the structure pass.
- English builds need the fonts embedded (PR #7), or epubcheck fails RSC-007.
