from __future__ import annotations

from app.cache import SimpleFileCache


def test_simple_file_cache_remember_reuses_cached_value(tmp_path):
    cache = SimpleFileCache(tmp_path, default_ttl_seconds=60)
    calls = {"count": 0}

    def producer():
        calls["count"] += 1
        return {"value": 1}

    first = cache.remember("alpha", producer)
    second = cache.remember("alpha", producer)

    assert first == {"value": 1}
    assert second == {"value": 1}
    assert calls["count"] == 1


def test_simple_file_cache_drops_expired_entries(tmp_path, monkeypatch):
    now = {"value": 100.0}
    monkeypatch.setattr("app.cache.time.time", lambda: now["value"])
    cache = SimpleFileCache(tmp_path, default_ttl_seconds=5)

    cache.set("alpha", {"value": 1})
    cached_path = cache._path_for_key("alpha")
    assert cached_path.exists()

    now["value"] = 106.0

    assert cache.get("alpha") is None
    assert cached_path.exists() is False

def test_simple_file_cache_prune_removes_expired_entries_without_direct_access(tmp_path, monkeypatch):
    now = {"value": 100.0}
    monkeypatch.setattr("app.cache.time.time", lambda: now["value"])
    cache = SimpleFileCache(tmp_path, default_ttl_seconds=5)

    cache.set("alpha", {"value": 1})
    alpha_path = cache._path_for_key("alpha")
    assert alpha_path.exists()

    now["value"] = 106.0

    removed = cache.prune()

    assert removed == 1
    assert alpha_path.exists() is False


def test_simple_file_cache_auto_prunes_on_write(tmp_path, monkeypatch):
    now = {"value": 100.0}
    monkeypatch.setattr("app.cache.time.time", lambda: now["value"])
    cache = SimpleFileCache(tmp_path, default_ttl_seconds=5)

    cache.set("alpha", {"value": 1})
    alpha_path = cache._path_for_key("alpha")
    assert alpha_path.exists()

    now["value"] = 401.0

    cache.set("beta", {"value": 2})

    assert alpha_path.exists() is False
    assert cache.get("beta") == {"value": 2}
