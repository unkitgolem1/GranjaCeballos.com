import asyncio
import time
from typing import Any, Callable, Coroutine, Optional, TypeVar

T = TypeVar("T")


class MemoryCache:
    """TTL cache in-memory con double-checked locking.

    Uso:
        cache = MemoryCache(default_ttl=60)
        paquetes = await cache.get_or_load("paquetes", loader=repo.list_active)
        cache.invalidate("paquetes")
    """

    def __init__(self, default_ttl: int = 60) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._default_ttl = default_ttl

    async def get_or_load(
        self,
        key: str,
        loader: Callable[[], Coroutine[Any, Any, T]],
        ttl: Optional[int] = None,
    ) -> T:
        ttl = ttl or self._default_ttl
        now = time.monotonic()
        entry = self._data.get(key)
        if entry is not None and (now - entry[0]) < ttl:
            return entry[1]
        async with self._lock:
            entry = self._data.get(key)
            if entry is not None and (now - entry[0]) < ttl:
                return entry[1]
            value = await loader()
            self._data[key] = (now, value)
            return value

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)

    def invalidate_all(self) -> None:
        self._data.clear()

    def get_nowait(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is not None:
            return entry[1]
        return None
