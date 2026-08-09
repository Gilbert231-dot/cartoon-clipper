"""
clip_videos.py — turn full cartoon episodes into post-ready clips.

For every episode in episodes/ (organized as episodes/<show>/file.mp4) that
hasn't been processed yet:

  1. Trims the intro and outro (per-show seconds from config.yaml).
  2. Finds scene changes in the trimmed range (ffmpeg scene detection).
  3. Splits into clips: scene boundaries become clip boundaries; scenes are
     chunked to max_clip_seconds and clips shorter than min_clip_seconds
     are dropped.
  4. Burns the "Subscribe for more videos" text into the TOP of each clip
     (the black bar area) and re-encodes at good quality.

No music, no voiceover, no captions — just the clip + the subscribe text.

State: processed_episodes.json (repo-pushed) so each episode is clipped
exactly once, and clips_manifest.json lists every produced clip.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

import yaml

CONFIG_FILE = "config.yaml"
EPISODES_DIR = "episodes"
CLIPS_DIR = "clips"
PROCESSED_FILE = "processed_episodes.json"
MANIFEST_FILE = "clips_manifest.json"

FONT_CANDIDATES = [
    # Linux runner
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
WINDOWS_FONTS = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariblk.ttf"]


def _safe(text):
    return str(text).encode("ascii", "replace").decode("ascii")


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
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


def resolve_font():
    """A font path with NO colon in it (Windows drive letters break ffmpeg's
    drawtext option parser). Linux runner path is used as-is; on Windows the
    font is copied to assets/font.ttf (colon-free, gitignored)."""
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    for src in WINDOWS_FONTS:
        if os.path.exists(src):
            os.makedirs("assets", exist_ok=True)
            dst = os.path.join("assets", "font.ttf")
            try:
                shutil.copy(src, dst)
                return dst
            except Exception:
                pass
    return None


def ffprobe_duration(video_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {video_path}: {out.stderr}")
    return float(out.stdout.strip())


def detect_scene_cuts(video_path, start, end, threshold):
    """Scene-change timestamps (absolute, seconds) within [start, end]."""
    cmd = ["ffmpeg", "-ss", str(start), "-to", str(end), "-i", video_path,
           "-vf", f"select='gt(scene,{threshold})',showinfo",
           "-an", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    times = []
    for line in out.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1)) + start
            if start < t < end:
                times.append(t)
    return times


def build_clip_ranges(start, end, cuts, min_sec, max_sec):
    """[(start, duration), ...] from scene boundaries, honoring min/max."""
    points = sorted({start, end} | {c for c in cuts if start < c < end})
    ranges = []
    for a, b in zip(points, points[1:]):
        dur = b - a
        if dur < min_sec:
            continue
        if dur > max_sec:
            # split into max_sec chunks; a short tail is merged into the
            # previous chunk instead of emitting a trash clip
            while dur >= max_sec:
                ranges.append((a, max_sec))
                a += max_sec
                dur -= max_sec
            if dur > 0:
                if dur >= min_sec:
                    ranges.append((a, dur))
                elif ranges:
                    pa, pd = ranges[-1]
                    ranges[-1] = (pa, pd + dur)
        else:
            ranges.append((a, dur))
    return ranges


def render_clip(episode, start, dur, out_path, overlay_cfg):
    """Extract one clip with the subscribe text burned into the top."""
    text = overlay_cfg.get("text", "Subscribe for more videos").replace("'", "")
    font = resolve_font()
    y = overlay_cfg.get("y_fraction", 0.05)
    fs = overlay_cfg.get("fontsize_fraction", 0.045)
    drawtext = (f"drawtext=text='{text}':fontsize=h*{fs:.3f}"
                f":x=(w-text_w)/2:y=h*{y:.3f}"
                f":fontcolor={overlay_cfg.get('color', 'white')}"
                f":box=1:boxcolor=black@0.35:boxborderw=10")
    if font:
        drawtext += f":fontfile={font}"
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", episode,
           "-t", str(dur), "-vf", drawtext,
           "-c:v", "libx264", "-crf", "18", "-preset", "medium",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
           out_path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (rc={p.returncode}): {p.stderr[-500:]}")


def process_episode(episode_path, show, cfg, processed, manifest):
    """Clip one episode; returns the number of clips produced."""
    duration = ffprobe_duration(episode_path)
    show_cfg = cfg["shows"].get(show, cfg["shows"]["default"])
    start = show_cfg["intro_seconds"]
    end = max(start + 1, duration - show_cfg["outro_seconds"])
    if end - start < show_cfg["min_clip_seconds"]:
        print(f"  [skip] episode too short after trim: {os.path.basename(episode_path)}")
        processed.setdefault(show, []).append(os.path.basename(episode_path))
        return 0

    cuts = detect_scene_cuts(episode_path, start, end, show_cfg["scene_threshold"])
    ranges = build_clip_ranges(start, end, cuts,
                               show_cfg["min_clip_seconds"],
                               show_cfg["max_clip_seconds"])
    if not ranges:
        print(f"  [skip] no usable clips from {os.path.basename(episode_path)}")
        processed.setdefault(show, []).append(os.path.basename(episode_path))
        return 0

    print(f"  {len(ranges)} clip(s) from '{os.path.basename(episode_path)}' "
          f"({len(cuts)} scene cuts)")
    base = os.path.splitext(os.path.basename(episode_path))[0]
    for i, (c_start, c_dur) in enumerate(ranges, 1):
        out_name = f"{base}_clip{i:02d}.mp4"
        out_path = os.path.join(CLIPS_DIR, show, out_name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        render_clip(episode_path, c_start, c_dur, out_path, cfg["overlay"])
        manifest.append({
            "clip": out_name,
            "episode": os.path.basename(episode_path),
            "show": show,
            "start": round(c_start, 2),
            "duration": round(c_dur, 2),
            "file": out_path,
        })
        print(f"    -> {out_name} ({c_start:.1f}s, {c_dur:.1f}s)")

    processed.setdefault(show, []).append(os.path.basename(episode_path))
    return len(ranges)


def main():
    cfg = load_config()
    processed = load_json(PROCESSED_FILE, {})
    manifest = load_json(MANIFEST_FILE, [])
    os.makedirs(CLIPS_DIR, exist_ok=True)

    total = 0
    for show_dir in sorted(glob.glob(os.path.join(EPISODES_DIR, "*"))):
        if not os.path.isdir(show_dir):
            continue
        show = os.path.basename(show_dir)
        done = set(processed.get(show, []))
        for episode in sorted(glob.glob(os.path.join(show_dir, "*.mp4"))):
            name = os.path.basename(episode)
            if name in done:
                print(f"  [skip] already processed: {show}/{name}")
                continue
            print(f"  Clipping {show}/{name} ...")
            try:
                n = process_episode(episode, show, cfg, processed, manifest)
                total += n
            except Exception as e:
                print(f"  [error] {name}: {_safe(e)}")

    save_json(PROCESSED_FILE, processed)
    save_json(MANIFEST_FILE, manifest)
    print(f"\nDone. {total} clip(s) produced -> {CLIPS_DIR}/")


if __name__ == "__main__":
    main()
