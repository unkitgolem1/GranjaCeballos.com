from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


@dataclass
class LogisticPedido:
    id: str = ""
    usuario_id: str = ""
    paquete_id: str = ""
    direccion: str = ""
    codigo_postal: Optional[str] = None
    cantidad: int = 0
    total: Decimal = Decimal("0")
    metodo_pago: str = ""
    estatus: str = ""
    fecha_usuario: Optional[date] = None
    fecha_entrega: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    usuario_nombre: str = ""
    usuario_telefono: str = ""
    paquete_nombre: str = ""


@dataclass
class LogisticCliente:
    id: str = ""
    nombre: str = ""
    telefono: str = ""
    email: Optional[str] = None
    es_cliente: bool = False
    created_at: Optional[datetime] = None
    total_pedidos: int = 0
    ultimo_pedido_fecha: Optional[datetime] = None
    ultimo_pedido_estatus: Optional[str] = None
