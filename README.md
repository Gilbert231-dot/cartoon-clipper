# 🎬 cartoon-clipper

Turn full cartoon episodes into post-ready clips, fully automated:

1. **`fetch_cartoons.py`** (runs on YOUR laptop) — finds & downloads
   **copyright-free** cartoons from public-domain playlists / CC channels
   on YouTube, organized by source, with a manifest recording each file's
   license so you always know what you're posting.
2. **You upload the episodes** to a Google Drive folder (your "episodes"
   folder in the cloud).
3. **GitHub Actions** (this repo) — picks up new episodes from the folder,
   trims the intro/outro, splits each episode into clips at scene changes,
   burns **"Subscribe for more videos"** into the top black bar, and posts
   each clip to **YouTube as scheduled (private + publishAt)** — invisible
   until its slot, then it goes live automatically. No music, no voiceover,
   no captions — just the clip + the subscribe text.

## ⚠️ Copyright (read this first)

"No dialogue" is **not** "copyright-free". Larva (TUBA Entertainment) and
Shaun the Sheep (Aardman) are copyrighted — posting them will get Content
ID claims (same as the "Feeling Blue" music did in the first project).
The bundled `sources.yaml` points at **public-domain cartoon playlists**
and CC searches. `fetch_cartoons.py` logs each file's declared license and
flags anything not clearly free — check the `[RISK]` warnings before
uploading. When in doubt, skip it.

## Local setup (desktop)

```bash
cd D:\Desktop\cartoon-clipper
python -m pip install -r requirements.txt
python fetch_cartoons.py --list        # preview what the sources yield
python fetch_cartoons.py --max 3       # download a few to test
```

Downloads land in `downloads/<source>/` + `downloads/manifest.json`.
Upload the good ones into your Drive **episodes folder** (the workflow
picks them up automatically). Optional: set per-show intro/outro in
`config.yaml` (episodes in a subfolder of the Drive folder become a
"show": `episodes/<show>/<file>.mp4`).

## GitHub setup (one-time, ~5 minutes)

1. **Drive folder** — create a folder for episodes, share it
   *Anyone with the link → Viewer*, and copy its ID from the URL
   (`drive.google.com/drive/folders/<ID>`).
2. **Google API key** — console.cloud.google.com → enable the
   **Google Drive API** → Credentials → API key.
3. **Secrets** in this repo (Settings → Secrets and variables → Actions):
   - `GDRIVE_FOLDER_ID` — the folder ID
   - `GDRIVE_API_KEY` — the API key
   - `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
     — you can reuse the faceless project's **client ID and client secret**
     (they're app-level, safe to share). The **refresh token is NOT** — it's
     bound to the Google account that authorized it, so it posts to THAT
     channel. If cartoon-clipper has its own YouTube channel, regenerate the
     token first with `python youtube_setup.py` (signed into the cartoon
     account) and store the NEW value here. Using the faceless token would
     upload cartoon clips to the faceless channel.
4. **Pause switch** (optional): create a file named `AUTOMATION_PAUSED` in
   the repo root to stop the pipeline; delete it to resume.

## The pipeline (GitHub Actions, `clip_and_post.yml`)

Runs daily at 03:30 UTC and on manual dispatch. For each new episode:
download from Drive → trim intro/outro → scene-detect split (min 15 s,
max 45 s per clip) → overlay subscribe text → upload each clip as
**private + publishAt** (2/day slots, 12:00 & 18:00 UTC, configurable) →
push state (`processed_episodes.json`, `schedule_state.json`,
`clips_manifest.json`). Episodes are clipped once, clips posted once,
slots never collide.

## Files

| File | Purpose |
|---|---|
| `fetch_cartoons.py` + `sources.yaml` | desktop downloader (copyright-free sources) |
| `drive_episodes.py` | workflow: download new episodes from the Drive folder |
| `clip_videos.py` | trim intro/outro, scene-split, burn subscribe text |
| `youtube_poster.py` | scheduled (private + publishAt) YouTube uploads |
| `youtube_setup.py` | one-time OAuth — mint a fresh YouTube refresh token for THIS channel |
| `config.yaml` | per-show trims, overlay text, posting cadence |
| `.github/workflows/clip_and_post.yml` | the daily pipeline |
