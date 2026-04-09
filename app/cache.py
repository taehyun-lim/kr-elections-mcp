from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class SimpleFileCache:
    """Small JSON file cache for single-user local execution."""

    def __init__(self, root: str | Path, default_ttl_seconds: int = 3600) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.default_ttl_seconds = default_ttl_seconds
        self._prune_interval_seconds = 300
        self._last_prune_at = 0.0
        self._maybe_prune()

    def _path_for_key(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def _maybe_prune(self) -> None:
        now = time.time()
        if now - self._last_prune_at < self._prune_interval_seconds:
            return
        self._last_prune_at = now
        self.prune(now=now)

    def prune(self, *, now: float | None = None) -> int:
        current_time = time.time() if now is None else now
        removed = 0
        for path in self.root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                try:
                    path.unlink()
                except OSError:
                    continue
                removed += 1
                continue
            expires_at = payload.get("expires_at")
            if expires_at is None or expires_at >= current_time:
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
        return removed

    def get(self, key: str) -> Any | None:
        self._maybe_prune()
        path = self._path_for_key(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        expires_at = payload.get("expires_at")
        if expires_at is not None and expires_at < time.time():
            try:
                path.unlink()
            except OSError:
                return None
            return None
        return payload.get("value")

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> Any:
        self._maybe_prune()
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        payload = {
            "expires_at": time.time() + ttl if ttl > 0 else None,
            "value": value,
        }
        path = self._path_for_key(key)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return value

    def remember(
        self,
        key: str,
        producer: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        return self.set(key, producer(), ttl_seconds=ttl_seconds)
