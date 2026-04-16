from __future__ import annotations

from aistation.cache import TTLCache


def test_ttl_cache_lifecycle(monkeypatch) -> None:
    now = {"value": 0.0}
    monkeypatch.setattr("aistation.cache.time.monotonic", lambda: now["value"])

    cache = TTLCache[str](ttl=10.0)

    assert cache.get() is None
    assert cache.expired() is True
    assert cache.age() is None

    cache.set("hello")
    assert cache.get() == "hello"
    assert cache.expired() is False
    assert cache.age() == 0.0

    now["value"] = 5.0
    assert cache.get() == "hello"
    assert cache.age() == 5.0

    now["value"] = 11.0
    assert cache.expired() is True
    assert cache.get() is None

    cache.invalidate()
    assert cache.age() is None


def test_ttl_cache_supports_keyed_entries(monkeypatch) -> None:
    now = {"value": 0.0}
    monkeypatch.setattr("aistation.cache.time.monotonic", lambda: now["value"])

    cache = TTLCache[str](ttl=10.0)

    cache.set("alpha", key="a")
    cache.set("beta", key="b")

    assert cache.get("a") == "alpha"
    assert cache.get("b") == "beta"

    now["value"] = 11.0
    assert cache.get("a") is None
    assert cache.get("b") is None

    cache.set("gamma", key="c")
    cache.invalidate("c")
    assert cache.get("c") is None
