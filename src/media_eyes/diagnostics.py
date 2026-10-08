"""Bounded structured diagnostics: never emit source URLs, cookies or provider secrets."""

import json
import re
import sys


def classify(detail):
    text = str(detail).lower()
    match = re.search(r"(?:http (?:error |status )?|status(?: code)?[=: ]+)(\d{3})", text)
    status = int(match[1]) if match else None
    if status in (412, 429) or any(term in text for term in ("captcha", "rate limit", "anti-bot")):
        code = "PLATFORM_BLOCKED"
    elif status in (401, 403) or any(
        term in text for term in ("access_required", "sign in", "login", "cookies")
    ):
        code = "ACCESS_REQUIRED"
    elif status in (404, 410):
        code = "SOURCE_UNAVAILABLE"
    elif "drm" in text:
        code = "DRM_UNSUPPORTED"
    elif any(term in text for term in ("geo-restricted", "country", "region_restricted")):
        code = "REGION_RESTRICTED"
    else:
        code = "MEDIA_PROCESSING_FAILED"
    return {"error_code": code, "http_status": status}


def emit(event, **fields):
    print(json.dumps({"event": event, **fields}), file=sys.stderr, flush=True)


def forward(detail):
    """Forward only our allowlisted protocol records, never downloader stderr text."""
    records = []
    for line in detail.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict) or record.get("event") not in (
            "download_started",
            "download_failed",
            "download_completed",
            "fallback_started",
            "fallback_resolved",
        ):
            continue
        fields = {}
        if record.get("backend") == "bilibili_public_api":
            fields["backend"] = record["backend"]
        if type(record.get("http_status")) is int and 100 <= record["http_status"] <= 599:
            fields["http_status"] = record["http_status"]
        if record.get("error_code") in (
            "PLATFORM_BLOCKED",
            "ACCESS_REQUIRED",
            "SOURCE_UNAVAILABLE",
            "DRM_UNSUPPORTED",
            "REGION_RESTRICTED",
            "MEDIA_PROCESSING_FAILED",
        ):
            fields["error_code"] = record["error_code"]
        emit(record["event"], **fields)
        records.append({"event": record["event"], **fields})
    return records


def failure_message(diagnostic):
    code = diagnostic["error_code"]
    status = diagnostic.get("http_status")
    reason = {
        "PLATFORM_BLOCKED": "The website rejected the worker request; use an authorized resolver or upload a local copy.",
        "ACCESS_REQUIRED": "The source requires authorized access; upload a permitted local copy.",
        "SOURCE_UNAVAILABLE": "The source is unavailable or has been removed.",
        "DRM_UNSUPPORTED": "Protected media is unsupported.",
        "REGION_RESTRICTED": "The source is unavailable in the worker region.",
        "MEDIA_PROCESSING_FAILED": "Media processing failed; check format and installed dependencies.",
    }[code]
    return f"{code}{f' (HTTP {status})' if status else ''}: {reason}"
