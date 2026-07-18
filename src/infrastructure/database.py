import asyncpg


async def create_pool(
    dsn: str,
    min_size: int = 5,
    max_size: int = 20,
) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
    )
