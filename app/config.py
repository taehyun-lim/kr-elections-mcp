from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import ConfigurationError
from .secret_store import SecretStore


@dataclass(frozen=True)
class NecApiKeyCandidate:
    value: str
    key_format: str


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nec_api_key: str | None = Field(default=None, repr=False)
    nec_api_key_encoded: str | None = Field(default=None, repr=False)
    nec_api_key_decoded: str | None = Field(default=None, repr=False)
    nec_api_key_source: str | None = None
    nec_api_base_url: str = "https://apis.data.go.kr/9760000"
    nec_result_format: str = "json"
    request_timeout_seconds: float = 20.0
    retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    cache_dir: Path = Path(".cache/http")
    cache_ttl_seconds: int = 3600
    krpoltext_base_url: str = "https://taehyun-lim.github.io/krpoltext/data"
    krpoltext_campaign_booklet_url: str | None = None
    log_level: str = "INFO"
    user_agent: str = "kr-elections-mcp/0.1"

    @field_validator("nec_result_format")
    @classmethod
    def validate_result_format(cls, value: str) -> str:
        lowered = value.lower()
        if lowered not in {"json", "xml"}:
            raise ValueError("NEC_RESULT_FORMAT must be either 'json' or 'xml'.")
        return lowered

    @classmethod
    def from_env(
        cls,
        env_file: str | Path | None = None,
        *,
        secret_store: SecretStore | None = None,
    ) -> "Settings":
        env_path = Path(env_file) if env_file else None
        file_values = {
            key: value
            for key, value in (dotenv_values(env_path).items() if env_path and env_path.exists() else [])
            if value is not None
        }
        secret_store = secret_store or SecretStore()
        nec_api_keys, nec_api_key_source = cls._resolve_nec_api_keys(
            file_values=file_values,
            secret_store=secret_store,
        )

        return cls(
            nec_api_key=nec_api_keys["legacy"] or nec_api_keys["decoded"] or nec_api_keys["encoded"],
            nec_api_key_encoded=nec_api_keys["encoded"],
            nec_api_key_decoded=nec_api_keys["decoded"],
            nec_api_key_source=nec_api_key_source,
            nec_api_base_url=cls._value("NEC_API_BASE_URL", file_values, cls.model_fields["nec_api_base_url"].default),
            nec_result_format=cls._value("NEC_RESULT_FORMAT", file_values, cls.model_fields["nec_result_format"].default),
            request_timeout_seconds=float(
                cls._value(
                    "REQUEST_TIMEOUT_SECONDS",
                    file_values,
                    cls.model_fields["request_timeout_seconds"].default,
                )
            ),
            retry_attempts=int(
                cls._value("RETRY_ATTEMPTS", file_values, cls.model_fields["retry_attempts"].default)
            ),
            retry_backoff_seconds=float(
                cls._value(
                    "RETRY_BACKOFF_SECONDS",
                    file_values,
                    cls.model_fields["retry_backoff_seconds"].default,
                )
            ),
            cache_dir=Path(cls._value("CACHE_DIR", file_values, str(cls.model_fields["cache_dir"].default))),
            cache_ttl_seconds=int(
                cls._value("CACHE_TTL_SECONDS", file_values, cls.model_fields["cache_ttl_seconds"].default)
            ),
            krpoltext_base_url=cls._value(
                "KRPOLTEXT_BASE_URL",
                file_values,
                cls.model_fields["krpoltext_base_url"].default,
            ),
            krpoltext_campaign_booklet_url=cls._value(
                "KRPOLTEXT_CAMPAIGN_BOOKLET_URL",
                file_values,
                cls.model_fields["krpoltext_campaign_booklet_url"].default,
            ),
            log_level=cls._value("LOG_LEVEL", file_values, cls.model_fields["log_level"].default),
            user_agent=cls._value("USER_AGENT", file_values, cls.model_fields["user_agent"].default),
        )

    @classmethod
    def _resolve_nec_api_keys(
        cls,
        *,
        file_values: dict[str, str],
        secret_store: SecretStore,
    ) -> tuple[dict[str, str | None], str | None]:
        for source_name, key_values in (
            (
                "env",
                {
                    "legacy": os.getenv("NEC_API_KEY"),
                    "encoded": os.getenv("NEC_API_KEY_ENCODED"),
                    "decoded": os.getenv("NEC_API_KEY_DECODED"),
                },
            ),
            ("keyring", secret_store.get_nec_api_keys(silent=True)),
            (
                "dotenv",
                {
                    "legacy": file_values.get("NEC_API_KEY"),
                    "encoded": file_values.get("NEC_API_KEY_ENCODED"),
                    "decoded": file_values.get("NEC_API_KEY_DECODED"),
                },
            ),
        ):
            normalized = cls._normalize_key_bundle(
                legacy=key_values.get("legacy"),
                encoded=key_values.get("encoded"),
                decoded=key_values.get("decoded"),
            )
            if any(normalized.values()):
                return normalized, source_name

        return {"legacy": None, "encoded": None, "decoded": None}, None

    @staticmethod
    def _value(name: str, file_values: dict[str, str], default: Any) -> Any:
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value
        file_value = file_values.get(name)
        if file_value not in (None, ""):
            return file_value
        return default

    @classmethod
    def _normalize_key_bundle(
        cls,
        *,
        legacy: str | None,
        encoded: str | None,
        decoded: str | None,
    ) -> dict[str, str | None]:
        legacy = cls._clean_key_value(legacy)
        encoded = cls._clean_key_value(encoded)
        decoded = cls._clean_key_value(decoded)

        if legacy and not encoded and not decoded:
            if cls._looks_url_encoded(legacy):
                encoded = legacy
                decoded = cls._decode_service_key(legacy)
            else:
                decoded = legacy
                encoded = cls._encode_service_key(legacy)
        else:
            if encoded and not decoded:
                decoded = cls._decode_service_key(encoded)
            if decoded and not encoded:
                encoded = cls._encode_service_key(decoded)

        return {
            "legacy": legacy,
            "encoded": encoded,
            "decoded": decoded,
        }

    @staticmethod
    def _clean_key_value(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _looks_url_encoded(value: str) -> bool:
        return bool(re.search(r"%[0-9A-Fa-f]{2}", value))

    @staticmethod
    def _decode_service_key(value: str) -> str:
        return unquote(value)

    @staticmethod
    def _encode_service_key(value: str) -> str:
        return quote(value, safe="")

    def api_key_candidates(self) -> list[NecApiKeyCandidate]:
        normalized = self._normalize_key_bundle(
            legacy=self.nec_api_key,
            encoded=self.nec_api_key_encoded,
            decoded=self.nec_api_key_decoded,
        )
        candidates: list[NecApiKeyCandidate] = []
        seen: set[tuple[str, str]] = set()
        for key_format in ("decoded", "encoded"):
            value = normalized[key_format]
            if not value:
                continue
            marker = (key_format, value)
            if marker in seen:
                continue
            seen.add(marker)
            candidates.append(NecApiKeyCandidate(value=value, key_format=key_format))
        return candidates

    def configured_key_formats(self) -> list[str]:
        return [candidate.key_format for candidate in self.api_key_candidates()]

    def require_api_keys(self) -> list[NecApiKeyCandidate]:
        candidates = self.api_key_candidates()
        if not candidates:
            raise ConfigurationError(
                "An NEC API key is required for live NEC API calls. "
                "Run 'kr-elections-mcp setup-key' to store your encoded and/or decoded key in the OS keyring, or use 'python server.py setup-key' from a source checkout, "
                "or set NEC_API_KEY_DECODED / NEC_API_KEY_ENCODED in your MCP client env. "
                "If you intentionally use a local dotenv file, pass it explicitly with '--env-file .env'. "
                "The legacy NEC_API_KEY variable is still supported as a fallback."
            )
        return candidates

    def require_api_key(self) -> str:
        return self.require_api_keys()[0].value

    def request_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json, application/xml;q=0.9, */*;q=0.8",
        }

