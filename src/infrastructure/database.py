import os

import asyncpg


async def create_pool(
    dsn: str,
    min_size: int = 0,
    max_size: int | None = None,
    command_timeout: int = 10,
) -> asyncpg.Pool:
    if max_size is None:
        max_size = int(os.getenv("DB_POOL_MAX_SIZE", "3"))
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
        statement_cache_size=0,
    )
