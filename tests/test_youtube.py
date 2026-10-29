import io
import json

from frisian_shorts import youtube


class FakeResponse(io.BytesIO):
    def __init__(self, body=b"", headers=None):
        super().__init__(body)
        self.headers = headers or {}


def test_upload(monkeypatch, tmp_path):
    for name in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
        monkeypatch.setenv(name, "test")
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
    status = json.loads(session.data)["status"]
    assert (status["privacyStatus"], status["publishAt"]) == ("private", "2026-10-30T18:00:00+01:00")
    assert (put.full_url, put.get_method(), put.data) == ("https://upload.example/session", "PUT", b"mp4 bytes")
    assert put.headers["Authorization"] == "Bearer token"
