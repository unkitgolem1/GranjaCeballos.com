"""End-to-end tests for REST API endpoints.

All external dependencies (DB, Nominatim) are mocked.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.api.dependencies import (
    get_paquete_repo,
    get_pedido_repo,
    get_usuario_repo,
    get_suscripcion_repo,
    get_cliente_repo,
    get_pedido_service,
    get_suscripcion_service,
    get_suscripcion_scheduler,
    get_health_service,
)
from src.application.services import PedidoService, SuscripcionService
from src.application.scheduler import SuscripcionScheduler
from src.infrastructure.health_service import HealthService
from tests.e2e.conftest import (
    MockPaqueteRepository,
    MockPedidoRepository,
    MockUsuarioRepository,
    MockSuscripcionRepository,
    MockClienteRepository,
    MockSepomexRepository,
    make_paquete,
    make_pedido,
    make_usuario,
    make_suscripcion,
)


@pytest.fixture
def mock_repos():
    paquete = make_paquete(
        id=uuid4(),
        nombre="Tradicional",
        precio=Decimal("150"),
        cantidad_fija=1,
        costo_envio=Decimal("0"),
        es_customizable=False,
        activo=True,
    )
    otro_paquete = make_paquete(
        id=uuid4(),
        nombre="Premium",
        precio=Decimal("250"),
        cantidad_fija=1,
        costo_envio=Decimal("30"),
        activo=True,
    )
    paquete_repo = MockPaqueteRepository([paquete, otro_paquete])
    pedido_repo = MockPedidoRepository()
    usuario_repo = MockUsuarioRepository()
    suscripcion_repo = MockSuscripcionRepository()
    cliente_repo = MockClienteRepository()
    sepomex_repo = MockSepomexRepository()
    health_service = HealthService([])

    pedido_service = PedidoService(pedido_repo, usuario_repo, paquete_repo)
    suscripcion_service = SuscripcionService(usuario_repo, paquete_repo, pedido_repo, suscripcion_repo, sepomex_repo)
    scheduler = SuscripcionScheduler(suscripcion_repo, pedido_repo, paquete_repo, health_service)

    app.dependency_overrides[get_usuario_repo] = lambda: usuario_repo
    app.dependency_overrides[get_paquete_repo] = lambda: paquete_repo
    app.dependency_overrides[get_pedido_repo] = lambda: pedido_repo
    app.dependency_overrides[get_suscripcion_repo] = lambda: suscripcion_repo
    app.dependency_overrides[get_cliente_repo] = lambda: cliente_repo
    app.dependency_overrides[get_pedido_service] = lambda: pedido_service
    app.dependency_overrides[get_suscripcion_service] = lambda: suscripcion_service
    app.dependency_overrides[get_suscripcion_scheduler] = lambda: scheduler

    return {
        "paquete": paquete,
        "otro_paquete": otro_paquete,
        "paquete_repo": paquete_repo,
        "pedido_repo": pedido_repo,
        "usuario_repo": usuario_repo,
        "suscripcion_repo": suscripcion_repo,
    }


class TestPaquetesAPI:
    def test_list_active(self, client, mock_repos):
        resp = client.get("/api/paquetes")
        assert resp.status_code == 200
        data = resp.json()
        names = [p["nombre"] for p in data]
        assert "Tradicional" in names
        assert "Premium" in names

    def test_get_by_id(self, client, mock_repos):
        pid = str(mock_repos["paquete"].id)
        resp = client.get(f"/api/paquetes/{pid}")
        assert resp.status_code == 200
        assert resp.json()["nombre"] == "Tradicional"

    def test_get_by_id_not_found(self, client, mock_repos):
        resp = client.get(f"/api/paquetes/{uuid4()}")
        assert resp.status_code == 404

    def test_precio_calculation(self, client, mock_repos):
        pid = str(mock_repos["paquete"].id)
        resp = client.get(f"/api/paquetes/{pid}/precio?cantidad=1")
        assert resp.status_code == 200
        assert resp.json()["total"] == "150"

    def test_invalid_uuid_returns_422(self, client, mock_repos):
        resp = client.get("/api/paquetes/not-a-uuid")
        assert resp.status_code == 422


class TestPedidosAPI:
    def test_create_order(self, client, mock_repos):
        paquete = mock_repos["paquete"]
        resp = client.post("/api/pedidos", json={
            "telefono": "9991234567",
            "nombre": "Juan",
            "paquete_id": str(paquete.id),
            "direccion": "Mérida, Yucatán",
            "codigo_postal": "97100",
            "metodo_pago": "efectivo",
            "fecha_usuario": str(date.today()),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["estatus"] == "pendiente"
        assert data["total"] == "150"

    def test_create_order_cp_fuera_yucatan_rejected(self, client, mock_repos):
        paquete = mock_repos["paquete"]
        resp = client.post("/api/pedidos", json={
            "telefono": "9991234567",
            "nombre": "Juan",
            "paquete_id": str(paquete.id),
            "direccion": "Cualquier dirección",
            "codigo_postal": "00000",
            "metodo_pago": "efectivo",
            "fecha_usuario": str(date.today()),
        })
        assert resp.status_code == 400

    def test_list_by_fecha(self, client, mock_repos):
        repo = mock_repos["pedido_repo"]
        pedido = make_pedido(fecha_entrega=date.today())
        repo._pedidos[str(pedido.id)] = pedido

        resp = client.get(f"/api/pedidos?fecha={date.today()}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_get_by_id(self, client, mock_repos):
        repo = mock_repos["pedido_repo"]
        pedido = make_pedido(fecha_entrega=date.today())
        repo._pedidos[str(pedido.id)] = pedido

        resp = client.get(f"/api/pedidos/{pedido.id}")
        assert resp.status_code == 200

    def test_update_estatus(self, client, mock_repos):
        repo = mock_repos["pedido_repo"]
        pedido = make_pedido(estatus="pendiente")
        repo._pedidos[str(pedido.id)] = pedido

        resp = client.patch(
            f"/api/pedidos/{pedido.id}/estatus",
            json={"estatus": "aceptado"},
        )
        assert resp.status_code == 200
        assert resp.json()["estatus"] == "aceptado"

    def test_update_estatus_not_found(self, client, mock_repos):
        resp = client.patch(
            f"/api/pedidos/{uuid4()}/estatus",
            json={"estatus": "aceptado"},
        )
        assert resp.status_code == 404


class TestSuscripcionesAPI:
    def test_create(self, client, mock_repos):
        paquete = mock_repos["paquete"]
        resp = client.post("/api/suscripciones", json={
            "telefono": "9991234567",
            "nombre": "Juan",
            "paquete_id": str(paquete.id),
            "direccion": "Mérida, Yucatán",
            "codigo_postal": "97100",
            "metodo_pago": "tarjeta",
            "dia_entrega": 1,
            "fecha_inicio": str(date.today()),
        })
        assert resp.status_code == 200

    def test_create_no_tarjeta_rejected(self, client, mock_repos):
        paquete = mock_repos["paquete"]
        resp = client.post("/api/suscripciones", json={
            "telefono": "9991234567",
            "nombre": "Juan",
            "paquete_id": str(paquete.id),
            "direccion": "Mérida, Yucatán",
            "codigo_postal": "97100",
            "metodo_pago": "efectivo",
            "dia_entrega": 1,
            "fecha_inicio": str(date.today()),
        })
        assert resp.status_code == 400

    def test_get_by_id(self, client, mock_repos):
        repo = mock_repos["suscripcion_repo"]
        sub = make_suscripcion()
        repo._subs[str(sub.id)] = sub

        resp = client.get(f"/api/suscripciones/{sub.id}")
        assert resp.status_code == 200

    def test_get_by_id_not_found(self, client, mock_repos):
        resp = client.get(f"/api/suscripciones/{uuid4()}")
        assert resp.status_code == 404

    def test_update_dia_entrega(self, client, mock_repos):
        repo = mock_repos["suscripcion_repo"]
        sub = make_suscripcion(dia_entrega=1)
        repo._subs[str(sub.id)] = sub

        resp = client.patch(f"/api/suscripciones/{sub.id}", json={"dia_entrega": 3})
        assert resp.status_code == 200
        assert resp.json()["dia_entrega"] == 3


class TestClientesAPI:
    def test_list_active(self, client, mock_repos):
        resp = client.get("/api/clientes")
        assert resp.status_code == 200

    def test_list_active_after_add(self, client, mock_repos):
        from tests.e2e.conftest import make_cliente
        repo = mock_repos["usuario_repo"]
        from tests.e2e.conftest import MockClienteRepository
        cli_repo = MockClienteRepository([make_cliente(nombre="Don Pepito")])
        app.dependency_overrides[get_cliente_repo] = lambda: cli_repo

        resp = client.get("/api/clientes")
        assert resp.status_code == 200
        assert any(c["nombre"] == "Don Pepito" for c in resp.json())


class TestSuscripcionScheduler:
    def test_procesar_vencidas(self, client, mock_repos):
        repo = mock_repos["suscripcion_repo"]
        sub = make_suscripcion(proxima_generacion=date.today())
        repo._subs[str(sub.id)] = sub

        resp = client.post("/api/suscripciones/procesar")
        assert resp.status_code == 200
        assert resp.json()["pedidos_generados"] >= 0
