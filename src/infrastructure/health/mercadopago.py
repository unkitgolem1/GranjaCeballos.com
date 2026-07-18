from .base import HealthCheckResult, HealthChecker


class MercadoPagoHealthChecker(HealthChecker):

    async def check(self) -> HealthCheckResult:
        return HealthCheckResult(service="mercadopago", ok=True)
