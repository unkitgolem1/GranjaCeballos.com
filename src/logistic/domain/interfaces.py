from abc import ABC, abstractmethod
from typing import Optional

from .models import LogisticCliente, LogisticPedido


class PedidoQueryRepository(ABC):
    @abstractmethod
    async def listar_pedidos(
        self, estatus: str, fecha_desde: Optional[str] = None,
        fecha_hasta: Optional[str] = None, orden: str = "DESC", limite: int = 25
    ) -> list[LogisticPedido]:
        ...

    @abstractmethod
    async def actualizar_estatus(self, pedido_id: str, nuevo_estatus: str) -> Optional[LogisticPedido]:
        ...


class ClienteQueryRepository(ABC):
    @abstractmethod
    async def listar_clientes(self) -> list[LogisticCliente]:
        ...

    @abstractmethod
    async def activar_cliente(self, usuario_id: str) -> None:
        ...
