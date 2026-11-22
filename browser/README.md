# EpubMe browser button

A bookmark that turns the article you are reading into an EPUB and downloads it.
It runs inside your browser, so it works on pages you can only open after signing
in (for example Cambridge Core through the Bar-Ilan library). Nothing is sent
anywhere and no Claude thread is needed, so it costs no tokens.

Works best on journal article pages with the full text on the page (Cambridge
Core is the main target). Other sites fall back to the page's main article.
It does not handle scans or PDFs: use `convert.sh` for those.

## Install (once, on a computer)

1. Open [`bookmarklet.txt`](bookmarklet.txt) on GitHub, press **Raw**, select all
   (Ctrl+A) and copy (Ctrl+C). It is one long line starting with `javascript:`.
2. Show the bookmarks bar (Ctrl+Shift+B in Chrome or Edge).
3. Right-click the bookmarks bar, choose **Add page...** (Chrome) or **Add
   bookmark...** (Firefox). Name it `EpubMe` and paste the copied line as the URL.
   Save.

When `bookmarklet.txt` changes in the repository, edit the bookmark and paste the
new line.

## Use

1. Open the article (sign in through the library first if needed) and wait until
   the full text has loaded.
2. Click **EpubMe** on the bookmarks bar. A dark box in the top right corner
   shows progress, then the file name.
3. The `.epub` lands in your Downloads folder, named after the article title.
   Copy it to the Boox (or to Dropbox `Apps/EpubMe`).

If the box says some figures "could not be downloaded", the EPUB still has their
captions; the site refused the picture download.

## What you get

- Title and author(s) (metadata is title and author only).
- Abstract, keywords, sections and subsections, with a table of contents.
- Numbered notes as popup footnotes, with the article's own numbers, collected
  at the end under "Notes" ("Ibid." links stay plain text).
- Figures with captions, tables, quotes and lists.
- Hebrew pages (detected from the text) come out right-to-left with the David
  Libre font embedded when it can be downloaded; English pages left-to-right.
- On blog-style sites (WordPress and similar) it takes only the post itself: the
  site name is dropped from the title, a bold first line becomes the author
  instead of the site's user name, and short plain lines used as section titles
  ("פתיחה", "חלק א'") become headings in the table of contents.
- The file passes epubcheck.

## For developers

The source is [`epub-me.js`](epub-me.js). After editing it run
`python3 scripts/build_bookmarklet.py` to regenerate `bookmarklet.txt`, then
`python3 -m unittest discover -s tests`. The browser tests (`tests/test_bookmarklet.py`)
run the real bookmarklet in headless Chromium on `tests/fixtures/web/` and need
Node with Playwright; CI runs them and epubchecks the output.
