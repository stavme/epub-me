# Lessons from the first manual run (Kant, "Perpetual Peace", 13 PDF pages → 24 book pages)

## Stage 1: page prep
- `pdfimages -list` showed each PDF page is built from 2-3 JPEG strips (~170 ppi), so extracting images is useless; render the page with `pdftoppm -r 300` instead.
- `pdftotext` returned nothing: no text layer.
- Tesseract OSD (`--psm 0`) detected orientation correctly on all pages. "Rotate: 270" means rotate 270° clockwise = ImageMagick `-rotate 270`. (I first applied 90 and got upside-down pages.)
- Spread detection by aspect ratio > 1.2 worked; gutter = minimum ink column in the 40-60% band.
- Each half had a different skew (−0.9° to 4°), confirming split-before-deskew. Skew search range must be ≥ ±6°; ±3° clipped.
- Page-number OCR on the bottom 7% strip (`-l eng --psm 6`) is a cheap sequence check: 23..46 continuous.
- Approval PDF: PNG pages gave 31 MB; JPEG q80 pages gave 9 MB.
