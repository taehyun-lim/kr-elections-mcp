from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_CACHE_FILE_PATTERN = re.compile(r"^[0-9a-f]{64}\.json$")


class SimpleFileCache:
    """Small JSON file cache for single-user local execution."""

    def __init__(self, root: str | Path, default_ttl_seconds: int = 3600, *, memory_entries: int = 256) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.default_ttl_seconds = default_ttl_seconds
        self._prune_interval_seconds = 300
        self._last_prune_at = 0.0
        # Small in-process layer so repeated tool calls skip disk reads and JSON parsing.
        self._memory: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._memory_limit = memory_entries
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
            # Only touch files this cache wrote; the directory may be shared or user-chosen.
            if not _CACHE_FILE_PATTERN.match(path.name):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                try:
                    path.unlink()
                except OSError:
                    continue
                removed += 1
                continue
            expires_at = payload.get("expires_at") if isinstance(payload, dict) else None
            if expires_at is None or expires_at >= current_time:
                continue
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
        return removed

    def _memory_get(self, key: str) -> Any | None:
        entry = self._memory.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.time():
            self._memory.pop(key, None)
            return None
        self._memory.move_to_end(key)
        return value

    def _memory_put(self, key: str, expires_at: float, value: Any) -> None:
        if self._memory_limit <= 0:
            return
        self._memory[key] = (expires_at, value)
        self._memory.move_to_end(key)
        while len(self._memory) > self._memory_limit:
            self._memory.popitem(last=False)

    def get(self, key: str) -> Any | None:
        remembered = self._memory_get(key)
        if remembered is not None:
            return remembered
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
        value = payload.get("value")
        if value is not None and expires_at is not None:
            self._memory_put(key, expires_at, value)
        return value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> Any:
        self._maybe_prune()
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            return value
        payload = {"expires_at": time.time() + ttl, "value": value}
        self._memory_put(key, payload["expires_at"], value)
        path = self._path_for_key(key)
        try:
            # Write to a temp file and rename, so a crash never leaves a half-written entry.
            descriptor, temp_name = tempfile.mkstemp(dir=self.root, prefix=".tmp-", suffix=".json")
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                os.replace(temp_name, path)
            except BaseException:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
                raise
        except OSError:
            # A cache that cannot be written must not fail the request that produced the value.
            return value
        return value

    def remember(
        self,
        key: str,
        producer: Callable[[], T],
        ttl_seconds: int | None = None,
    ) -> T:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            return producer()
        cached = self.get(key)
        if cached is not None:
            return cached
        return self.set(key, producer(), ttl_seconds=ttl)
