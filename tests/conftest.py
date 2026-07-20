from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

import pytest

from src.domain.models import Cliente, CustomTier, Paquete, Pedido, Suscripcion, Usuario

# ── Test data factories ──────────────────────────────────────────────────

_TELEFONO = "9991234567"


def make_usuario(**kwargs) -> Usuario:
    return Usuario(
        id=kwargs.get("id", uuid4()),
        nombre=kwargs.get("nombre", "Test User"),
        telefono=kwargs.get("telefono", _TELEFONO),
        email=kwargs.get("email", "test@example.com"),
        created_at=kwargs.get("created_at", datetime.utcnow()),
    )


def make_paquete(**kwargs) -> Paquete:
    return Paquete(
        id=kwargs.get("id", uuid4()),
        nombre=kwargs.get("nombre", "Paquete Test"),
        descripcion=kwargs.get("descripcion", "Descripción"),
        precio=kwargs.get("precio", Decimal("150")),
        costo_envio=kwargs.get("costo_envio", Decimal("0")),
        cantidad_fija=kwargs.get("cantidad_fija", 1),
        es_suscripcion=kwargs.get("es_suscripcion", False),
        es_customizable=kwargs.get("es_customizable", False),
        precio_minimo=kwargs.get("precio_minimo", Decimal("0")),
        tiers=kwargs.get("tiers", []),
        es_popular=kwargs.get("es_popular", False),
        badge=kwargs.get("badge"),
        activo=kwargs.get("activo", True),
        created_at=kwargs.get("created_at", datetime.utcnow()),
    )


def make_pedido(**kwargs) -> Pedido:
    usuario_id = kwargs.get("usuario_id", uuid4())
    return Pedido(
        id=kwargs.get("id", uuid4()),
        usuario_id=usuario_id,
        paquete_id=kwargs.get("paquete_id", uuid4()),
        suscripcion_id=kwargs.get("suscripcion_id"),
        direccion=kwargs.get("direccion", "Calle 53 #298, Mérida, Yucatán"),
        cantidad=kwargs.get("cantidad", 1),
        total=kwargs.get("total", Decimal("150")),
        metodo_pago=kwargs.get("metodo_pago", "efectivo"),
        estatus=kwargs.get("estatus", "pendiente"),
        notas=kwargs.get("notas"),
        fecha_usuario=kwargs.get("fecha_usuario", date.today()),
        fecha_entrega=kwargs.get("fecha_entrega", date.today()),
        created_at=kwargs.get("created_at", datetime.utcnow()),
        updated_at=kwargs.get("updated_at", datetime.utcnow()),
    )


def make_suscripcion(**kwargs) -> Suscripcion:
    usuario_id = kwargs.get("usuario_id", uuid4())
    return Suscripcion(
        id=kwargs.get("id", uuid4()),
        usuario_id=usuario_id,
        paquete_id=kwargs.get("paquete_id", uuid4()),
        direccion=kwargs.get("direccion", "Calle 53 #298, Mérida, Yucatán"),
        cantidad=kwargs.get("cantidad", 1),
        metodo_pago=kwargs.get("metodo_pago", "tarjeta"),
        dia_entrega=kwargs.get("dia_entrega", 1),
        fecha_inicio=kwargs.get("fecha_inicio", date.today()),
        proxima_generacion=kwargs.get("proxima_generacion", date.today()),
        activa=kwargs.get("activa", True),
        created_at=kwargs.get("created_at", datetime.utcnow()),
        updated_at=kwargs.get("updated_at", datetime.utcnow()),
    )


def make_cliente(**kwargs) -> Cliente:
    return Cliente(
        id=kwargs.get("id", uuid4()),
        nombre=kwargs.get("nombre", "Cliente Test"),
        lugar=kwargs.get("lugar", "Mérida"),
        icono_svg=kwargs.get("icono_svg", "<svg></svg>"),
        testimonio=kwargs.get("testimonio", "Excelente servicio"),
        activo=kwargs.get("activo", True),
        created_at=kwargs.get("created_at", datetime.utcnow()),
    )


# ── Mock repositories ────────────────────────────────────────────────────

class MockUsuarioRepository:
    def __init__(self):
        self._usuarios: dict[str, Usuario] = {}

    async def get_by_phone(self, telefono: str) -> Optional[Usuario]:
        return self._usuarios.get(telefono)

    async def get_or_create_by_phone(self, telefono: str, nombre: str, email: Optional[str] = None) -> Usuario:
        if telefono in self._usuarios:
            return self._usuarios[telefono]
        u = make_usuario(telefono=telefono, nombre=nombre, email=email)
        self._usuarios[telefono] = u
        return u


class MockPaqueteRepository:
    def __init__(self, paquetes: Optional[list[Paquete]] = None):
        self._paquetes: dict[str, Paquete] = {}
        for p in (paquetes or []):
            self._paquetes[str(p.id)] = p

    async def list_active(self) -> list[Paquete]:
        return [p for p in self._paquetes.values() if p.activo]

    async def get_by_id(self, paquete_id: str) -> Optional[Paquete]:
        return self._paquetes.get(paquete_id)


