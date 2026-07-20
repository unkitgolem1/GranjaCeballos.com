from typing import Optional

from ..domain.interfaces import ClienteQueryRepository, PedidoQueryRepository
from ..domain.models import LogisticCliente, LogisticPedido


class LogisticService:
    def __init__(
        self,
        pedido_repo: PedidoQueryRepository,
        cliente_repo: ClienteQueryRepository,
    ):
        self._pedido_repo = pedido_repo
        self._cliente_repo = cliente_repo

    async def listar_pedidos(
        self, estatus: str = "", fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None, orden: str = "DESC", limite: int = 25
    ) -> list[LogisticPedido]:
        return await self._pedido_repo.listar_pedidos(
            estatus, fecha_desde, fecha_hasta, orden, limite
        )

    async def actualizar_estatus(self, pedido_id: str, nuevo_estatus: str) -> Optional[LogisticPedido]:
        pedido = await self._pedido_repo.actualizar_estatus(pedido_id, nuevo_estatus)
        if pedido and nuevo_estatus == "aceptado":
            await self._cliente_repo.activar_cliente(pedido.usuario_id)
        return pedido

    async def listar_clientes(self) -> list[LogisticCliente]:
        return await self._cliente_repo.listar_clientes()
