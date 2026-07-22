"""Stress tests: try to break every endpoint with invalid inputs.

Uses the default mock pool from conftest helpers.
Every test must return a non-500 status code.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.api.dependencies import get_paquete_repo
from src.infrastructure.cache import MemoryCache
from src.infrastructure.limiter import limiter
from tests.e2e.conftest import (
    MockPaqueteRepository,
    _make_mock_pool,
    make_paquete,
)


@pytest.fixture(autouse=True)
def _setup():
    limiter.enabled = False
    app.dependency_overrides.clear()
    pool, _mock_conn = _make_mock_pool()
    app.state.db_pool = pool
    app.state._mock_conn = _mock_conn
    app.state.cache = MemoryCache(default_ttl=60)
    paquete_repo = MockPaqueteRepository()
    app.dependency_overrides[get_paquete_repo] = lambda: paquete_repo
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


class TestAPIStress:
    """Hit every API endpoint with garbage inputs — no 500s allowed."""

    def test_paquetes_list(self, client):
        resp = client.get("/api/paquetes")
        assert resp.status_code < 500

    def test_paquetes_get_by_id_invalid_uuid(self, client):
        resp = client.get("/api/paquetes/not-a-uuid")
        assert resp.status_code < 500

    def test_paquetes_get_by_id_nonexistent(self, client):
        resp = client.get(f"/api/paquetes/{uuid4()}")
        assert resp.status_code < 500

    def test_paquetes_precio_invalid_uuid(self, client):
        resp = client.get("/api/paquetes/not-a-uuid/precio?cantidad=1")
        assert resp.status_code < 500

    def test_paquetes_precio_missing_cantidad(self, client):
        resp = client.get(f"/api/paquetes/{uuid4()}/precio")
        assert resp.status_code < 500

    def test_paquetes_precio_negative_cantidad(self, client):
        resp = client.get(f"/api/paquetes/{uuid4()}/precio?cantidad=-1")
        assert resp.status_code < 500

    def test_paquetes_precio_html_invalid_uuid(self, client):
        resp = client.get("/api/paquetes/precio-html?paquete_id=bad&cantidad=1")
        assert resp.status_code < 500

    def test_pedidos_create_missing_fields(self, client):
        resp = client.post("/api/pedidos", json={})
        assert resp.status_code < 500

    def test_pedidos_create_invalid_json(self, client):
        resp = client.post("/api/pedidos", data="not-json", headers={"Content-Type": "application/json"})
        assert resp.status_code < 500

    def test_pedidos_list_missing_fecha(self, client):
        resp = client.get("/api/pedidos")
        assert resp.status_code < 500

    def test_pedidos_list_invalid_fecha(self, client):
        resp = client.get("/api/pedidos?fecha=not-a-date")
        assert resp.status_code < 500

    def test_pedidos_get_by_id_invalid_uuid(self, client):
        resp = client.get("/api/pedidos/not-a-uuid")
        assert resp.status_code < 500

    def test_pedidos_update_estatus_invalid_uuid(self, client):
        resp = client.patch("/api/pedidos/not-a-uuid/estatus", json={"estatus": "aceptado"})
        assert resp.status_code < 500

    def test_pedidos_update_estatus_missing_body(self, client):
        resp = client.patch(f"/api/pedidos/{uuid4()}/estatus", json={})
        assert resp.status_code < 500

    def test_pedidos_clusters_missing_fecha(self, client):
        resp = client.get("/api/pedidos/clusters")
        assert resp.status_code < 500

    def test_suscripciones_create_missing_fields(self, client):
        resp = client.post("/api/suscripciones", json={})
        assert resp.status_code < 500

    def test_suscripciones_create_invalid_json(self, client):
        resp = client.post("/api/suscripciones", data="garbage", headers={"Content-Type": "application/json"})
        assert resp.status_code < 500

    def test_suscripciones_get_by_id_invalid_uuid(self, client):
        resp = client.get("/api/suscripciones/not-a-uuid")
        assert resp.status_code < 500

    def test_suscripciones_update_invalid_uuid(self, client):
        resp = client.patch("/api/suscripciones/not-a-uuid", json={"dia_entrega": 3})
        assert resp.status_code < 500

    def test_suscripciones_update_missing_body(self, client):
        resp = client.patch(f"/api/suscripciones/{uuid4()}", json={})
        assert resp.status_code < 500

    def test_suscripciones_procesar(self, client):
        resp = client.post("/api/suscripciones/procesar")
        assert resp.status_code < 500

    def test_clientes_list(self, client):
        resp = client.get("/api/clientes")
        assert resp.status_code < 500

    def test_cp_invalid_format(self, client):
        resp = client.get("/api/cp/abc")
        assert resp.status_code < 500

    def test_cp_short(self, client):
        resp = client.get("/api/cp/123")
        assert resp.status_code < 500

    def test_cp_nonexistent(self, client):
        resp = client.get("/api/cp/00000")
        assert resp.status_code < 500

    def test_cp_valid(self, client):
        resp = client.get("/api/cp/97100")
        assert resp.status_code < 500

    def test_colonias_merida(self, client):
        resp = client.get("/api/colonias/merida")
        assert resp.status_code < 500

    def test_colonia_search_empty(self, client):
        resp = client.get("/api/colonia?q=")
        assert resp.status_code < 500

    def test_colonia_search_short(self, client):
        resp = client.get("/api/colonia?q=a")
        assert resp.status_code < 500

    def test_ticket_invalid_uuid(self, client):
        resp = client.get("/api/ticket/not-a-uuid.pdf")
        assert resp.status_code < 500

    def test_ticket_nonexistent(self, client):
        app.state._mock_conn.fetchrow = AsyncMock(return_value=None)
        resp = client.get(f"/api/ticket/{uuid4()}.pdf")
        assert resp.status_code < 500

    def test_reverse_geocode_missing_params(self, client):
        resp = client.get("/api/reverse-geocode")
        assert resp.status_code < 500

    def test_reverse_geocode_invalid_lat(self, client):
        resp = client.get("/api/reverse-geocode?lat=abc&lng=def")
        assert resp.status_code < 500

    def test_localizar_ip(self, client):
        resp = client.get("/api/localizar-ip")
        assert resp.status_code < 500

    def test_detectar_cp(self, client):
        resp = client.get("/api/detectar-cp")
        assert resp.status_code < 500

    def test_ubicacion_por_ip(self, client):
        resp = client.get("/api/ubicacion-por-ip")
        assert resp.status_code < 500


class TestPagesStress:
    """Hit every page endpoint with edge cases — no 500s."""

    def test_homepage(self, client):
        resp = client.get("/")
        assert resp.status_code < 500

    def test_partial_welcome(self, client):
        resp = client.get("/partial/welcome")
        assert resp.status_code < 500

    def test_partial_nonexistent(self, client):
        resp = client.get("/partial/nonexistent")
        assert resp.status_code < 500

    def test_checkout_get_no_params(self, client):
        resp = client.get("/checkout")
        assert resp.status_code < 500

    def test_checkout_get_invalid_paquete_id(self, client):
        resp = client.get("/checkout?paquete_id=not-a-uuid")
        assert resp.status_code < 500

    def test_checkout_post_empty(self, client):
        resp = client.post("/checkout", data={})
        assert resp.status_code < 500

    def test_checkout_post_missing_fields(self, client):
        resp = client.post("/checkout", data={"nombre": "Juan"})
        assert resp.status_code < 500

    def test_checkout_post_invalid_paquete_id(self, client):
        resp = client.post("/checkout", data={
            "csrf_token": "fake",
            "paquete_id": "not-a-uuid",
            "nombre": "Juan",
            "telefono": "9991234567",
        })
        assert resp.status_code < 500


class TestLogisticStress:
    """Hit logistic endpoints without auth — no 500s."""

    def test_logistic_dashboard_no_auth(self, client):
        resp = client.get("/logistic", follow_redirects=False)
        assert resp.status_code < 500

    def test_logistic_login_get(self, client):
        resp = client.get("/logistic/login")
        assert resp.status_code < 500

    def test_logistic_login_post_empty(self, client):
        resp = client.post("/logistic/login", data={})
        assert resp.status_code < 500

    def test_logistic_login_post_missing_fields(self, client):
        resp = client.post("/logistic/login", data={"username": "rodri"})
        assert resp.status_code < 500

    def test_logistic_status_update_no_auth(self, client):
        resp = client.post(
            "/logistic/pedidos/00000000-0000-0000-0000-000000000001/estatus",
            data={"estatus": "aceptado"},
        )
        assert resp.status_code < 500

    def test_logistic_partial_pedidos_no_auth(self, client):
        resp = client.get("/logistic/partial/pedidos")
        assert resp.status_code < 500

    def test_logistic_partial_clientes_no_auth(self, client):
        resp = client.get("/logistic/partial/clientes")
        assert resp.status_code < 500

    def test_logistic_clientes_no_auth(self, client):
        resp = client.get("/logistic/clientes")
        assert resp.status_code < 500

    def test_logistic_logout(self, client):
        resp = client.get("/logistic/logout")
        assert resp.status_code < 500