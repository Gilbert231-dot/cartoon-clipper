"""
check_youtube_token.py — verify WHICH YouTube channel a refresh token
belongs to, BEFORE you save it to GitHub. Read-only: it only reads the
channel name, it never uploads or changes anything.

Usage:
    python check_youtube_token.py
    # or: YOUTUBE_REFRESH_TOKEN=1//xxx python check_youtube_token.py

The Client ID/Secret are read from .env (gitignored) — same values the
pipeline already uses. If the printed channel name is NOT Cartoon Dash,
re-run youtube_setup.py and authorize with the right account.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Read .env ourselves (no python-dotenv dependency)
try:
    with open(".env", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
except OSError:
    pass


def post(url, data):
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get(url, token):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "")
    secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

    if not (cid and secret):
        print("❌ YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET not found in .env")
        sys.exit(1)

    if not refresh:
        refresh = input("Paste your refresh token: ").strip()

    try:
        tok = post("https://oauth2.googleapis.com/token", {
            "refresh_token": refresh, "client_id": cid,
            "client_secret": secret, "grant_type": "refresh_token"})
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except Exception:
            body = {}
        print("❌ Google rejected the token:")
        print("   error:", body.get("error"), "-", body.get("error_description", ""))
        print("   - Copy the FULL value the setup script printed (starts with 1//...).")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Could not reach Google (network?): {e}")
        sys.exit(1)

    if "access_token" not in tok:
        print("❌ Token rejected by Google:")
        print("   error:", tok.get("error"), "-", tok.get("error_description", ""))
        print("   - Copy the FULL value the setup script printed (starts with 1//...).")
        sys.exit(1)

    try:
        chan = get("https://www.googleapis.com/youtube/v3/channels"
                   "?part=snippet&mine=true", tok["access_token"])
    except Exception as e:
        print(f"❌ Token works, but reading the channel failed: {e}")
        sys.exit(1)

    items = chan.get("items") or []
    if not items:
        print("⚠️  Token works but no channel was found on this account.")
        sys.exit(1)

    title = items[0]["snippet"]["title"]
    print(f"✅ This token belongs to the channel: {title}")
    print(f"   Channel ID: {items[0]['id']}")
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    if norm(title) != "cartoondash":
        print("   ⚠️  That is NOT Cartoon Dash — you authorized with the wrong account.")
        sys.exit(2)
    print("   ✓ Matches Cartoon Dash — safe to save into the GitHub secret.")


if __name__ == "__main__":
    main()
