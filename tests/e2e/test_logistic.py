"""End-to-end tests for the logistic panel (login, dashboard, status updates).

These tests mock the DB pool to stay hermetic and fast.
"""

import os
import re
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.pages.dependencies import get_db_pool

_CREDS = {"username": "rodri", "password": "pass123"}


@pytest.fixture(autouse=True)
def _set_creds():
    _old_user = os.environ.get("LOGISTIC_USERNAME")
    _old_pass = os.environ.get("LOGISTIC_PASSWORD")
    os.environ["LOGISTIC_USERNAME"] = _CREDS["username"]
    os.environ["LOGISTIC_PASSWORD"] = _CREDS["password"]
    yield
    if _old_user is not None:
        os.environ["LOGISTIC_USERNAME"] = _old_user
    else:
        os.environ.pop("LOGISTIC_USERNAME", None)
    if _old_pass is not None:
        os.environ["LOGISTIC_PASSWORD"] = _old_pass
    else:
        os.environ.pop("LOGISTIC_PASSWORD", None)


@pytest.fixture
def mock_pool():
    mock_conn = MagicMock()
    mock_conn.fetchval = AsyncMock(return_value=date.today())
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock(return_value=None)

    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire.return_value = ctx_mgr

    app.dependency_overrides[get_db_pool] = lambda: pool
    return pool, mock_conn


def _csrf_from_html(resp) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
    if m:
        return m.group(1)
    raise ValueError("CSRF token not found in response")


def _do_login(client: TestClient) -> str:
    resp = client.get("/logistic/login")
    csrf = _csrf_from_html(resp)
    resp = client.post("/logistic/login", data={
        "csrf_token": csrf,
        "username": _CREDS["username"],
        "password": _CREDS["password"],
    })
    return csrf


class TestLogin:
    def test_login_form_returns_200(self, client):
        resp = client.get("/logistic/login")
        assert resp.status_code == 200
        assert "Logística" in resp.text
        assert "csrf_token" in resp.text

    def test_login_success_redirects(self, client):
        resp = client.get("/logistic/login")
        csrf = _csrf_from_html(resp)
        resp = client.post("/logistic/login", data={
            "csrf_token": csrf,
            "username": _CREDS["username"],
            "password": _CREDS["password"],
        }, follow_redirects=False)
        assert resp.status_code == 302
        parsed = urlparse(resp.headers["location"])
        assert parsed.path == "/logistic"

    def test_login_wrong_credentials_shows_error(self, client):
        resp = client.get("/logistic/login")
        csrf = _csrf_from_html(resp)
        resp = client.post("/logistic/login", data={
            "csrf_token": csrf,
            "username": "bad",
            "password": "wrong",
        })
        assert resp.status_code == 200
        assert "Usuario o contraseña incorrectos" in resp.text

    def test_already_authenticated_redirects_to_dashboard(self, client):
        _do_login(client)
        resp = client.get("/logistic/login", follow_redirects=False)
        assert resp.status_code == 302
        assert urlparse(resp.headers["location"]).path == "/logistic"


class TestDashboard:
    def test_dashboard_requires_auth(self, client):
        resp = client.get("/logistic", follow_redirects=False)
        assert resp.status_code == 302
        assert urlparse(resp.headers["location"]).path == "/logistic/login"

    def test_dashboard_renders_with_auth(self, client, mock_pool):
        _do_login(client)
        resp = client.get("/logistic")
        assert resp.status_code == 200
        assert "logistic" in resp.text.lower()

    def test_dashboard_with_estatus_filter(self, client, mock_pool):
        _do_login(client)
        resp = client.get("/logistic?estatus=pendiente")
        assert resp.status_code == 200

    def test_dashboard_with_seccion_pasado(self, client, mock_pool):
        _do_login(client)
        resp = client.get("/logistic?seccion=pasado")
        assert resp.status_code == 200


class TestStatusUpdate:
    def test_status_update_requires_auth(self, client):
        resp = client.post(
            "/logistic/pedidos/00000000-0000-0000-0000-000000000001/estatus",
            data={"estatus": "aceptado"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert urlparse(resp.headers["location"]).path == "/logistic/login"

    def _get_csrf_from_login(self, client):
        resp = client.get("/logistic/login")
        return _csrf_from_html(resp)

    def test_status_update_nonexistent_pedido_returns_404(self, client, mock_pool):
        csrf = self._get_csrf_from_login(client)
        _do_login(client)
        resp = client.post(
            "/logistic/pedidos/00000000-0000-0000-0000-000000000001/estatus",
            data={"csrf_token": csrf, "estatus": "aceptado"},
        )
        assert resp.status_code == 404

    def test_status_update_with_valid_pedido(self, client, mock_pool):
        pool, mock_conn = mock_pool
        csrf = self._get_csrf_from_login(client)
        mock_conn.fetchrow.return_value = {
            "id": "00000000-0000-0000-0000-000000000001",
            "usuario_id": "00000000-0000-0000-0000-000000000002",
            "paquete_id": "00000000-0000-0000-0000-000000000003",
            "suscripcion_id": None,
            "direccion": "Mérida, Yucatán",
            "cantidad": 1,
            "total": 150,
            "metodo_pago": "efectivo",
            "estatus": "aceptado",
            "notas": None,
            "fecha_usuario": date.today(),
            "fecha_entrega": date.today(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        _do_login(client)
        resp = client.post(
            "/logistic/pedidos/00000000-0000-0000-0000-000000000001/estatus",
            data={"csrf_token": csrf, "estatus": "aceptado"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert urlparse(resp.headers["location"]).path == "/logistic"


class TestLogout:
    def test_logout_clears_session(self, client):
        _do_login(client)
        resp = client.get("/logistic/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert urlparse(resp.headers["location"]).path == "/logistic/login"

        resp = client.get("/logistic", follow_redirects=False)
        assert resp.status_code == 302
        assert urlparse(resp.headers["location"]).path == "/logistic/login"
