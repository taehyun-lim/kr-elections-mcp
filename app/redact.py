from __future__ import annotations

import re
from typing import Iterable

SERVICE_KEY_PATTERN = re.compile(r"(serviceKey=)([^&#\s]+)")
REDACTED_API_KEY = "***"


def mask_secret(value: str | None) -> str:
    text = "" if value is None else str(value)
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def redact_api_key(text: str | None, *, known_values: Iterable[str] = ()) -> str:
    redacted = "" if text is None else str(text)
    redacted = SERVICE_KEY_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED_API_KEY}", redacted)
    for value in sorted({str(item) for item in known_values if item}, key=len, reverse=True):
        redacted = redacted.replace(value, REDACTED_API_KEY)
    return redacted


def redact_service_keys(text: str | None, *, known_values: Iterable[str] = ()) -> str:
    return redact_api_key(text, known_values=known_values)
