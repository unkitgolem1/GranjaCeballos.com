"""End-to-end tests for error handling and edge cases.

Tests cover validation errors, missing fields, invalid data, and 404s.
"""

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
    make_paquete,
)


@pytest.fixture
def mock_checkout():
    paquete = make_paquete(
        id=uuid4(),
        nombre="Test",
        precio=Decimal("150"),
        cantidad_fija=1,
        activo=True,
    )
    paquete_repo = MockPaqueteRepository([paquete])

    app.dependency_overrides[get_paquete_repo] = lambda: paquete_repo
    app.dependency_overrides[get_cliente_repo] = lambda: MockClienteRepository()

    import importlib
    _mod = importlib.import_module("src.pages.router")
    _mod._PAQUETES_CACHE["all"] = [paquete]

    return paquete


class TestCheckoutGET:
    def test_invalid_uuid_returns_422(self, client):
        resp = client.get("/checkout?paquete_id=not-a-uuid")
        assert resp.status_code == 422

    def test_valid_uuid_returns_200(self, client, mock_checkout):
        resp = client.get("/checkout")
        assert resp.status_code == 200

    def test_with_paquete_id_and_cantidad(self, client, mock_checkout):
        paquete = mock_checkout
        resp = client.get(f"/checkout?paquete_id={paquete.id}&cantidad=3")
        assert resp.status_code == 200


class TestCheckoutPOST:
    def test_missing_fields_returns_422(self, client):
        resp = client.post("/checkout", data={})
        assert resp.status_code == 422

    def test_partial_fields_returns_422(self, client):
        resp = client.post("/checkout", data={
            "nombre": "Juan",
            "telefono": "9991234567",
        })
        assert resp.status_code == 422

    def test_cantidad_zero_returns_422(self, client, mock_checkout):
        paquete = mock_checkout
        resp = client.post("/checkout", data={
            "paquete_id": str(paquete.id),
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Mérida, Yucatán",
            "codigo_postal": "97100",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": str(date.today()),
            "cantidad": "0",
        })
        assert resp.status_code == 422

    def test_invalid_paquete_id_returns_200_with_error(self, client, mock_checkout):
        resp = client.post("/checkout", data={
            "paquete_id": "not-a-uuid",
            "nombre": "Juan",
            "telefono": "9991234567",
            "direccion": "Mérida, Yucatán",
            "codigo_postal": "97100",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": str(date.today()),
            "cantidad": "1",
        })
        assert resp.status_code == 200
        assert "no encontrado" in resp.text.lower()


class TestPartialView:
    def test_valid_partial_returns_200(self, client):
        resp = client.get("/partial/welcome")
        assert resp.status_code == 200

    def test_invalid_partial_returns_404(self, client):
        resp = client.get("/partial/nonexistent")
        assert resp.status_code == 404

    def test_partial_with_htmx_header(self, client):
        resp = client.get("/partial/welcome", headers={"HX-Request": "true"})
        assert resp.status_code == 200


class TestLogisticErrors:
    @pytest.fixture(autouse=True)
    def _creds(self):
        import os
        self._username = "rodri"
        self._password = "pass123"
        _old_user = os.environ.get("LOGISTIC_USERNAME")
        _old_pass = os.environ.get("LOGISTIC_PASSWORD")
        os.environ["LOGISTIC_USERNAME"] = self._username
        os.environ["LOGISTIC_PASSWORD"] = self._password
        yield
        if _old_user is not None:
            os.environ["LOGISTIC_USERNAME"] = _old_user
        else:
            os.environ.pop("LOGISTIC_USERNAME", None)
        if _old_pass is not None:
            os.environ["LOGISTIC_PASSWORD"] = _old_pass
        else:
            os.environ.pop("LOGISTIC_PASSWORD", None)

    def test_login_missing_fields_returns_422(self, client):
        resp = client.post("/logistic/login", data={"username": "rodri"})
        assert resp.status_code == 422

    def test_status_update_invalid_estatus(self, client):
        import re

        resp = client.get("/logistic/login")
        csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text).group(1)
        client.post("/logistic/login", data={
            "csrf_token": csrf,
            "username": self._username,
            "password": self._password,
        })

        resp = client.post(
            "/logistic/pedidos/00000000-0000-0000-0000-000000000001/estatus",
            data={"csrf_token": csrf, "estatus": "invalid_status"},
        )
        assert resp.status_code == 404


class TestAPIErrors:
    def test_pedidos_missing_fecha_returns_422(self, client):
        resp = client.get("/api/pedidos")
        assert resp.status_code == 422

    def test_create_pedido_missing_fields_returns_422(self, client):
        resp = client.post("/api/pedidos", json={"nombre": "Juan"})
        assert resp.status_code == 422

    def test_create_pedido_invalid_json(self, client):
        resp = client.post("/api/pedidos", data="not-json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422
