from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.pages.dependencies import get_paquete_repo, get_cliente_repo
from tests.e2e.conftest import (
    MockClienteRepository,
    MockPaqueteRepository,
    MockPedidoRepository,
    MockUsuarioRepository,
    make_paquete,
)


@pytest.fixture
def mock_repos(client: TestClient):
    paquete = make_paquete(
        id=uuid4(),
        nombre="Tradicional E2E",
        precio=Decimal("150"),
        cantidad_fija=1,
        costo_envio=Decimal("30"),
        es_customizable=False,
        activo=True,
    )

    paquete_repo = MockPaqueteRepository([paquete])
    pedido_repo = MockPedidoRepository()
    usuario_repo = MockUsuarioRepository()
    suscripcion_repo = MockUsuarioRepository()

    app.dependency_overrides[get_paquete_repo] = lambda: paquete_repo
    app.dependency_overrides[get_cliente_repo] = lambda: MockClienteRepository()

    import importlib
    _pages_router_mod = importlib.import_module("src.pages.router")
    _pages_router_mod._PAQUETES_CACHE["all"] = [paquete]

    return paquete_repo, pedido_repo, usuario_repo, suscripcion_repo, paquete


class TestFullCheckoutFlow:
    def test_visit_checkout_page(self, client, mock_repos):
        resp = client.get("/checkout")
        assert resp.status_code == 200
        assert "Tradicional E2E" in resp.text
        assert "plan-card" in resp.text
        assert "csrf_token" not in resp.text
        assert "selectPaquete" in resp.text

    def test_pricing_data_in_html(self, client, mock_repos):
        resp = client.get("/checkout")
        assert resp.status_code == 200
        assert "data-id" in resp.text
        assert "data-customizable" in resp.text

    def test_homepage_partial_shows_paquetes(self, client, mock_repos):
        resp = client.get("/partial/welcome")
        assert resp.status_code == 200
        assert "Tradicional E2E" in resp.text
        assert "plan-card" in resp.text or "Elige tu plan" in resp.text

    def test_single_order_cp_fuera_yucatan_rejected(self, client, mock_repos):
        _, _, _, _, paquete = mock_repos
        resp = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Cualquier dirección",
            "codigo_postal": "00000",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp.status_code == 200
        assert "Código postal no válido" in resp.text

    def test_subscription_requires_tarjeta(self, client, mock_repos):
        _, _, _, _, paquete = mock_repos
        resp = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Mérida, Yucatán",
            "codigo_postal": "97100",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "true",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp.status_code == 200
        assert "tarjeta" in resp.text
