import functools
import json
import logging
import os
import time

_log = logging.getLogger(__name__)


def profile(threshold_ms: float = 15):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = await func(*args, **kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed > threshold_ms or os.getenv("DEBUG_PROFILING") == "true":
                _log.warning(json.dumps({
                    "t": "profile",
                    "handler": func.__name__,
                    "ms": round(elapsed, 2),
                }))
            return result
        return wrapper
    return decorator


class PhaseTimer:
    def __init__(self):
        self._marks: dict[str, float] = {}

    def mark(self, name: str):
        self._marks[name] = time.perf_counter()

    def report(self) -> dict[str, float]:
        items = list(self._marks.items())
        if len(items) < 2:
            return {}
        return {
            items[i][0]: round((items[i+1][1] - items[i][1]) * 1000, 2)
            for i in range(len(items) - 1)
        }
