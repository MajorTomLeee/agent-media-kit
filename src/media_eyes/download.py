"""Isolated downloader: pin public IPs at the socket boundary, including redirects."""

import ipaddress
import json
import os
import socket
import sys
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, ExtractorError

from .core import LOCAL_MEDIA_FORMATS
from .diagnostics import classify, emit

MERGER_ARGS = ["-protocol_whitelist", "file,pipe", "-format_whitelist", LOCAL_MEDIA_FORMATS]


def media_filter(info, *, incomplete=False):
    if info.get("is_live") or (info.get("duration") or 0) > 3600:
        return "Live/long media is unsupported"
    protocol = info.get("protocol")
    if protocol and any(
        part not in ("http", "https", "m3u8_native", "http_dash_segments")
        for part in protocol.split("+")
    ):
        return "Only native HTTP media downloads are permitted"
    return None


class PublicSocket(socket.socket):
    def connect(self, address):
        if self.family not in (socket.AF_INET, socket.AF_INET6):
            raise OSError("Only public internet connections are permitted")
        host, port = address[:2]
        resolved = socket.getaddrinfo(host, port, self.family, socket.SOCK_STREAM)
        if not resolved or any(not ipaddress.ip_address(item[4][0]).is_global for item in resolved):
            raise OSError("Private network connections are not permitted")
        # Connect to the validated numeric address, never resolve the hostname again.
        return super().connect(resolved[0][4])

    def connect_ex(self, address):
        try:
            self.connect(address)
        except OSError:
            return 13
        return 0


def download():
    socket.socket = PublicSocket
    with YoutubeDL(
        {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "max_filesize": 256 * 1024 * 1024,
            "socket_timeout": 20,
            "retries": 1,
            "fragment_retries": 1,
            "format": "bv[height<=720]+ba/b[height<=720]/b",
            "merge_output_format": "mp4",
            "postprocessor_args": {"merger+ffmpeg_i": MERGER_ARGS},
            "fixup": "never",
            "outtmpl": sys.argv[2],
            "external_downloader": {"default": "native"},
            "proxy": "",
            "enable_file_urls": False,
            "match_filter": media_filter,
        },
        auto_init=False,
    ) as downloader:
        from .bilibili import BilibiliPublicApiIE

        downloader.add_default_info_extractors()
        downloader.add_info_extractor(BilibiliPublicApiIE())
        backend = sys.argv[3] if len(sys.argv) > 3 else "yt-dlp"
        if backend != "yt-dlp":
            from .providers import resolve

            resolved = resolve(
                downloader,
                sys.argv[1],
                backend,
                os.environ.get("MEDIA_EYES_COBALT_URL"),
                os.environ.get("MEDIA_EYES_COBALT_API_KEY")
                if backend == "cobalt"
                else os.environ.get("MEDIA_EYES_TIKHUB_API_KEY"),
            )
            for key, basename in (("url", "video"), ("audio_url", "audio")):
                if not resolved.get(key):
                    continue
                address = resolved[key]
                if not isinstance(address, str) or not address.startswith(("https://", "http://")):
                    raise ValueError("Resolver returned an invalid media URL")
                downloader.params["outtmpl"] = {
                    "default": str(Path(sys.argv[2]).parent / (basename + ".%(ext)s"))
                }
                downloader.params["http_headers"] = {
                    "Referer": resolved.get("referer", sys.argv[1])
                }
                downloader.extract_info(address, download=True)
            from .core import MediaEyes

            directory = Path(sys.argv[2]).parent
            video = list(directory.glob("video.*"))
            audio = list(directory.glob("audio.*"))
            if len(video) != 1 or len(audio) > 1:
                raise ValueError("Resolver did not produce supported media")
            if audio:
                MediaEyes.run(
                    [
                        "ffmpeg",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-nostdin",
                        "-v",
                        "error",
                        "-i",
                        str(video[0]),
                        "-i",
                        str(audio[0]),
                        "-map",
                        "0:v:0",
                        "-map",
                        "1:a:0",
                        "-c",
                        "copy",
                        "-y",
                        str(directory / "source.mp4"),
                    ]
                )
                video[0].unlink()
                audio[0].unlink()
            else:
                video[0].rename(directory / ("source" + video[0].suffix))
            return
        info = downloader.extract_info(sys.argv[1], download=True)
        if info:
            from .captions import choose_caption_track, parse_captions

            directory = Path(sys.argv[2]).parent
            tracks = []
            # Bound downloads and never fetch subtitles through a different network stack.
            for language in ("auto", "zh", "en"):
                selected = choose_caption_track(info, language)
                if not selected or any(t["language"] == selected[0] for t in tracks):
                    continue
                code, provenance, track = selected
                try:
                    if track.get("data"):
                        raw = track["data"].encode()
                    else:
                        with downloader.urlopen(track["url"]) as response:
                            raw = response.read(2 * 1024 * 1024 + 1)
                    if len(raw) > 2 * 1024 * 1024:
                        continue
                    segments = parse_captions(raw.decode("utf-8"), track["ext"])
                    tracks.append(
                        {"language": code, "provenance": provenance, "segments": segments}
                    )
                except (OSError, ValueError, UnicodeError):
                    continue
            (directory / "captions.json").write_text(json.dumps(tracks))


def main():
    emit("download_started")
    try:
        download()
    except (DownloadError, ExtractorError, ValueError, KeyError, TypeError, OSError) as error:
        emit("download_failed", **classify(error))
        return 1
    emit("download_completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
