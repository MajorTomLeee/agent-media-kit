"""Explicit, interchangeable URL resolvers. Network I/O uses the guarded downloader."""

import json
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Resolver redirects are not permitted")


def platform(source):
    host = (urlsplit(source).hostname or "").lower()
    for name, domains in {
        "bilibili": ("bilibili.com", "b23.tv"),
        "douyin": ("douyin.com", "iesdouyin.com"),
        "tiktok": ("tiktok.com",),
        "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
        "kuaishou": ("kuaishou.com", "gifshow.com"),
    }.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            return name
    return "other"


def json_request(downloader, url, *, body=None, authorization=None):
    headers = {"Accept": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    if body is not None:
        headers["Content-Type"] = "application/json"
    # Do not let a provider redirect a credential-bearing request to another host.
    request = Request(
        url, data=json.dumps(body).encode() if body is not None else None, headers=headers
    )
    with build_opener(NoRedirect(), ProxyHandler({})).open(request, timeout=60) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Resolver response exceeds 2 MiB")
    return json.loads(raw)


def resolve(downloader, source, backend, endpoint=None, token=None):
    if backend == "cobalt":
        if not endpoint or urlsplit(endpoint).scheme != "https":
            raise ValueError("Configure an HTTPS Cobalt endpoint you own or are authorized to use")
        result = json_request(
            downloader,
            endpoint,
            body={"url": source, "videoQuality": "720", "downloadMode": "auto"},
            authorization=f"Api-Key {token}" if token else None,
        )
        if result.get("status") not in ("tunnel", "redirect"):
            raise ValueError(
                "Cobalt could not return a single media stream; check platform access or select a single video"
            )
        return {"url": result["url"]}
    if backend == "tikhub":
        if not token:
            raise ValueError("TikHub is opt-in: configure MEDIA_EYES_TIKHUB_API_KEY")
        site = platform(source)
        if site in ("douyin", "tiktok"):
            result = json_request(
                downloader,
                "https://api.tikhub.io/api/v1/hybrid/video_data?"
                + urlencode({"url": source, "minimal": "true"}),
                authorization=f"Bearer {token}",
            )
            data = result.get("data") or {}
            # Hybrid endpoint's normalized download fields; never choose a cover URL.
            video = data.get("video_data") or {}
            address = video.get("nwm_video_url")
            if isinstance(address, list):
                address = address[0] if address else None
            if not address:
                raise ValueError("TikHub returned no downloadable video stream")
            return {"url": address}
        if site == "bilibili":
            result = json_request(
                downloader,
                "https://api.tikhub.io/api/v1/bilibili/web/fetch_video_play_info?"
                + urlencode({"url": source}),
                authorization=f"Bearer {token}",
            )
            data = result.get("data") or {}
            data = data.get("data", data)
            dash = data.get("dash") or {}
            if dash.get("video") and dash.get("audio"):
                video = min(dash["video"], key=lambda item: abs(item.get("height", 720) - 720))
                audio = dash["audio"][0]
                return {
                    "url": video.get("baseUrl") or video.get("base_url"),
                    "audio_url": audio.get("baseUrl") or audio.get("base_url"),
                    "referer": "https://www.bilibili.com/",
                }
            durl = data.get("durl") or []
            if len(durl) == 1:
                return {"url": durl[0]["url"], "referer": "https://www.bilibili.com/"}
            raise ValueError("TikHub returned no supported single video stream")
        raise ValueError(
            "TikHub adapter currently supports Bilibili, Douyin and TikTok; use yt-dlp for other platforms"
        )
    raise ValueError("Unknown URL backend; choose yt-dlp, cobalt or tikhub")
