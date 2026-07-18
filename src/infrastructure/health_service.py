import asyncio
import logging

from .health.base import HealthChecker

logger = logging.getLogger(__name__)


class HealthService:

    def __init__(self, checkers: list[HealthChecker]) -> None:
        self._checkers = checkers

    async def check_all(self) -> bool:
        if not self._checkers:
            return True

        results = await asyncio.gather(
            *(c.check() for c in self._checkers), return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                logger.error("Health check error: %s", r)
                return False
            if not r.ok:
                logger.warning("Health check failed: %s", r.service)
                return False
        return True
