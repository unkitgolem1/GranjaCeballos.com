import asyncpg

from src.domain.interfaces import SepomexRepository


class PostgresSepomexRepository(SepomexRepository):

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def consultar(self, cp: str) -> dict | None:
        rows = await self._pool.fetch(
            """SELECT DISTINCT colonia, municipio, estado, ciudad
               FROM codigos_postales
               WHERE codigo_postal = $1
               ORDER BY colonia""",
            cp,
        )
        if not rows:
            return None
        return {
            "codigo_postal": cp,
            "estado": rows[0]["estado"],
            "municipio": rows[0]["municipio"],
            "colonias": [r["colonia"] for r in rows],
        }

    async def existe(self, cp: str) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT 1 FROM codigos_postales WHERE codigo_postal = $1 LIMIT 1",
                cp,
            )
        )

    async def listar_colonias_merida(self) -> list[dict]:
        return await self._pool.fetch(
            """SELECT DISTINCT ON (colonia) colonia, codigo_postal
               FROM codigos_postales
               WHERE estado = 'Yucatán'
               ORDER BY colonia, codigo_postal"""
        )

    async def buscar_colonias(self, query: str) -> list[dict]:
        if not query or len(query) < 2:
            return []
        rows = await self._pool.fetch(
            """SELECT DISTINCT colonia, codigo_postal
               FROM codigos_postales
               WHERE estado = 'Yucatán'
                 AND lower(colonia) LIKE lower($1)
               ORDER BY colonia
               LIMIT 10""",
            f"%{query}%",
        )
        return [{"colonia": r["colonia"], "codigo_postal": r["codigo_postal"]} for r in rows]

    async def buscar_cp_por_colonia(self, nombre_colonia: str) -> str | None:
        if not nombre_colonia or len(nombre_colonia) < 3:
            return None
        row = await self._pool.fetchrow(
            """SELECT codigo_postal FROM codigos_postales
               WHERE estado = 'Yucatán'
                 AND lower(colonia) LIKE lower($1)
               LIMIT 1""",
            f"%{nombre_colonia}%",
        )
        if row:
            return row["codigo_postal"]
        row = await self._pool.fetchrow(
            """SELECT codigo_postal FROM codigos_postales
               WHERE estado = 'Yucatán'
               LIMIT 1"""
        )
        return row["codigo_postal"] if row else None
