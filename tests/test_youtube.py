import io
import json
import urllib.error

import pytest

from frisian_shorts import youtube


class FakeResponse(io.BytesIO):
    def __init__(self, body=b"", headers=None):
        super().__init__(body)
        self.headers = headers or {}


def test_upload(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "123-abc.apps.googleusercontent.com\n")  # pasted with a newline
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh")
    video = tmp_path / "puzzle.mp4"
    video.write_bytes(b"mp4 bytes")
    requests = []
    responses = iter(
        [
            FakeResponse(b'{"access_token": "token"}'),
            FakeResponse(headers={"Location": "https://upload.example/session"}),
            FakeResponse(b'{"id": "abc123"}'),
        ]
    )

    def fake_urlopen(req, timeout):
        requests.append(req)
        return next(responses)

    monkeypatch.setattr(youtube.urllib.request, "urlopen", fake_urlopen)
    assert youtube.upload(video, "title", "description", ["tag"], "2026-10-30T18:00:00+01:00") == "abc123"

    token, session, put = requests
    assert b"grant_type=refresh_token" in token.data
    assert b"client_id=123-abc.apps.googleusercontent.com&" in token.data
    status = json.loads(session.data)["status"]
    assert (status["privacyStatus"], status["publishAt"]) == ("private", "2026-10-30T18:00:00+01:00")
    assert (put.full_url, put.get_method(), put.data) == ("https://upload.example/session", "PUT", b"mp4 bytes")
    assert put.headers["Authorization"] == "Bearer token"


def test_token_error_explains_what_to_check(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "123-abc.apps.googleusercontent.com")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh")
    body = b'{"error": "invalid_client", "error_description": "The OAuth client was not found."}'

    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, io.BytesIO(body))

    monkeypatch.setattr(youtube.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(SystemExit, match="Google Auth Platform > Clients"):
        youtube.access_token()


def test_client_id_format_is_checked(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "GOCSPX-looks-like-a-client-secret")
    with pytest.raises(SystemExit, match="apps.googleusercontent.com"):
        youtube.access_token()
