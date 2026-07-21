from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.application.services import (
    _calcular_fecha_entrega,
    _calcular_precio_unitario,
    _calcular_total,
    PedidoService,
    SuscripcionService,
)
from src.application.schemas import PedidoCreate, SuscripcionCreate
from src.domain.interfaces import PaqueteRepository, SepomexRepository
from tests.conftest import make_paquete, make_suscripcion, make_usuario


class MockPaqueteRepositoryWithGetById(PaqueteRepository):
    def __init__(self, result):
        self._result = result

    async def list_active(self) -> list:
        return []

    async def get_by_id(self, paquete_id: str):
        return self._result


class MockSepomexRepository(SepomexRepository):
    def __init__(self):
        self._data = {
            "97000": {"municipio": "Mérida", "colonias": ["Centro"]},
            "97100": {"municipio": "Mérida", "colonias": ["Itzimna"]},
            "97700": {"municipio": "Tizimín", "colonias": ["Tizimín Centro"]},
        }

    async def consultar(self, cp: str) -> dict | None:
        return self._data.get(cp)

    async def existe(self, cp: str) -> bool:
        return cp in self._data


# ── _calcular_precio_unitario ────────────────────────────────────────────

class TestCalcularPrecioUnitario:
    def test_no_customizable_returns_precio(self, paquete_tradicional):
        assert _calcular_precio_unitario(paquete_tradicional, 1) == Decimal("150")

    def test_no_customizable_ignores_cantidad(self, paquete_tradicional):
        assert _calcular_precio_unitario(paquete_tradicional, 99) == Decimal("150")

    def test_customizable_base_price(self, paquete_customizable):
        assert _calcular_precio_unitario(paquete_customizable, 1) == Decimal("160")

    def test_customizable_tier_5(self, paquete_customizable):
        assert _calcular_precio_unitario(paquete_customizable, 5) == Decimal("140")

    def test_customizable_tier_10(self, paquete_customizable):
        assert _calcular_precio_unitario(paquete_customizable, 10) == Decimal("130")

    def test_customizable_tier_above(self, paquete_customizable):
        assert _calcular_precio_unitario(paquete_customizable, 20) == Decimal("130")

    def test_precio_minimo_floor(self):
        p = make_paquete(
            es_customizable=True,
            precio=Decimal("100"),
            precio_minimo=Decimal("120"),
            tiers=[],
        )
        assert _calcular_precio_unitario(p, 1) == Decimal("120")

    def test_precio_minimo_below_tier(self):
        p = make_paquete(
            es_customizable=True,
            precio=Decimal("200"),
            precio_minimo=Decimal("110"),
            tiers=[{"min_cantidad": 10, "precio_unitario": Decimal("100")}],
        )
        # tier 10 gives 100, but min is 110
        assert _calcular_precio_unitario(p, 10) == Decimal("110")


# ── _calcular_total ──────────────────────────────────────────────────────

class TestCalcularTotal:
    def test_no_customizable_no_envio(self, paquete_tradicional):
        paquete_tradicional.costo_envio = Decimal("0")
        assert _calcular_total(paquete_tradicional, 1) == Decimal("150")

    def test_no_customizable_con_envio(self, paquete_tradicional):
        paquete_tradicional.costo_envio = Decimal("30")
        assert _calcular_total(paquete_tradicional, 1) == Decimal("180")

    def test_no_customizable_envio_gratis(self, paquete_tradicional):
        paquete_tradicional.costo_envio = Decimal("30")
        assert _calcular_total(paquete_tradicional, 1, envio_gratis=True) == Decimal("150")

    def test_customizable_con_envio(self, paquete_customizable):
        paquete_customizable.costo_envio = Decimal("20")
        assert _calcular_total(paquete_customizable, 3) == Decimal("500")  # 160*3 + 20

    def test_customizable_envio_gratis(self, paquete_customizable):
        paquete_customizable.costo_envio = Decimal("20")
        total = _calcular_total(paquete_customizable, 3, envio_gratis=True)
        assert total == Decimal("480")  # 160*3

    def test_cantidad_fija_multiplica(self):
        p = make_paquete(precio=Decimal("150"), cantidad_fija=2, es_customizable=False)
        assert _calcular_total(p, 1) == Decimal("300")


# ── _calcular_fecha_entrega ──────────────────────────────────────────────

class TestCalcularFechaEntrega:
    def test_fecha_futura(self):
        f = date.today() + timedelta(days=5)
        assert _calcular_fecha_entrega(f) == f

    def test_hoy_antes_de_12(self, monkeypatch):
        fake = datetime.now().replace(hour=11, minute=0)
        monkeypatch.setattr("src.application.services.datetime", _MockDatetime(fake))
        hoy = date.today()
        assert _calcular_fecha_entrega(hoy) == hoy

    def test_hoy_despues_de_12(self, monkeypatch):
        fake = datetime.now().replace(hour=13, minute=0)
        monkeypatch.setattr("src.application.services.datetime", _MockDatetime(fake))
        hoy = date.today()
        assert _calcular_fecha_entrega(hoy) == hoy + timedelta(days=1)


class _MockDatetime:
    def __init__(self, now):
        self._now = now

    def now(self):
        return self._now

    def __getattr__(self, name):
        import datetime as dt
        return getattr(dt, name)


# ── PedidoService ────────────────────────────────────────────────────────

