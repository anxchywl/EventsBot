from __future__ import annotations

import time
from typing import Any


# cache small api payloads with expiry
class TTLCache:
    def __init__(self, ttl_seconds: int = 30, max_items: int | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at <= time.time():
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if self.max_items is not None and len(self._items) >= self.max_items:
            self._evict_expired()
            if len(self._items) >= self.max_items:
                oldest_key = min(self._items, key=lambda item_key: self._items[item_key][0])
                self._items.pop(oldest_key, None)
        self._items[key] = (time.time() + self.ttl_seconds, value)

    def clear(self) -> None:
        self._items.clear()

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [key for key, (expires_at, _) in self._items.items() if expires_at <= now]
        for key in expired:
            self._items.pop(key, None)
