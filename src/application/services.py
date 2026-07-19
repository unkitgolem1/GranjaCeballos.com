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
    desc = Decimal(min(cantidad - 1, 8)) * Decimal("5")
    unitario = paquete.precio - desc
    return max(unitario, paquete.precio_minimo)


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


MERIDA_CP = {
    "97000","97003","97004","97005","97006","97007","97008","97009",
    "97050","97060","97070","97080","97089","97090","97098","97099",
    "97100","97104","97105","97106","97107","97108","97109",
    "97110","97113","97114","97115","97116","97117","97118","97119",
    "97120","97121","97123","97124","97125","97127","97128","97129",
    "97130","97133","97134","97135","97136","97137","97138","97139",
    "97140","97143","97144","97145","97146","97147","97148","97149",
    "97150","97153","97154","97155","97156","97157","97158","97159",
    "97160","97163","97164","97165","97166","97167","97168","97169",
    "97170","97173","97174","97175","97176","97177","97178","97179",
    "97180","97183","97184","97185","97186","97187","97188","97189",
    "97190","97193","97194","97195","97196","97197","97198","97199",
    "97200","97203","97204","97205","97206","97207","97208","97209",
    "97210","97214","97215","97216","97217","97218","97219",
    "97220","97223","97224","97225","97226","97227","97228","97229",
    "97230","97234","97235","97236","97237","97238","97239",
    "97240","97243","97244","97245","97246","97247","97248","97249",
    "97250","97254","97255","97256","97257","97258","97259",
    "97260","97263","97264","97265","97266","97267","97268","97269",
    "97270","97273","97274","97275","97276","97277","97278","97279",
    "97280","97284","97285","97286","97287","97288","97289",
    "97290","97294","97295","97296","97297","97298","97299",
    "97300","97302","97303","97304","97305","97306","97307","97308","97309","97310",
    "97312","97313","97314","97315","97316","97317","97318",
    "97320","97321","97322","97324","97325","97326","97327",
}


def _validar_cp_merida(codigo_postal: str | None) -> tuple[bool, str]:
    if not codigo_postal:
        return True, ""
    cp = codigo_postal.strip()
    if not cp.isdigit() or len(cp) != 5:
        return False, "El código postal debe ser de 5 dígitos."
    if cp not in MERIDA_CP:
        return False, "Solo entregamos en Mérida. El código postal no corresponde a Mérida."
    return True, ""


def _validar_direccion_yucatan(direccion: str) -> bool:
    """Check that the address is in Yucatán."""
    direccion_lower = direccion.lower()

    _palabras_yucatan = [
        "yucatán", "yucatan",
        "mérida", "merida",
        "progreso", "valladolid", "tizimín", "tizimin",
        "motul", "umán", "uman", "kanasín", "kanasin", "oxkutzcab",
        "tekax", "izamal", "peto", "ticul", "espita", "baca",
        "conkal", "chicxulub", "hocabá", "hocaba", "acanceh",
        "sotuta", "dzemul", "hunucmá", "hunucma", "celestún", "celestun",
        "dzilam", "temax", "telchac", "sinaanche", "dzidzantún", "dzidzantun",
        "xoclán", "xoclan", "chablekal", "caucel", "dzityá", "dzitya",
        "nolo", "susulá", "susula", "tixcacal", "kennedy",
    ]

    _no_yucatan = [
        "cdmx", "ciudad de méxico", "ciudad de mexico",
        "nuevo león", "nuevo leon", "monterrey",
        "jalisco", "guadalajara",
        "baja california", "tijuana",
        "chihuahua", "sonora",
        "veracruz", "puebla", "guanajuato",
        "quintana roo", "cancún", "cancun", "chetumal",
        "campeche", "tabasco", "chiapas",
        "oaxaca", "guerrero", "michoacán", "michoacan",
        "sinaloa", "tamaulipas", "coahuila",
        "estado de méxico", "estado de mexico", "edomex",
    ]

    tiene_yucatan = False
    for palabra in _palabras_yucatan:
        if palabra in direccion_lower:
            tiene_yucatan = True
            break

    if not tiene_yucatan:
        return False

    for palabra in _no_yucatan:
        if palabra in direccion_lower:
            return False

    return True


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
        if not _validar_direccion_yucatan(datos.direccion):
            raise ValueError(
                "Solo entregamos en Yucatán. "
                "Asegúrate de incluir tu ciudad o 'Yucatán' en la dirección."
            )
        cp_ok, cp_msg = _validar_cp_merida(datos.codigo_postal)
        if not cp_ok:
            raise ValueError(cp_msg)

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
            codigo_postal=datos.codigo_postal,
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
        if not _validar_direccion_yucatan(datos.direccion):
            raise ValueError(
                "Solo entregamos en Yucatán. "
                "Asegúrate de incluir tu ciudad o 'Yucatán' en la dirección."
            )
        cp_ok, cp_msg = _validar_cp_merida(datos.codigo_postal)
        if not cp_ok:
            raise ValueError(cp_msg)

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
