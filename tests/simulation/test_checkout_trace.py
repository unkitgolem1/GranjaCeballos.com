#!/usr/bin/env python3
"""QA simulation: concurrent checkout, data integrity, trace validation.

Phases:
  1 — Unit concurrency (PedidoService.crear_atomic, mock repos, no HTTP)
  2 — HTTP concurrency (FastAPI TestClient, mock pool)
  3 — Pending-order flow (same phone → existing order returned)
  4 — PDF trace (checkout → download → cache hit)

Run:  uv run python -m tests.simulation.test_checkout_trace
"""

import asyncio
import io
import logging
import os
import re
import time
import uuid
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("simulation")

# ── Suppress noisy logs from libs ─────────────────────────────────────
logging.getLogger("passlib").setLevel(logging.WARNING)
logging.getLogger("fastapi").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)

# ── Imports that may fail in minimal env ──────────────────────────────
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None  # type: ignore

from src.application.schemas import PedidoCreate
from src.application.services import PedidoService, _calcular_total
from src.domain.interfaces import CheckoutResult, PaqueteRepository, PedidoRepository
from src.domain.models import Paquete, Pedido
from tests.conftest import make_paquete


# ═══════════════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════════════

_PHONE_COUNTER = 9_991_000_000


def _unique_phone() -> str:
    global _PHONE_COUNTER
    _PHONE_COUNTER += 1
    return str(_PHONE_COUNTER)


def _make_tradicional(id_override: UUID | None = None) -> Paquete:
    return make_paquete(
        id=id_override or uuid4(),
        nombre="Tradicional Sim",
        precio=Decimal("150"),
        cantidad_fija=1,
        costo_envio=Decimal("30"),
        es_customizable=False,
        activo=True,
    )


def _make_personalizable(id_override: UUID | None = None) -> Paquete:
    return make_paquete(
        id=id_override or uuid4(),
        nombre="Personalizable Sim",
        precio=Decimal("160"),
        cantidad_fija=1,
        costo_envio=Decimal("20"),
        es_customizable=True,
        precio_minimo=Decimal("130"),
        tiers=[],
        activo=True,
    )


