from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from .models import LogisticCliente, LogisticPedido

_COLUMNAS_FECHA = frozenset({"fecha_entrega", "created_at"})


class PedidoQueryRepository(ABC):
    @abstractmethod
    async def listar_pedidos(
        self, estatus: str, fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None, orden: str = "DESC", limite: int = 25,
        fecha_columna: str = "fecha_entrega",
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
