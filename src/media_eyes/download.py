"""Isolated downloader: pin public IPs at the socket boundary, including redirects."""

import ipaddress
import socket
import sys

from yt_dlp import YoutubeDL


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


def main():
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
            "format": "b[height<=720]/b",
            "outtmpl": sys.argv[2],
            "external_downloader": {"default": "native"},
            "proxy": "",
            "enable_file_urls": False,
            "match_filter": lambda info, *, incomplete=False: (
                "Live/long media is unsupported"
                if info.get("is_live") or (info.get("duration") or 0) > 3600
                else None
            ),
        }
    ) as downloader:
        downloader.download([sys.argv[1]])


if __name__ == "__main__":
    main()
