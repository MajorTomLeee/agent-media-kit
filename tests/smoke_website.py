"""Opt-in real-website verification through the installed one-shot MCP interface."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def call(cache, tool, arguments):
    result = subprocess.run(
        [sys.executable, "-m", "media_eyes.server", "--json", "--cache-dir", str(cache)],
        input=json.dumps({"tool": tool, "arguments": arguments}),
        capture_output=True,
        text=True,
        timeout=600,
        check=True,
    )
    response = json.loads(result.stdout)
    if response.get("isError"):
        raise RuntimeError(response["content"][0]["text"])
    # The engine forwards safe structured records only, not signed CDN addresses.
    for line in result.stderr.splitlines():
        if line.startswith('{"event":'):
            print(line)
    return response["content"]


def main():
    with TemporaryDirectory(prefix="agent-media-kit-website-") as directory:
        cache = Path(directory)
        media = json.loads(call(cache, "open_media", {"source": sys.argv[1]})[0]["text"])
        assert media["has_video"] and media["has_audio"]
        identity = media["media_id"]
        assert media["duration"] > 0
        for timestamp in (0, media["duration"] / 2, max(0, media["duration"] - 1)):
            content = call(cache, "get_frame", {"media_id": identity, "timestamp": timestamp})
            assert content[1]["type"] == "image"
            assert content[1]["mimeType"] == "image/jpeg"
            assert len(content[1]["data"]) > 1000
        segment = call(
            cache,
            "inspect_segment",
            {"media_id": identity, "start": 0, "end": min(10, media["duration"]), "count": 3},
        )
        assert sum(item["type"] == "image" for item in segment) == 3
        audio = call(
            cache,
            "get_audio_segment",
            {"media_id": identity, "start": 0, "end": min(2, media["duration"])},
        )
        assert audio[1]["type"] == "audio" and audio[1]["mimeType"] == "audio/wav"
        print(
            json.dumps(
                {
                    "verified": True,
                    "duration": media["duration"],
                    "video": True,
                    "audio": True,
                    "frames": 6,
                    "audio_segment": True,
                }
            )
        )


if __name__ == "__main__":
    main()
