from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CustomTier(BaseModel):
    min_cantidad: int = Field(..., ge=1)
    precio_unitario: Decimal = Field(..., gt=0, decimal_places=2)


class Usuario(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    nombre: str = Field(..., min_length=1, max_length=200)
    telefono: str = Field(..., min_length=7, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Paquete(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: str = Field(default="", max_length=1000)
    precio: Decimal = Field(..., gt=0, decimal_places=2)
    costo_envio: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    cantidad_fija: int = Field(default=1, ge=1)
    es_suscripcion: bool = False
    es_customizable: bool = False
    precio_minimo: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    tiers: list[CustomTier] = Field(default_factory=list)
    es_popular: bool = False
    badge: Optional[str] = Field(default=None, max_length=50)
    activo: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Pedido(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    usuario_id: UUID = Field(...)
    paquete_id: UUID = Field(...)
    suscripcion_id: Optional[UUID] = Field(default=None)
    direccion: str = Field(..., max_length=500)
    codigo_postal: Optional[str] = Field(default=None, max_length=10)
    estado: str = Field(default="", max_length=50)
    ciudad: str = Field(default="", max_length=100)
    colonia: str = Field(default="", max_length=200)
    cantidad: int = Field(default=1, ge=1)
    total: Decimal = Field(..., ge=0, decimal_places=2)
    metodo_pago: str = Field(
        ..., pattern=r"^(tarjeta|efectivo)$"
    )
    estatus: str = Field(
        default="pendiente",
        pattern=r"^(pendiente|aceptado|entregado|cancelado|rechazado)$",
    )
    notas: Optional[str] = Field(default=None, max_length=1000)
    fecha_usuario: date = Field(...)
    fecha_entrega: date = Field(...)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Suscripcion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    usuario_id: UUID = Field(...)
    paquete_id: UUID = Field(...)
    direccion: str = Field(..., max_length=500)
    codigo_postal: Optional[str] = Field(default=None, max_length=10)
    estado: str = Field(default="", max_length=50)
    ciudad: str = Field(default="", max_length=100)
    colonia: str = Field(default="", max_length=200)
    cantidad: int = Field(default=1, ge=1)
    metodo_pago: str = Field(
        ..., pattern=r"^(tarjeta|efectivo)$"
    )
    dia_entrega: int = Field(..., ge=1, le=7)
    fecha_inicio: date = Field(...)
    proxima_generacion: date = Field(...)
    activa: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Cliente(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    nombre: str = Field(..., max_length=200)
    lugar: str = Field(default="", max_length=200)
    icono_svg: Optional[str] = Field(default=None)
    testimonio: str = Field(default="", max_length=1000)
    activo: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
