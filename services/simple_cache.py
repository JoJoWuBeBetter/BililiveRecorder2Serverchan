from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable, Optional


@dataclass
class CacheEntry:
    value: object
    expires_at: float


class SimpleTTLCache:
    def __init__(self, clock: Optional[Callable[[], float]] = None):
        self._clock = clock or monotonic
        self._entries: dict[str, CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: str) -> Optional[object]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None

            if entry.expires_at <= self._clock():
                self._entries.pop(key, None)
                return None

            return entry.value

    def set(self, key: str, value: object, ttl_seconds: int) -> None:
        expires_at = self._clock() + max(ttl_seconds, 0)
        with self._lock:
            self._purge_expired_locked()
            self._entries[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear_namespace(self, namespace: str) -> None:
        prefix = f"{namespace}:"
        with self._lock:
            keys = [key for key in self._entries if key.startswith(prefix)]
            for key in keys:
                self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @staticmethod
    def build_key(namespace: str, parts: tuple[object, ...]) -> str:
        serialized = ":".join("" if part is None else str(part) for part in parts)
        if not serialized:
            return f"{namespace}:"
        return f"{namespace}:{serialized}"

    def _purge_expired_locked(self) -> None:
        now = self._clock()
        expired_keys = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired_keys:
            self._entries.pop(key, None)


app_cache = SimpleTTLCache()
