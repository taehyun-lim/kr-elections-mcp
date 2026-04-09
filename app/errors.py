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


class ResourceUnavailableError(KrElectionError):
    """Raised when an upstream resource cannot be resolved."""


class AmbiguousCandidateError(KrElectionError):
    """Raised when a candidate query resolves to multiple plausible matches."""




class SecretStoreError(KrElectionError):
    """Raised when secure key storage cannot be used."""
