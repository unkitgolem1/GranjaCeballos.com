import os
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.limiter import limiter
from src.main import app


@pytest.fixture(autouse=True)
def _app_setup():
    limiter.enabled = False
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = ctx_mgr
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value="2026-07-18")
    app.state.db_pool = mock_pool
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()
    limiter.enabled = True


@pytest.fixture
def client():
    yield TestClient(app)


class TestLogin:
    def test_get_login_form(self, client):
        resp = client.get("/logistic/login")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "csrf_token" in resp.text
        assert "contraseña" in resp.text.lower()

    def test_login_success_redirects(self, client):
        user = os.getenv("LOGISTIC_USERNAME", "rodri")
        pw = os.getenv("LOGISTIC_PASSWORD")
        csrf = _get_csrf(client)
        resp = client.post("/logistic/login", data={
            "username": user,
            "password": pw,
            "csrf_token": csrf,
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/logistic"

    def test_login_fail_stays_on_page(self, client):
        csrf = _get_csrf(client)
        resp = client.post("/logistic/login", data={
            "username": "wrong",
            "password": "wrong",
            "csrf_token": csrf,
        })
        assert resp.status_code == 200
        assert "incorrectos" in resp.text

    def test_login_without_csrf_returns_403(self, client):
        resp = client.post("/logistic/login", data={
            "username": "rodri",
            "password": "test",
        })
        assert resp.status_code == 403

class TestDashboardAccess:
    def test_redirect_to_login_if_not_authed(self, client):
        resp = client.get("/logistic", follow_redirects=False)
        assert resp.status_code == 302
        assert "/logistic/login" in resp.headers["location"]

    def test_dashboard_loads_when_authed(self, client):
        _login(client)
        resp = client.get("/logistic")
        assert resp.status_code == 200
        assert "Logística" in resp.text

    def test_logout_clears_session(self, client):
        _login(client)
        resp = client.get("/logistic/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/logistic/login"


class TestPedidoStatusUpdate:
    def test_update_requires_csrf(self, client):
        _login(client)
        resp = client.post("/logistic/pedidos/some-id/estatus", data={"estatus": "aceptado"})
        assert resp.status_code == 403

    def test_update_redirects_to_login_if_not_authed(self, client):
        resp = client.post("/logistic/pedidos/some-id/estatus", data={
            "estatus": "aceptado",
            "csrf_token": "whatever",
        }, follow_redirects=False)
        assert resp.status_code == 302
        assert "/logistic/login" in resp.headers["location"]

    def test_update_with_csrf_and_auth(self, client):
        # Extract CSRF token from login page first, reuse throughout
        r = client.get("/logistic/login")
        m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
        csrf = m.group(1)
        user = os.getenv("LOGISTIC_USERNAME", "rodri")
        pw = os.getenv("LOGISTIC_PASSWORD")
        client.post("/logistic/login", data={
            "username": user,
            "password": pw,
            "csrf_token": csrf,
        })
        resp = client.post("/logistic/pedidos/some-id/estatus", data={
            "estatus": "aceptado",
            "csrf_token": csrf,
        }, follow_redirects=False)
        assert resp.status_code in (302, 404)


# ── Helpers ──────────────────────────────────────────────────────────────

def _get_csrf(client):
    resp = client.get("/logistic/login")
    m = re.search(r'name="csrf_token" value="([^"]+)"', resp.text)
    return m.group(1) if m else ""


def _login(client):
    user = os.getenv("LOGISTIC_USERNAME", "rodri")
    pw = os.getenv("LOGISTIC_PASSWORD")
    csrf = _get_csrf(client)
    client.post("/logistic/login", data={
        "username": user,
        "password": pw,
        "csrf_token": csrf,
    })
