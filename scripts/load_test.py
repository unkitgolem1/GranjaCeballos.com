"""
Load test — 100 usuarios concurrentes simulando el flujo completo de checkout.

Uso:
    uv run python scripts/load_test.py

Requiere que el servidor esté corriendo localmente (por defecto http://127.0.0.1:8000).
"""

import asyncio
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx

BASE_URL = os.environ.get("LOAD_TEST_URL", "http://127.0.0.1:8000")
CONCURRENT_USERS = 100
CONCURRENT_LIMIT = 25  # semaphore
REQUEST_TIMEOUT = 30.0


@dataclass
class Result:
    success: bool = False
    status_code: int = 0
    elapsed_ms: float = 0.0
    error: str = ""
    step: str = ""
    telefono: str = ""


@dataclass
class Stats:
    total: int = 0
    ok: int = 0
    fail: int = 0
    latencies: list[float] = field(default_factory=list)
    errors: dict[str, int] = field(default_factory=dict)


stats = Stats()
_stats_lock = asyncio.Lock()


async def record(r: Result):
    async with _stats_lock:
        stats.total += 1
        if r.success:
            stats.ok += 1
        else:
            stats.fail += 1
            key = f"{r.status_code} {r.step} {r.error[:50]}"
            stats.errors[key] = stats.errors.get(key, 0) + 1
        if r.elapsed_ms > 0:
            stats.latencies.append(r.elapsed_ms)


async def simulate_user(sem: asyncio.Semaphore, uid: int):
    async with sem:
        telefono = f"999{uid:07d}"
        name = f"LoadTest {uid}"
        paquete_id = ""
        result = Result(telefono=telefono)

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
            # 1. GET welcome → obtiene paquetes
            t0 = time.monotonic()
            try:
                r = await client.get(f"{BASE_URL}/partial/welcome")
                result.elapsed_ms = (time.monotonic() - t0) * 1000
                if r.status_code != 200:
                    result.step = "GET /partial/welcome"
                    result.status_code = r.status_code
                    await record(result)
                    return
                import re
                m = re.search(r'paquete_id=([a-f0-9-]+)', r.text)
                if m:
                    paquete_id = m.group(1)
                else:
                    result.step = "parse paquete_id"
                    result.error = "no paquete_id in welcome"
                    await record(result)
                    return
            except Exception as e:
                result.step = "GET /partial/welcome"
                result.error = str(e)
                await record(result)
                return

            # 2. Escoge paquete: 70% customizable, 30% fijo
            es_custom = bool(random.random() < 0.7 and paquete_id)
            cantidad = random.randint(1, 5) if es_custom else 1

            # 3. GET checkout con paquete
            t0 = time.monotonic()
            try:
                r = await client.get(
                    f"{BASE_URL}/checkout",
                    params={"paquete_id": paquete_id, "cantidad": cantidad},
                )
                result.elapsed_ms = (time.monotonic() - t0) * 1000
                if r.status_code != 200:
                    result.step = "GET /checkout"
                    result.status_code = r.status_code
                    await record(result)
                    return
            except Exception as e:
                result.step = "GET /checkout"
                result.error = str(e)
                await record(result)
                return

            # 4. POST checkout
            t0 = time.monotonic()
            try:
                r = await client.post(
                    f"{BASE_URL}/checkout",
                    data={
                        "nombre": name,
                        "telefono": telefono,
                        "paquete_id": paquete_id,
                        "codigo_postal": "97000",
                        "direccion": f"Calle {uid} #123 x 56 y 58, Centro",
                        "colonia": "Centro",
                        "ciudad": "Mérida",
                        "estado": "Yucatán",
                        "cantidad": str(cantidad),
                        "metodo_pago": "efectivo",
                        "es_suscripcion": "false",
                        "dia_entrega": str(random.randint(1, 7)),
                        "fecha_entrega": "",
                    },
                )
                result.elapsed_ms = (time.monotonic() - t0) * 1000
                result.status_code = r.status_code
                result.step = "POST /checkout"
                result.success = r.status_code == 200
            except Exception as e:
                result.elapsed_ms = (time.monotonic() - t0) * 1000
                result.error = str(e)
                result.step = "POST /checkout"

        await record(result)


def print_stats():
    print(f"\n{'='*60}")
    print(f"  Load Test — {CONCURRENT_USERS} usuarios, {CONCURRENT_LIMIT} concurrentes")
    print(f"{'='*60}")
    print(f"  Total:    {stats.total}")
    print(f"  ✅ Éxito:  {stats.ok}")
    print(f"  ❌ Falla:  {stats.fail}")
    print()

    if stats.latencies:
        lat = sorted(stats.latencies)
        avg = statistics.mean(lat)
        p50 = lat[len(lat) // 2]
        p95 = lat[int(len(lat) * 0.95)]
        p99 = lat[int(len(lat) * 0.99)]
        print(f"  Latencia POST /checkout (ms):")
        print(f"    Promedio: {avg:.0f}")
        print(f"    P50:      {p50:.0f}")
        print(f"    P95:      {p95:.0f}")
        print(f"    P99:      {p99:.0f}")
        print()

    if stats.errors:
        print(f"  Errores:")
        for key, count in sorted(stats.errors.items(), key=lambda x: -x[1]):
            print(f"    [{count:3d}x] {key}")
        print()

    if stats.fail == 0:
        print(f"  🎉 Sin errores — listo para producción!")
    else:
        print(f"  ⚠️  Revisa los errores antes de desplegar.")
    print()


async def main():
    print(f" Load test: {CONCURRENT_USERS} usuarios a {BASE_URL}")
    print(f" Concurrentes: {CONCURRENT_LIMIT}")
    print(f" Timeout: {REQUEST_TIMEOUT}s")
    print()

    sem = asyncio.Semaphore(CONCURRENT_LIMIT)
    t0 = time.monotonic()

    tasks = [asyncio.create_task(simulate_user(sem, i)) for i in range(1, CONCURRENT_USERS + 1)]

    # progress bar
    for i, task in enumerate(asyncio.as_completed(tasks), 1):
        await task
        pct = i / CONCURRENT_USERS * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        sys.stdout.write(f"\r  [{bar}] {i}/{CONCURRENT_USERS} ({pct:.0f}%)")
        sys.stdout.flush()

    elapsed = time.monotonic() - t0
    print(f"\n\n  Duración total: {elapsed:.1f}s")
    print(f"  Throughput:     {stats.total / elapsed:.1f} req/s")

    print_stats()


if __name__ == "__main__":
    asyncio.run(main())
