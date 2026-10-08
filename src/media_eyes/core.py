"""Deterministic media evidence. No model credentials are needed to look at frames."""

import hashlib
import ipaddress
import json
import math
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


class MediaEyes:
    def __init__(self, cache_dir: Path, roots: list[Path] | None = None):
        self.cache = cache_dir.resolve()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.roots = [root.resolve() for root in roots] if roots is not None else None

    @staticmethod
    def run(args: list[str], timeout: int = 120) -> str:
        if args[0] in ("ffmpeg", "ffprobe"):
            # Reject playlist/concat demuxers that could read files outside allowed roots.
            args = [
                args[0],
                "-format_whitelist",
                "mov,matroska,mp3,wav,ogg,flac,aac,mpegts,mpeg,avi",
                *args[1:],
            ]
        try:
            result = subprocess.run(args, capture_output=True, timeout=timeout, check=True)
        except FileNotFoundError as exc:
            raise ValueError(f"Install the missing executable: {args[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Media processing exceeded its time limit") from exc
        except subprocess.CalledProcessError as exc:
            # Downloader errors can include signed URLs or credentials.
            raise ValueError(
                f"{args[0]} failed; check format, access and installed version"
            ) from exc
        return result.stdout.decode()

    def open_media(self, source: str) -> dict:
        if source.startswith(("https://", "http://")):
            parsed = urlsplit(source)
            if parsed.username or parsed.password or not parsed.hostname:
                raise ValueError("Provide a public HTTP(S) URL without embedded credentials")
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise ValueError("Private and local network URLs are not allowed")
            identity = hashlib.sha256(source.encode()).hexdigest()
            directory = self.cache / identity
            directory.mkdir(exist_ok=True)
            existing = [p for p in directory.glob("source.*") if p.suffix != ".part"]
            if existing:
                path = existing[0]
            else:
                self.run(
                    [
                        sys.executable,
                        "-m",
                        "media_eyes.download",
                        source,
                        str(directory / "source.%(ext)s"),
                    ],
                    timeout=300,
                )
                existing = [p for p in directory.glob("source.*") if p.suffix != ".part"]
                if len(existing) != 1:
                    raise ValueError("No supported finite media file was downloaded")
                path = existing[0]
        else:
            path = Path(source).expanduser().resolve(strict=True)
            if self.roots is not None and not any(path.is_relative_to(r) for r in self.roots):
                raise ValueError("Media file is outside the configured allowed roots")
            if not path.is_file():
                raise ValueError("Source must be a regular file")
            stat = path.stat()
            identity = hashlib.sha256(
                f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode()
            ).hexdigest()
            directory = self.cache / identity
            directory.mkdir(exist_ok=True)
        if path.stat().st_size > 256 * 1024 * 1024:
            raise ValueError("Media exceeds the 256 MiB limit")
        info = json.loads(
            self.run(
                [
                    "ffprobe",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ]
            )
        )
        duration = float(info.get("format", {}).get("duration", 0))
        if not math.isfinite(duration) or not 0 < duration <= 3600:
            raise ValueError("Media must have a finite duration between 0 and 3600 seconds")
        streams = info.get("streams", [])
        metadata = {
            "media_id": identity,
            "duration": duration,
            "has_video": any(s["codec_type"] == "video" for s in streams),
            "has_audio": any(s["codec_type"] == "audio" for s in streams),
            "path": str(path),
        }
        if not metadata["has_video"] and not metadata["has_audio"]:
            raise ValueError("Source has no audio or video stream")
        (directory / "metadata.json").write_text(json.dumps(metadata))
        return {key: value for key, value in metadata.items() if key != "path"}

    def metadata(self, media_id: str) -> dict:
        if len(media_id) != 64 or any(c not in "0123456789abcdef" for c in media_id):
            raise ValueError("Invalid media ID; call open_media first")
        try:
            return json.loads((self.cache / media_id / "metadata.json").read_text())
        except FileNotFoundError as exc:
            raise ValueError("Unknown media ID; call open_media first") from exc

    def frame(self, media_id: str, timestamp: float) -> Path:
        media = self.metadata(media_id)
        if not media["has_video"]:
            raise ValueError("This media has no video stream")
        if not math.isfinite(timestamp) or not 0 <= timestamp < media["duration"]:
            raise ValueError("Timestamp must be within the media duration")
        target = self.cache / media_id / f"frame-{timestamp:.6f}.jpg"
        if not target.exists():
            self.run(
                [
                    "ffmpeg",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    str(timestamp),
                    "-i",
                    media["path"],
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=1280:720:force_original_aspect_ratio=decrease",
                    "-q:v",
                    "3",
                    "-y",
                    str(target),
                ]
            )
        if not target.exists() or not target.stat().st_size:
            raise ValueError("No frame is decodable at this timestamp; try an earlier time")
        return target

    def timestamps(self, media_id: str, start: float, end: float, count: int) -> list[float]:
        duration = self.metadata(media_id)["duration"]
        if not all(math.isfinite(t) for t in [start, end]) or not 0 <= start < end <= duration:
            raise ValueError("Segment must be inside media duration, with start < end")
        if not 1 <= count <= 24:
            raise ValueError("Request between 1 and 24 frames")
        return [start + (end - start) * i / count for i in range(count)]

    def audio_segment(self, media_id: str, start: float, end: float) -> Path:
        media = self.metadata(media_id)
        self.timestamps(media_id, start, end, 1)
        if not media["has_audio"]:
            raise ValueError("This media has no audio stream")
        if end - start > 60:
            raise ValueError("Audio clips are limited to 60 seconds per call")
        target = self.cache / media_id / f"audio-{start:.6f}-{end:.6f}.wav"
        if not target.exists():
            self.run(
                [
                    "ffmpeg",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    str(start),
                    "-i",
                    media["path"],
                    "-t",
                    str(end - start),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-y",
                    str(target),
                ]
            )
        return target

    def transcript(self, media_id: str, start: float = 0, end: float | None = None) -> dict:
        media = self.metadata(media_id)
        end = media["duration"] if end is None else end
        self.timestamps(media_id, start, end, 1)
        if not media["has_audio"]:
            return {"segments": [], "has_audio": False}
        target = self.cache / media_id / "transcript.json"
        if not target.exists():
            cpp_model = os.environ.get("MEDIA_EYES_WHISPER_CPP_MODEL")
            if cpp_model:
                wav = self.cache / media_id / "speech.wav"
                self.run(
                    [
                        "ffmpeg",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-nostdin",
                        "-v",
                        "error",
                        "-i",
                        media["path"],
                        "-vn",
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        "-c:a",
                        "pcm_s16le",
                        "-y",
                        str(wav),
                    ]
                )
                prefix = self.cache / media_id / "whisper"
                self.run(
                    [
                        "whisper-cli",
                        "-m",
                        cpp_model,
                        "-f",
                        str(wav),
                        "-l",
                        "auto",
                        "-oj",
                        "-of",
                        str(prefix),
                    ],
                    timeout=600,
                )
                raw = json.loads(prefix.with_suffix(".json").read_text())
                result = {
                    "language": raw["result"]["language"],
                    "segments": [
                        {
                            "start": s["offsets"]["from"] / 1000,
                            "end": s["offsets"]["to"] / 1000,
                            "text": s["text"],
                        }
                        for s in raw["transcription"]
                    ],
                }
            else:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise ValueError(
                        "Install media-eyes[transcription], or configure whisper-cli and MEDIA_EYES_WHISPER_CPP_MODEL"
                    ) from exc
                model = WhisperModel(
                    os.environ.get("MEDIA_EYES_WHISPER_MODEL", "base"),
                    device="cpu",
                    compute_type="int8",
                )
                segments, info = model.transcribe(media["path"], vad_filter=True)
                result = {
                    "language": info.language,
                    "segments": [
                        {"start": s.start, "end": s.end, "text": s.text} for s in segments
                    ],
                }
            result["scope"] = (
                "Speech transcription only; music and sound effects are not described."
            )
            target.write_text(json.dumps(result))
        result = json.loads(target.read_text())
        result["segments"] = [
            s for s in result["segments"] if s["end"] > start and s["start"] < end
        ]
        return result
