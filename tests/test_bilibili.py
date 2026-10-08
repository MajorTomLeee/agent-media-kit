import json
import subprocess
import sys

import pytest
from yt_dlp.networking.exceptions import HTTPError
from yt_dlp.utils import ExtractorError

from media_eyes.bilibili import BilibiliPublicApiIE
from media_eyes.core import MediaEyes
from media_eyes.diagnostics import classify, failure_message
from media_eyes.download import media_filter


class ApiFixture(BilibiliPublicApiIE):
    def __init__(self):
        super().__init__()
        self.queries = []
        self.video = {
            "bvid": "BV1pg411W79J",
            "title": "Public fixture",
            "pages": [{"cid": 11, "duration": 20}, {"cid": 12, "duration": 30}],
        }
        self.play = {"dash": {}}

    def _sign_wbi(self, query, identifier):
        self.queries.append(query)
        return query

    def _download_json(self, *args, **kwargs):
        return {"code": 0, "data": {"View": self.video}}

    def _download_playinfo(self, bvid, cid, **kwargs):
        self.cid = cid
        assert kwargs["query"] == {"try_look": 0}
        return self.play

    def extract_formats(self, play):
        return [{"url": "https://public.example/video", "height": 480}]


def test_signed_public_metadata_and_requested_part(capsys):
    api = ApiFixture()
    info = api._public_api("https://www.bilibili.com/video/BV1pg411W79J/?p=2")
    assert api.cid == 12
    assert info["duration"] == 30
    assert api.queries == [{"platform": "web", "bvid": "BV1pg411W79J"}]
    assert "fallback_resolved" in capsys.readouterr().err
    api._public_api("https://www.bilibili.com/video/av123")
    assert api.queries[-1] == {"platform": "web", "aid": "123"}


@pytest.mark.parametrize("part", ["0", "3", "bad", "-1"])
def test_invalid_part_never_downloads(part):
    with pytest.raises(ExtractorError, match="part number"):
        ApiFixture()._public_api(f"https://www.bilibili.com/video/BV1pg411W79J/?p={part}")


def test_paid_preview_and_long_media_are_not_bypassed():
    api = ApiFixture()
    api.video["is_upower_exclusive"] = True
    with pytest.raises(ExtractorError, match="ACCESS_REQUIRED"):
        api._public_api("https://www.bilibili.com/video/BV1pg411W79J")
    api.video.pop("is_upower_exclusive")
    api.play["is_preview"] = True
    with pytest.raises(ExtractorError, match="Preview-only"):
        api._public_api("https://www.bilibili.com/video/BV1pg411W79J")
    api.play.pop("is_preview")
    api.video["pages"][0]["duration"] = 3601
    with pytest.raises(ExtractorError, match="long media"):
        api._public_api("https://www.bilibili.com/video/BV1pg411W79J")


def test_only_412_uses_fallback(monkeypatch):
    from yt_dlp.extractor.bilibili import BiliBiliIE

    class Response:
        status = 412
        reason = "Precondition Failed"

    def failed(*args):
        raise ExtractorError("Blocked", cause=HTTPError(Response()))

    monkeypatch.setattr(BiliBiliIE, "_real_extract", failed)
    assert ApiFixture()._real_extract("https://www.bilibili.com/video/BV1pg411W79J")["title"]
    Response.status = 403
    with pytest.raises(ExtractorError, match="Blocked"):
        ApiFixture()._real_extract("https://www.bilibili.com/video/BV1pg411W79J")


def test_failure_code_and_status_survive_subprocess_boundary(monkeypatch):
    secret = "https://cdn.example/video?token=secret-cookie-value"
    detail = json.dumps({"event": "download_failed", **classify(f"HTTP Error 412: {secret}")})

    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr=detail.encode())

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(ValueError, match=r"PLATFORM_BLOCKED \(HTTP 412\)") as error:
        MediaEyes.run([sys.executable, "-m", "media_eyes.download"])
    assert "secret" not in str(error.value)
    assert classify("HTTP Error 404")["error_code"] == "SOURCE_UNAVAILABLE"
    assert classify("HTTP Error 403")["error_code"] == "ACCESS_REQUIRED"
    assert "HTTP 429" in failure_message(classify("HTTP Error 429"))


def test_separate_http_audio_and_video_are_allowed_but_private_protocols_are_not():
    assert media_filter({"protocol": "https+https", "duration": 20}) is None
    assert media_filter({"protocol": "http_dash_segments+https", "duration": 20}) is None
    assert media_filter({"protocol": "https+file", "duration": 20}) is not None
    assert media_filter({"protocol": "https+rtmp", "duration": 20}) is not None
    assert media_filter({"protocol": "https+https", "duration": 3601}) is not None


def test_explicit_shortlink_redirect_routes_to_our_extractor():
    from yt_dlp import YoutubeDL

    with YoutubeDL({"quiet": True}, auto_init=False) as downloader:
        downloader.add_default_info_extractors()
        downloader.add_info_extractor(BilibiliPublicApiIE())
        assert isinstance(downloader.get_info_extractor("BiliBili"), BilibiliPublicApiIE)
