import asyncio
import re
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.domain.models import CustomTier, Paquete
from src.main import app
from src.infrastructure.limiter import limiter


@pytest.fixture(autouse=True)
def _app_setup():
    """Override rate limiter to disable it for tests + mock DB pool + mock cache."""
    limiter.enabled = False

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = ctx_mgr
    app.state.db_pool = mock_pool

    from src.infrastructure.cache import MemoryCache
    app.state.cache = MemoryCache(default_ttl=60)

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
        assert "x-data" in resp.text
        assert "Selecciona tu paquete" in resp.text

    def test_checkout_sin_cantidad_no_marca_4(self, client):
        """Regresión: omitir cantidad no debe pre-llenar 4 cartones ($420)."""
        resp = client.get("/checkout")
        assert "cantidad: 1," in resp.text
        assert "cantidad: 4," not in resp.text

    def test_checkout_cantidad_explicita(self, client):
        resp = client.get("/checkout", params={"cantidad": "4"})
        assert "cantidad: 4," in resp.text


_CUSTOM_ID = UUID("00000000-0000-0000-0000-00000000000a")
_P1_ID = UUID("00000000-0000-0000-0000-000000000001")
_P4_ID = UUID("00000000-0000-0000-0000-000000000004")


def _seed_paquetes_real():
    """Escenario real del incidente: el paquete custom ($120/cartón) tiene un tier
    de 4+ cartones a $105 → 4 cartones = $420. Este es el escenario de la clienta."""
    custom = Paquete(
        id=_CUSTOM_ID,
        nombre="Cartón a tu medida",
        precio=Decimal("120"),
        cantidad_fija=1,
        es_customizable=True,
        precio_minimo=Decimal("80"),
        tiers=[CustomTier(min_cantidad=4, precio_unitario=Decimal("105"))],
    )
    p1 = Paquete(
        id=_P1_ID, nombre="1 Cartón", precio=Decimal("120"), cantidad_fija=1,
    )
    p4 = Paquete(
        id=_P4_ID, nombre="4 Cartones", precio=Decimal("100"), cantidad_fija=4,
    )

    async def load():
        return [custom, p1, p4]

    asyncio.run(app.state.cache.get_or_load("paquetes", loader=load, ttl=60))


class TestCheckoutRegresion:
    def _renders(self, url) -> str:
        _seed_paquetes_real()
        return TestClient(app).get(url).text

    def test_custom_sin_cantidad_es_1_carton(self):
        """Regresión raíz del incidente: el paquete "a tu medida" sin cantidad
        NO debe pre-llenar 4 cartones ($420), sino 1 ($120)."""
        html = self._renders(f"/checkout?paquete_id={_CUSTOM_ID}")
        assert "cantidad: 1," in html
        # el tier 4→105 viaja al cliente para que el precio JS coincida con el server
        assert "tiers" in html
        assert "105" in html

    def test_custom_con_cantidad_4_mantiene_4(self):
        html = self._renders(f"/checkout?paquete_id={_CUSTOM_ID}&cantidad=4")
        assert "cantidad: 4," in html

    def test_fijo_4_cartones_sin_cantidad_fuerza_4(self):
        html = self._renders(f"/checkout?paquete_id={_P4_ID}")
        assert "cantidad: 4," in html

    def test_fijo_1_carton_ignora_cantidad_erronea(self):
        """Aunque llegue cantidad=4 por URL, el paquete fijo "1 Cartón" debe
        facturarse como 1 cartón ($120), no 4."""
        html = self._renders(f"/checkout?paquete_id={_P1_ID}&cantidad=4")
        assert "cantidad: 1," in html