class TestPedidoService:
    @pytest.fixture
    def service(self, pedido_repo):
        return PedidoService(pedido_repo=pedido_repo)

    async def test_crear_atomic_success(self, service, paquete_tradicional):
        datos = PedidoCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_tradicional.id,
            direccion="Mérida, Yucatán",
            codigo_postal="97000",
            metodo_pago="efectivo",
            fecha_usuario=date.today(),
        )
        pedido = await service.crear_atomic(datos, paquete=paquete_tradicional)
        assert pedido.estatus == "pendiente"
        assert pedido.total == Decimal("150")
        assert pedido.cantidad == 1

    async def test_crear_fuera_de_yucatan(self, service, paquete_tradicional):
        """Mock pedido_repo returns cp_valido=False for CP 97700."""
        datos = PedidoCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_tradicional.id,
            direccion="Cancún, Quintana Roo",
            codigo_postal="97700",
            metodo_pago="efectivo",
            fecha_usuario=date.today(),
        )
        with pytest.raises(ValueError, match="solo cubre Mérida"):
            await service.crear_atomic(datos, paquete=paquete_tradicional)

    async def test_crear_paquete_inactivo(self, service, paquete_tradicional):
        paquete_inactivo = make_paquete(activo=False)
        datos = PedidoCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_inactivo.id,
            direccion="Mérida, Yucatán",
            codigo_postal="97000",
            metodo_pago="efectivo",
            fecha_usuario=date.today(),
        )
        with pytest.raises(ValueError, match="Paquete no disponible"):
            await service.crear_atomic(datos, paquete=paquete_inactivo)

    async def test_crear_customizable_cantidad_variable(self, service, paquete_customizable):
        datos = PedidoCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_customizable.id,
            direccion="Mérida, Yucatán",
            codigo_postal="97000",
            cantidad=5,
            metodo_pago="efectivo",
            fecha_usuario=date.today(),
        )
        pedido = await service.crear_atomic(datos, paquete=paquete_customizable)
        assert pedido.cantidad == 5

    async def test_crear_no_customizable_ignora_cantidad(self, service, paquete_tradicional):
        datos = PedidoCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_tradicional.id,
            direccion="Mérida, Yucatán",
            codigo_postal="97000",
            cantidad=99,
            metodo_pago="efectivo",
            fecha_usuario=date.today(),
        )
        pedido = await service.crear_atomic(datos, paquete=paquete_tradicional)
        assert pedido.cantidad == 1


# ── SuscripcionService ───────────────────────────────────────────────────

class TestSuscripcionService:
    @pytest.fixture
    def sepomex_repo(self):
        return MockSepomexRepository()

    @pytest.fixture
    def service(self, usuario_repo, paquete_repo, pedido_repo, suscripcion_repo, sepomex_repo):
        return SuscripcionService(usuario_repo, paquete_repo, pedido_repo, suscripcion_repo, sepomex_repo)

    async def test_crear_success(self, service, paquete_tradicional, pedido_repo, suscripcion_repo):
        datos = SuscripcionCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_tradicional.id,
            direccion="Mérida, Yucatán",
            codigo_postal="97000",
            metodo_pago="tarjeta",
            dia_entrega=1,
            fecha_inicio=date.today(),
        )
        sub = await service.crear(datos)
        assert sub.activa is True
        assert sub.dia_entrega == 1

    async def test_crear_no_tarjeta_rejected(self, service, paquete_tradicional):
        datos = SuscripcionCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_tradicional.id,
            direccion="Mérida, Yucatán",
            codigo_postal="97000",
            metodo_pago="efectivo",
            dia_entrega=1,
            fecha_inicio=date.today(),
        )
        with pytest.raises(ValueError, match="tarjeta"):
            await service.crear(datos)

    async def test_crear_genera_primer_pedido(self, service, paquete_tradicional, pedido_repo):
        datos = SuscripcionCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_tradicional.id,
            direccion="Mérida, Yucatán",
            codigo_postal="97000",
            metodo_pago="tarjeta",
            dia_entrega=1,
            fecha_inicio=date.today(),
        )
        sub = await service.crear(datos)
        pedidos = await pedido_repo.list_by_fecha(sub.proxima_generacion)
        assert len(pedidos) == 1
        assert str(pedidos[0].suscripcion_id) == str(sub.id)

    async def test_crear_dia_entrega_calcula_proxima(self, service, paquete_tradicional, pedido_repo):
        """Si hoy es lunes (1) y pide día 3, la primera generación debe ser miércoles (diferencia = 2)."""
        from datetime import timedelta
        hoy = date.today()
        dia_deseado = ((hoy.isoweekday() + 2) % 7) or 7  # 2 días después
        datos = SuscripcionCreate(
            telefono="9991234567",
            nombre="Juan",
            paquete_id=paquete_tradicional.id,
            direccion="Mérida, Yucatán",
            codigo_postal="97000",
            metodo_pago="tarjeta",
            dia_entrega=dia_deseado,
            fecha_inicio=hoy,
        )
        sub = await service.crear(datos)
        esperado = dia_deseado - hoy.isoweekday()
        if esperado <= 0:
            esperado += 7
        assert (sub.proxima_generacion - hoy).days == esperado

    async def test_cambiar_dia_entrega(self, service, paquete_tradicional, suscripcion_repo):
        sub = await suscripcion_repo.create(make_suscripcion(paquete_id=paquete_tradicional.id))
        nueva = await service.cambiar_dia_entrega(str(sub.id), 3)
        assert nueva.dia_entrega == 3

    async def test_cambiar_dia_entrega_inexistente(self, service, paquete_tradicional):
        with pytest.raises(ValueError, match="Suscripción no encontrada"):
            await service.cambiar_dia_entrega(str(uuid4()), 3)
