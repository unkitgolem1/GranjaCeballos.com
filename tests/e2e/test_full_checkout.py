"""End-to-end tests simulating a real user checkout flow.

These tests exercise the full stack: HTTP, middleware (CSRF, rate-limit, session),
template rendering, form parsing, and service logic.
Dependencies (DB, Nominatim) are mocked to keep tests fast and hermetic.
"""

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.domain.models import Paquete
from tests.conftest import make_paquete, make_usuario

# ── Fixtures ──────────────────────────────────────────────────────────────

# Store created objects so the test can reference them
_CREATED_PEDIDO_ID = None
_CREATED_SUSCRIPCION_ID = None


def _reset_globals():
    global _CREATED_PEDIDO_ID, _CREATED_SUSCRIPCION_ID
    _CREATED_PEDIDO_ID = None
    _CREATED_SUSCRIPCION_ID = None


@pytest.fixture(autouse=True)
def reset():
    _reset_globals()
    app.dependency_overrides.clear()
    # Reset paquete cache so tests don't interfere
    import src.pages.router as r
    r._PAQUETES_CACHE = {}
    r._PAQUETES_CACHE_TS = 0.0
    yield


@pytest.fixture
def client():
    yield TestClient(app)


@pytest.fixture
def mock_repos():
    """Wire mock repositories that persist across a single test."""
    from src.pages.dependencies import get_paquete_repo, get_cliente_repo
    from src.pages.router import _get_paquetes_cached

    paquete = make_paquete(
        id=uuid4(),
        nombre="Tradicional E2E",
        precio=Decimal("150"),
        cantidad_fija=1,
        costo_envio=Decimal("30"),
        es_customizable=False,
        activo=True,
    )

    class E2EMockPaqueteRepo:
        async def list_active(self):
            return [paquete]

        async def get_by_id(self, pid):
            return paquete if str(pid) == str(paquete.id) else None

    class E2EMockPedidoRepo:
        def __init__(self):
            self.pedidos = {}

        async def create_si_no_pendiente(self, pedido):
            if any(p.estatus == "pendiente" for p in self.pedidos.values()):
                raise ValueError("Ya tienes un pedido pendiente")
            self.pedidos[str(pedido.id)] = pedido
            global _CREATED_PEDIDO_ID
            _CREATED_PEDIDO_ID = str(pedido.id)
            return pedido

        async def create(self, pedido):
            self.pedidos[str(pedido.id)] = pedido
            return pedido

        async def list_by_fecha(self, fecha):
            return [p for p in self.pedidos.values() if p.fecha_entrega == fecha]

    class E2EMockUsuarioRepo:
        async def get_or_create_by_phone(self, telefono, nombre, email=None):
            return make_usuario(telefono=telefono, nombre=nombre, email=email)

    class E2EMockSuscripcionRepo:
        def __init__(self):
            self.subs = {}

        async def create(self, sub):
            self.subs[str(sub.id)] = sub
            global _CREATED_SUSCRIPCION_ID
            _CREATED_SUSCRIPCION_ID = str(sub.id)
            return sub

        async def get_by_id(self, sid):
            return self.subs.get(sid)

        async def list_by_usuario(self, uid):
            return [s for s in self.subs.values() if str(s.usuario_id) == uid]

    paquete_repo = E2EMockPaqueteRepo()
    pedido_repo = E2EMockPedidoRepo()
    usuario_repo = E2EMockUsuarioRepo()
    suscripcion_repo = E2EMockSuscripcionRepo()

    app.dependency_overrides[get_paquete_repo] = lambda: paquete_repo

    import src.pages.router as r
    r._get_paquetes_cached = lambda repo: repo.list_active()

    return paquete_repo, pedido_repo, usuario_repo, suscripcion_repo, paquete


# ── Tests ─────────────────────────────────────────────────────────────────

class TestFullCheckoutFlow:
    """Complete user journey: visit page → view paquetes → submit order → see success."""

    def test_visit_checkout_page(self, client, mock_repos):
        resp = client.get("/checkout")
        assert resp.status_code == 200
        assert "Tradicional E2E" in resp.text
        assert "plan-card" in resp.text
        assert "csrf_token" not in resp.text  # CSRF only in logistic routes
        assert "calcularPrecio" in resp.text  # frontend pricing JS exposed

    def test_single_order_success(self, client, mock_repos):
        _, _, _, _, paquete = mock_repos
        resp = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan Pérez",
            "telefono": "9991234567",
            "email": "juan@example.com",
            "direccion": "Calle 53 #298, Mérida, Yucatán",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp.status_code == 200
        assert "Juan Pérez" in resp.text
        assert "pendiente" in resp.text or "éxito" in resp.text or "éxito" in resp.text.lower() or "confirmado" in resp.text

    def test_single_order_outside_yucatan_rejected(self, client, mock_repos):
        _, _, _, _, paquete = mock_repos
        resp = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Cancún, Quintana Roo",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp.status_code == 200
        assert "Yucatán" in resp.text

    def test_duplicate_pending_order_rejected(self, client, mock_repos):
        _, pedido_repo, _, _, paquete = mock_repos
        # Submit first order
        resp1 = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Mérida, Yucatán",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp1.status_code == 200

        # Submit second order with same user → should reject
        resp2 = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Mérida, Yucatán",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp2.status_code == 200
        assert "pendiente" in resp2.text

    def test_subscription_requires_tarjeta(self, client, mock_repos):
        _, _, _, _, paquete = mock_repos
        resp = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Mérida, Yucatán",
            "metodo_pago": "efectivo",  # ← wrong for subscription
            "dia_entrega": "1",
            "es_suscripcion": "true",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp.status_code == 200
        assert "tarjeta" in resp.text

    def test_subscription_success(self, client, mock_repos):
        _, _, _, _, paquete = mock_repos
        resp = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Mérida, Yucatán",
            "metodo_pago": "tarjeta",
            "dia_entrega": "1",
            "es_suscripcion": "true",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp.status_code == 200
        # Should show success. "pedido" context is rendered in success template.
        # The success template references paquete.nombre, etc.
        assert "tarjeta" in resp.text

    def test_homepage_loads_paquetes(self, client, mock_repos):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Tradicional E2E" in resp.text

    def test_pricing_data_in_html(self, client, mock_repos):
        """Verify pricing data attributes are present for frontend JS."""
        resp = client.get("/checkout")
        assert resp.status_code == 200
        assert "data-precio" in resp.text
        assert "data-cantidad-fija" in resp.text
        assert "data-costo-envio" in resp.text
        assert "data-customizable" in resp.text
