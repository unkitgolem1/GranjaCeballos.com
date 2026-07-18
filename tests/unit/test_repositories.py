from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.models import Pedido, Suscripcion
from src.infrastructure.repositories import (
    PostgresPaqueteRepository,
    PostgresPedidoRepository,
    PostgresSuscripcionRepository,
    PostgresUsuarioRepository,
    PostgresClienteRepository,
)


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=None)
    pool.acquire.return_value = ctx_mgr
    return pool


@pytest.fixture
def mock_conn(mock_pool):
    return mock_pool.acquire.return_value.__aenter__.return_value


class _FakeRow(dict):
    """Async mock that wraps a dict so dict(row) returns the dict."""
    pass


def _make_row(**kwargs):
    return _FakeRow(kwargs)


# ── UsuarioRepository ────────────────────────────────────────────────────

class TestPostgresUsuarioRepository:
    @pytest.fixture
    def repo(self, mock_pool):
        return PostgresUsuarioRepository(mock_pool)

    async def test_get_by_phone_found(self, repo, mock_conn):
        uid = uuid4()
        mock_conn.fetchrow = AsyncMock(return_value=_make_row(
            id=uid, nombre="Juan", telefono="9991234567",
            email="j@t.com", created_at=datetime.utcnow(),
        ))
        u = await repo.get_by_phone("9991234567")
        assert u is not None
        assert u.telefono == "9991234567"

    async def test_get_by_phone_not_found(self, repo, mock_conn):
        mock_conn.fetchrow = AsyncMock(return_value=None)
        u = await repo.get_by_phone("9991234567")
        assert u is None

    async def test_get_or_create_by_phone_new(self, repo, mock_conn):
        uid = uuid4()
        mock_conn.fetchrow = AsyncMock(return_value=_make_row(
            id=uid, nombre="Juan", telefono="9991234567",
            email=None, created_at=datetime.utcnow(),
        ))
        u = await repo.get_or_create_by_phone("9991234567", "Juan")
        assert u.nombre == "Juan"

    async def test_get_or_create_by_phone_with_email(self, repo, mock_conn):
        uid = uuid4()
        mock_conn.fetchrow = AsyncMock(return_value=_make_row(
            id=uid, nombre="Juan", telefono="9991234567",
            email="j@t.com", created_at=datetime.utcnow(),
        ))
        u = await repo.get_or_create_by_phone("9991234567", "Juan", "j@t.com")
        assert u.email == "j@t.com"


# ── PaqueteRepository ────────────────────────────────────────────────────

class TestPostgresPaqueteRepository:
    @pytest.fixture
    def repo(self, mock_pool):
        return PostgresPaqueteRepository(mock_pool)

    async def test_list_active(self, repo, mock_conn):
        mock_conn.fetch = AsyncMock(return_value=[])
        result = await repo.list_active()
        assert result == []

    async def test_get_by_id_found(self, repo, mock_conn):
        pid = uuid4()
        mock_conn.fetchrow = AsyncMock(return_value=_make_row(
            id=pid, nombre="Test", descripcion="", precio=Decimal("150"),
            costo_envio=Decimal("0"), cantidad_fija=1, es_suscripcion=False,
            es_customizable=False, precio_minimo=Decimal("0"), tiers="[]",
            es_popular=False, badge=None, activo=True, created_at=datetime.utcnow(),
        ))
        p = await repo.get_by_id(str(pid))
        assert p is not None
        assert p.nombre == "Test"

    async def test_get_by_id_not_found(self, repo, mock_conn):
        mock_conn.fetchrow = AsyncMock(return_value=None)
        p = await repo.get_by_id(str(uuid4()))
        assert p is None


# ── PedidoRepository ─────────────────────────────────────────────────────

class TestPostgresPedidoRepository:
    @pytest.fixture
    def repo(self, mock_pool):
        return PostgresPedidoRepository(mock_pool)

    async def test_create_si_no_pendiente_success(self, repo, mock_conn):
        uid = uuid4()
        mock_conn.fetchrow = AsyncMock(return_value=_make_row(
            id=uid, usuario_id=uuid4(), paquete_id=uuid4(),
            suscripcion_id=None, direccion="Mérida", cantidad=1,
            total=Decimal("150"), metodo_pago="efectivo", estatus="pendiente",
            notas=None, fecha_usuario=date.today(), fecha_entrega=date.today(),
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        pedido = Pedido(
            id=uid, usuario_id=uuid4(), paquete_id=uuid4(),
            direccion="Mérida", cantidad=1, total=Decimal("150"),
            metodo_pago="efectivo", fecha_usuario=date.today(), fecha_entrega=date.today(),
        )
        result = await repo.create_si_no_pendiente(pedido)
        assert result.estatus == "pendiente"

    async def test_create_si_no_pendiente_rejected(self, repo, mock_conn):
        mock_conn.fetchrow = AsyncMock(return_value=None)
        pedido = Pedido(id=uuid4(), usuario_id=uuid4(), paquete_id=uuid4(),
                        direccion="Mérida", cantidad=1, total=Decimal("150"),
                        metodo_pago="efectivo", fecha_usuario=date.today(), fecha_entrega=date.today())
        with pytest.raises(ValueError, match="pendiente"):
            await repo.create_si_no_pendiente(pedido)


# ── SuscripcionRepository ────────────────────────────────────────────────

class TestPostgresSuscripcionRepository:
    @pytest.fixture
    def repo(self, mock_pool):
        return PostgresSuscripcionRepository(mock_pool)

    async def test_create(self, repo, mock_conn):
        sid = uuid4()
        mock_conn.fetchrow = AsyncMock(return_value=_make_row(
            id=sid, usuario_id=uuid4(), paquete_id=uuid4(),
            direccion="Mérida", cantidad=1, metodo_pago="tarjeta",
            dia_entrega=1, fecha_inicio=date.today(), proxima_generacion=date.today(),
            activa=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        sub = Suscripcion(id=sid, usuario_id=uuid4(), paquete_id=uuid4(), direccion="Mérida",
                          metodo_pago="tarjeta", dia_entrega=1,
                          fecha_inicio=date.today(), proxima_generacion=date.today())
        result = await repo.create(sub)
        assert result.activa is True

    async def test_get_by_id_found(self, repo, mock_conn):
        sid = uuid4()
        mock_conn.fetchrow = AsyncMock(return_value=_make_row(
            id=sid, usuario_id=uuid4(), paquete_id=uuid4(),
            direccion="Mérida", cantidad=1, metodo_pago="tarjeta",
            dia_entrega=1, fecha_inicio=date.today(), proxima_generacion=date.today(),
            activa=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        ))
        result = await repo.get_by_id(str(sid))
        assert result is not None

    async def test_get_by_id_not_found(self, repo, mock_conn):
        mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await repo.get_by_id(str(uuid4()))
        assert result is None

    async def test_avanzar_proxima(self, repo, mock_conn):
        mock_conn.execute = AsyncMock(return_value=None)
        await repo.avanzar_proxima(str(uuid4()))
        mock_conn.execute.assert_awaited_once()


# ── ClienteRepository ────────────────────────────────────────────────────

class TestPostgresClienteRepository:
    @pytest.fixture
    def repo(self, mock_pool):
        return PostgresClienteRepository(mock_pool)

    async def test_list_active(self, repo, mock_conn):
        mock_conn.fetch = AsyncMock(return_value=[])
        result = await repo.list_active()
        assert result == []
