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
- `::: box` ... `:::` for framed boxes; a box that runs across pages is written whole on the page where it starts.
- Margin notes with `*` become footnotes; caption-only margin text becomes the image caption.
- `![caption](img/NAME.jpg)` for figures; a later block that starts with `+` continues the last paragraph when a figure interrupts it.
- Pipe tables with `: caption`; list cells use `• item<br>` (assemble_book turns `<br>` into XHTML `<br />`, otherwise epubcheck fails).
- Citations printed in RTL come out reversed (`(Richmond, 2005 ;2001`); write them in logical order.
- pandoc turns a fenced div that starts with a heading into `<section class="level4 box">`, so CSS must target `.box`, not `div.box`.

### Figures
- Crop photos from the ORIGINAL images (`00_render`), not from the cleaned grayscale pages: the cleanup washes photos out and drops color (two cartoons and two photos here are in color). Coordinates in `figs_orig.txt` with a light `-level`; line art can come from `02_pages` with a stronger level (`crops.txt`).
- To find coordinates fast: 20% thumbnails with a 200 px grid, then a 25% preview montage of the crops.

## Third book: Hobbes, "לויתן" ch. 13 (4 phone photos of photocopies, pp. 113-119)
- Check every upload with `file` first. The first upload was named `.docx` but was the HTML of a Moodle (lemida.biu.ac.il) guest-login page, saved while logged out.
- `prep_pages.py` needs OpenCV: `apt-get install python3-opencv` installs it only for `/usr/bin/python3.12`, not for the default `/usr/local/bin/python3`. Run prep with python3.12.
- Photocopied spreads with a pasted-over gutter: the auto gutter (min ink in the 40-60% band) failed on 2 of 3 spreads (dark copy line off-centre, pages overlapping). Look at a montage after prep and split by hand with `convert -crop` when a half shows text from the other page, then feed the halves back in as singles.
- Copier edges cut the first or last 1-2 letters of every line on one side of each page. OCR leaves junk there; reconstruct from context while reading the image, and list only the doubtful ones in `uncertain.txt`. `check_vs_ocr.py` then lists exactly the reconstructed words.
- Letter-spaced run-in phrases at paragraph starts are Hobbes's margin summaries; written as `**...**` (bold). When one spans a page break, put the whole phrase on the earlier page.
- Student underlining in the copies is ignored.
