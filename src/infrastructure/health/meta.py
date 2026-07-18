from .base import HealthCheckResult, HealthChecker


class MetaHealthChecker(HealthChecker):

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(service="meta", ok=True)
