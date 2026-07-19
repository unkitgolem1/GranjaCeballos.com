from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from src.domain.interfaces import (
    PaqueteRepository,
    PedidoRepository,
    SuscripcionRepository,
    UsuarioRepository,
)
from src.domain.models import CustomTier, Paquete, Pedido, Suscripcion

from .schemas import PedidoCreate, SuscripcionCreate


def _calcular_precio_unitario(paquete: Paquete, cantidad: int) -> Decimal:
    if not paquete.es_customizable:
        return paquete.precio
    precio = paquete.precio
    for tier in sorted(paquete.tiers, key=lambda t: t.min_cantidad, reverse=True):
        if cantidad >= tier.min_cantidad:
            precio = tier.precio_unitario
            break
    return max(precio, paquete.precio_minimo)


def _calcular_total(paquete: Paquete, cantidad: int, envio_gratis: bool = False) -> Decimal:
    envio = Decimal("0") if envio_gratis else (paquete.costo_envio or Decimal("0"))
    if paquete.es_customizable:
        unitario = _calcular_precio_unitario(paquete, cantidad)
        return unitario * cantidad + envio
    return paquete.precio * paquete.cantidad_fija + envio


def _calcular_fecha_entrega(deseada: date) -> date:
    hoy = date.today()
    ahora = datetime.now()
    if deseada == hoy and ahora.hour >= 12:
        return hoy + timedelta(days=1)
    return deseada


_CP_YUCATAN_MIN = 97000
_CP_YUCATAN_MAX = 97999


def _validar_codigo_postal(cp: str) -> bool:
    if not cp.isdigit() or len(cp) != 5:
        return False
    return _CP_YUCATAN_MIN <= int(cp) <= _CP_YUCATAN_MAX


class PedidoService:

    def __init__(
        self,
        usuario_repo: UsuarioRepository,
        paquete_repo: PaqueteRepository,
        pedido_repo: PedidoRepository,
    ) -> None:
        self._usuario_repo = usuario_repo
        self._paquete_repo = paquete_repo
        self._pedido_repo = pedido_repo

    async def crear(self, datos: PedidoCreate, paquete: Optional[Paquete] = None) -> Pedido:
        if not _validar_codigo_postal(datos.codigo_postal):
            raise ValueError("Solo entregamos en Yucatán. Código postal no válido.")

        usuario = await self._usuario_repo.get_or_create_by_phone(
            telefono=datos.telefono,
            nombre=datos.nombre,
            email=datos.email,
        )
        if paquete is None:
            paquete = await self._paquete_repo.get_by_id(str(datos.paquete_id))
        if paquete is None:
            raise ValueError("Paquete no encontrado")
        if not paquete.activo:
            raise ValueError("Paquete no disponible")

        cantidad = datos.cantidad if paquete.es_customizable else paquete.cantidad_fija
        total = _calcular_total(paquete, cantidad)
        fecha_entrega = _calcular_fecha_entrega(datos.fecha_usuario)

        pedido = Pedido(
            usuario_id=usuario.id,
            paquete_id=paquete.id,
            direccion=datos.direccion,
            cantidad=cantidad,
            total=total,
            metodo_pago=datos.metodo_pago,
            estatus="pendiente",
            notas=datos.notas,
            fecha_usuario=datos.fecha_usuario,
            fecha_entrega=fecha_entrega,
        )
        return await self._pedido_repo.create_si_no_pendiente(pedido)


class SuscripcionService:

    def __init__(
        self,
        usuario_repo: UsuarioRepository,
        paquete_repo: PaqueteRepository,
        pedido_repo: PedidoRepository,
        suscripcion_repo: SuscripcionRepository,
    ) -> None:
        self._usuario_repo = usuario_repo
        self._paquete_repo = paquete_repo
        self._pedido_repo = pedido_repo
        self._suscripcion_repo = suscripcion_repo

    async def crear(self, datos: SuscripcionCreate, paquete: Optional[Paquete] = None) -> Suscripcion:
        if datos.metodo_pago != "tarjeta":
            raise ValueError(
                "Las suscripciones solo están disponibles con pago con tarjeta."
            )
        if not _validar_codigo_postal(datos.codigo_postal):
            raise ValueError("Solo entregamos en Yucatán. Código postal no válido.")

        usuario = await self._usuario_repo.get_or_create_by_phone(
            telefono=datos.telefono,
            nombre=datos.nombre,
            email=datos.email,
        )
        if paquete is None:
            paquete = await self._paquete_repo.get_by_id(str(datos.paquete_id))
        if paquete is None or not paquete.activo:
            raise ValueError("Paquete no disponible")

        cantidad = datos.cantidad if paquete.es_customizable else paquete.cantidad_fija

        dia_semana = datos.dia_entrega
        diff = (dia_semana - datos.fecha_inicio.isoweekday()) % 7
        if diff == 0:
            diff = 7
        primera_generacion = datos.fecha_inicio + timedelta(days=diff)

        suscripcion = Suscripcion(
            usuario_id=usuario.id,
            paquete_id=paquete.id,
            direccion=datos.direccion,
            cantidad=cantidad,
            metodo_pago=datos.metodo_pago,
            dia_entrega=dia_semana,
            fecha_inicio=datos.fecha_inicio,
            proxima_generacion=primera_generacion,
        )
        creada = await self._suscripcion_repo.create(suscripcion)

        total = _calcular_total(paquete, cantidad)
        primer_pedido = Pedido(
            usuario_id=usuario.id,
            paquete_id=paquete.id,
            suscripcion_id=creada.id,
            direccion=datos.direccion,
            cantidad=cantidad,
            total=total,
            metodo_pago=datos.metodo_pago,
            estatus="pendiente",
            fecha_usuario=datos.fecha_inicio,
            fecha_entrega=primera_generacion,
        )
        await self._pedido_repo.create_si_no_pendiente(primer_pedido)
        return creada

    async def cambiar_dia_entrega(
        self, suscripcion_id: str, nuevo_dia: int
    ) -> Suscripcion:
        sub = await self._suscripcion_repo.get_by_id(suscripcion_id)
        if sub is None:
            raise ValueError("Suscripción no encontrada")
        if not sub.activa:
            raise ValueError("Suscripción inactiva")

        hoy = date.today()
        diff = (nuevo_dia - hoy.isoweekday()) % 7
        if diff == 0:
            diff = 7
        nueva_proxima = hoy + timedelta(days=diff)

        resultado = await self._suscripcion_repo.update_proxima(
            suscripcion_id, nuevo_dia, nueva_proxima
        )
        if resultado is None:
            raise ValueError("Suscripción no encontrada")
        return resultado
