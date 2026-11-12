# EpubMe: scanned or digital PDFs to EPUB (Hebrew RTL, also English)

- Converting a book: read `docs/low-token-workflow.md` first (two commands, helper and structure prompts). Background and gotchas per book: `docs/lessons.md`.
- Changing a script: add or extend a test in `tests/` and run `python3 -m unittest discover -s tests`.
- **Never retype pages.** Book text lives in files made by OCR or scripts (`04_text_fixed/NNN.md`). Fix it with small targeted edits: Edit with a short anchor, or a TSV for `scripts/replace_text.py`. Never print or retype a whole page in a reply, a tool input, a heredoc or `python -c`, and work a few pages at a time. Retyped pages cost the most tokens and trip "Output blocked by content filtering policy". A hook in `.claude/settings.json` (`scripts/guard_page_edits.py`) blocks large writes to page files; details in `docs/low-token-workflow.md`.
