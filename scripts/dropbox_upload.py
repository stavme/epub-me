#!/usr/bin/env python3
"""Upload a file to the EpubMe Dropbox app folder (Apps/EpubMe).

Needs env vars DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN
and network access to api.dropboxapi.com and content.dropboxapi.com.
Never prints the secrets.

Usage:
  dropbox_upload.py LOCAL_FILE [DEST_PATH]     # DEST defaults to /<basename>
  dropbox_upload.py --delete DEST_PATH
"""
import json
import os
import sys
import urllib.parse
import urllib.request


def access_token():
    for v in ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN"):
        if not os.environ.get(v):
            sys.exit(f"missing env var {v}")
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"],
        "client_id": os.environ["DROPBOX_APP_KEY"],
        "client_secret": os.environ["DROPBOX_APP_SECRET"],
    }).encode()
    with urllib.request.urlopen("https://api.dropboxapi.com/oauth2/token", data) as r:
        return json.load(r)["access_token"]


def call(url, token, body, arg=None):
    headers = {"Authorization": f"Bearer {token}"}
    if arg is not None:
        # Dropbox-API-Arg must be ASCII: ensure_ascii escapes Hebrew as \uXXXX.
        headers["Dropbox-API-Arg"] = json.dumps(arg, ensure_ascii=True)
        headers["Content-Type"] = "application/octet-stream"
    else:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, body, headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')}")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    token = access_token()
    if args[0] == "--delete":
        res = call("https://api.dropboxapi.com/2/files/delete_v2", token,
                   json.dumps({"path": args[1]}).encode())
        print("deleted", res["metadata"]["path_display"])
        return
    local = args[0]
    dest = args[1] if len(args) > 1 else "/" + os.path.basename(local)
    with open(local, "rb") as f:
        body = f.read()
    res = call("https://content.dropboxapi.com/2/files/upload", token, body,
               {"path": dest, "mode": "overwrite", "mute": False})
    print("uploaded", res["path_display"], res["size"], "bytes")


if __name__ == "__main__":
    main()
