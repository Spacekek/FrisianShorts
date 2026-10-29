# Upload a video to YouTube, scheduled to go public later, using OAuth credentials from the environment (stdlib only).
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
# what to check for Google's token errors, matched on the error code in the response
HINTS = {
    "invalid_client": "Google doesn't recognise YOUTUBE_CLIENT_ID, or YOUTUBE_CLIENT_SECRET doesn't belong to it: "
    "compare both with the client under Google Auth Platform > Clients.",
    "unauthorized_client": "YOUTUBE_REFRESH_TOKEN was made with a different OAuth client: redo the OAuth Playground "
    "step with 'Use your own OAuth credentials' ticked.",
    "invalid_grant": "YOUTUBE_REFRESH_TOKEN is expired or revoked: check the app is 'In production' under "
    "Google Auth Platform > Audience, then get a new one from the OAuth Playground.",
}


def _open(req, timeout=60):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        hints = [hint for error, hint in HINTS.items() if f'"{error}"' in body]
        raise SystemExit("\n".join([f"YouTube API error {e.code}: {body}", *hints])) from None


def _secret(name):
    """An environment variable that must be set; surrounding whitespace from pasting is dropped."""
    if not (value := os.environ.get(name, "").strip()):
        raise SystemExit(f"{name} is empty or not set; add it with: gh secret set {name}")
    return value


def access_token():
    print("YouTube: getting an access token")
    client_id = _secret("YOUTUBE_CLIENT_ID")
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise SystemExit(
            "YOUTUBE_CLIENT_ID doesn't look like an OAuth client ID: it should end in .apps.googleusercontent.com"
        )
    form = {
        "client_id": client_id,
        "client_secret": _secret("YOUTUBE_CLIENT_SECRET"),
        "refresh_token": _secret("YOUTUBE_REFRESH_TOKEN"),
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
    print(f"YouTube: uploading {path} ({len(video) / 1e6:.1f} MB)")
    with _open(urllib.request.Request(UPLOAD_URL, json.dumps(meta).encode(), headers)) as resp:
        session = resp.headers["Location"]
    put = urllib.request.Request(session, video, {**auth, "Content-Type": "video/mp4"}, method="PUT")
    with _open(put, timeout=600) as resp:
        return json.load(resp)["id"]
