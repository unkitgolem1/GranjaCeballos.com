from .base import HealthCheckResult, HealthChecker


class SupabaseHealthChecker(HealthChecker):

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(service="supabase", ok=True)
