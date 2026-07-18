from typing import Annotated

import asyncpg
from fastapi import Depends, Request

from src.domain.interfaces import ClienteRepository, PaqueteRepository
from src.infrastructure.repositories import (
    PostgresClienteRepository,
    PostgresPaqueteRepository,
)


async def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


PoolDep = Annotated[asyncpg.Pool, Depends(get_db_pool)]


async def get_paquete_repo(pool: PoolDep) -> PaqueteRepository:
    return PostgresPaqueteRepository(pool)


PaqueteRepoDep = Annotated[PaqueteRepository, Depends(get_paquete_repo)]


async def get_cliente_repo(pool: PoolDep) -> ClienteRepository:
    return PostgresClienteRepository(pool)


ClienteRepoDep = Annotated[ClienteRepository, Depends(get_cliente_repo)]
