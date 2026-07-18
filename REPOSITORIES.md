# Guía de Repositorios — Arquitectura de Adaptadores

## Estructura por capa

```
┌───────────────────────────────────────────────────────────┐
│  DOMAIN (interfaces.py)                                   │
│  └── class XxxRepository(ABC)                            │
│       Define el CONTRATO (métodos abstractos)              │
├───────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE (repositories.py)                         │
│  └── class PostgresXxxRepository(XxxRepository)           │
│       Implementa el CONTRATO con asyncpg                   │
├───────────────────────────────────────────────────────────┤
│  API (dependencies.py)                                    │
│  └── async def get_xxx_repo(pool: PoolDep)                │
│       Crea el alias de tipo Annotated[..., Depends(...)]  │
├───────────────────────────────────────────────────────────┤
│  API (router.py)                                          │
│  └── def endpoint(repo: XxxRepoDep):                      │
│       Usa el alias en los parámetros de ruta              │
└───────────────────────────────────────────────────────────┘
```

---

## Paso a paso: agregar una entidad nueva

### 1. Modelo — `domain/models.py`

```python
class Categoria(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    nombre: str = Field(..., min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 2. Interfaz — `domain/interfaces.py`

```python
class CategoriaRepository(ABC):
    @abstractmethod
    async def list_all(self) -> list[Categoria]: ...

    @abstractmethod
    async def get_by_id(self, categoria_id: str) -> Optional[Categoria]: ...

    @abstractmethod
    async def create(self, categoria: Categoria) -> Categoria: ...
```

### 3. Implementación Postgres — `infrastructure/repositories.py`

```python
class PostgresCategoriaRepository(CategoriaRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_all(self) -> list[Categoria]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM categorias ORDER BY nombre")
            return [Categoria(**dict(row)) for row in rows]

    async def get_by_id(self, categoria_id: str) -> Optional[Categoria]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM categorias WHERE id = $1", categoria_id
            )
            return Categoria(**dict(row)) if row else None

    async def create(self, categoria: Categoria) -> Categoria:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO categorias (id, nombre, created_at)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                categoria.id, categoria.nombre, categoria.created_at,
            )
            return Categoria(**dict(row))
```

### 4. DI provider — `api/dependencies.py`

```python
async def get_categoria_repo(pool: PoolDep) -> CategoriaRepository:
    return PostgresCategoriaRepository(pool)

CategoriaRepoDep = Annotated[CategoriaRepository, Depends(get_categoria_repo)]
```

### 5. Endpoint — `api/router.py`

```python
@router.get("/categorias")
async def listar_categorias(repo: CategoriaRepoDep):
    return await repo.list_all()

@router.post("/categorias")
async def crear_categoria(payload: Categoria, repo: CategoriaRepoDep):
    return await repo.create(payload)
```

### 6. Exportar — `__init__.py`

- `src/domain/__init__.py` → agregar `Categoria`, `CategoriaRepository`
- `src/infrastructure/__init__.py` → agregar `PostgresCategoriaRepository`

---

## Reglas generales

| Regla | Explicación |
|---|---|
| **Nunca importes `Postgres*` en `router.py`** | Las rutas solo ven interfaces (`CategoriaRepository`), nunca la implementación concreta |
| **async siempre** | `async with self._pool.acquire() as conn` para cada operación |
| **RETURNING \*** | Siempre en INSERT y UPDATE para devolver la fila completa tipada |
| **dict(row)** | Convierte fila asyncpg a dict, Pydantic lo instancia directo (`Categoria(**dict(row))`) |
| **$1, $2, ...** | Placeholders de asyncpg, no f-strings (SQL injection safe) |
| **UUID como `str` en queries** | `get_by_id(str(uuid))` — asyncpg acepta string y la convierte |
| **Un repositorio por entidad** | No mezcles lógica de distintas entidades en un mismo repo |

---

## Esquema de migraciones (orden de ejecución)

```
001_initial.sql           → CREATE usuarios, paquetes, pedidos + índices
002_suscripciones.sql     → CREATE suscripciones + ALTER pedidos + índices
003_custom_descuentos.sql → ALTER paquetes + seed data (3 paquetes)
004_performance.sql       → Índices compuestos adicionales
```

---

## Mapa de archivos actuales

```
src/
├── domain/
│   ├── models.py          → Usuario, Paquete, CustomTier, Pedido, Suscripcion
│   ├── interfaces.py      → UsuarioRepository, PaqueteRepository,
│   │                         PedidoRepository, SuscripcionRepository
│   └── __init__.py        → exports públicos
├── application/
│   ├── services.py        → PedidoService, SuscripcionService + helpers
│   ├── scheduler.py       → SuscripcionScheduler
│   ├── schemas.py         → PedidoCreate, SuscripcionCreate, ...
│   └── __init__.py
├── infrastructure/
│   ├── database.py        → create_pool()
│   ├── repositories.py    → Postgres*Repository (cada uno implementa su ABC)
│   ├── health/            → Checkers dummy (Supabase, MercadoPago, Meta)
│   ├── health_service.py  → HealthService.reunir checkers
│   ├── migrations/        → 001 a 004
│   └── __init__.py
└── api/
    ├── dependencies.py    → PoolDep, *RepoDep, *ServiceDep, *SchedulerDep
    ├── router.py          → 13 endpoints REST
    └── __init__.py
```
