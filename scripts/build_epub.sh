#!/usr/bin/env bash
# Stage 5b: assemble pages and build the EPUB.
# Usage: build_epub.sh BOOK_DIR OUT_NAME FIRST_PAGE [extra assemble_book.py args...]
#   e.g. --no-marker 003 --page-map page_map.json
# Images referenced as img/NAME.jpg are read from BOOK_DIR/img.
# Expects BOOK_DIR/04_text_fixed, BOOK_DIR/05_book_md/meta.yaml, BOOK_DIR/fonts/*.ttf (optional)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
book="$1"; name="$2"; first="$3"; shift 3
cd "$book"
mkdir -p 05_book_md 06_epub
python3 "$here/assemble_book.py" 04_text_fixed 05_book_md/book.md --first-page "$first" --page-markers "$@"
fonts=()
for f in fonts/*.ttf; do [ -e "$f" ] && fonts+=(--epub-embed-font="$f"); done
pandoc 05_book_md/book.md -f markdown-smart -t epub3 \
  --metadata-file=05_book_md/meta.yaml \
  --css "$here/epub.css" "${fonts[@]}" \
  --split-level=2 --toc --toc-depth=3 --resource-path=. \
  -o "06_epub/$name.epub"
python3 "$here/fix_epub_rtl.py" "06_epub/$name.epub"
echo "built 06_epub/$name.epub"
