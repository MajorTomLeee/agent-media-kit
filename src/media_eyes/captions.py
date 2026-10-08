"""Normalize SRT, VTT and yt-dlp JSON subtitles into timestamped evidence."""

import html
import json
import math
import re


def seconds(raw: str) -> float:
    parts = raw.replace(",", ".").split(":")
    return sum(float(part) * 60**i for i, part in enumerate(reversed(parts)))


def parse_captions(raw: str, extension: str) -> list[dict]:
    if extension == "json3":
        events = json.loads(raw).get("events", [])
        segments = [
            {
                "start": event["tStartMs"] / 1000,
                "end": (event["tStartMs"] + event.get("dDurationMs", 0)) / 1000,
                "text": "".join(segment.get("utf8", "") for segment in event.get("segs", [])),
            }
            for event in events
            if "tStartMs" in event
        ]
    else:
        segments = []
        for block in re.split(r"\n\s*\n", raw.replace("\r", "")):
            lines = block.splitlines()
            for index, line in enumerate(lines):
                if "-->" not in line:
                    continue
                start, end = line.split("-->", 1)
                segments.append(
                    {
                        "start": seconds(start.strip()),
                        "end": seconds(end.strip().split()[0]),
                        "text": " ".join(lines[index + 1 :]),
                    }
                )
                break
    normalized = []
    for segment in segments:
        segment["text"] = html.unescape(re.sub(r"<[^>]*>", "", segment["text"])).strip()
        if (
            segment["text"]
            and all(math.isfinite(segment[k]) for k in ("start", "end"))
            and 0 <= segment["start"] < segment["end"] <= 3600
            and (not normalized or segment != normalized[-1])
        ):
            normalized.append(segment)
    return normalized


def choose_caption_track(info: dict, language: str = "auto"):
    for key, provenance in (
        ("subtitles", "website_subtitles"),
        ("automatic_captions", "website_auto_captions"),
    ):
        tracks = info.get(key) or {}
        candidates = sorted(tracks, key=lambda code: (not code.startswith("en"), code))
        if language != "auto":
            candidates = [
                code for code in candidates if code == language or code.startswith(language + "-")
            ]
        for code in candidates:
            for extension in ("vtt", "srt", "json3"):
                for track in tracks[code]:
                    if track.get("ext") == extension and (track.get("url") or track.get("data")):
                        return code, provenance, track
    return None
