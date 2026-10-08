"""Public, signed API fallback for ordinary Bilibili videos blocked at the HTML page."""

import math
from urllib.parse import parse_qs, urlsplit

from yt_dlp.extractor.bilibili import BiliBiliIE
from yt_dlp.networking.exceptions import HTTPError
from yt_dlp.utils import ExtractorError

from .diagnostics import emit


class BilibiliPublicApiIE(BiliBiliIE):
    def _real_extract(self, url):
        try:
            return super()._real_extract(url)
        except ExtractorError as error:
            if not isinstance(error.cause, HTTPError) or error.cause.status != 412:
                raise
            emit("fallback_started", backend="bilibili_public_api", http_status=412)
            return self._public_api(url)

    def _public_api(self, url):
        match = self._match_valid_url(url)
        identifier, prefix = match.group("id", "prefix")
        query = {"platform": "web"}
        query["bvid" if prefix.upper() == "BV" else "aid"] = (
            "BV" + identifier if prefix.upper() == "BV" else identifier
        )
        headers = {"Referer": "https://www.bilibili.com/", "Origin": "https://www.bilibili.com"}
        response = self._download_json(
            "https://api.bilibili.com/x/web-interface/wbi/view/detail",
            identifier,
            query=self._sign_wbi(query, identifier),
            headers=headers,
        )
        if response.get("code") != 0:
            raise ExtractorError("Public video metadata is unavailable", expected=True)
        video = response["data"]["View"]
        if video.get("redirect_url") or video.get("is_upower_exclusive"):
            raise ExtractorError(
                "ACCESS_REQUIRED: Only ordinary public videos are supported", expected=True
            )
        if video.get("rights", {}).get("is_stein_gate"):
            raise ExtractorError("Interactive videos are unsupported", expected=True)
        pages = video.get("pages") or []
        try:
            part = int(parse_qs(urlsplit(url).query).get("p", ["1"])[-1])
        except ValueError as error:
            raise ExtractorError("Invalid Bilibili part number", expected=True) from error
        if not 1 <= part <= len(pages):
            raise ExtractorError("Bilibili part number is out of range", expected=True)
        page = pages[part - 1]
        duration = float(page.get("duration", 0))
        if not math.isfinite(duration) or not 0 < duration <= 3600:
            raise ExtractorError("Live/long media is unsupported", expected=True)
        bvid = video["bvid"]
        play = self._download_playinfo(bvid, page["cid"], headers=headers, query={"try_look": 0})
        if play.get("is_preview"):
            raise ExtractorError(
                "ACCESS_REQUIRED: Preview-only media is unsupported", expected=True
            )
        formats = self.extract_formats(play)
        if not formats:
            raise ExtractorError("Public video has no available formats", expected=True)
        emit("fallback_resolved", backend="bilibili_public_api")
        return {
            "id": f"{bvid}_p{part}",
            "title": video.get("title") or bvid,
            "duration": duration,
            "formats": formats,
            "http_headers": headers,
        }