class TestModalAvisoPrecio:
    """Contrato A+B del modal de confirmación: el precio que muestra el aviso
    (GET /api/paquetes/{id}/precio) es EXACTAMENTE el que facturará el server.
    Garantiza que el total visible == total real (sin drift JS)."""

    def _precio(self, paquete_id: str, cantidad: int = 1) -> dict:
        from src.api.dependencies import get_paquete_repo
        from tests.e2e.conftest import MockPaqueteRepository

        custom = Paquete(
            id=_CUSTOM_ID, nombre="Cartón a tu medida", precio=Decimal("120"),
            cantidad_fija=1, es_customizable=True, precio_minimo=Decimal("80"),
            tiers=[CustomTier(min_cantidad=4, precio_unitario=Decimal("105"))],
        )
        p1 = Paquete(id=_P1_ID, nombre="1 Cartón", precio=Decimal("120"), cantidad_fija=1)
        p4 = Paquete(id=_P4_ID, nombre="4 Cartones", precio=Decimal("100"), cantidad_fija=4)
        app.dependency_overrides[get_paquete_repo] = lambda: MockPaqueteRepository([custom, p1, p4])
        try:
            return TestClient(app).get(
                f"/api/paquetes/{paquete_id}/precio", params={"cantidad": cantidad}
            ).json()
        finally:
            app.dependency_overrides.pop(get_paquete_repo, None)

    def _es_number(self, v: str) -> float:
        return float(v)

    def test_custom_1_carton_es_120(self):
        """Incidente raíz: 1 cartón a tu medida == $120 (NUNCA $420 por error de default)."""
        d = self._precio(_CUSTOM_ID, cantidad=1)
        assert self._es_number(d["total"]) == 120
        assert self._es_number(d["precio_unitario"]) == 120
        assert self._es_number(d["envio"]) == 0

    def test_custom_4_cartones_es_420(self):
        """El MISMO paquete con 4 cartones __eligen__ el tier 4→$105 ⇒ $420. Este es
        el escenario donde la clienta sí pagó $420; el aviso debe mostrarlo."""
        d = self._precio(_CUSTOM_ID, cantidad=4)
        assert self._es_number(d["precio_unitario"]) == 105
        assert self._es_number(d["total"]) == 420

    def test_fijo_un_carton_ignora_cantidad_url(self):
        """Paquete fijo '1 Cartón' rehúsa cantidad=4: total queda $120, no $420."""
        d = self._precio(_P1_ID, cantidad=4)
        assert self._es_number(d["total"]) == 120
        assert self._es_number(d["precio_unitario"]) == 120

    def test_fijo_4_cartones_fuerza_cantidad_fija(self):
        """Paquete fijo '4 Cartones' fuerza cantidad_fija=4 aunque llegue cantidad=1."""
        d = self._precio(_P4_ID, cantidad=1)
        assert self._es_number(d["total"]) == 400
        assert self._es_number(d["precio_unitario"]) == 100

    def test_subtotal_mas_envio_igual_total(self):
        """Invariante del contrato: unitario*cantidad + envio == total (lo que firma el modal)."""
        for pid, c in ((_CUSTOM_ID, 3), (_P1_ID, 1), (_P4_ID, 4)):
            d = self._precio(pid, cantidad=c)
            esperado = self._es_number(d["precio_unitario"]) * c + self._es_number(d["envio"])
            assert abs(esperado - self._es_number(d["total"])) < 0.01

    def test_checkout_contiene_modal_aviso(self):
        """El HTML de /checkout incluye el modal de confirmación con 'Volver a ajustar'."""
        _seed_paquetes_real()
        html = TestClient(app).get("/checkout").text
        assert "avisoAbierto" in html
        assert "Volver a ajustar" in html
        assert "abrirAviso" in html
        assert "confirmarAviso" in html


class TestCheckoutSubmit:
    def test_post_checkout_missing_fields_returns_422(self, client):
        resp = client.post("/checkout", data={})
        assert resp.status_code == 422

    def test_post_checkout_valid_submission(self, client):
        get_resp = client.get("/checkout")
        m = re.search(r'name="csrf_token" value="([^"]+)"', get_resp.text)
        assert m is not None, "CSRF token not found in checkout form"
        resp = client.post("/checkout", data={
            "csrf_token": m.group(1),
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


class TestAnuncios:
    def test_anuncio_existe_renderiza_200(self, client):
        resp = client.get("/anuncios/fresco_vs_30dias")
        assert resp.status_code == 200

    def test_anuncio_contiene_og_tags(self, client):
        html = client.get("/anuncios/fresco_vs_30dias").text
        assert "¿Sabes qué pierde un huevo en 30 días?" in html
        assert 'property="og:title"' in html
        assert 'property="og:image"' in html
        assert "static/anuncios/fresco_vs_30dias.png" in html

    def test_anuncio_sin_whatsapp_float(self, client):
        html = client.get("/anuncios/fresco_vs_30dias").text
        assert "Envíanos un WhatsApp" not in html

    def test_anuncio_contiene_tabla_comparativa(self, client):
        html = client.get("/anuncios/fresco_vs_30dias").text
        assert "Recién puesto" in html
        assert "Hace 30 días" in html
        assert "Vitamina A" in html
        assert "wa.me/5219995050854" in html

    def test_anuncio_invalido_404(self, client):
        assert client.get("/anuncios/no-existe").status_code == 404

    def test_api_anuncios_lista_slugs(self, client):
        resp = client.get("/api/anuncios")
        assert resp.status_code == 200
        slugs = [a["slug"] for a in resp.json()["anuncios"]]
        assert "fresco_vs_30dias" in slugs
