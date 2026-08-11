"""
drive_io.py — Google Drive WRITE operations (upload / delete) via a service
account.

The read-only API key (GDRIVE_API_KEY) can list and download, but uploading
and deleting need write access. A Google Cloud service account provides that:

  1. console.cloud.google.com -> IAM & Admin -> Service Accounts -> Create
     service account (e.g. "cartoon-drive").
  2. Keys -> Add key -> JSON -> download the key file.
  3. Share your Drive episodes folder with the service account's email as
     **Editor** (right-click folder -> Share -> add the email -> Editor).
  4. Point this code at the key via GDRIVE_SERVICE_ACCOUNT:
       - on your laptop: set it to the JSON file's path, or
       - in GitHub Actions: paste the whole JSON into a secret of the same
         name (the workflow writes it into the env).

Requires google-auth (already in requirements.txt).
"""

import json
import os

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

FOLDER_MIME = "application/vnd.google-apps.folder"


def get_token():
    """OAuth access token for the service account, or None if not configured."""
    raw = os.environ.get("GDRIVE_SERVICE_ACCOUNT", "").strip()
    if not raw:
        return None
    try:
        if os.path.exists(raw):
            info = json.load(open(raw, encoding="utf-8"))
        else:
            info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES)
        creds.refresh(Request())
        return creds.token
    except Exception as e:
        print(f"[drive-io] service-account auth failed: {e}")
        return None


def upload_file(folder_id, local_path, name=None):
    """Upload a file into the folder. Returns the new file id, or None if\n    the service account isn't configured."""
    token = get_token()
    if not token:
        return None
    name = name or os.path.basename(local_path)
    meta = {"name": name, "parents": [folder_id]}
    with open(local_path, "rb") as fh:
        files = {
            "metadata": (None, json.dumps(meta), "application/json"),
            "file": (name, fh, "video/mp4"),
        }
        r = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={"Authorization": f"Bearer {token}"}, files=files, timeout=900)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Drive upload failed {r.status_code}: {r.text[:200]}")
    return r.json().get("id")


def list_all(folder_id, token):
    """[(file_id, name)] including one level of subfolders ('<sub>/<name>')."""
    out = []
    params = {"q": f"'{folder_id}' in parents and trashed = false",
              "fields": "nextPageToken, files(id, name, mimeType)",
              "pageSize": 200}
    page = None
    while True:
        if page:
            params["pageToken"] = page
        r = requests.get("https://www.googleapis.com/drive/v3/files",
                         params=params,
                         headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"Drive API error {r.status_code}: {r.text[:200]}")
        data = r.json()
        for f in data.get("files", []):
            if f.get("mimeType") == FOLDER_MIME:
                for sub in list_all(f["id"], token):
                    out.append((sub[0], f"{f['name']}/{sub[1]}"))
            elif f.get("mimeType") == "video/mp4" or f.get("name", "").lower().endswith(".mp4"):
                out.append((f["id"], f["name"]))
        page = data.get("nextPageToken")
        if not page:
            break
    return out


def delete_file(file_id, token):
    """Delete a file by id (404 is treated as already-gone)."""
    r = requests.delete(f"https://www.googleapis.com/drive/v3/files/{file_id}",
                        headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if r.status_code == 404:
        return
    if r.status_code not in (200, 204):
        raise RuntimeError(f"Drive delete failed {r.status_code}: {r.text[:200]}")
