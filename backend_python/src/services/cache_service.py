import time
from typing import Any, Dict, Tuple

CacheKey = Tuple[str, str]

class InMemoryCache:
    def __init__(self, ttl_seconds: int = 600):
        self.ttl = ttl_seconds
        self._store: Dict[CacheKey, Dict[str, Any]] = {}

    def get(self, key: CacheKey):
        entry = self._store.get(key)
        if not entry:
            return None
        if entry["expires_at"] < time.time():
            self._store.pop(key, None)
            return None
        return entry["value"]

    def set(self, key: CacheKey, value: Any):
        self._store[key] = {"value": value, "expires_at": time.time() + self.ttl}

cache = InMemoryCache()