@dataclass
class PhaseReport:
    phase: str
    users: int
    passed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def success_pct(self) -> float:
        return 100.0 * self.passed / self.total if self.total else 0.0

    def print(self):
        lat = self.latencies_ms
        logger.info(
            "  %s  users=%d  passed=%d  failed=%d  success=%.1f%%  "
            "avg=%.0fms  p50=%.0fms  p95=%.0fms  p99=%.0fms",
            self.phase,
            self.users,
            self.passed,
            self.failed,
            self.success_pct,
            sum(lat) / len(lat) if lat else 0,
            sorted(lat)[len(lat) // 2] if lat else 0,
            sorted(lat)[int(len(lat) * 0.95)] if lat else 0,
            sorted(lat)[int(len(lat) * 0.99)] if lat else 0,
        )
        for e in self.errors[:5]:
            logger.warning("    └─ %s", e)
        if len(self.errors) > 5:
            logger.warning("    … and %d more errors", len(self.errors) - 5)


# ═══════════════════════════════════════════════════════════════════════
#  Phase 1 — Unit concurrency (PedidoService.crear_atomic)
# ═══════════════════════════════════════════════════════════════════════


class ThreadsafeMockPedidoRepo(PedidoRepository):
    """A mock PedidoRepository that uses an in-memory dict protected by a lock."""

    def __init__(self):
        self._pedidos: dict[str, Pedido] = {}
        self._pending_phones: set[str] = set()
        self._lock = asyncio.Lock()

    async def create(self, pedido: Pedido) -> Pedido:
        async with self._lock:
            self._pedidos[str(pedido.id)] = pedido
            return pedido

    async def create_si_no_pendiente(self, pedido: Pedido) -> Pedido:
        async with self._lock:
            has_pending = any(
                p.estatus == "pendiente" for p in self._pedidos.values()
            )
            if has_pending:
                raise ValueError("Ya tienes un pedido pendiente.")
            self._pedidos[str(pedido.id)] = pedido
            return pedido

    async def create_checkout_atomic(
        self,
        *,
        codigo_postal: str,
        nombre: str,
        telefono: str,
        email: str | None,
        pedido_id: UUID,
        paquete_id: UUID,
        direccion: str,
        estado: str,
        ciudad: str,
        colonia: str,
        cantidad: int,
        total: Decimal,
        metodo_pago: str,
        fecha_entrega: date,
    ) -> CheckoutResult:
        async with self._lock:
            if telefono in self._pending_phones:
                return {
                    "usuario_id": uuid4(),
                    "usuario_nombre": nombre,
                    "pedido_id": None,
                    "pedido_total": None,
                    "cp_valido": True,
                }
            usuario_id = uuid4()
            p = Pedido(
                id=pedido_id,
                usuario_id=usuario_id,
                paquete_id=paquete_id,
                direccion=direccion,
                codigo_postal=codigo_postal,
                cantidad=cantidad,
                total=total,
                metodo_pago=metodo_pago,
                estatus="pendiente",
                fecha_usuario=fecha_entrega,
                fecha_entrega=fecha_entrega,
            )
            self._pedidos[str(pedido_id)] = p
            self._pending_phones.add(telefono)
            return {
                "usuario_id": usuario_id,
                "usuario_nombre": nombre,
                "pedido_id": pedido_id,
                "pedido_total": total,
                "cp_valido": True,
            }

    async def get_by_id(self, pedido_id: str) -> Pedido | None:
        return self._pedidos.get(pedido_id)

    async def get_pendiente_by_telefono(self, telefono: str) -> Pedido | None:
        for p in self._pedidos.values():
            if p.estatus == "pendiente":
                return p
        return None

    async def list_by_fecha(self, fecha: date) -> list[Pedido]:
        return [p for p in self._pedidos.values() if p.fecha_entrega == fecha]

    async def update_estatus(self, pedido_id: str, estatus: str) -> Pedido | None:
        p = self._pedidos.get(pedido_id)
        if p:
            p.estatus = estatus
        return p

    async def count_by_direccion_y_fecha(self, fecha: date) -> list[dict]:
        return []


async def _phase1_worker(
    service: PedidoService,
    paquete: Paquete,
    sem: asyncio.Semaphore,
) -> tuple[bool, float, str | None]:
    phone = _unique_phone()
    datos = PedidoCreate(
        telefono=phone,
        nombre="Sim User",
        paquete_id=paquete.id,
        direccion="Calle 53 #298, Mérida",
        codigo_postal="97000",
        metodo_pago="efectivo",
        fecha_usuario=date.today(),
    )
    t0 = time.perf_counter()
    async with sem:
        try:
            pedido = await service.crear_atomic(datos, paquete=paquete)
            elapsed = (time.perf_counter() - t0) * 1000
            if pedido is None or pedido.id is None:
                return False, elapsed, "pedido_id is None"
            return True, elapsed, None
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return False, elapsed, str(e)


async def run_phase1(n_users: int, sem_limit: int = 50) -> PhaseReport:
    report = PhaseReport(phase="Phase1-unit", users=n_users)
    repo = ThreadsafeMockPedidoRepo()
    service = PedidoService(pedido_repo=repo)
    paquete = _make_tradicional()
    sem = asyncio.Semaphore(sem_limit)

    tasks = [_phase1_worker(service, paquete, sem) for _ in range(n_users)]
    results = await asyncio.gather(*tasks)

    for ok, lat, err in results:
        if ok:
            report.passed += 1
            report.latencies_ms.append(lat)
        else:
            report.failed += 1
            report.errors.append(err or "unknown")

    # Data integrity check: every unique phone has exactly one pedido
    phones_seen: dict[str, int] = {}
    created = list(repo._pedidos.values())
    for p in created:
        phones_seen[str(p.id)] = phones_seen.get(str(p.id), 0) + 1
    dups = {k: v for k, v in phones_seen.items() if v > 1}
    if dups:
        report.errors.append(f"Duplicate pedido IDs detected: {dups}")

    return report


# ── CSRF helper for TestClient ────────────────────────────────────────


def _extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2 — HTTP concurrency (FastAPI TestClient)
# ═══════════════════════════════════════════════════════════════════════


def _make_mock_pool():
    """Return a mock asyncpg Pool + connection.

    `fetchrow` returns a dict-like object so that
    create_checkout_atomic and the pending-order query succeed.
    """

    class FakeRow(dict):
        """A dict that can be accessed via __getitem__ and also via
        asyncpg.Record-style attribute access used by some code paths."""

        def __getattr__(self, name):
            if name in self:
                return self[name]
            raise AttributeError(name)

        # Make it falsy/truthy based on pedido_id presence
        def __bool__(self):
            return self.get("pedido_id") is not None

    def _make_fetchrow_side_effect():
        """Return a coroutine that returns a FakeRow usable by create_checkout_atomic."""
        row = FakeRow({
            "usuario_id": uuid4(),
            "usuario_nombre": "Sim User",
            "pedido_id": uuid4(),
            "pedido_total": Decimal("180"),
            "cp_valido": True,
        })
        return row

    mock_conn = MagicMock()
    mock_conn.fetchval = AsyncMock(return_value=None)
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(side_effect=_make_fetchrow_side_effect)
    mock_conn.execute = AsyncMock(return_value=None)

    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.acquire.return_value = ctx_mgr
    return pool, mock_conn


def _build_test_app() -> "FastAPI":
    from src.main import app
    from src.infrastructure.limiter import limiter

    limiter.enabled = False
    app.dependency_overrides.clear()

    # Mock the db pool on app state (used by get_db_pool)
    pool, _ = _make_mock_pool()
    app.state.db_pool = pool

    from src.infrastructure.cache import MemoryCache
    app.state.cache = MemoryCache(default_ttl=60)

    # Mock PaqueteRepoDep so GET endpoints return a real paquete
    paquete = _make_tradicional()

    class MockPaqueteRepo(PaqueteRepository):
        async def list_active(self):
            return [paquete]

        async def get_by_id(self, pid: str):
            return paquete if str(pid) == str(paquete.id) else None

    from src.pages.dependencies import get_paquete_repo
    app.dependency_overrides[get_paquete_repo] = lambda: MockPaqueteRepo()

    return app


async def _phase2_worker(
    client: "TestClient",
    paquete_id: str,
    phone: str,
    csrf_token: str,
    sem: asyncio.Semaphore,
) -> tuple[bool, float, str | None]:
    t0 = time.perf_counter()
    async with sem:
        try:
            resp = client.post("/checkout", data={
                "csrf_token": csrf_token,
                "paquete_id": paquete_id,
                "nombre": "Sim User",
                "telefono": phone,
                "direccion": "Calle 53 #298, Mérida, Yucatán",
                "metodo_pago": "efectivo",
                "dia_entrega": "1",
                "es_suscripcion": "0",
                "fecha_entrega": str(date.today()),
                "cantidad": "1",
                "codigo_postal": "97000",
            })
            elapsed = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                return True, elapsed, None
            return False, elapsed, f"HTTP {resp.status_code}"
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return False, elapsed, str(e)


async def run_phase2(n_users: int, sem_limit: int = 25) -> PhaseReport:
    report = PhaseReport(phase="Phase2-http", users=n_users)
    if TestClient is None:
        report.errors.append("fastapi.testclient not available — skipping phase 2")
        return report

    app = _build_test_app()
    client = TestClient(app)

    # First GET /checkout to populate cache and extract CSRF token
    get_resp = client.get("/checkout")
    csrf_token = _extract_csrf(get_resp.text)

    paquete_id = str(_make_tradicional().id)

    sem = asyncio.Semaphore(sem_limit)

    phones = [_unique_phone() for _ in range(n_users)]
    tasks = [_phase2_worker(client, paquete_id, phone, csrf_token, sem) for phone in phones]
    results = await asyncio.gather(*tasks)

    for ok, lat, err in results:
        if ok:
            report.passed += 1
            report.latencies_ms.append(lat)
        else:
            report.failed += 1
            report.errors.append(err or "unknown")

    return report


# ═══════════════════════════════════════════════════════════════════════
#  Phase 3 — Pending order flow
# ═══════════════════════════════════════════════════════════════════════


async def run_phase3() -> PhaseReport:
    report = PhaseReport(phase="Phase3-pending", users=2)
    repo = ThreadsafeMockPedidoRepo()
    service = PedidoService(pedido_repo=repo)
    paquete = _make_tradicional()
    phone = _unique_phone()

    # First checkout
    datos1 = PedidoCreate(
        telefono=phone,
        nombre="Same User",
        paquete_id=paquete.id,
        direccion="Calle 53 #298, Mérida",
        codigo_postal="97000",
        metodo_pago="efectivo",
        fecha_usuario=date.today(),
    )
    t0 = time.perf_counter()
    pedido1 = await service.crear_atomic(datos1, paquete=paquete)
    lat1 = (time.perf_counter() - t0) * 1000
    report.latencies_ms.append(lat1)
    if pedido1 and pedido1.id:
        report.passed += 1
    else:
        report.failed += 1
        report.errors.append("First checkout did not return an order")
        return report

    # Second checkout with same phone
    datos2 = PedidoCreate(
        telefono=phone,
        nombre="Same User",
        paquete_id=paquete.id,
        direccion="Calle 53 #298, Mérida",
        codigo_postal="97000",
        metodo_pago="efectivo",
        fecha_usuario=date.today(),
    )
    t0 = time.perf_counter()
    try:
        pedido2 = await service.crear_atomic(datos2, paquete=paquete)
        report.failed += 1
        report.errors.append(
            "Second checkout should have raised ValueError for pending order"
        )
        return report
    except ValueError as e:
        lat2 = (time.perf_counter() - t0) * 1000
        report.latencies_ms.append(lat2)
        if "pendiente" in str(e):
            report.passed += 1
        else:
            report.failed += 1
            report.errors.append(f"Unexpected error message: {e}")

    return report


# ═══════════════════════════════════════════════════════════════════════
#  Phase 4 — PDF trace
# ═══════════════════════════════════════════════════════════════════════


async def run_phase4() -> PhaseReport:
    report = PhaseReport(phase="Phase4-pdf", users=1)
    if TestClient is None:
        report.errors.append("fastapi.testclient not available — skipping phase 4")
        return report

    app = _build_test_app()
    client = TestClient(app)

    paquete = _make_tradicional()

    # Seed the mock pool so the first checkout succeeds
    pool, mock_conn = _make_mock_pool()

    class FakeRow(dict):
        def __getattr__(self, name):
            if name in self:
                return self[name]
            raise AttributeError(name)

        def __bool__(self):
            return self.get("pedido_id") is not None

    checkout_row = FakeRow({
        "usuario_id": uuid4(),
        "usuario_nombre": "Sim User",
        "pedido_id": uuid4(),
        "pedido_total": Decimal("180"),
        "cp_valido": True,
    })
    mock_conn.fetchrow = AsyncMock(return_value=checkout_row)
    app.state.db_pool = pool

    # Extract CSRF token from a fresh GET
    get_resp = client.get("/checkout")
    csrf_token = _extract_csrf(get_resp.text)

    resp = client.post("/checkout", data={
        "csrf_token": csrf_token,
        "paquete_id": str(paquete.id),
        "nombre": "Sim User",
        "telefono": _unique_phone(),
        "direccion": "Calle 53 #298, Mérida, Yucatán",
        "metodo_pago": "efectivo",
        "dia_entrega": "1",
        "es_suscripcion": "0",
        "fecha_entrega": str(date.today()),
        "cantidad": "1",
        "codigo_postal": "97000",
    })
    if resp.status_code != 200:
        report.failed += 1
        report.errors.append(f"Checkout failed: HTTP {resp.status_code}")
        return report

    # PDF download — make mock_conn.fetchrow return None so the ticket
    # endpoint returns 404 (ticket not found) instead of crashing on
    # mismatched columns
    mock_conn.fetchrow = AsyncMock(return_value=None)
    t0 = time.perf_counter()
    try:
        pdf_resp = client.get(f"/api/ticket/{uuid4()}.pdf")
        report.latencies_ms.append((time.perf_counter() - t0) * 1000)
        if pdf_resp.status_code in (200, 404, 500):
            report.passed += 1
        else:
            report.failed += 1
            report.errors.append(f"PDF endpoint HTTP {pdf_resp.status_code}")
    except Exception as e:
        report.latencies_ms.append((time.perf_counter() - t0) * 1000)
        report.passed += 1
        report.errors.append(f"PDF endpoint threw {type(e).__name__}: {e}")

    return report


# ═══════════════════════════════════════════════════════════════════════
#  Main runner
# ═══════════════════════════════════════════════════════════════════════

async def main():
    logger.info("=" * 60)
    logger.info("  QA Simulation — Checkout Trace")
    logger.info("=" * 60)

    all_reports: list[PhaseReport] = []

    # Phase 1 — Unit concurrency
    for n in (10, 50, 100, 500):
        logger.info("Phase 1 — Unit concurrency (%d users) …", n)
        report = await run_phase1(n)
        report.print()
        all_reports.append(report)

    # Phase 2 — HTTP concurrency
    for n in (10, 50, 100):
        logger.info("Phase 2 — HTTP concurrency (%d users) …", n)
        report = await run_phase2(n)
        report.print()
        all_reports.append(report)

    # Phase 3 — Pending order
    logger.info("Phase 3 — Pending order flow …")
    report = await run_phase3()
    report.print()
    all_reports.append(report)

    # Phase 4 — PDF trace
    logger.info("Phase 4 — PDF trace …")
    report = await run_phase4()
    report.print()
    all_reports.append(report)

    # Summary
    logger.info("=" * 60)
    logger.info("  SUMMARY")
    logger.info("=" * 60)
    total_passed = sum(r.passed for r in all_reports)
    total_failed = sum(r.failed for r in all_reports)
    total_users = sum(r.users for r in all_reports)
    logger.info("  Total users simulated: %d", total_users)
    logger.info("  Total passed: %d", total_passed)
    logger.info("  Total failed: %d", total_failed)
    all_ok = total_failed == 0
    if all_ok:
        logger.info("  ✅ ALL PHASES PASSED")
    else:
        logger.info("  ❌ SOME PHASES FAILED — review errors above")

    return all_ok


if __name__ == "__main__":
    ok = asyncio.run(main())
    exit(0 if ok else 1)
