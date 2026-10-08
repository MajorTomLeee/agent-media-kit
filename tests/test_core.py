import json
import subprocess

import pytest

from media_eyes.core import MediaEyes


@pytest.fixture
def media(tmp_path):
    path = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x240:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "3",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(path),
        ],
        check=True,
    )
    engine = MediaEyes(tmp_path / "cache", roots=[tmp_path])
    return engine, engine.open_media(str(path)), path


def test_observe_real_video_and_audio(media):
    engine, info, _ = media
    assert info["has_video"] and info["has_audio"]
    frame = engine.frame(info["media_id"], 1)
    assert frame.read_bytes().startswith(b"\xff\xd8")
    assert engine.frame(info["media_id"], 1) == frame
    audio = engine.audio_segment(info["media_id"], 0, 1)
    assert audio.read_bytes().startswith(b"RIFF")
    assert engine.timestamps(info["media_id"], 0, 3, 3) == [0, 1, 2]


def test_boundaries(media, tmp_path):
    engine, info, path = media
    for timestamp in [-1, 4, float("nan")]:
        with pytest.raises(ValueError):
            engine.frame(info["media_id"], timestamp)
    with pytest.raises(ValueError):
        engine.timestamps(info["media_id"], 0, 3, 25)
    with pytest.raises(ValueError):
        engine.metadata("../../etc/passwd")
    with pytest.raises(ValueError):
        MediaEyes(tmp_path / "other-cache", roots=[]).open_media(str(path))
    with pytest.raises(ValueError, match="Private"):
        engine.open_media("http://127.0.0.1/private")


def test_json_interface(media, tmp_path):
    _, _, path = media
    result = subprocess.run(
        ["media-eyes", "--cache-dir", str(tmp_path / "cli-cache"), "--json"],
        input=json.dumps({"tool": "open_media", "arguments": {"source": str(path)}}),
        capture_output=True,
        text=True,
        check=True,
    )
    content = json.loads(result.stdout)["content"]
    assert json.loads(content[0]["text"])["has_video"]


def test_playlist_cannot_read_other_files(tmp_path):
    playlist = tmp_path / "playlist.mp4"
    playlist.write_text("#EXTM3U\n#EXTINF:1,\nfile:/etc/passwd\n#EXT-X-ENDLIST\n")
    with pytest.raises(ValueError, match="ffprobe failed"):
        MediaEyes(tmp_path / "cache", roots=[tmp_path]).open_media(str(playlist))
