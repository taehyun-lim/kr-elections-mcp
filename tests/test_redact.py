from __future__ import annotations

import requests

from app.config import Settings
from app.diagnostics import DiagnosticsService
from app.errors import ApiRequestError
from app.nec_api import NecApiClient
from app.redact import mask_secret, redact_api_key, redact_service_keys


def test_redact_service_keys_masks_query_parameters():
    message = redact_service_keys(
        "boom for url: https://example.test?foo=1&serviceKey=decoded-key&bar=2"
    )

    assert "decoded-key" not in message
    assert "serviceKey=***" in message


def test_mask_secret_handles_short_values():
    assert mask_secret("short") == "*****"


def test_redact_api_key_masks_known_values():
    message = redact_api_key(
        "failure with decoded-key and encoded%2Bkey",
        known_values=["decoded-key", "encoded%2Bkey"],
    )

    assert "decoded-key" not in message
    assert "encoded%2Bkey" not in message
    assert "***" in message


class ErrorSession:
    def get(self, url: str, **kwargs):
        raise requests.HTTPError(f"failure for {url}")


class NoCache:
    def remember(self, key, fn, ttl_seconds=None):
        return fn()


def test_request_errors_are_redacted_before_raising():
    client = NecApiClient(
        Settings(
            nec_api_key_encoded="encoded%2Bkey",
            nec_api_key_decoded="decoded-key",
            retry_attempts=1,
        ),
        session=ErrorSession(),
        cache=NoCache(),
    )

    try:
        client.fetch_winner_rows(sg_id="20240410", sg_typecode="2")
    except ApiRequestError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ApiRequestError to be raised")

    assert "decoded-key" not in message
    assert "encoded%2Bkey" not in message
    assert "***" in message


class RaisingNecClient:
    class _Candidate:
        def __init__(self, value: str) -> None:
            self.value = value

    class _Settings:
        def api_key_candidates(self):
            return [RaisingNecClient._Candidate("decoded-key")]

    def __init__(self) -> None:
        self.settings = self._Settings()

    def list_elections(self, **kwargs):
        raise ApiRequestError("boom with decoded-key")


class DummyResultsClient:
    pass


def test_diagnostics_redacts_error_messages():
    report = DiagnosticsService(RaisingNecClient(), DummyResultsClient()).diagnose_core_api_access()
    message = report.checks[0].message

    assert "decoded-key" not in message
    assert "***" in message


