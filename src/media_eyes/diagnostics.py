"""Bounded structured diagnostics: never emit source URLs, cookies or provider secrets."""

import json
import re
import sys

ERROR_MESSAGES = {
    "PLATFORM_BLOCKED": "The website rejected the worker request; use an authorized resolver or upload a local copy.",
    "ACCESS_REQUIRED": "The source requires authorized access; upload a permitted local copy.",
    "SOURCE_UNAVAILABLE": "The source is unavailable or has been removed.",
    "DRM_UNSUPPORTED": "Protected media is unsupported.",
    "REGION_RESTRICTED": "The source is unavailable in the worker region.",
    "NETWORK_ERROR": "The media transfer was interrupted; try again or upload a local copy.",
    "MEDIA_PROCESSING_FAILED": "Media processing failed; check format and installed dependencies.",
}
NETWORK_REASONS = {
    "timeout": ("timed out", "timeout"),
    "incomplete_transfer": (
        "incompleteread",
        "incomplete read",
        "contenttooshort",
        "content too short",
        "did not get any data blocks",
        "data retrieval failed",
    ),
    "connection_failure": (
        "connection reset",
        "connection aborted",
        "connection refused",
        "remote end closed",
        "network is unreachable",
    ),
    "dns_failure": ("temporary failure in name resolution", "name or service not known"),
    "upstream_unavailable": (),
}


def classify(detail):
    text = str(detail).lower()
    match = re.search(r"(?:http (?:error |status )?|status(?: code)?[=: ]+)(\d{3})", text)
    status = int(match[1]) if match else None
    network_reason = next(
        (reason for reason, terms in NETWORK_REASONS.items() if any(t in text for t in terms)),
        "upstream_unavailable" if status in (500, 502, 503, 504) else None,
    )
    if re.search(r"downloaded \d+ bytes, expected \d+ bytes", text):
        network_reason = "incomplete_transfer"
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
    elif network_reason:
        code = "NETWORK_ERROR"
    else:
        code = "MEDIA_PROCESSING_FAILED"
    result = {"error_code": code, "http_status": status}
    if code == "NETWORK_ERROR":
        result["failure_reason"] = network_reason
    return result


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
            "download_retry",
            "fallback_started",
            "fallback_resolved",
        ):
            continue
        fields = {}
        if record.get("backend") == "bilibili_public_api":
            fields["backend"] = record["backend"]
        if type(record.get("http_status")) is int and 100 <= record["http_status"] <= 599:
            fields["http_status"] = record["http_status"]
        if isinstance(record.get("error_code"), str) and record["error_code"] in ERROR_MESSAGES:
            fields["error_code"] = record["error_code"]
        if (
            isinstance(record.get("failure_reason"), str)
            and record["failure_reason"] in NETWORK_REASONS
        ):
            fields["failure_reason"] = record["failure_reason"]
        if type(record.get("attempt")) is int and record["attempt"] == 2:
            fields["attempt"] = 2
        emit(record["event"], **fields)
        records.append({"event": record["event"], **fields})
    return records


def failure_message(diagnostic):
    code = diagnostic["error_code"]
    status = diagnostic.get("http_status")
    reason = ERROR_MESSAGES[code]
    if diagnostic.get("failure_reason") in NETWORK_REASONS:
        reason = f"{reason} Network reason: {diagnostic['failure_reason']}."
    return f"{code}{f' (HTTP {status})' if status else ''}: {reason}"
