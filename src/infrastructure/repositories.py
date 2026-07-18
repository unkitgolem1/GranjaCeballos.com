import json
from datetime import date
from typing import Optional

import asyncpg

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
                "SELECT * FROM usuarios WHERE telefono = $1", telefono
            )
            return Usuario(**dict(row)) if row else None

    async def get_or_create_by_phone(
        self, telefono: str, nombre: str, email: Optional[str] = None
    ) -> Usuario:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO usuarios (nombre, telefono, email)
                VALUES ($1, $2, $3)
                ON CONFLICT (telefono) DO UPDATE
                    SET nombre = EXCLUDED.nombre,
                        email  = COALESCE(EXCLUDED.email, usuarios.email)
                RETURNING *
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
                "SELECT * FROM paquetes WHERE activo = true ORDER BY es_customizable ASC, precio DESC"
            )
            return [self._row_to_paquete(row) for row in rows]

    async def get_by_id(self, paquete_id: str) -> Optional[Paquete]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paquetes WHERE id = $1", paquete_id
            )
            return self._row_to_paquete(row) if row else None


class PostgresPedidoRepository(PedidoRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, pedido: Pedido) -> Pedido:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO pedidos
                    (id, usuario_id, paquete_id, suscripcion_id,
                     direccion, cantidad, total, metodo_pago, estatus,
                     notas, fecha_usuario, fecha_entrega,
                     created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                RETURNING *
                """,
                pedido.id,
                pedido.usuario_id,
                pedido.paquete_id,
                pedido.suscripcion_id,
                pedido.direccion,
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

    async def get_by_id(self, pedido_id: str) -> Optional[Pedido]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM pedidos WHERE id = $1", pedido_id
            )
            return Pedido(**dict(row)) if row else None

    async def list_by_fecha(self, fecha: date) -> list[Pedido]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pedidos WHERE fecha_entrega = $1 ORDER BY created_at DESC",
                fecha,
            )
            return [Pedido(**dict(row)) for row in rows]

    async def update_estatus(
        self, pedido_id: str, estatus: str
    ) -> Optional[Pedido]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE pedidos
                SET estatus = $1, updated_at = NOW()
                WHERE id = $2
                RETURNING *
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

    async def create(self, suscripcion: Suscripcion) -> Suscripcion:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO suscripciones
                    (id, usuario_id, paquete_id, direccion, cantidad,
                     metodo_pago, dia_entrega, fecha_inicio,
                     proxima_generacion, activa, created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                RETURNING *
                """,
                suscripcion.id,
                suscripcion.usuario_id,
                suscripcion.paquete_id,
                suscripcion.direccion,
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

    async def get_by_id(self, suscripcion_id: str) -> Optional[Suscripcion]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM suscripciones WHERE id = $1", suscripcion_id
            )
            return Suscripcion(**dict(row)) if row else None

    async def list_by_usuario(self, usuario_id: str) -> list[Suscripcion]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM suscripciones WHERE usuario_id = $1 ORDER BY created_at DESC",
                usuario_id,
            )
            return [Suscripcion(**dict(row)) for row in rows]

    async def list_vencidas(self) -> list[Suscripcion]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM suscripciones
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
                """
                UPDATE suscripciones
                SET dia_entrega = $1,
                    proxima_generacion = $2,
                    updated_at = NOW()
                WHERE id = $3
                RETURNING *
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
                "SELECT * FROM clientes WHERE activo = true ORDER BY nombre"
            )
            return [Cliente(**dict(row)) for row in rows]
