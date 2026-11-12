#!/usr/bin/env bash
# One command per phase, so a conversion thread spends few steps (every step
# re-reads the whole conversation, which is where most tokens go).
#
#   convert.sh start  SOURCE BOOK_DIR [--lang en] [--gutter FILE=X ...]
#       SOURCE: a PDF, a folder of photos/scans, "dropbox:FILE NAME" (that file
#       from Apps/EpubMe/inbox), or "dropbox" (only when the inbox has one file).
#       --lang en: English scan (eng OCR, left-to-right word and page order).
#       Text PDF  -> BOOK/04_text_fixed/NNN.md written; next: structure, then finish.
#       Scan      -> render, rotate upright, split/deskew, OCR, review queue.
#                    Next: helper agent writes BOOK/03_queue/fixes.txt (prompt in
#                    docs/low-token-workflow.md), then structure, then finish.
#   convert.sh finish BOOK_DIR "TITLE" "AUTHOR" OUT_NAME [--first-page N] [--lang en] [--upload]
#       Applies fixes (if 03_queue exists and 04_text_fixed doesn't), builds the
#       EPUB, runs epubcheck, picks 2 sample pages, uploads with --upload.
#       Without --first-page, a scan's printed page numbers set it (guess_first_page.py).
#
# Prints only short summaries, so its output is cheap to read.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
TOOLS=${EPUB_TOOLS:-$HOME/.epub-tools}
cmd=${1:-}; shift || true

start() {
  local src="$1" book="$2" lang=he; shift 2
  local prep=()
  while [ $# -gt 0 ]; do
    case "$1" in --lang) lang="$2"; shift ;; *) prep+=("$1") ;; esac; shift
  done
  local tlang=heb; [ "$lang" = en ] && tlang=eng
  "$here/setup_env.sh" >/dev/null
  mkdir -p "$book"
  case "$src" in
    dropbox|dropbox:*)
      rm -rf "$book/00_inbox"
      if [ "$src" = dropbox ]; then
        python3 "$here/dropbox_fetch.py" "$book/00_inbox"
      else
        python3 "$here/dropbox_fetch.py" "$book/00_inbox" --name "${src#dropbox:}"
      fi
      src=$(find "$book/00_inbox" -maxdepth 1 -type f | head -1) ;;
  esac
  local srcdir="$book/00_src"
  rm -rf "$srcdir"; mkdir -p "$srcdir"
  if [ -f "$src" ]; then
    case "$(file -b --mime-type "$src")" in
      application/pdf)
        if python3 "$here/check_pdf.py" "$src" "$book/04_text_fixed"; then
          echo "NEXT: structure pass on $book/04_text_fixed (text only), then: convert.sh finish"
          return
        fi
        pdftoppm -r 300 -png "$src" "$srcdir/p" ;;
      image/*) cp "$src" "$srcdir/" ;;
      *) echo "not a PDF or image: $(file -b "$src")"; exit 1 ;;
    esac
  else
    find "$src" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.tif*' \) \
      -exec cp {} "$srcdir/" \;
  fi
  # rotate upright (Tesseract OSD; "Rotate: N" = rotate N degrees clockwise)
  local up="$book/01_upright"; rm -rf "$up"; mkdir -p "$up"
  for f in "$srcdir"/*; do
    r=$(tesseract "$f" - --psm 0 2>/dev/null | awk '/^Rotate:/{print $2}')
    convert "$f" -rotate "${r:-0}" "$up/$(basename "${f%.*}").png"
  done
  local ltr=(); [ "$lang" = en ] && ltr=(--ltr)
  python3 "$here/prep_pages.py" "$up" "$book" "${ltr[@]}" "${prep[@]}" 2>&1 | grep -E "WARNING" || true
  python3 "$here/review_queue.py" "$book/02_pages_ocr" "$book/03_queue" --tessdata "$TOOLS/tessdata" \
    --lang "$tlang" | tail -1
  echo "pages: $(ls "$book/02_pages" | wc -l); sheets: $(ls "$book/03_queue/sheets" | wc -l)"
  echo "NEXT: helper agent -> $book/03_queue/fixes.txt, then structure pass, then: convert.sh finish${ltr:+ ... --lang en}"
}

finish() {
  local book="$1" title="$2" author="$3" name="$4" upload="" first="" lang=he; shift 4
  while [ $# -gt 0 ]; do
    case "$1" in --upload) upload=1 ;; --first-page) first="$2"; shift ;; --lang) lang="$2"; shift ;; esac; shift
  done
  if [ -z "$first" ]; then
    # scans: printed page numbers that review_queue dropped give the offset
    if [ -f "$book/03_queue/headers.txt" ] && first=$(python3 "$here/guess_first_page.py" "$book/03_queue/headers.txt"); then
      echo "first page: $first (from page numbers in headers.txt; pass --first-page to override)"
    else
      first=1; echo "first page: 1 (no --first-page and no page numbers found)"
    fi
  fi
  if [ -d "$book/03_queue" ] && [ ! -d "$book/04_text_fixed" ]; then
    touch "$book/03_queue/fixes.txt"
    python3 "$here/apply_fixes.py" "$book/03_queue" "$book/03_queue/fixes.txt" "$book/04_text_fixed"
  fi
  mkdir -p "$book/05_book_md" "$book/fonts"
  # JSON is valid YAML and quotes titles like פרק י"ג safely
  python3 -c 'import json,sys; m={"title":sys.argv[1],"lang":sys.argv[3]}; sys.argv[2] and m.update(author=sys.argv[2]); print(json.dumps(m,ensure_ascii=False))' \
    "$title" "$author" "$lang" > "$book/05_book_md/meta.yaml"
  cp -n "$TOOLS"/fonts/*.ttf "$book/fonts/" 2>/dev/null || true
  if [ "$lang" = en ]; then
    python3 "$here/check_en.py" "$book/04_text_fixed" | tail -15   # OCR slips: "ina", "|" for "I"
  fi
  "$here/build_epub.sh" "$book" "$name" "$first" 2>"$book/build.log" | tail -1 || { tail -5 "$book/build.log"; exit 1; }
  local tmp; tmp=$(mktemp -d); cp "$book/06_epub/$name.epub" "$tmp/book.epub"
  java -jar /usr/bin/epubcheck "$tmp/book.epub" 2>&1 | grep -E "^(ERROR|FATAL)|Messages:" | head -5
  rm -rf "$tmp"
  if [ -d "$book/03_queue" ]; then
    python3 "$here/sample_check.py" "$book/02_pages" "$book/04_text_fixed" "$book/03_queue" "$book/sample" | cut -f1,2
  fi
  if [ -n "$upload" ]; then
    python3 "$here/dropbox_upload.py" "$book/06_epub/$name.epub" "/$name.epub"
  fi
}

case "$cmd" in
  start) start "$@" ;;
  finish) finish "$@" ;;
  *) sed -n 2,16p "$0"; exit 1 ;;
esac
