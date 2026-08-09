"""
fetch_cartoons.py — desktop tool: find & download copyright-free cartoons.

Runs on YOUR laptop (like fetch_stories.py in the main project). It lists
sources from sources.yaml (public-domain playlists, channels, or search
queries), downloads each video with yt-dlp at a sane quality, and stores
them in downloads/<source>/ with a manifest.json that records the source
URL, channel, and DECLARED license for each file — so you always know what
you're posting and from where.

LICENSE REALITY CHECK (important):
  "No dialogue" is NOT the same as "copyright-free". Larva (TUBA
  Entertainment), Shaun the Sheep (Aardman) etc. are all copyrighted —
  posting them gets Content ID claims (exactly like the "Feeling Blue"
  music did in the first project). The sources.yaml defaults point at
  PUBLIC-DOMAIN cartoon playlists and CC0/CC-BY animation channels. The
  tool logs each file's declared license and flags anything not clearly
  free so you can skip it.

Usage:
  python fetch_cartoons.py                 # process all sources in sources.yaml
  python fetch_cartoons.py --list          # just list what sources would give
  python fetch_cartoons.py --max 5         # limit downloads per source
  python fetch_cartoons.py --source pd_cartoons   # only one source
"""

import argparse
import json
import os
import re
import sys
import time

import yaml

try:
    import yt_dlp
except ImportError:
    print("❌ yt_dlp is not installed. Run:  python -m pip install yt-dlp")
    sys.exit(1)

SOURCES_FILE = "sources.yaml"
OUTPUT_ROOT = "downloads"

# License strings yt-dlp usually reports for clearly-free content.
FREE_LICENSE_HINTS = ("cc", "creative commons", "public domain", "cc0",
                      "attribution", "no rights reserved")


def _safe(text):
    return str(text).encode("ascii", "replace").decode("ascii")


def license_risk(info):
    """Return ('low'|'high', note) about a video's licensing."""
    lic = (info.get("license") or "").lower()
    desc = (info.get("description") or "").lower()
    if any(h in lic for h in FREE_LICENSE_HINTS):
        return "low", (lic or "creative commons declared")
    if "standard youtube license" in lic:
        return "high", "standard YouTube license (copyrighted!)"
    if any(h in desc for h in ("creative commons", "public domain")):
        return "low", "license text found in description"
    return "medium", f"license not declared ('{lic or 'unknown'}') — verify manually"


def sanitize_name(name):
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip()[:80] or "video"


def build_ydl_opts(source_name, out_dir, max_height):
    return {
        "format": f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(out_dir, "%(title).80s [%(id)s].%(ext)s"),
        "noplaylist": True,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
    }


def iter_entries(source):
    """Yield video dicts for a source (playlist/channel/search), flat-listing
    first so downloads only happen for videos that pass the filters."""
    with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": True,
                           "ignoreerrors": True, "no_warnings": True}) as ydl:
        if source.get("type") == "search":
            query = source["query"]
            url = f"ytsearch{source.get('limit', 20)}:{query}"
            info = ydl.extract_info(url, download=False)
            yield from (info.get("entries") or [])
            return
        # playlist or channel URL
        info = ydl.extract_info(source["url"], download=False)
        if "entries" in info:
            for e in info["entries"]:
                if e:
                    yield e


def download_video(source_name, entry, opts, manifest, max_duration, min_duration):
    """Download one entry; returns (ok, reason)."""
    if not entry:
        return False, "empty entry"
    title = entry.get("title") or entry.get("id")
    duration = entry.get("duration") or 0
    if duration and max_duration and duration > max_duration:
        return False, f"{_safe(title)[:40]}: too long ({duration}s)"
    if duration and min_duration and duration < min_duration:
        return False, f"{_safe(title)[:40]}: too short ({duration}s)"
    if entry.get("live_status") == "is_live":
        return False, "skip live stream"

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(entry["url"] if "url" in entry else entry["webpage_url"], download=True)
        if not info:
            return False, "download produced nothing"

    risk, note = license_risk(info)
    manifest.append({
        "title": info.get("title", ""),
        "channel": info.get("channel", ""),
        "url": info.get("webpage_url", ""),
        "duration": info.get("duration"),
        "license": info.get("license", ""),
        "risk": risk,
        "note": note,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    flag = "" if risk == "low" else f"  [RISK={risk}] {note}"
    print(f"   [OK] {_safe(info.get('title',''))[:60]}{flag}")
    return True, "ok"


def process_source(source, max_downloads, opts, manifest_path, manifest):
    name = source.get("name") or sanitize_name(source.get("url") or source.get("query", "source"))
    out_dir = os.path.join(OUTPUT_ROOT, name)
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n[source] {name}")
    count = 0
    for entry in iter_entries(source):
        if max_downloads and count >= max_downloads:
            break
        ok, reason = download_video(
            source_name=name, entry=entry, opts=opts, manifest=manifest,
            max_duration=source.get("max_duration", 0),
            min_duration=source.get("min_duration", 0))
        if ok:
            count += 1
        elif reason not in ("empty entry",):
            print(f"   - {_safe(reason)}")
    save_json(manifest_path, manifest)
    print(f"   Downloaded {count} video(s) -> {out_dir}/")
    return count


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_yaml(path):
    if not os.path.exists(path):
        print(f"❌ {path} not found.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="only list what sources would yield")
    ap.add_argument("--max", type=int, default=0, help="max downloads per source")
    ap.add_argument("--source", default=None, help="process only this source name")
    args = ap.parse_args()

    cfg = load_yaml(SOURCES_FILE)
    sources = cfg.get("sources", [])
    max_height = cfg.get("download", {}).get("max_height", 720)

    if args.source:
        sources = [s for s in sources if s.get("name") == args.source]
        if not sources:
            print(f"❌ No source named '{args.source}'")
            sys.exit(1)

    if args.list:
        for s in sources:
            print(f"\n[source] {s.get('name')}:")
            for e in iter_entries(s):
                t = e.get("title") or e.get("id")
                print(f"   - {_safe(t)[:80]}")
        return

    manifest = []
    manifest_path = os.path.join(OUTPUT_ROOT, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
        except Exception:
            manifest = []

    total = 0
    for s in sources:
        opts = build_ydl_opts(s.get("name"), os.path.join(OUTPUT_ROOT, s.get("name")), max_height)
        total += process_source(s, args.max, opts, manifest_path, manifest)

    print(f"\n[DONE] {total} video(s) downloaded into {OUTPUT_ROOT}/")
    print("   Next: upload the files into your Drive 'cartoon episodes' folder —")
    print("   the GitHub workflow will clip and schedule them automatically.")


if __name__ == "__main__":
    main()
