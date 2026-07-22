from datetime import date
from typing import Optional

import asyncpg
from dataclasses import fields as dc_fields

from ..domain.interfaces import (
    ClienteQueryRepository, PedidoQueryRepository, _COLUMNAS_FECHA,
)
from ..domain.models import LogisticCliente, LogisticPedido

_ORDERS_SQL = """SELECT
                    p.id, p.usuario_id, p.paquete_id,
                    p.direccion, p.codigo_postal, p.colonia, p.cantidad, p.total,
                    p.metodo_pago, p.estatus,
                    p.fecha_usuario, p.fecha_entrega,
                    p.created_at, p.updated_at,
                    u.nombre AS usuario_nombre,
                    u.telefono AS usuario_telefono,
                    paq.nombre AS paquete_nombre
                FROM pedidos p
                JOIN usuarios u ON u.id = p.usuario_id
                JOIN paquetes paq ON paq.id = p.paquete_id
                WHERE ($1 = '' OR p.estatus = $1)"""


class PostgresPedidoQueryRepo(PedidoQueryRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def listar_pedidos(
        self, estatus: str, fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None, orden: str = "ASC", limite: int = 25,
        fecha_columna: str = "fecha_entrega",
    ) -> list[LogisticPedido]:
        if fecha_columna not in _COLUMNAS_FECHA:
            fecha_columna = "fecha_entrega"

        async with self._pool.acquire() as conn:
            sql = _ORDERS_SQL
            params = [estatus]

            if fecha_desde:
                sql += f" AND p.{fecha_columna} >= $2"
                params.append(fecha_desde)
            if fecha_hasta:
                n = len(params) + 1
                sql += f" AND p.{fecha_columna} < ${n}"
                params.append(fecha_hasta)

            n = len(params) + 1
            sql += f" ORDER BY p.estatus <> 'pendiente', p.created_at DESC LIMIT ${n}"
            params.append(limite)

            rows = await conn.fetch(sql, *params)

        return [LogisticPedido(**dict(r)) for r in rows]

    async def actualizar_estatus(self, pedido_id: str, nuevo_estatus: str) -> Optional[LogisticPedido]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE pedidos p
                SET estatus = $1, updated_at = NOW()
                FROM usuarios u, paquetes paq
                WHERE p.id = $2
                  AND u.id = p.usuario_id
                  AND paq.id = p.paquete_id
                RETURNING p.id, p.usuario_id, p.paquete_id,
                          p.direccion, p.codigo_postal, p.colonia,
                          p.cantidad, p.total, p.metodo_pago, p.estatus,
                          p.fecha_usuario, p.fecha_entrega,
                          p.created_at, p.updated_at,
                          u.nombre AS usuario_nombre,
                          u.telefono AS usuario_telefono,
                          paq.nombre AS paquete_nombre
                """,
                nuevo_estatus, pedido_id,
            )
            if row is None:
                return None

            valid = {f.name for f in dc_fields(LogisticPedido)}
            return LogisticPedido(**{k: v for k, v in dict(row).items() if k in valid})


class PostgresClienteQueryRepo(ClienteQueryRepository):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def listar_clientes(self) -> list[LogisticCliente]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    u.telefono,
                    (SELECT u2.nombre FROM usuarios u2
                     WHERE u2.telefono = u.telefono
                     ORDER BY u2.created_at DESC LIMIT 1) AS nombre,
                    COUNT(p.id)::int AS total_pedidos,
                    MAX(p.created_at) AS ultimo_pedido_fecha,
                    (SELECT p2.estatus FROM pedidos p2
                     JOIN usuarios u2 ON u2.id = p2.usuario_id
                     WHERE u2.telefono = u.telefono
                     ORDER BY p2.created_at DESC LIMIT 1) AS ultimo_pedido_estatus,
                    MIN(u.created_at) AS created_at
                FROM usuarios u
                LEFT JOIN pedidos p ON p.usuario_id = u.id
                WHERE u.telefono IS NOT NULL AND u.telefono != ''
                GROUP BY u.telefono
                ORDER BY total_pedidos DESC, u.telefono
            """)
        return [LogisticCliente(**dict(r)) for r in rows]

    async def activar_cliente(self, usuario_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE usuarios SET es_cliente = TRUE WHERE id = $1 AND NOT es_cliente",
                usuario_id,
            )