class MockPedidoRepository:
    def __init__(self):
        self._pedidos: dict[str, Pedido] = {}
        self._fail_next_create = False

    async def create_checkout_atomic(
        self,
        *,
        codigo_postal: str,
        nombre: str,
        telefono: str,
        email: str | None,
        pedido_id: UUID,
        paquete_id: UUID,
        direccion: str,
        estado: str,
        ciudad: str,
        colonia: str,
        cantidad: int,
        total: Decimal,
        metodo_pago: str,
        fecha_entrega: date,
    ) -> dict:
        cp_valido = codigo_postal == "97000"
        if not cp_valido:
            return {"usuario_id": uuid4(), "usuario_nombre": nombre, "pedido_id": None, "pedido_total": None, "cp_valido": False}
        has_pending = any(
            p.estatus == "pendiente" for p in self._pedidos.values()
        )
        if has_pending:
            return {"usuario_id": uuid4(), "usuario_nombre": nombre, "pedido_id": None, "pedido_total": None, "cp_valido": True}
        usuario_id = uuid4()
        p = Pedido(
            id=pedido_id,
            usuario_id=usuario_id,
            paquete_id=paquete_id,
            direccion=direccion,
            codigo_postal=codigo_postal,
            cantidad=cantidad,
            total=total,
            metodo_pago=metodo_pago,
            estatus="pendiente",
            fecha_usuario=fecha_entrega,
            fecha_entrega=fecha_entrega,
        )
        self._pedidos[str(pedido_id)] = p
        return {"usuario_id": usuario_id, "usuario_nombre": nombre, "pedido_id": pedido_id, "pedido_total": total, "cp_valido": True}

    async def create_si_no_pendiente(self, pedido: Pedido) -> Pedido:
        if self._fail_next_create:
            self._fail_next_create = False
            raise ValueError("Ya tienes un pedido pendiente.")
        has_pending = any(
            str(p.usuario_id) == str(pedido.usuario_id) and p.estatus == "pendiente"
            for p in self._pedidos.values()
        )
        if has_pending:
            raise ValueError("Ya tienes un pedido pendiente.")
        self._pedidos[str(pedido.id)] = pedido
        return pedido

    async def create(self, pedido: Pedido) -> Pedido:
        self._pedidos[str(pedido.id)] = pedido
        return pedido

    async def get_by_id(self, pedido_id: str) -> Optional[Pedido]:
        return self._pedidos.get(pedido_id)

    async def get_pendiente_by_telefono(self, telefono: str) -> Optional[Pedido]:
        for p in self._pedidos.values():
            if p.estatus == "pendiente":
                return p
        return None

    async def list_by_fecha(self, fecha: date) -> list[Pedido]:
        return [p for p in self._pedidos.values() if p.fecha_entrega == fecha]

    async def update_estatus(self, pedido_id: str, estatus: str) -> Optional[Pedido]:
        p = self._pedidos.get(pedido_id)
        if p:
            p.estatus = estatus
        return p

    async def count_by_direccion_y_fecha(self, fecha: date) -> list[dict]:
        return []


class MockSuscripcionRepository:
    def __init__(self):
        self._subs: dict[str, Suscripcion] = {}

    async def create(self, suscripcion: Suscripcion) -> Suscripcion:
        self._subs[str(suscripcion.id)] = suscripcion
        return suscripcion

    async def get_by_id(self, suscripcion_id: str) -> Optional[Suscripcion]:
        return self._subs.get(suscripcion_id)

    async def list_by_usuario(self, usuario_id: str) -> list[Suscripcion]:
        return [s for s in self._subs.values() if str(s.usuario_id) == usuario_id]

    async def list_vencidas(self) -> list[Suscripcion]:
        return [s for s in self._subs.values() if s.activa and s.proxima_generacion <= date.today()]

    async def update_proxima(self, suscripcion_id: str, dia_entrega: int, proxima_generacion: date) -> Optional[Suscripcion]:
        s = self._subs.get(suscripcion_id)
        if s:
            s.dia_entrega = dia_entrega
            s.proxima_generacion = proxima_generacion
        return s

    async def avanzar_proxima(self, suscripcion_id: str) -> None:
        s = self._subs.get(suscripcion_id)
        if s:
            from datetime import timedelta
            s.proxima_generacion += timedelta(days=7)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def usuario_repo():
    return MockUsuarioRepository()


@pytest.fixture
def paquete_tradicional() -> Paquete:
    return make_paquete(
        nombre="Tradicional",
        precio=Decimal("150"),
        cantidad_fija=1,
        costo_envio=Decimal("0"),
        es_customizable=False,
    )


@pytest.fixture
def paquete_customizable() -> Paquete:
    return make_paquete(
        nombre="Personalizable",
        precio=Decimal("160"),
        cantidad_fija=1,
        costo_envio=Decimal("0"),
        es_customizable=True,
        precio_minimo=Decimal("130"),
        tiers=[
            CustomTier(min_cantidad=5, precio_unitario=Decimal("140")),
            CustomTier(min_cantidad=10, precio_unitario=Decimal("130")),
        ],
    )


@pytest.fixture
def paquete_repo(paquete_tradicional, paquete_customizable):
    return MockPaqueteRepository([paquete_tradicional, paquete_customizable])


@pytest.fixture
def pedido_repo():
    return MockPedidoRepository()


@pytest.fixture
def suscripcion_repo():
    return MockSuscripcionRepository()
