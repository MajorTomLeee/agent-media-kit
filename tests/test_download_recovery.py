import json

import pytest
from yt_dlp.utils import DownloadError

from media_eyes import download
from media_eyes.diagnostics import classify, failure_message, forward


def test_pinned_downloader_short_content_message_is_recoverable():
    from yt_dlp.utils import ContentTooShortError

    assert (
        classify(ContentTooShortError(847417, 1000000))["failure_reason"] == "incomplete_transfer"
    )


def records(capsys):
    return [json.loads(line) for line in capsys.readouterr().err.splitlines()]


def test_interrupted_transfer_refreshes_once_without_exposing_signed_url(monkeypatch, capsys):
    attempts = []

    def transfer():
        attempts.append(1)
        if len(attempts) == 1:
            raise DownloadError("Read operation timed out: https://cdn.example/?token=secret-value")

    monkeypatch.setattr(download, "download", transfer)
    monkeypatch.setattr(download.sys, "argv", ["download", "source", "output", "yt-dlp"])
    assert download.main() == 0
    assert len(attempts) == 2
    emitted = records(capsys)
    assert [r["event"] for r in emitted] == [
        "download_started",
        "download_retry",
        "download_completed",
    ]
    assert emitted[1]["failure_reason"] == "timeout"
    assert emitted[1]["error_code"] == "NETWORK_ERROR"
    assert emitted[1]["attempt"] == 2
    assert "secret-value" not in json.dumps(emitted)


def test_recovery_stops_after_second_transfer_failure(monkeypatch, capsys):
    attempts = []

    def transfer():
        attempts.append(1)
        raise DownloadError("Did not get any data blocks")

    monkeypatch.setattr(download, "download", transfer)
    monkeypatch.setattr(download.sys, "argv", ["download", "source", "output", "yt-dlp"])
    assert download.main() == 1
    assert len(attempts) == 2
    emitted = records(capsys)
    assert emitted[-1]["event"] == "download_failed"
    assert emitted[-1]["failure_reason"] == "incomplete_transfer"
    assert "NETWORK_ERROR" in failure_message(emitted[-1])


@pytest.mark.parametrize(
    "error",
    [
        "HTTP Error 401",
        "HTTP Error 403",
        "HTTP Error 404",
        "HTTP Error 412",
        "HTTP Error 429",
        "Private network connections are not permitted",
        "Unsupported format",
    ],
)
def test_denials_and_format_errors_are_not_retried(error, monkeypatch, capsys):
    attempts = []

    def transfer():
        attempts.append(1)
        raise DownloadError(error)

    monkeypatch.setattr(download, "download", transfer)
    monkeypatch.setattr(download.sys, "argv", ["download", "source", "output", "yt-dlp"])
    assert download.main() == 1
    assert len(attempts) == 1
    assert records(capsys)[-1]["event"] == "download_failed"


@pytest.mark.parametrize("backend", ["cobalt", "tikhub"])
def test_optional_resolver_is_not_billed_again_by_recovery(backend, monkeypatch):
    attempts = []

    def transfer():
        attempts.append(1)
        raise DownloadError("Connection reset by peer")

    monkeypatch.setattr(download, "download", transfer)
    monkeypatch.setattr(download.sys, "argv", ["download", "source", "output", backend])
    assert download.main() == 1
    assert len(attempts) == 1


def test_network_reason_is_sanitized_across_subprocess_protocol(capsys):
    diagnostic = classify("HTTP Error 503: https://cdn.example/?token=secret-value")
    assert diagnostic["failure_reason"] == "upstream_unavailable"
    detail = json.dumps(
        {"event": "download_retry", "attempt": 2, **diagnostic, "secret": "secret-value"}
    )
    emitted = forward(detail)
    assert emitted[0]["failure_reason"] == "upstream_unavailable"
    assert emitted[0]["attempt"] == 2
    assert "secret-value" not in json.dumps(records(capsys))
    assert forward(
        json.dumps({"event": "download_failed", "error_code": [], "failure_reason": []})
    ) == [{"event": "download_failed"}]
