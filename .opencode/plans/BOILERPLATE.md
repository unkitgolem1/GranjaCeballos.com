# Boilerplate de una Plataforma Python Concurrente-por-Defecto

> Extraído de GranjaCeballos.com — un monolito mantenible con clean architecture,
> health checks, lifespan, 0 race conditions, y pruebas de 100/500/1000 usuarios.

---

## 1. Manifiesto del Platform Engineer

- **Concurrente por defecto** — todo es `async def`. No hay código síncrono en hot path.
- **El framework maneja el event loop** — ni `if __name__ == "__main__"` ni `asyncio.run()`.
  Uvicorn/Granian corren el loop; `lifespan` es el hook de init/shutdown.
- **Clean Architecture en capas**:
  ```
  Domain (models + interfaces) → Application (services + schemas)
      → Infrastructure (repos + cache + db) → Interface (routers + deps)
  ```
- **Monolito mantenible** — módulos cohesivos, bounded contexts (logística separada
  del core), sin microservicios prematuros. 100 usuarios/min es baseline; la misma
  estructura aguanta 1000+.
- **Inyección de dependencias explícita** — FastAPI `Depends` + `Annotated` type aliases.
  Sin magia global, sin service locators.
- **Cada capa se prueba de forma aislada** — unit tests sin I/O, integration con mock
  pool, e2e con FakeRecord, stress sin 500s permitidos.

---

## 2. El `main.py` — La Entrada Correcta

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──────────────────────────────────────────────
    if os.getenv("DISABLE_ACCESS_LOG", "0") == "1":
        logging.getLogger("uvicorn.access").disabled = True

    if ASYNC_DEBUG:
        loop = asyncio.get_running_loop()
        loop.slow_callback_duration = 0.05
        loop.set_exception_handler(_async_debug_hook)

    dsn = os.environ["DATABASE_URL"]
    pool = await create_pool(dsn)
    app.state.db_pool = pool
    app.state.cache = MemoryCache(default_ttl=60)
    yield
    # ── shutdown ─────────────────────────────────────────────
    await pool.close()


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Error interno del servidor"}, 500)
    return HTMLResponse("Error interno del servidor", 500)

# ── Middleware stack (orden importa) ─────────────────────────
app.add_middleware(CORSMiddleware, allow_origins=[], ...)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LatencyMiddleware)       # mide todo, log JSON
app.add_middleware(SlowAPIMiddleware)        # rate limiting
app.add_middleware(SessionMiddleware, ...)   # sesiones para CSRF

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router)
app.include_router(pages_router)
app.include_router(logistic_router)
```

**Reglas del entry point:**
1. `load_dotenv()` al inicio del módulo (no esperar a lifespan).
2. Config desde env vars, con defaults seguros (`os.urandom(32).hex()` para SECRET_KEY).
3. Logger configurado manualmente para controlar formato (JSON structured logging).
4. `app.state` para singletons: pool, cache, limiter.
5. Sin factory function — el `app` es módulo-level, creado una sola vez al importar.
6. El serverless (Vercel) importa `from src.main import app`.

---

## 3. Async Debug Hook — Atrapa Bloqueos

```python
async def _async_debug_hook(loop: asyncio.AbstractEventLoop, context: dict):
    source = context.get("source_traceback")
    msg = context.get("message", "")
    if source:
        _log.warning(
            "ASYNCIO_BLOCK %.3fs | %s | %s",
            context.get("duration", 0), msg, "".join(source.format()),
        )
    else:
        _log.warning("ASYNCIO_BLOCK %s", msg)
```

Activar con `ASYNC_DEBUG=1`. `loop.slow_callback_duration = 0.05` — cualquier
operación que tome >50ms imprime stack trace. Esto atrapa `time.sleep()`,
requests síncronos, operaciones de disco bloqueantes, etc.

---

## 4. Database Pool — `asyncpg`

```python
async def create_pool(dsn: str, min_size: int = 0, max_size: int | None = None,
                      command_timeout: int = 10) -> asyncpg.Pool:
    if max_size is None:
        max_size = int(os.getenv("DB_POOL_MAX_SIZE", "3"))
    return await asyncpg.create_pool(
        dsn=dsn, min_size=min_size, max_size=max_size,
        command_timeout=command_timeout, statement_cache_size=0,
    )
