from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class HealthCheckResult:
    service: str
    ok: bool


class HealthChecker(ABC):

    @abstractmethod
    async def check(self) -> HealthCheckResult:
        ...
