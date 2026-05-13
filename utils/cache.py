"""
Simple in-memory TTL cache keyed by query text.

Why here and not Redis/Memcached? This is a single-process demo.
Swap out QueryCache for a Redis client to make it multi-process.
"""
import hashlib
import time
from typing import Any


class QueryCache:
    """
    Thread-safe*-ish in-memory cache with per-entry TTL.
    (*asyncio is single-threaded, so GIL makes this safe enough for demos.)

    Keys are MD5 hashes of the lowercased, stripped query string so that
    minor whitespace variations share the same cache entry.
    """

    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, query: str) -> Any | None:
        key = self._key(query)
        if key in self._store:
            ts, value = self._store[key]
            if time.time() - ts < self.ttl:
                return value
            del self._store[key]
        return None

    def set(self, query: str, value: Any) -> None:
        self._store[self._key(query)] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        # Evict stale entries before reporting size
        now = time.time()
        stale = [k for k, (ts, _) in self._store.items() if now - ts >= self.ttl]
        for k in stale:
            del self._store[k]
        return len(self._store)

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _key(query: str) -> str:
        return hashlib.md5(query.lower().strip().encode()).hexdigest()
