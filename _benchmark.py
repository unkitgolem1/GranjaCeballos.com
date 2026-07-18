"""
Benchmark comparativo Uvicorn vs Granian.
Mide: throughput (req/s), latencia p50/p95/p99/p99.9, tasa de error.
"""
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx

ENDPOINTS = [
    ("GET /", "GET", "http://127.0.0.1:8000/", None),
    ("GET /api/paquetes", "GET", "http://127.0.0.1:8000/api/paquetes", None),
    (
        "POST /checkout",
        "POST",
        "http://127.0.0.1:8000/checkout",
        {
            "nombre": "Test User",
            "telefono": "9991234567",
            "paquete_id": "1",
            "direccion": "Mérida, Yucatán, México",
            "cantidad": "1",
            "metodo_pago": "efectivo",
            "dia_entrega": "1",
            "es_suscripcion": "0",
            "fecha_entrega": "2026-07-20",
        },
    ),
]

LEVELS = [10, 20, 40, 80]
DURATION = 15


@dataclass
class Result:
    concurrency: int
    endpoint: str
    server: str
    total: int = 0
    errors: int = 0
    ok: int = 0
    latencies: list = field(default_factory=list)

    @property
    def rps(self) -> float:
        return self.ok / DURATION

    @property
    def error_pct(self) -> float:
        return (self.errors / max(self.total, 1)) * 100

    def p(self, n: int) -> float:
        if not self.latencies:
            return 0.0
        return sorted(self.latencies)[int(len(self.latencies) * n / 100)]

    def csv_line(self) -> str:
        return (
            f"{self.server},{self.endpoint},{self.concurrency},"
            f"{self.rps:.1f},{self.ok},{self.errors},{self.error_pct:.1f},"
            f"{self.p(50):.1f},{self.p(95):.1f},{self.p(99):.1f},{self.p(99.9):.1f}"
        )

    def header(self) -> str:
        return "server,endpoint,concurrency,rps,ok,errors,error%,p50,p95,p99,p99.9"

    def report(self) -> str:
        return (
            f"  RPS: {self.rps:.0f}  OK: {self.ok}  "
            f"Errors: {self.errors} ({self.error_pct:.1f}%)  "
            f"p50={self.p(50):.1f}  p95={self.p(95):.1f}  "
            f"p99={self.p(99):.1f}  p99.9={self.p(99.9):.1f} ms"
        )


async def _worker(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    data: dict | None,
    latencies: list,
    stop: asyncio.Event,
):
    while not stop.is_set():
        try:
            start = time.perf_counter()
            if method == "GET":
                r = await client.get(url)
            else:
                r = await client.post(url, data=data)
            elapsed = (time.perf_counter() - start) * 1000
            if r.status_code >= 400:
                latencies.append(("err", r.status_code))
            else:
                latencies.append(("ok", elapsed))
        except Exception as e:
            latencies.append(("exc", str(e)))


def flush_log(client: httpx.AsyncClient, latencies: list):
    ok_count = sum(1 for v in latencies if isinstance(v, tuple) and v[0] == "ok")
    err_count = sum(1 for v in latencies if isinstance(v, tuple) and v[0] == "err")
    exc_count = sum(1 for v in latencies if isinstance(v, tuple) and v[0] == "exc")
    ok_vals = [v[1] for v in latencies if isinstance(v, tuple) and v[0] == "ok"]
    return ok_count, err_count, exc_count, ok_vals


async def run_bench(server: str, concurrency: int, ep_name: str, method: str, url: str, data: dict | None) -> Result:
    latencies = []
    stop = asyncio.Event()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=5.0),
        limits=httpx.Limits(max_connections=concurrency * 2),
    ) as client:
        tasks = [
            asyncio.create_task(_worker(client, method, url, data, latencies, stop))
            for _ in range(concurrency)
        ]
        await asyncio.sleep(DURATION)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    ok_count, err_count, exc_count, ok_vals = flush_log(client, latencies)
    total = ok_count + err_count + exc_count
    return Result(
        concurrency=concurrency, endpoint=ep_name, server=server,
        total=total, errors=err_count + exc_count, ok=ok_count,
        latencies=ok_vals,
    )


async def main():
    server = sys.argv[1] if len(sys.argv) > 1 else "uvicorn"

    print(f"BENCHMARK: {server.upper()}")
    header_shown = False

    for ep_name, method, url, data in ENDPOINTS:
        for c in LEVELS:
            result = await run_bench(server, c, ep_name, method, url, data)
            if not header_shown:
                print(result.header())
                header_shown = True
            print(result.csv_line())
        # blank line between endpoints
        print()


if __name__ == "__main__":
    asyncio.run(main())
