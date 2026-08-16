"""Cache mémoire minimal avec expiration, pour éviter de spammer Binance."""

import time
from typing import Dict, Tuple

from app.config import CACHE_TTL_SECONDS


class TTLCache:
    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, object]] = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: object):
        self._store[key] = (time.monotonic() + self.ttl, value)


# Instance partagée par toute l'app
cache = TTLCache(CACHE_TTL_SECONDS)
