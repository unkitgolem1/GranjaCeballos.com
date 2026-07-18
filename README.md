# Granja Ceballos

Plataforma de pedidos de huevo de libre pastoreo — Yucatán, México.

---

## Arquitectura Hexagonal (Ports & Adapters)

```
┌─────────────────────────────────────────────────────────┐
│                     INTERFACES (API)                     │
│    FastAPI routes · Dependency injection · HTTP          │
│    src/api/                                              │
│      router.py       ←  endpoints REST                   │
│      dependencies.py ←  proveedores DI (Depends)        │
├─────────────────────────────────────────────────────────┤
│                     APPLICATION                           │
│    Use cases · DTOs · Orquestación                       │
│    src/application/                                       │
│      services.py    ←  PedidoService (crear pedido)      │
│      schemas.py     ←  PedidoCreate, PedidoUpdateEstatus │
├─────────────────────────────────────────────────────────┤
│                     DOMAIN                                │
│    Entidades · Reglas de negocio · Puertos (interfaces)  │
│    src/domain/                                            │
│      models.py     ←  Usuario, Paquete, Pedido (Pydantic)│
│      interfaces.py ←  UsuarioRepository, ... (ABCs)      │
├─────────────────────────────────────────────────────────┤
│                  INFRASTRUCTURE                           │
│    Adaptadores secundarios · PostgreSQL · asyncpg         │
│    src/infrastructure/                                    │
│      database.py     ←  create_pool()                    │
│      repositories.py ←  Postgres*Repo (implementan ABCs) │
│      migrations/     ←  SQL DDL                          │
└─────────────────────────────────────────────────────────┘
```

### Flujo de una petición

```
HTTP POST /api/pedidos
       │
       ▼
  router.py  ←  recibe PedidoCreate (DTO)
       │
       ▼
  dependencies.py  ←  inyecta PedidoService
       │
       ▼
  services.py  ←  PedidoService.crear()
       │  ├─ 1. get_or_create_by_phone()  →  PostgresUsuarioRepository
       │  ├─ 2. get_by_id()               →  PostgresPaqueteRepository
       │  ├─ 3. calcula total             →  regla de negocio
       │  └─ 4. create()                  →  PostgresPedidoRepository
       ▼
  response  ←  Pedido (JSON)
```

### Principios SOLID aplicados

| Principio | Implementación |
|---|---|
| **SRP** | Cada archivo = una responsabilidad (modelos, interfaces, repos, servicios, rutas) |
| **OCP** | Para cambiar de DB solo se crea una nueva implementación del ABC; el dominio no se toca |
| **LSP** | Cualquier `*Repository` que implemente el ABC puede intercambiarse |
| **ISP** | Interfaces pequeñas y específicas por entidad (`UsuarioRepository`, `PaqueteRepository`, `PedidoRepository`) |
| **DIP** | Las rutas y servicios dependen de *abstracciones* (`PaqueteRepository`), no de `PostgresPaqueteRepository` |

---

## Modelo de datos

### `usuarios`
| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID PK | |
| nombre | VARCHAR(200) | |
| telefono | VARCHAR(20) **UNIQUE** | Identificador del usuario |
| email | VARCHAR(255) | nullable |
| created_at | TIMESTAMPTZ | |

### `paquetes`
| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID PK | |
| nombre | VARCHAR(100) | "1 Cartón", "Suscripción Semanal" |
| descripcion | TEXT | |
| precio | DECIMAL(10,2) | |
| costo_envio | DECIMAL(10,2) | default 0 |
| es_suscripcion | BOOLEAN | |
| es_popular | BOOLEAN | |
| badge | VARCHAR(50) | "Más popular" |
| activo | BOOLEAN | soft delete |
| created_at | TIMESTAMPTZ | |

### `pedidos`
| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID PK | |
| usuario_id | UUID FK → usuarios | |
| paquete_id | UUID FK → paquetes | |
| direccion | VARCHAR(500) | Dirección de **entrega** (por pedido, no por usuario) |
| cantidad | INT | ≥ 1 |
| total | DECIMAL(10,2) | Calculado por backend |
| metodo_pago | VARCHAR(20) | `tarjeta` o `efectivo` |
| estatus | VARCHAR(20) | `pendiente` / `aceptado` / `entregado` / `cancelado` / `rechazado` |
| notas | TEXT | nullable |
| fecha_entrega | DATE | Indexado — filtrar pedidos del día |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

---

## API REST

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/paquetes` | Paquetes activos |
| `GET` | `/api/paquetes/{id}` | Detalle de paquete |
| `POST` | `/api/pedidos` | Crear pedido (usa `PedidoCreate` DTO) |
| `GET` | `/api/pedidos?fecha=2025-07-17` | Pedidos de una fecha |
| `GET` | `/api/pedidos/{id}` | Detalle de pedido |
| `PATCH` | `/api/pedidos/{id}/estatus` | Cambiar estatus |
| `GET` | `/api/pedidos/clusters?fecha=2025-07-17` | Clusters por dirección (+1 usuario en misma dirección) |

### Reglas de negocio (en `PedidoService`)

1. **Identificación por teléfono**: si el `telefono` ya existe en `usuarios`, se reusa el registro (`ON CONFLICT DO UPDATE`)
2. **Dirección en el pedido**: un mismo usuario puede pedir hoy a su casa y mañana a su negocio
3. **Cálculo de total**: `backend = paquete.precio * cantidad + paquete.costo_envio` — el frontend nunca envía `total`
4. **Clusters**: endpoint que agrupa por `direccion` y detecta direcciones con +1 `usuario_id` distinto — ideal para proponer descuentos por volumen

---

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.13 + FastAPI |
| Database | PostgreSQL (async via asyncpg) |
| Frontend | Tailwind CSS v4 + HTMX 2.x |
| Templates | Jinja2 |
| Paquetería | `uv` |
| Deploy | Vercel (Serverless Functions) |
