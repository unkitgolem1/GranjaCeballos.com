import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.infrastructure.limiter import limiter


@pytest.fixture(autouse=True)
def _app_setup():
    """Override rate limiter to disable it for tests + mock DB pool."""
    limiter.enabled = False

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = ctx_mgr
    app.state.db_pool = mock_pool
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    limiter.enabled = True


@pytest.fixture
def client():
    yield TestClient(app)


class TestCheckoutPage:
    def test_get_checkout_returns_200(self, client):
        resp = client.get("/checkout")
        assert resp.status_code == 200

    def test_get_checkout_with_paquete_id(self, client):
        resp = client.get("/checkout?paquete_id=00000000-0000-0000-0000-000000000001&cantidad=3")
        assert resp.status_code == 200

    def test_get_checkout_invalid_uuid(self, client):
        resp = client.get("/checkout?paquete_id=not-a-uuid")
        assert resp.status_code == 422

    def test_checkout_renders_pricing_js(self, client):
        resp = client.get("/checkout")
        assert "calcularPrecio" in resp.text


class TestCheckoutSubmit:
    def test_post_checkout_missing_fields_returns_422(self, client):
        resp = client.post("/checkout", data={})
        assert resp.status_code == 422

    def test_post_checkout_valid_submission(self, client):
        resp = client.post("/checkout", data={
            "paquete_id": "00000000-0000-0000-0000-000000000001",
            "nombre": "Test",
            "telefono": "9991234567",
            "direccion": "Mérida, Yucatán",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": "2026-07-18",
            "cantidad": "1",
        })
        assert resp.status_code == 200


class TestApiEndpoints:
    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_paquetes_api(self, client):
        resp = client.get("/api/paquetes")
        assert resp.status_code == 200

    def test_clientes_api(self, client):
        resp = client.get("/api/clientes")
        assert resp.status_code == 200

    def test_reverse_geocode_invalid_bounds(self, client):
        resp = client.get("/api/reverse-geocode", params={"lat": 200, "lng": -89.62})
        assert resp.status_code in (400, 422)

    def test_reverse_geocode_missing_param(self, client):
        resp = client.get("/api/reverse-geocode")
        assert resp.status_code == 422

    def test_reverse_geocode_valid(self, client):
        resp = client.get("/api/reverse-geocode", params={"lat": 20.97, "lng": -89.62})
        assert resp.status_code in (200, 502, 400)
