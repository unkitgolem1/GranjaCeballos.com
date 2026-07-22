from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from src.domain.interfaces import (
    CheckoutResult,
    PaqueteRepository,
    PedidoRepository,
    SepomexRepository,
    SuscripcionRepository,
    UsuarioRepository,
)
from src.domain.models import CustomTier, Paquete, Pedido, Suscripcion

from .schemas import PedidoCreate, SuscripcionCreate


def _calcular_precio_unitario(paquete: Paquete, cantidad: int) -> Decimal:
    if not paquete.es_customizable:
        return paquete.precio

    if paquete.tiers:
        prices = sorted(paquete.tiers, key=lambda t: t.min_cantidad, reverse=True)
        for tier in prices:
            if cantidad >= tier.min_cantidad:
                return max(tier.precio_unitario, paquete.precio_minimo)
        return max(paquete.precio, paquete.precio_minimo)

    desc = Decimal(min(cantidad - 1, 8)) * Decimal("5")
    unitario = paquete.precio - desc
    return max(unitario, paquete.precio_minimo)


def _calcular_total(paquete: Paquete, cantidad: int, envio_gratis: bool = False) -> Decimal:
    envio = Decimal("0") if envio_gratis else (paquete.costo_envio or Decimal("0"))
    if paquete.es_customizable:
        unitario = _calcular_precio_unitario(paquete, cantidad)
        return unitario * cantidad + envio
    return paquete.precio * paquete.cantidad_fija + envio


class PedidoService:
    def __init__(
        self,
        pedido_repo: PedidoRepository,
        usuario_repo: Optional[UsuarioRepository] = None,
        paquete_repo: Optional[PaqueteRepository] = None,
        sepomex_repo: Optional[SepomexRepository] = None,
    ) -> None:
        self._pedido_repo = pedido_repo
        self._usuario_repo = usuario_repo
        self._paquete_repo = paquete_repo
        self._sepomex_repo = sepomex_repo

    async def crear(self, datos: PedidoCreate, paquete: Optional[Paquete] = None) -> Pedido:
        if paquete is None:
            if self._paquete_repo is None:
                raise ValueError("PaqueteRepository required for this operation")
            paquete = await self._paquete_repo.get_by_id(str(datos.paquete_id))
            if paquete is None:
                raise ValueError("Paquete no encontrado")
        return await self.crear_atomic(datos, paquete=paquete)

    async def crear_atomic(
        self,
        datos: PedidoCreate,
        paquete: Paquete,
    ) -> Pedido:
        if not datos.codigo_postal.isdigit() or len(datos.codigo_postal) != 5:
            raise ValueError("El código postal debe ser de 5 dígitos.")
        if not paquete.activo:
            raise ValueError("Paquete no disponible")

        cantidad = datos.cantidad if paquete.es_customizable else paquete.cantidad_fija
        total = _calcular_total(paquete, cantidad)
        fecha_entrega = datos.fecha_usuario

        result: CheckoutResult = await self._pedido_repo.create_checkout_atomic(
            codigo_postal=datos.codigo_postal,
            nombre=datos.nombre,
            telefono=datos.telefono,
            email=datos.email,
            pedido_id=uuid4(),
            paquete_id=paquete.id,
            direccion=datos.direccion,
            estado=datos.estado,
            ciudad=datos.ciudad,
            colonia=datos.colonia,
            cantidad=cantidad,
            total=total,
            metodo_pago=datos.metodo_pago,
            fecha_entrega=fecha_entrega,
        )

        if not result["cp_valido"]:
            raise ValueError(
                "Por el momento nuestra ruta solo cubre Mérida, pero estamos "
                "trabajando para llegar a más zonas. ¿Quieres intentar con otro "
                "código postal o buscar por el nombre de tu colonia?"
            )
        if result["pedido_id"] is None:
            raise ValueError(
                "Ya tienes un pedido pendiente. "
                "Espera a que sea confirmado antes de hacer otro."
            )

        return Pedido(
            id=result["pedido_id"],
            usuario_id=result["usuario_id"],
            paquete_id=paquete.id,
            direccion=datos.direccion,
            codigo_postal=datos.codigo_postal,
            estado=datos.estado,
            ciudad=datos.ciudad,
            colonia=datos.colonia,
            cantidad=cantidad,
            total=result["pedido_total"],
            metodo_pago=datos.metodo_pago,
            estatus="pendiente",
            notas=datos.notas,
            fecha_usuario=datos.fecha_usuario,
            fecha_entrega=fecha_entrega,
        )


class SuscripcionService:

    def __init__(
        self,
        usuario_repo: UsuarioRepository,
        paquete_repo: PaqueteRepository,
        pedido_repo: PedidoRepository,
        suscripcion_repo: SuscripcionRepository,
        sepomex_repo: SepomexRepository,
    ) -> None:
        self._usuario_repo = usuario_repo
        self._paquete_repo = paquete_repo
        self._pedido_repo = pedido_repo
        self._suscripcion_repo = suscripcion_repo
        self._sepomex_repo = sepomex_repo

    async def _resolver_colonia(self, cp: str, colonia: str, info: dict | None) -> str:
        if colonia:
            return colonia
        if info and len(info.get("colonias", [])) == 1:
            return info["colonias"][0]
        return colonia

    async def crear(self, datos: SuscripcionCreate, paquete: Optional[Paquete] = None) -> Suscripcion:
        if datos.metodo_pago != "tarjeta":
            raise ValueError(
                "Las suscripciones solo están disponibles con pago con tarjeta."
            )

        if not datos.codigo_postal.isdigit() or len(datos.codigo_postal) != 5:
            raise ValueError("El código postal debe ser de 5 dígitos.")
        info = await self._sepomex_repo.consultar(datos.codigo_postal)
        if info is None or info.get("estado") != "Yucatán":
            raise ValueError(
                "Por el momento nuestra ruta solo cubre Mérida, pero estamos "
                "trabajando para llegar a más zonas. ¿Quieres intentar con otro "
                "código postal o buscar por el nombre de tu colonia?"
            )
        colonia = await self._resolver_colonia(datos.codigo_postal, datos.colonia, info)

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
            codigo_postal=datos.codigo_postal,
            estado=datos.estado,
            ciudad=datos.ciudad,
            colonia=colonia,
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
            codigo_postal=datos.codigo_postal,
            estado=datos.estado,
            ciudad=datos.ciudad,
            colonia=colonia,
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