```

- `statement_cache_size=0` para evitar cache de prepared statements con conexiones
  poolables (comportamiento predecible en serverless).
- Pool size configurable por env var, default 3.
- Sin ORM — SQL crudo. Las columnas se definen como constantes:
  ```python
  _PEDIDO_COLS = "id, usuario_id, paquete_id, ... total, estatus, ... updated_at"
  ```

---

## 5. Lifespan + Health Checks (Strategy Pattern)

### Base abstracta

```python
@dataclass
class HealthCheckResult:
    service: str
    ok: bool

class HealthChecker(ABC):
    @abstractmethod
    async def check(self) -> HealthCheckResult: ...
```

### Agregador con `asyncio.gather`

```python
class HealthService:
    def __init__(self, checkers: list[HealthChecker]) -> None:
        self._checkers = checkers

    async def check_all(self) -> bool:
        if not self._checkers:
            return True
        results = await asyncio.gather(
            *(c.check() for c in self._checkers), return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                logger.error("Health check error: %s", r)
                return False
            if not r.ok:
                logger.warning("Health check failed: %s", r.service)
                return False
        return True
```

### Uso en scheduler (health gate)

```python
salud_ok = await self._health_service.check_all()
if not salud_ok:
    logger.warning("Health check falló — no se generarán pedidos")
    return 0
```

Cada checker es su propia clase (`SupabaseHealthChecker`, `MercadoPagoHealthChecker`,
etc.), todas implementan `async def check()`. Se agregan en `dependencies.py`:

```python
def get_health_service() -> HealthService:
    return HealthService([
        SupabaseHealthChecker(),
        MercadoPagoHealthChecker(),
        MetaHealthChecker(),
    ])
```

---

## 6. Capa de Dominio — Interfaces Abstractas

```python
class UsuarioRepository(ABC):
    @abstractmethod
    async def get_by_phone(self, telefono: str) -> Optional[Usuario]: ...
    @abstractmethod
    async def get_or_create_by_phone(self, telefono: str, nombre: str,
                                     email: Optional[str] = None) -> Usuario: ...

class PedidoRepository(ABC):
    @abstractmethod
    async def create_checkout_atomic(self, *, codigo_postal: str, nombre: str,
                                     telefono: str, ...) -> CheckoutResult: ...
    @abstractmethod
    async def get_by_id(self, pedido_id: str) -> Optional[Pedido]: ...
    @abstractmethod
    async def create_si_no_pendiente(self, pedido: Pedido) -> Pedido: ...
```

**Cada repositorio es una interfaz abstracta.** La implementación concreta
(`PostgresPedidoRepository`) se inyecta en tiempo de ejecución via `Depends`.
Esto permite testear servicios sin base de datos.

---

## 7. Capa de Infraestructura — Repositorios PostgreSQL

```python
class PostgresPedidoRepository(PedidoRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_si_no_pendiente(self, pedido: Pedido) -> Pedido:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                INSERT INTO pedidos (...) VALUES ($1,...)
                WHERE NOT EXISTS (
                    SELECT 1 FROM pedidos
                    WHERE usuario_id = $2 AND estatus = 'pendiente'
                )
                RETURNING {_PEDIDO_COLS}
            """, ...)
            if row is None:
                raise ValueError("Ya tienes un pedido pendiente.")
            return Pedido(**dict(row))
```

**Patrones clave:**
- Columnas como constantes `_PEDIDO_COLS` (DRY, fácil de mantener).
- `Pedido(**dict(row))` — conversión directa de Record a modelo Pydantic.
- Métodos que aceptan `conn: Optional[asyncpg.Connection] = None` para transacciones
  externas: si se pasa conexión, no adquiere del pool; si no, adquiere automáticamente.
- `WHERE NOT EXISTS` para operaciones condicionales sin race conditions (no es
  necesario bloquear tablas).

---

## 8. El CTE Atómico — Belleza en SQL

```sql
WITH
cp_info AS (
    SELECT municipio, estado, COUNT(*)::int AS num_colonias,
           MIN(colonia) AS una_colonia
    FROM codigos_postales WHERE codigo_postal = $1 GROUP BY municipio, estado
),
usuario AS (
    INSERT INTO usuarios (nombre, telefono, email) VALUES ($2, $3, $4)
    ON CONFLICT (telefono) DO UPDATE
        SET nombre = EXCLUDED.nombre, email = COALESCE(EXCLUDED.email, usuarios.email)
    RETURNING id, nombre
),
colonia_resuelta AS (
    SELECT CASE WHEN $11 <> '' THEN $11
                WHEN (SELECT num_colonias FROM cp_info) = 1
                    THEN (SELECT una_colonia FROM cp_info)
                ELSE '' END AS colonia
),
pedido AS (
    INSERT INTO pedidos (...)
    SELECT ... FROM ...
    WHERE (SELECT municipio FROM cp_info) IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM pedidos WHERE usuario_id = (SELECT id FROM usuario)
                      AND estatus = 'pendiente')
    RETURNING id, total
)
SELECT (SELECT id FROM usuario) AS usuario_id, ...
```

**En una sola transacción implícita:** resuelve CP, upsert usuario, resuelve colonia
automáticamente, verifica pedidos pendientes, inserta pedido, retorna resultado.
Zero race conditions, zero round-trips.

---

## 9. MemoryCache con Double-Checked Locking

```python
class MemoryCache:
    def __init__(self, default_ttl: int = 60) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._default_ttl = default_ttl

    async def get_or_load(self, key: str, loader: Callable[[], Coroutine[Any, Any, T]],
                          ttl: Optional[int] = None) -> T:
        ttl = ttl or self._default_ttl
        now = time.monotonic()
        entry = self._data.get(key)
        if entry is not None and (now - entry[0]) < ttl:  # 1ra chequeada sin lock
            return entry[1]
        async with self._lock:
            entry = self._data.get(key)     # 2da chequeada con lock
            if entry is not None and (now - entry[0]) < ttl:
                return entry[1]
            value = await loader()
            self._data[key] = (now, value)
            return value

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)
```

**Protege contra thundering herd:** la primera chequeada es rápida (sin lock),
la segunda (con lock) asegura que solo un loader ejecuta.

---

## 10. Dependency Injection — El Patrón `Annotated`

```python
PoolDep = Annotated[asyncpg.Pool, Depends(get_db_pool)]

def get_usuario_repo(pool: PoolDep) -> UsuarioRepository:
    return PostgresUsuarioRepository(pool)

def get_pedido_service(usuario_repo: UsuarioRepoDep, paquete_repo: PaqueteRepoDep,
                       pedido_repo: PedidoRepoDep, sepomex_repo: SepomexRepoDep) -> PedidoService:
    return PedidoService(pedido_repo=pedido_repo, usuario_repo=usuario_repo,
                         paquete_repo=paquete_repo, sepomex_repo=sepomex_repo)

PedidoServiceDep = Annotated[PedidoService, Depends(get_pedido_service)]
```

**Árbol de composición:**
```
get_db_pool(request) → PoolDep
  ├── get_usuario_repo(pool)    → UsuarioRepoDep
  ├── get_paquete_repo(pool)    → PaqueteRepoDep
  ├── get_pedido_repo(pool)     → PedidoRepoDep
  ├── get_suscripcion_repo(pool) → SuscripcionRepoDep
  ├── get_cliente_repo(pool)    → ClienteRepoDep
  ├── get_sepomex_repo(pool)    → SepomexRepoDep
  ├── get_pedido_service(...)   → PedidoServiceDep
  ├── get_suscripcion_service(...) → SuscripcionServiceDep
  └── get_suscripcion_scheduler(...) → SuscripcionSchedulerDep
```

**En los routers:**
```python
@router.get("/paquetes")
async def listar_paquetes(repo: PaqueteRepoDep):
    return await repo.list_active()

@router.post("/pedidos")
async def crear_pedido(payload: PedidoCreate, service: PedidoServiceDep):
    try:
        return await service.crear(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

---

## 11. Servicios con Excepciones de Negocio

```python
class PedidoService:
    def __init__(self, pedido_repo: PedidoRepository,
                 usuario_repo: Optional[UsuarioRepository] = None,
                 paquete_repo: Optional[PaqueteRepository] = None,
                 sepomex_repo: Optional[SepomexRepository] = None) -> None:
        ...

    async def crear_atomic(self, datos: PedidoCreate, paquete: Paquete) -> Pedido:
        if not datos.codigo_postal.isdigit() or len(datos.codigo_postal) != 5:
            raise ValueError("El código postal debe ser de 5 dígitos.")
        if not paquete.activo:
            raise ValueError("Paquete no disponible")
        ...
```

- **`ValueError` = error de negocio.** Los routers hacen catch y convierten a 400.
- Repositorios opcionales para servicios que pueden operar en modos reducidos.
- Funciones de dominio **puras sin clases**: `_calcular_precio_unitario`, `_calcular_total`,
  testeables sin mocks.

---

## 12. Middleware de Latencia (ASGI Puro)

```python
class LatencyMiddleware:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        async def send_with_metrics(message):
            if message["type"] == "http.response.start":
                elapsed_ms = (time.perf_counter() - start) * 1000
                _log.info(json.dumps({
                    "t": "http",
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": message.get("status"),
                    "ms": round(elapsed_ms, 2),
                    "server": SERVER_MODE,
                }))
            await send(message)
        await self.app(scope, receive, send_with_metrics)
```

- Mide **todas** las requests (no solo las de router) — incluye static files,
  errores 404, redirects.
- JSON logging estructurado — fácil de parsear por Datadog/CloudWatch.
- `SERVER_MODE` tag para distinguir Uvicorn vs Granian en dashboards.

---

## 13. Security Headers Middleware

```python
class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app
        self._csp = (
            b"default-src 'self'; "
            b"script-src 'self' 'unsafe-inline' ...; "
            b"form-action 'self'"
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                headers.extend([
                    (b"content-security-policy", self._csp),
                    (b"x-frame-options", b"DENY"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                ])
                message["headers"] = headers
            await send(message)
        await self.app(scope, receive, send_with_headers)
```

ASGI puro, sin dependencias de framework, aplica a todas las respuestas HTTP.

---

## 14. CSRF con Sesiones

```python
def _get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        request.session["csrf_token"] = token
    return token

def csrf_context(request: Request) -> dict:
    return {"csrf_token": _get_csrf_token(request)}

async def validate_csrf(request: Request, token: str | None = None) -> None:
    session_token = request.session.get("csrf_token")
    if token is None:
        form = await request.form()
        token = form.get("csrf_token", "")
    if not session_token or not token or not secrets.compare_digest(session_token, token):
        raise HTTPException(status_code=403, detail="CSRF token inválido")
```

- `secrets.compare_digest` — timing-safe comparison.
- Generación lazy: el token se crea en el primer GET y se persiste en sesión.
- `csrf_context()` se inyecta en templates Jinja2.

---

## 15. Patrones de Concurrencia

| Patrón | Uso | Código |
|--------|-----|--------|
| `asyncio.Semaphore` | Rate-limit APIs externas (Nominatim: 1 req/s) | `_sem_nominatim = asyncio.Semaphore(1)` |
| `asyncio.Lock` | Double-checked locking en cache | `async with self._lock:` |
| `asyncio.create_task` | Background PDF generation | `asyncio.create_task(pdf_service.pre_generar_background(...))` |
| `run_in_executor` | CPU-bound PDF (WeasyPrint) | `pdf_bytes = await loop.run_in_executor(None, _generar_pdf_sync, html)` |
| `asyncio.gather` | Health checks paralelos | `results = await asyncio.gather(*(c.check() for c in self._checkers), return_exceptions=True)` |
| `asyncio.as_completed` | Load test progress | `for task in asyncio.as_completed(tasks):` |

---

## 16. Pirámide de Testing

### Test Factories

```python
def make_usuario(**kwargs) -> Usuario:
    return Usuario(
        id=kwargs.get("id", uuid4()),
        nombre=kwargs.get("nombre", "Test User"),
        telefono=kwargs.get("telefono", "9991234567"),
        email=kwargs.get("email", "test@example.com"),
        created_at=kwargs.get("created_at", datetime.utcnow()),
    )
```

Patrón: `**kwargs` con defaults sensibles. El test solo pasa lo que necesita
cambiar. Una sola fuente de verdad compartida entre unit, integration y e2e.

### Mock Repositories (In-Memory)

```python
class MockPedidoRepository:
    def __init__(self):
        self._pedidos: dict[str, Pedido] = {}
        self._fail_next_create = False

    async def create_checkout_atomic(self, ..., codigo_postal: str, ...) -> dict:
        cp_valido = codigo_postal == "97000"
        if not cp_valido:
            return {"cp_valido": False, "pedido_id": None, ...}
        ...
```

Implementaciones en memoria que siguen la misma interfaz abstracta.
Fáciles de extender con flags como `_fail_next_create` para probar errores.

### Mock asyncpg Pool

```python
def _make_mock_pool():
    mock_conn = MagicMock()
    mock_conn.fetchval = AsyncMock(return_value=None)
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=checkout_row())
    mock_conn.execute = AsyncMock(return_value=None)
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=mock_conn)
    ctx_mgr.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = ctx_mgr
    ...
    return pool, mock_conn
```

### FakeRecord — La Joya

```python
class _FakeRecord(dict):
    _DEFAULTS = {
        "cp_valido": True, "total": Decimal("150"), "estatus": "pendiente",
        "created_at": datetime.utcnow(), "nombre": "Juan", ...
    }
    def __missing__(self, key):
        return self._DEFAULTS.get(key, uuid4())
    def __getattr__(self, name):
        return self[name] if name in self else self.__missing__(name)
    def __getitem__(self, key):
        try: return super().__getitem__(key)
        except KeyError: return self.__missing__(key)
```

**Un solo mock para todas las queries.** `__missing__` da defaults sensibles
para cualquier columna que falte. `__getattr__` emula `row.colonia`.

```python
def checkout_row(cp_valido=True, pedido_id=None) -> _FakeRecord:
    """FakeRecord con keys de create_checkout_atomic + usuario + pedido + suscripcion."""
    ...
```

### Configuración de Tests E2E

```python
@pytest.fixture(autouse=True)
def _reset():
    limiter.enabled = False          # desactiva rate limiting
    app.dependency_overrides.clear() # limpia overrides de tests anteriores
    pool, mock_conn = _make_mock_pool()
    app.state.db_pool = pool
    app.state.cache = MemoryCache(default_ttl=60)
    yield
    app.dependency_overrides.clear()
    limiter.enabled = True
```

### Stress Tests — No 500s Allowed

```python
class TestAPIStress:
    def test_pedidos_create_missing_fields(self, client):
        resp = client.post("/api/pedidos", json={})
        assert resp.status_code < 500   # 400, 422, etc. OK. 500 = FAIL

    def test_paquetes_get_by_id_invalid_uuid(self, client):
        resp = client.get("/api/paquetes/not-a-uuid")
        assert resp.status_code < 500
```

Cada endpoint recibe inputs inválidos: UUIDs malos, JSON vacío, fechas inválidas,
cantidades negativas. La aserción es `< 500` — no `== 200`. Cualquier 500 es bug.

### Load Test con httpx + Semaphore

```python
async def simulate_user(sem: asyncio.Semaphore, uid: int):
    async with sem:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{BASE_URL}/partial/welcome")
            # parse paquete_id del HTML
            r = await client.get(f"{BASE_URL}/checkout", params={...})
            r = await client.post(f"{BASE_URL}/checkout", data={...})
            record(Result(success=r.status_code == 200, elapsed_ms=...))
```

```python
async def main():
    sem = asyncio.Semaphore(CONCURRENT_LIMIT)  # 25 concurrentes
    tasks = [asyncio.create_task(simulate_user(sem, i)) for i in range(1, 101)]
    for task in asyncio.as_completed(tasks):
        await task
        # progress bar
    # Report: P50, P95, P99, throughput
```

Stats con `asyncio.Lock`, print P50/95/99 mediante percentiles de lista ordenada.

---

## 17. Estructura de Directorios para Nuevo Proyecto

```
proyecto/
├── pyproject.toml
├── .env.example
├── src/
│   ├── main.py                      # lifespan + middleware + routers
│   ├── domain/
│   │   ├── models.py                # Pydantic models
│   │   └── interfaces.py            # Abstract repositories
│   ├── application/
│   │   ├── schemas.py               # Pydantic request/response
│   │   ├── services.py              # Business logic
│   │   └── scheduler.py             # Background jobs (opcional)
│   ├── infrastructure/
│   │   ├── database.py              # asyncpg pool factory
│   │   ├── repositories.py          # Postgres*Repository
│   │   ├── cache.py                 # MemoryCache con TTL
│   │   ├── security.py              # SecurityHeadersMiddleware
│   │   ├── csrf.py                  # CSRF con sesiones
│   │   ├── limiter.py               # slowapi Limiter singleton
│   │   └── health/
│   │       ├── base.py              # HealthChecker ABC + HealthCheckResult
│   │       ├── service_a.py         # Checker para Service A
│   │       └── service_b.py         # Checker para Service B
│   ├── api/
│   │   ├── router.py                # REST endpoints
│   │   └── dependencies.py          # DI wiring
│   └── pages/ (opcional)
│       ├── router.py                # HTML endpoints
│       └── dependencies.py          # DI wiring para pages
└── tests/
    ├── conftest.py                  # Factories + mock repos (compartido)
    ├── unit/
    │   ├── test_services.py
    │   └── test_schemas.py
    ├── integration/
    │   └── test_api.py
    ├── e2e/
    │   ├── conftest.py              # FakeRecord + mock pool + fixtures autouse
    │   ├── test_full_checkout.py
    │   └── test_error_flows.py
    └── stress/
        └── test_stress.py
scripts/
    └── load_test.py                 # httpx + Semaphore + stats
```

---

## 18. Dependencias Clave (`pyproject.toml`)

```toml
[project]
requires-python = ">=3.13"
dependencies = [
    "fastapi[standard]>=0.139.0",
    "asyncpg>=0.31.0",
    "python-dotenv>=1.1.0",
    "slowapi>=0.1.10",
    "weasyprint>=69.0",
    "granian>=2.7.9",
]

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "pytest-asyncio>=0.26.0",
    "granian>=1.7.0",
    "locust>=2.46.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## 19. Bounded Contexts (DDD)

Para separar dominios dentro del mismo monolitho:

```
src/logistic/                     # Contexto delimitado: logística
├── domain/
│   ├── models.py                 # LogisticPedido, LogisticCliente (dataclasses)
│   └── interfaces.py             # PedidoQueryRepository (solo lectura)
├── application/
│   └── services.py               # LogisticService
├── infrastructure/
│   └── repositories.py           # Solo consultas SELECT
└── interfaces/
    └── web/
        ├── router.py             # Dashboard, login, HTMX partials
        ├── deps.py               # Wiring específico de logística
        └── templates/
            ├── dashboard.html
            └── components/
                ├── atoms/
                ├── molecules/
                └── organisms/
```

Cada contexto tiene su propio `domain/`, `application/`, `infrastructure/`.
Comparten la misma base de datos pero cada uno accede a sus tablas.

---

## 20. Principios del Código Sublime

1. **Una sola línea de `import os`** — toda la config se lee al inicio del módulo.
2. **Sin clases sin propósito** — las funciones puras (`_calcular_precio_unitario`)
   están fuera de las clases. No pongas todo dentro de una clase "Utils".
3. **Errores como valores, no como excepciones de framework** — `ValueError` en
   services, catch en routers, convert a HTTPException. El service layer no
   sabe que existe HTTP.
4. **SQL columnas como constantes** — un solo lugar para cambiar, menos bugs de
   typo en queries.
5. **Factories de test con `**kwargs`** — un solo lugar de verdad para crear
   modelos de prueba.
6. **FakeRecord con `__missing__`** — un mock que funciona para todo, sin
   tener que mockear cada query diferente.
7. **Stress tests asertan `< 500`** — no `== 200`. El sistema debe fallar
   elegantemente (con 400, 404, 422) nunca con 500.
8. **`asyncio.Lock` + double-checked locking en cache** — previene thundering
   herd sin locks innecesarios.
9. **CTEs atómicas en SQL** — una sola query que hace todo lo que una transacción
   haría, sin necesidad de BEGIN/COMMIT en código.
10. **Middleware ASGI puro** — no necesitas FastAPI específico para security
    headers o latency logging. Funciona con cualquier framework ASGI.
