from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from .models import Cliente, Paquete, Pedido, Suscripcion, Usuario


class UsuarioRepository(ABC):
    @abstractmethod
    async def get_by_phone(self, telefono: str) -> Optional[Usuario]: ...

    @abstractmethod
    async def get_or_create_by_phone(
        self, telefono: str, nombre: str, email: Optional[str] = None
    ) -> Usuario: ...


class PaqueteRepository(ABC):
    @abstractmethod
    async def list_active(self) -> list[Paquete]: ...

    @abstractmethod
    async def get_by_id(self, paquete_id: str) -> Optional[Paquete]: ...


class PedidoRepository(ABC):
    @abstractmethod
    async def create(self, pedido: Pedido) -> Pedido: ...

    @abstractmethod
    async def create_si_no_pendiente(self, pedido: Pedido) -> Pedido: ...

    @abstractmethod
    async def get_by_id(self, pedido_id: str) -> Optional[Pedido]: ...

    @abstractmethod
    async def get_pendiente_by_telefono(self, telefono: str) -> Optional[Pedido]: ...

    @abstractmethod
    async def list_by_fecha(self, fecha: date) -> list[Pedido]: ...

    @abstractmethod
    async def update_estatus(
        self, pedido_id: str, estatus: str
    ) -> Optional[Pedido]: ...

    @abstractmethod
    async def count_by_direccion_y_fecha(self, fecha: date) -> list[dict]: ...


class SuscripcionRepository(ABC):
    @abstractmethod
    async def create(self, suscripcion: Suscripcion) -> Suscripcion: ...

    @abstractmethod
    async def get_by_id(self, suscripcion_id: str) -> Optional[Suscripcion]: ...

    @abstractmethod
    async def list_by_usuario(self, usuario_id: str) -> list[Suscripcion]: ...

    @abstractmethod
    async def list_vencidas(self) -> list[Suscripcion]: ...

    @abstractmethod
    async def update_proxima(
        self, suscripcion_id: str, dia_entrega: int, proxima_generacion: date
    ) -> Optional[Suscripcion]: ...

    @abstractmethod
    async def avanzar_proxima(self, suscripcion_id: str) -> None: ...


class ClienteRepository(ABC):
    @abstractmethod
    async def list_active(self) -> list[Cliente]: ...
