"""
build_data.py — generate dashboard/data.json for the Cartoon Dash schedule
dashboard.

Reads:
  clips_manifest.json  (every produced clip + its YouTube schedule)

Writes:
  dashboard/data.json  (what the dashboard renders)

Run manually after a run, or automatically in the workflow — the
'Regenerate dashboard data' step runs right before the state push so the
committed data.json stays fresh.
"""

import datetime
import json
import os
import re
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO, "clips_manifest.json")
OUT = os.path.join(REPO, "dashboard", "data.json")


def clean_episode(name):
    """'Popeye_..._[ID]_clip01.mp4' -> 'Popeye the Sailor - Little Swee Pea 1936'"""
    name = os.path.splitext(name)[0]
    name = re.sub(r"_clip\d+$", "", name)
    name = re.sub(r"\s*\[[A-Za-z0-9_-]+\]\s*$", "", name)
    name = name.replace("_", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name


def main():
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            clips = json.load(f)
    except Exception:
        clips = []

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    def as_utc(iso):
        try:
            t = datetime.datetime.fromisoformat(str(iso))
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
            return t.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        except Exception:
            return None

    rows = []
    for c in clips:
        t = as_utc(c.get("publish_at", ""))
        if t is None:
            continue
        rows.append({
            "episode": clean_episode(c.get("episode", c.get("clip", ""))),
            "clip": c.get("clip", ""),
            "duration": round(float(c.get("duration", 0) or 0)),
            "publish_at": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "url": c.get("url", ""),
        })

    rows.sort(key=lambda r: r["publish_at"])
    upcoming = [r for r in rows if r["publish_at"] >= now.strftime("%Y-%m-%dT%H:%M:%SZ")]
    published = [r for r in rows if r["publish_at"] < now.strftime("%Y-%m-%dT%H:%M:%SZ")]

    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "channel": "Cartoon_dash",
        "slots": ["12:00", "18:00"],
        "clips_per_day": 2,
        "total_clips": len(rows),
        "scheduled_count": len(upcoming),
        "published_count": len(published),
        "next_publish_utc": upcoming[0]["publish_at"] if upcoming else None,
        "last_publish_utc": published[-1]["publish_at"] if published else None,
        "upcoming": upcoming,
        "published": published,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[build_data] Wrote {OUT}")
    print(f"   {len(rows)} clips: {len(upcoming)} upcoming, {len(published)} published")


if __name__ == "__main__":
    main()
