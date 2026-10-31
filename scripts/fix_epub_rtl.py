#!/usr/bin/env python3
"""Add dir="rtl" to every XHTML <html> element in an EPUB, keeping mimetype first and stored.
Pandoc puts lang="he" but not dir; some readers ignore CSS direction.
Usage: fix_epub_rtl.py BOOK.epub
"""
import re
import shutil
import sys
import tempfile
import zipfile

src = sys.argv[1]
tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".epub").name
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w") as zout:
    zout.writestr(zin.getinfo("mimetype"), zin.read("mimetype"), compress_type=zipfile.ZIP_STORED)
    for item in zin.infolist():
        if item.filename == "mimetype":
            continue
        data = zin.read(item.filename)
        if item.filename.endswith(".xhtml"):
            text = data.decode("utf-8")
            text = re.sub(r"<html(?![^>]*\bdir=)", '<html dir="rtl"', text, count=1)
            data = text.encode("utf-8")
        zout.writestr(item, data, compress_type=zipfile.ZIP_DEFLATED)
shutil.move(tmp, src)
print("rtl fixed:", src)
