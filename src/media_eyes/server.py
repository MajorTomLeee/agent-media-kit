"""MCP and one-shot JSON interface share the same evidence engine."""

import argparse
import base64
import json
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import AudioContent, ImageContent, TextContent

from .core import MediaEyes


def main():
    parser = argparse.ArgumentParser(description="Give AI agents eyes and ears over MCP")
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/media-eyes")
    parser.add_argument("--allow-root", type=Path, action="append")
    parser.add_argument(
        "--json", action="store_true", help="Read one {tool, arguments} JSON request from stdin"
    )
    args = parser.parse_args()
    engine = MediaEyes(args.cache_dir, args.allow_root)

    def text(value):
        return TextContent(type="text", text=json.dumps(value, ensure_ascii=False))

    def frames(media_id, times):
        result = []
        for timestamp in times:
            result.extend(
                [
                    text({"media_id": media_id, "timestamp": timestamp}),
                    ImageContent(
                        type="image",
                        mimeType="image/jpeg",
                        data=base64.b64encode(
                            engine.frame(media_id, timestamp).read_bytes()
                        ).decode(),
                    ),
                ]
            )
        return result

    mcp = FastMCP("media-eyes")

    @mcp.tool()
    def open_media(source: str) -> list:
        """Open a local video/audio file or public website URL. Returns media_id and duration."""
        return [text(engine.open_media(source))]

    @mcp.tool()
    def get_overview(media_id: str, count: int = 8) -> list:
        """Look across a video with timestamped images. Sampled evidence may miss brief actions."""
        media = engine.metadata(media_id)
        if not media["has_video"]:
            return [
                text(
                    {
                        "duration": media["duration"],
                        "has_video": False,
                        "next": "read_transcript or get_audio_segment",
                    }
                )
            ]
        return frames(media_id, engine.timestamps(media_id, 0, media["duration"], count))

    @mcp.tool()
    def get_frame(media_id: str, timestamp: float) -> list:
        """Observe the video frame at a specific time in seconds."""
        return frames(media_id, [timestamp])

    @mcp.tool()
    def inspect_segment(media_id: str, start: float, end: float, count: int = 12) -> list:
        """Observe sequential timestamped frames in a segment; increase density for fast actions."""
        return frames(media_id, engine.timestamps(media_id, start, end, count))

    @mcp.tool()
    def get_audio_segment(media_id: str, start: float, end: float) -> list:
        """Return a mono WAV clip of at most 60 seconds. Requires a client/model supporting audio."""
        path = engine.audio_segment(media_id, start, end)
        return [
            text({"start": start, "end": end}),
            AudioContent(
                type="audio",
                mimeType="audio/wav",
                data=base64.b64encode(path.read_bytes()).decode(),
            ),
        ]

    @mcp.tool()
    def read_transcript(media_id: str, start: float = 0, end: float | None = None) -> list:
        """Read cached timestamped speech transcription. Requires the transcription extra; not sound-effect analysis."""
        return [text(engine.transcript(media_id, start, end))]

    functions = {
        fn.__name__: fn
        for fn in [
            open_media,
            get_overview,
            get_frame,
            inspect_segment,
            get_audio_segment,
            read_transcript,
        ]
    }
    if args.json:
        try:
            request = json.load(sys.stdin)
            result = functions[request["tool"]](**request.get("arguments", {}))
            json.dump(
                {"content": [item.model_dump(exclude_none=True) for item in result]}, sys.stdout
            )
        except (ValueError, KeyError, TypeError, OSError) as exc:
            json.dump(
                {"isError": True, "content": [{"type": "text", "text": str(exc)}]}, sys.stdout
            )
        return
    mcp.run()


if __name__ == "__main__":
    main()
