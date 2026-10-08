import os
import subprocess
import time

import pytest
from test_core import media  # noqa: F401

from media_eyes.cache import prune, write_json
from media_eyes.captions import choose_caption_track, parse_captions
from media_eyes.core import MediaEyes
from media_eyes.providers import NoRedirect, platform, resolve


def test_caption_formats_and_priority():
    assert parse_captions("WEBVTT\n\n00:01.000 --> 00:02.000\n<b>Hello</b>", "vtt") == [
        {"start": 1, "end": 2, "text": "Hello"}
    ]
    assert (
        parse_captions(
            '{"events":[{"tStartMs":1000,"dDurationMs":1000,"segs":[{"utf8":"你好"}]}]}', "json3"
        )[0]["text"]
        == "你好"
    )
    info = {
        "subtitles": {"zh": [{"ext": "srt", "data": "captions"}]},
        "automatic_captions": {"en": [{"ext": "vtt", "url": "https://example.org"}]},
    }
    assert choose_caption_track(info)[1] == "website_subtitles"
    assert choose_caption_track(info, "en")[1] == "website_auto_captions"
    assert choose_caption_track(info, "fr") is None


def test_png_and_caption_evidence(media):  # noqa: F811
    engine, info, _ = media
    identity = info["media_id"]
    assert engine.frame(identity, 1, "png", 1920).read_bytes().startswith(b"\x89PNG")
    write_json(
        engine.cache / identity / "captions.json",
        [
            {
                "language": "zh",
                "provenance": "website_subtitles",
                "segments": [{"start": 0, "end": 2, "text": "你好"}],
            }
        ],
    )
    result = engine.transcript(identity, 1, 2, "zh")
    assert result["provenance"] == "website_subtitles"
    assert result["segments"][0]["text"] == "你好"
    with pytest.raises(ValueError):
        engine.frame(identity, 1, "gif")
    with pytest.raises(ValueError):
        engine.transcript(identity, 0, 2, "../")


def test_scene_and_silence_real_ffmpeg(tmp_path):
    path = tmp_path / "cuts.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=160x120:d=1",
            "-f",
            "lavfi",
            "-i",
            "color=white:s=160x120:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-t",
            "2",
            "-y",
            str(path),
        ],
        check=True,
    )
    engine = MediaEyes(tmp_path / "cache")
    info = engine.open_media(str(path))
    result = engine.analyze_media(info["media_id"])
    assert any(abs(t - 1) < 0.6 for t in result["scene_changes"])
    assert result["silences"][0]["start"] == 0
    assert result["silences"][0]["end"] == pytest.approx(2, abs=0.1)


def test_retention_never_removes_original(media):  # noqa: F811
    engine, info, original = media
    marker = engine.cache / info["media_id"] / ".access"
    os.utime(marker, (time.time() - 10 * 86400,) * 2)
    assert prune(engine.cache, 7, 2 * 1024**3)["removed"] == 1
    assert original.exists()


def test_explicit_provider_routing(monkeypatch):
    assert platform("https://b23.tv/abc") == "bilibili"
    assert platform("https://bilibili.com.attacker.test") == "other"
    with pytest.raises(ValueError, match="opt-in"):
        resolve(None, "https://v.douyin.com/a", "tikhub")
    with pytest.raises(ValueError, match="HTTPS"):
        resolve(None, "https://example.org", "cobalt", "http://localhost")
    monkeypatch.setattr(
        "media_eyes.providers.json_request",
        lambda *a, **kw: {"status": "tunnel", "url": "https://example.org/video.mp4"},
    )
    assert resolve(None, "https://example.org", "cobalt", "https://resolver.example.org")[
        "url"
    ].endswith("mp4")
    with pytest.raises(ValueError, match="redirects"):
        NoRedirect().redirect_request(None, None, 302, None, {}, "https://attacker.test")


def test_cloud_audio_disabled_by_default(media, monkeypatch):  # noqa: F811
    engine, info, _ = media
    monkeypatch.delenv("MEDIA_EYES_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MEDIA_EYES_GEMINI_MODEL", raising=False)
    with pytest.raises(ValueError, match="disabled"):
        engine.analyze_audio(info["media_id"], 0, 1)


def test_tikhub_normalized_streams(monkeypatch):
    monkeypatch.setattr(
        "media_eyes.providers.json_request",
        lambda *a, **kw: {
            "data": {"video_data": {"nwm_video_url": "https://cdn.example.org/movie.mp4"}}
        },
    )
    assert resolve(None, "https://v.douyin.com/a", "tikhub", token="test")["url"].endswith(
        "movie.mp4"
    )
    monkeypatch.setattr(
        "media_eyes.providers.json_request",
        lambda *a, **kw: {
            "data": {
                "dash": {
                    "video": [{"height": 720, "baseUrl": "https://cdn.example.org/video.m4s"}],
                    "audio": [{"baseUrl": "https://cdn.example.org/audio.m4s"}],
                }
            }
        },
    )
    result = resolve(None, "https://www.bilibili.com/video/BVtest", "tikhub", token="test")
    assert result["audio_url"].endswith("audio.m4s")
    assert result["referer"] == "https://www.bilibili.com/"


def test_interval_transcription_absolute_times(media, monkeypatch):  # noqa: F811
    engine, info, _ = media
    monkeypatch.setenv("MEDIA_EYES_WHISPER_CPP_MODEL", "/model.bin")
    real_run = engine.run
    calls = []

    def run(args, timeout=120):
        calls.append(args)
        if args[0] == "whisper-cli":
            write_json(
                engine.cache / info["media_id"] / "whisper.json",
                {
                    "result": {"language": "en"},
                    "transcription": [{"offsets": {"from": 0, "to": 500}, "text": "hello"}],
                },
            )
            return ""
        return real_run(args, timeout)

    monkeypatch.setattr(engine, "run", run)
    result = engine.transcript(info["media_id"], 1, 2, "en")
    assert result["segments"] == [{"start": 1, "end": 1.5, "text": "hello"}]
    assert engine.transcript(info["media_id"], 1, 2, "en") == result
    assert sum(args[0] == "whisper-cli" for args in calls) == 1
