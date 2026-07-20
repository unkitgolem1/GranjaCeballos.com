import json
from datetime import date
from typing import Optional

import asyncpg

_USUARIO_COLS = "id, nombre, telefono, email, created_at"
_PAQUETE_COLS = "id, nombre, descripcion, precio, costo_envio, cantidad_fija, es_suscripcion, es_customizable, precio_minimo, tiers, es_popular, badge, activo, created_at"
_PEDIDO_COLS = "id, usuario_id, paquete_id, suscripcion_id, direccion, codigo_postal, cantidad, total, metodo_pago, estatus, notas, fecha_usuario, fecha_entrega, created_at, updated_at"
_SUSCRIPCION_COLS = "id, usuario_id, paquete_id, direccion, codigo_postal, cantidad, metodo_pago, dia_entrega, fecha_inicio, proxima_generacion, activa, created_at, updated_at"
_CLIENTE_COLS = "id, nombre, lugar, icono_svg, testimonio, activo, created_at"

from src.domain.interfaces import (
    ClienteRepository,
    PaqueteRepository,
    PedidoRepository,
    SuscripcionRepository,
    UsuarioRepository,
)
from src.domain.models import Cliente, Paquete, Pedido, Suscripcion, Usuario


class PostgresUsuarioRepository(UsuarioRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_phone(self, telefono: str) -> Optional[Usuario]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_USUARIO_COLS} FROM usuarios WHERE telefono = $1", telefono
            )
            return Usuario(**dict(row)) if row else None

    async def get_or_create_by_phone(
        self, telefono: str, nombre: str, email: Optional[str] = None
    ) -> Usuario:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO usuarios (nombre, telefono, email)
                VALUES ($1, $2, $3)
                ON CONFLICT (telefono) DO UPDATE
                    SET nombre = EXCLUDED.nombre,
                        email  = COALESCE(EXCLUDED.email, usuarios.email)
                RETURNING {_USUARIO_COLS}
                """,
                nombre,
                telefono,
                email,
            )
            return Usuario(**dict(row))


class PostgresPaqueteRepository(PaqueteRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @staticmethod
    def _row_to_paquete(row: asyncpg.Record) -> Paquete:
        data = dict(row)
        if isinstance(data.get("tiers"), str):
            data["tiers"] = json.loads(data["tiers"])
        return Paquete(**data)

    async def list_active(self) -> list[Paquete]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_PAQUETE_COLS} FROM paquetes WHERE activo = true ORDER BY es_customizable ASC, precio DESC"
            )
            return [self._row_to_paquete(row) for row in rows]

    async def get_by_id(self, paquete_id: str) -> Optional[Paquete]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_PAQUETE_COLS} FROM paquetes WHERE id = $1", paquete_id
            )
            return self._row_to_paquete(row) if row else None


class PostgresPedidoRepository(PedidoRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_si_no_pendiente(self, pedido: Pedido) -> Pedido:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO pedidos
                    (id, usuario_id, paquete_id, suscripcion_id,
                     direccion, codigo_postal, cantidad, total, metodo_pago, estatus,
                     notas, fecha_usuario, fecha_entrega,
                     created_at, updated_at)
                SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15
                WHERE NOT EXISTS (
                    SELECT 1 FROM pedidos
                    WHERE usuario_id = $2 AND estatus = 'pendiente'
                )
                RETURNING {_PEDIDO_COLS}
                """,
                pedido.id,
                pedido.usuario_id,
                pedido.paquete_id,
                pedido.suscripcion_id,
                pedido.direccion,
                pedido.codigo_postal,
                pedido.cantidad,
                pedido.total,
                pedido.metodo_pago,
                pedido.estatus,
                pedido.notas,
                pedido.fecha_usuario,
                pedido.fecha_entrega,
                pedido.created_at,
                pedido.updated_at,
            )
            if row is None:
                raise ValueError(
                    "Ya tienes un pedido pendiente. "
                    "Espera a que sea confirmado antes de hacer otro."
                )
            return Pedido(**dict(row))

    async def create(self, pedido: Pedido, conn: Optional[asyncpg.Connection] = None) -> Pedido:
        async def _do(c: asyncpg.Connection) -> Pedido:
            row = await c.fetchrow(
                f"""
                INSERT INTO pedidos
                    (id, usuario_id, paquete_id, suscripcion_id,
                     direccion, codigo_postal, cantidad, total, metodo_pago, estatus,
                     notas, fecha_usuario, fecha_entrega,
                     created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                RETURNING {_PEDIDO_COLS}
                """,
                pedido.id,
                pedido.usuario_id,
                pedido.paquete_id,
                pedido.suscripcion_id,
                pedido.direccion,
                pedido.codigo_postal,
                pedido.cantidad,
                pedido.total,
                pedido.metodo_pago,
                pedido.estatus,
                pedido.notas,
                pedido.fecha_usuario,
                pedido.fecha_entrega,
                pedido.created_at,
                pedido.updated_at,
            )
            return Pedido(**dict(row))
        if conn:
            return await _do(conn)
        async with self._pool.acquire() as c:
            return await _do(c)

    async def get_by_id(self, pedido_id: str) -> Optional[Pedido]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_PEDIDO_COLS} FROM pedidos WHERE id = $1", pedido_id
            )
            return Pedido(**dict(row)) if row else None

    async def get_pendiente_by_telefono(self, telefono: str) -> Optional[Pedido]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_PEDIDO_COLS} FROM pedidos p
                JOIN usuarios u ON u.id = p.usuario_id
                WHERE u.telefono = $1 AND p.estatus = 'pendiente'
                LIMIT 1
                """,
                telefono,
            )
            return Pedido(**dict(row)) if row else None

    async def list_by_fecha(self, fecha: date) -> list[Pedido]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_PEDIDO_COLS} FROM pedidos WHERE fecha_entrega = $1 ORDER BY created_at DESC",
                fecha,
            )
            return [Pedido(**dict(row)) for row in rows]

    async def update_estatus(
        self, pedido_id: str, estatus: str
    ) -> Optional[Pedido]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE pedidos
                SET estatus = $1, updated_at = NOW()
                WHERE id = $2
                RETURNING {_PEDIDO_COLS}
                """,
                estatus,
                pedido_id,
            )
            return Pedido(**dict(row)) if row else None

    async def count_by_direccion_y_fecha(self, fecha: date) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    direccion,
                    COUNT(DISTINCT usuario_id) AS usuarios_distintos,
                    COUNT(*)                 AS total_pedidos
                FROM pedidos
                WHERE fecha_entrega = $1
                GROUP BY direccion
                HAVING COUNT(DISTINCT usuario_id) > 1
                ORDER BY total_pedidos DESC
                """,
                fecha,
            )
            return [dict(row) for row in rows]


class PostgresSuscripcionRepository(SuscripcionRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, suscripcion: Suscripcion, conn: Optional[asyncpg.Connection] = None) -> Suscripcion:
        async def _do(c: asyncpg.Connection) -> Suscripcion:
            row = await c.fetchrow(
                f"""
                INSERT INTO suscripciones
                    (id, usuario_id, paquete_id, direccion, codigo_postal, cantidad,
                     metodo_pago, dia_entrega, fecha_inicio,
                     proxima_generacion, activa, created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                RETURNING {_SUSCRIPCION_COLS}
                """,
                suscripcion.id,
                suscripcion.usuario_id,
                suscripcion.paquete_id,
                suscripcion.direccion,
                suscripcion.codigo_postal,
                suscripcion.cantidad,
                suscripcion.metodo_pago,
                suscripcion.dia_entrega,
                suscripcion.fecha_inicio,
                suscripcion.proxima_generacion,
                suscripcion.activa,
                suscripcion.created_at,
                suscripcion.updated_at,
            )
            return Suscripcion(**dict(row))
        if conn:
            return await _do(conn)
        async with self._pool.acquire() as c:
            return await _do(c)

    async def get_by_id(self, suscripcion_id: str) -> Optional[Suscripcion]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_SUSCRIPCION_COLS} FROM suscripciones WHERE id = $1", suscripcion_id
            )
            return Suscripcion(**dict(row)) if row else None

    async def list_by_usuario(self, usuario_id: str) -> list[Suscripcion]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SUSCRIPCION_COLS} FROM suscripciones WHERE usuario_id = $1 ORDER BY created_at DESC",
                usuario_id,
            )
            return [Suscripcion(**dict(row)) for row in rows]

    async def list_vencidas(self) -> list[Suscripcion]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {_SUSCRIPCION_COLS} FROM suscripciones
                WHERE activa = true AND proxima_generacion <= CURRENT_DATE
                ORDER BY proxima_generacion
                """
            )
            return [Suscripcion(**dict(row)) for row in rows]

    async def update_proxima(
        self, suscripcion_id: str, dia_entrega: int, proxima_generacion: date
    ) -> Optional[Suscripcion]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                UPDATE suscripciones
                SET dia_entrega = $1,
                    proxima_generacion = $2,
                    updated_at = NOW()
                WHERE id = $3
                RETURNING {_SUSCRIPCION_COLS}
                """,
                dia_entrega,
                proxima_generacion,
                suscripcion_id,
            )
            return Suscripcion(**dict(row)) if row else None

    async def avanzar_proxima(self, suscripcion_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE suscripciones
                SET proxima_generacion = proxima_generacion + INTERVAL '7 days',
                    updated_at = NOW()
                WHERE id = $1
                """,
                suscripcion_id,
            )


class PostgresClienteRepository(ClienteRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_active(self) -> list[Cliente]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_CLIENTE_COLS} FROM clientes WHERE activo = true ORDER BY nombre"
            )
            return [Cliente(**dict(row)) for row in rows]
