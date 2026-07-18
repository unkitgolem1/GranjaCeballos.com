import logging
from datetime import date

from src.domain.interfaces import (
    PaqueteRepository,
    PedidoRepository,
    SuscripcionRepository,
)
from src.domain.models import Pedido
from src.infrastructure.health_service import HealthService

from .services import _calcular_total

logger = logging.getLogger(__name__)


class SuscripcionScheduler:

    def __init__(
        self,
        suscripcion_repo: SuscripcionRepository,
        pedido_repo: PedidoRepository,
        paquete_repo: PaqueteRepository,
        health_service: HealthService,
    ) -> None:
        self._suscripcion_repo = suscripcion_repo
        self._pedido_repo = pedido_repo
        self._paquete_repo = paquete_repo
        self._health_service = health_service

    async def procesar_vencidas(self) -> int:
        vencidas = await self._suscripcion_repo.list_vencidas()
        generados = 0

        if not vencidas:
            logger.info("No hay suscripciones vencidas para procesar")
            return 0

        salud_ok = await self._health_service.check_all()
        if not salud_ok:
            logger.warning("Health check falló — no se generarán pedidos")
            return 0

        for sub in vencidas:
            try:
                paquete = await self._paquete_repo.get_by_id(str(sub.paquete_id))
                if paquete is None or not paquete.activo:
                    logger.warning(
                        "Suscripción %s: paquete %s no disponible, saltando",
                        sub.id,
                        sub.paquete_id,
                    )
                    continue

                total = _calcular_total(paquete, sub.cantidad)

                pedido = Pedido(
                    usuario_id=sub.usuario_id,
                    paquete_id=sub.paquete_id,
                    suscripcion_id=sub.id,
                    direccion=sub.direccion,
                    cantidad=sub.cantidad,
                    total=total,
                    metodo_pago=sub.metodo_pago,
                    estatus="pendiente",
                    fecha_usuario=sub.proxima_generacion,
                    fecha_entrega=sub.proxima_generacion,
                )
                await self._pedido_repo.create(pedido)
                await self._suscripcion_repo.avanzar_proxima(str(sub.id))
                generados += 1

            except Exception:
                logger.exception(
                    "Error procesando suscripción %s", sub.id
                )

        logger.info("Scheduler: %d pedidos generados de suscripciones", generados)
        return generados
