from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


_TELEFONO_RE = r"^\+?\d{7,20}$"
_EMAIL_RE = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


class PedidoCreate(BaseModel):
    telefono: str = Field(..., pattern=_TELEFONO_RE)
    nombre: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, pattern=_EMAIL_RE, max_length=255)
    paquete_id: UUID = Field(...)
    direccion: str = Field(..., max_length=500)
    cantidad: int = Field(default=1, ge=1)
    metodo_pago: str = Field(..., pattern=r"^(tarjeta|efectivo)$")
    notas: Optional[str] = Field(default=None, max_length=1000)
    fecha_usuario: date = Field(...)


class PedidoUpdateEstatus(BaseModel):
    estatus: str = Field(
        ...,
        pattern=r"^(pendiente|aceptado|entregado|cancelado|rechazado)$",
    )


class SuscripcionCreate(BaseModel):
    telefono: str = Field(..., pattern=_TELEFONO_RE)
    nombre: str = Field(..., min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, pattern=_EMAIL_RE, max_length=255)
    paquete_id: UUID = Field(...)
    direccion: str = Field(..., max_length=500)
    cantidad: int = Field(default=1, ge=1)
    metodo_pago: str = Field(..., pattern=r"^(tarjeta|efectivo)$")
    dia_entrega: int = Field(..., ge=1, le=7)
    fecha_inicio: date = Field(...)


class SuscripcionUpdate(BaseModel):
    dia_entrega: Optional[int] = Field(default=None, ge=1, le=7)
    direccion: Optional[str] = Field(default=None, max_length=500)
    activa: Optional[bool] = Field(default=None)
