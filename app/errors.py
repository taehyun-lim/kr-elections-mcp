from __future__ import annotations


class KrElectionError(Exception):
    """Base exception for the KR election MCP project."""


class ConfigurationError(KrElectionError):
    """Raised when local configuration is missing or invalid."""


class ApiRequestError(KrElectionError):
    """Raised when a remote API request fails."""


class ApiAuthorizationError(ApiRequestError):
    """Raised when the current service key is unauthorized."""


class ApiNotAppliedError(ApiRequestError):
    """Raised when the service key exists but has not been approved for the API."""


class ApiQuotaError(ApiRequestError):
    """Raised when the service key has exhausted its request quota."""


class ApiTransientError(ApiRequestError):
    """Raised for upstream failures that are worth retrying (HTTP 429/5xx, NEC codes 01-05/99)."""

    def __init__(self, message: str = "", *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ResourceUnavailableError(KrElectionError):
    """Raised when an upstream resource cannot be resolved."""


class AmbiguousCandidateError(KrElectionError):
    """Raised when a candidate query resolves to multiple plausible matches."""




class SecretStoreError(KrElectionError):
    """Raised when secure key storage cannot be used."""
