import asyncpg


async def create_pool(
    dsn: str,
    min_size: int = 0,
    max_size: int = 3,
    command_timeout: int = 10,
) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
    )
