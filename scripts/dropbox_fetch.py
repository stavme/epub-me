#!/usr/bin/env python3
"""Download source files from the EpubMe Dropbox inbox straight to disk.

Files dropped into Apps/EpubMe/inbox (from a phone, the Boox, or a computer)
are fetched here without ever passing through the conversation, so they cost
no tokens. After a successful download each file is moved to /inbox/done
(pass --keep to leave it).

Same env vars and network access as dropbox_upload.py.

With several books in the inbox, threads run in parallel and each one must
fetch only its own file: pass --name. Without --name, a fetch is refused when
the inbox holds more than one file (it would download and move them all).

Usage:
  dropbox_fetch.py OUT_DIR [--name FILE] [--inbox /inbox] [--keep]
  dropbox_fetch.py --list [--inbox /inbox]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dropbox_upload import access_token, call  # noqa: E402


def list_folder(token, path):
    res = call("https://api.dropboxapi.com/2/files/list_folder", token,
               json.dumps({"path": path}).encode())
    entries = res["entries"]
    while res.get("has_more"):
        res = call("https://api.dropboxapi.com/2/files/list_folder/continue", token,
                   json.dumps({"cursor": res["cursor"]}).encode())
        entries += res["entries"]
    return [e for e in entries if e[".tag"] == "file"]


def pick(files, name):
    """The inbox entries to fetch, or an error message (str)."""
    if name:
        hit = [e for e in files if e["name"] == name]
        return hit or f"not in the inbox: {name!r}; files: {[e['name'] for e in files]}"
    if len(files) > 1:
        return ("several files in the inbox; fetch one with --name (convert.sh start "
                f"'dropbox:NAME'): {[e['name'] for e in files]}")
    return files or "inbox is empty"


def download(token, path, out):
    req = urllib.request.Request(
        "https://content.dropboxapi.com/2/files/download", None,
        {"Authorization": f"Bearer {token}",
         "Dropbox-API-Arg": json.dumps({"path": path}, ensure_ascii=True)}, method="POST")
    try:
        with urllib.request.urlopen(req) as r, open(out, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--inbox", default="/inbox")
    ap.add_argument("--name", help="fetch only this file (exact name)")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    token = access_token()
    files = list_folder(token, a.inbox)
    if a.list or not a.out_dir:
        for e in files:
            print(f"{e['size']:>10}  {e['path_display']}")
        return
    files = pick(files, a.name)
    if isinstance(files, str):
        sys.exit(files)
    os.makedirs(a.out_dir, exist_ok=True)
    for e in files:
        out = os.path.join(a.out_dir, e["name"])
        download(token, e["path_lower"], out)
        if os.path.getsize(out) != e["size"]:
            sys.exit(f"size mismatch for {e['name']}")
        print(f"downloaded {e['name']} ({e['size']} bytes) -> {out}")
        if not a.keep:
            call("https://api.dropboxapi.com/2/files/move_v2", token, json.dumps({
                "from_path": e["path_lower"], "to_path": f"{a.inbox}/done/{e['name']}",
                "autorename": True}).encode())


if __name__ == "__main__":
    main()
