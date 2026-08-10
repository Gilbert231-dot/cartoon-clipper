"""
youtube_poster.py — upload clips to YouTube as SCHEDULED (private + publishAt).

Uses the same YouTube OAuth credentials as the main faceless-video project
(YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN). Each
clip is uploaded private with a publishAt timestamp from the config's
2/day slot cadence — invisible until publishAt, then it goes live on its
own. Progress is tracked in schedule_state.json + clips_manifest.json
(both repo-pushed), so clips are posted exactly once and slots never
collide.
"""

import datetime
import glob
import json
import os
import re
import sys
import time

import yaml
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CLIPS_DIR = "clips"
CONFIG_FILE = "config.yaml"
SCHEDULE_STATE = "schedule_state.json"
MANIFEST_FILE = "clips_manifest.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _safe(text):
    return str(text).encode("ascii", "replace").decode("ascii")


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_authenticated_service():
    refresh = os.getenv("YOUTUBE_REFRESH_TOKEN")
    cid = os.getenv("YOUTUBE_CLIENT_ID")
    secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    if not all([refresh, cid, secret]):
        raise RuntimeError("Missing YOUTUBE_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN env")
    from google.oauth2.credentials import Credentials
    creds = Credentials(token=None, refresh_token=refresh, client_id=cid,
                        client_secret=secret,
                        token_uri="https://oauth2.googleapis.com/token",
                        scopes=SCOPES)
    return build("youtube", "v3", credentials=creds)


def episode_title_from_path(clip_path):
    """'clips/default/Popeye_the_Sailor_-_Little_Swee_Pea_1936 [UTvWXh7cQB0]_clip01.mp4'
    -> 'Popeye the Sailor - Little Swee Pea 1936' (for titles)."""
    name = os.path.basename(clip_path)
    name = os.path.splitext(name)[0]                            # drop .mp4
    name = re.sub(r"_clip\d+$", "", name)                    # drop clip suffix
    name = re.sub(r"\s*\[[A-Za-z0-9_-]+\]\s*$", "", name)  # drop trailing [videoID]
    name = name.replace("_", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:70]


def next_publish_at(schedule_cfg, state):
    """Next free 2/day slot (UTC), like the main project's schedule logic."""
    slots = [int(h) for h in schedule_cfg.get("slot_hours_utc", [12, 18])]
    per_day = schedule_cfg.get("clips_per_day", 2)
    idx = state.get("next_index", 0)
    now = datetime.datetime.now(datetime.timezone.utc)
    candidate = None
    guard = idx
    while idx < guard + 60:
        slot = slots[idx % len(slots)]
        day = now.date() + datetime.timedelta(days=idx // len(slots))
        candidate = datetime.datetime(day.year, day.month, day.day, slot,
                                      tzinfo=datetime.timezone.utc)
        if candidate > now + datetime.timedelta(hours=1):
            break
        idx += 1
    state["next_index"] = idx + 1
    return candidate


def schedule_upload(youtube, clip_path, title, description, tags, publish_at, privacy):
    body = {
        "snippet": {"title": title[:100], "description": description[:5000],
                    "tags": tags[:15], "categoryId": "22"},
        "status": {"privacyStatus": privacy, "publishAt": publish_at.isoformat(),
                   "selfDeclaredMadeForKids": False, "embeddable": True},
    }
    media = MediaFileUpload(clip_path, chunksize=1024 * 1024 * 8, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media,
                                  notifySubscribers=False)
    resp = req.execute()
    return resp["id"]


def main():
    cfg = load_yaml(CONFIG_FILE)
    sched = cfg["schedule"]
    state = load_json(SCHEDULE_STATE, {})
    manifest = load_json(MANIFEST_FILE, [])

    clips = sorted(glob.glob(os.path.join(CLIPS_DIR, "*", "*.mp4")))
    if not clips:
        print("No clips to post (clips/ is empty). Run clip_videos.py first.")
        return

    posted_ids = {c.get("youtube_id") for c in manifest if c.get("youtube_id")}
    # map by clip file so already-posted clips are skipped
    posted_files = {c.get("file") for c in manifest if c.get("youtube_id")}

    todo = [c for c in clips if c not in posted_files]
    if not todo:
        print("All clips already scheduled. Nothing to do.")
        return

    youtube = get_authenticated_service()
    now = datetime.datetime.now(datetime.timezone.utc)
    for i, clip in enumerate(todo):
        publish_at = next_publish_at(sched, state)
        n = len(posted_ids) + i + 1
        episode = episode_title_from_path(clip)
        title_tpl = sched.get("title_template", "Cartoon Clips - Episode {n}")
        title = title_tpl.format(n=n, episode=episode)
        print(f"  [upload] {os.path.basename(clip)} -> scheduled {publish_at:%Y-%m-%d %H:%M} UTC")
        print(f"    [title] {title}")
        try:
            vid = schedule_upload(youtube, clip, title,
                                  sched.get("description", ""),
                                  sched.get("tags", []),
                                  publish_at, sched.get("privacy", "private"))
        except Exception as e:
            print(f"  [error] {os.path.basename(clip)}: {_safe(e)}")
            continue
        print(f"    [OK] scheduled -> https://youtu.be/{vid}")
        # record on the matching manifest entry if present, else append
        entry = next((m for m in manifest if m.get("file") == clip), None)
        if entry is None:
            entry = {"clip": os.path.basename(clip), "file": clip}
            manifest.append(entry)
        entry["youtube_id"] = vid
        entry["url"] = f"https://youtu.be/{vid}"
        entry["publish_at"] = publish_at.isoformat()
        entry["status"] = "scheduled"

    save_json(SCHEDULE_STATE, state)
    save_json(MANIFEST_FILE, manifest)
    print(f"\nScheduled {len(todo)} clip(s). Manifest: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
