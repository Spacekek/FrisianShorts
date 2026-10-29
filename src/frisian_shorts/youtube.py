# Upload a video to YouTube, scheduled to go public later, using OAuth credentials from the environment (stdlib only).
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"


def _open(req, timeout=60):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"YouTube API error {e.code}: {e.read().decode(errors='replace')}") from None


def access_token():
    form = {
        "client_id": os.environ["YOUTUBE_CLIENT_ID"],
        "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }
    req = urllib.request.Request("https://oauth2.googleapis.com/token", urllib.parse.urlencode(form).encode())
    with _open(req) as resp:
        return json.load(resp)["access_token"]


def upload(path, title, description, tags, publish_at):
    """Upload an mp4 as private, going public at publish_at (ISO 8601), and return its id.

    Resumable upload: open a session, then send the file.
    """
    video = Path(path).read_bytes()
    auth = {"Authorization": f"Bearer {access_token()}"}
    meta = {
        "snippet": {"title": title, "description": description, "tags": tags, "categoryId": "20"},  # 20 = Gaming
        "status": {"privacyStatus": "private", "publishAt": publish_at, "selfDeclaredMadeForKids": False},
    }
    headers = {
        **auth,
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(len(video)),
    }
    with _open(urllib.request.Request(UPLOAD_URL, json.dumps(meta).encode(), headers)) as resp:
        session = resp.headers["Location"]
    put = urllib.request.Request(session, video, {**auth, "Content-Type": "video/mp4"}, method="PUT")
    with _open(put, timeout=600) as resp:
        return json.load(resp)["id"]
