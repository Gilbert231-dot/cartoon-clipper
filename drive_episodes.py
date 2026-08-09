"""
drive_episodes.py — pull new cartoon episodes from a Google Drive folder.

Same pattern as the main project: dynamic folder listing via the Drive API
(API key only) + gdown download. Files (and one level of subfolders, which
become show names) land in episodes/<show>/<file>.mp4. Episodes already in
processed_episodes.json are skipped, so re-runs only download new content.

Requires env: GDRIVE_FOLDER_ID (public folder, "Anyone with the link") and
GDRIVE_API_KEY (Google Cloud key with Drive API enabled).
"""

import json
import os
import re
import subprocess

import requests

EPISODES_DIR = "episodes"
PROCESSED_FILE = "processed_episodes.json"

DRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
GDRIVE_API_KEY = os.environ.get("GDRIVE_API_KEY", "").strip()


def _safe(text):
    return str(text).encode("ascii", "replace").decode("ascii")


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def list_folder(folder_id, api_key):
    """All files in a folder (files + one level of subfolders, named '<sub>/<file>')."""
    entries = []
    params = {"q": f"'{folder_id}' in parents and trashed = false",
              "fields": "nextPageToken, files(id, name, mimeType)",
              "pageSize": 200, "key": api_key}
    page = None
    while True:
        if page:
            params["pageToken"] = page
        r = requests.get("https://www.googleapis.com/drive/v3/files",
                         params=params, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Drive API error {r.status_code}: {r.text[:200]}")
        data = r.json()
        for f in data.get("files", []):
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                # recurse one level -> show folder
                for sub in list_folder(f["id"], api_key):
                    entries.append({"id": sub["id"], "name": f"{f['name']}/{sub['name']}"})
            elif f.get("mimeType") == "video/mp4" or f.get("name", "").lower().endswith(".mp4"):
                entries.append({"id": f["id"], "name": f["name"]})
        page = data.get("nextPageToken")
        if not page:
            break
    entries.sort(key=lambda e: e["name"].lower())
    return entries


def download(file_id, dest):
    import gdown  # lazy: only needed when downloading
    url = f"https://drive.google.com/uc?id={file_id}"
    gdown.download(url, dest, quiet=True)


def main():
    if not (DRIVE_FOLDER_ID and GDRIVE_API_KEY):
        print("[drive-episodes] GDRIVE_FOLDER_ID/GDRIVE_API_KEY not set — skipping download.")
        return
    processed = load_json(PROCESSED_FILE, {})
    entries = list_folder(DRIVE_FOLDER_ID, GDRIVE_API_KEY)
    print(f"[drive-episodes] {len(entries)} episode file(s) in the folder")

    new_count = 0
    for e in entries:
        parts = e["name"].split("/")
        show = parts[0] if len(parts) > 1 else "default"
        filename = parts[-1]
        if filename in processed.get(show, []):
            continue
        dest_dir = os.path.join(EPISODES_DIR, show)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)
        if os.path.exists(dest):
            continue
        print(f"  [download] {show}/{filename} ...")
        try:
            download(e["id"], dest)
            if os.path.getsize(dest) < 100_000:
                os.remove(dest)
                print("    (too small / failed — skipped)")
                continue
            new_count += 1
            print(f"    [OK] {filename}")
        except Exception as ex:
            print(f"    [error] {_safe(ex)}")

    print(f"[drive-episodes] downloaded {new_count} new episode(s)")


if __name__ == "__main__":
    main()
