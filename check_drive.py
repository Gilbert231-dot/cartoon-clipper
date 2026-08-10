"""
check_drive.py — prove GDRIVE_API_KEY + GDRIVE_FOLDER_ID work BEFORE the
workflow ever runs (5-second check, no run wasted).

Usage:
    python check_drive.py
        (prompts for the API key and the folder ID / URL if not already set)

    GDRIVE_API_KEY=AIza... GDRIVE_FOLDER_ID=1AbC... python check_drive.py
        (or put both in a local .env file — it's gitignored)

What it checks:
    1. The key is a real Google API key (starts with AIza).
    2. The Drive API is enabled for the project that owns the key.
    3. The folder ID exists AND is shared "Anyone with the link → Viewer"
       (API keys can only read public files — no login).
    4. It lists every file it can see (same code the workflow uses), so if
       this prints your episodes, the workflow will see them too.

PASS  -> the pipeline's drive_episodes.py will work, no run needed to test.
FAIL  -> prints the most likely cause and how to fix it.
"""

import os
import re
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda: None  # python-dotenv optional; env vars still work

from drive_episodes import list_folder  # same function the workflow uses

# Make emoji-safe output even when stdout is redirected (Windows cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()


def extract_folder_id(raw):
    """Accept a bare ID or a full drive.google.com URL; return the ID.

    Handles the /u/N/ multi-account form too:
      drive.google.com/drive/folders/<ID>
      drive.google.com/drive/u/1/folders/<ID>
      drive.google.com/open?id=<ID>
    """
    raw = (raw or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", raw)
    if m:
        return m.group(1)
    return raw


def main():
    api_key = os.getenv("GDRIVE_API_KEY", "").strip()
    folder_id = os.getenv("GDRIVE_FOLDER_ID", "").strip()

    if not api_key:
        api_key = input("GDRIVE_API_KEY (starts with AIza...): ").strip()
    if not folder_id:
        folder_id = input("GDRIVE_FOLDER_ID (or the full Drive folder link): ").strip()

    folder_id = extract_folder_id(folder_id)

    if not api_key or not folder_id:
        print("❌ Both values are required. Aborting.")
        sys.exit(1)

    if "/" in folder_id or folder_id.startswith("http"):
        print("❌ Couldn't extract a folder ID from that input.")
        print("   Paste the folder's URL (drive.google.com/drive/.../folders/<ID>)")
        print("   or just the ID itself — the part after 'folders/'.")
        sys.exit(1)

    if not api_key.startswith("AIza"):
        print("⚠️  The key doesn't start with 'AIza' — that's not a Google API key.")
        print("   Get one: console.cloud.google.com → APIs & Services → Credentials → API key")

    print(f"Checking folder {folder_id} with the Drive API...")
    try:
        entries = list_folder(folder_id, api_key)
    except Exception as e:
        print(f"\n❌ FAILED: {e}\n")
        print("Most likely causes, in order:")
        print("  1. Key is wrong or not a Drive API key — re-copy it from")
        print("     console.cloud.google.com → APIs & Services → Credentials")
        print("  2. Google Drive API not enabled — console.cloud.google.com →")
        print("     APIs & Services → Library → 'Google Drive API' → Enable")
        print("  3. Wrong folder ID — copy the ID from the URL:")
        print("     drive.google.com/drive/folders/<THIS-IS-THE-ID>")
        print("  4. Folder not shared publicly — right-click the folder in Drive →")
        print("     Share → General access → 'Anyone with the link' → Viewer")
        sys.exit(1)

    if not entries:
        print("✅ CONNECTION WORKS — the key and folder ID are valid, but the")
        print("   folder is EMPTY (or has no .mp4 files).")
        print("   Upload your episodes and re-run; the workflow will pick them up.")
        sys.exit(0)

    print(f"✅ CONNECTION OK — {len(entries)} file(s) visible:")
    for e in entries:
        print(f"   • {e['name']}   (id: {e['id']})")
    print("\nThe workflow (drive_episodes.py) uses this exact same listing, so")
    print("these files will be downloaded and clipped on the next run.")


if __name__ == "__main__":
    main()
