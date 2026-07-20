from typing import Annotated

import asyncpg
from fastapi import Depends, Request

from src.application.scheduler import SuscripcionScheduler
from src.application.services import PedidoService, SuscripcionService
from src.domain.interfaces import (
    ClienteRepository,
    PaqueteRepository,
    PedidoRepository,
    SuscripcionRepository,
    UsuarioRepository,
)
from src.infrastructure.sepomex_repository import PostgresSepomexRepository
from src.infrastructure.health.mercadopago import MercadoPagoHealthChecker
from src.infrastructure.health.meta import MetaHealthChecker
from src.infrastructure.health.supabase import SupabaseHealthChecker
from src.infrastructure.health_service import HealthService
from src.infrastructure.repositories import (
    PostgresClienteRepository,
    PostgresPaqueteRepository,
    PostgresPedidoRepository,
    PostgresSuscripcionRepository,
    PostgresUsuarioRepository,
)
from src.domain.interfaces import SepomexRepository


async def get_db_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


PoolDep = Annotated[asyncpg.Pool, Depends(get_db_pool)]


async def get_usuario_repo(pool: PoolDep) -> UsuarioRepository:
    return PostgresUsuarioRepository(pool)


async def get_paquete_repo(pool: PoolDep) -> PaqueteRepository:
    return PostgresPaqueteRepository(pool)


async def get_pedido_repo(pool: PoolDep) -> PedidoRepository:
    return PostgresPedidoRepository(pool)


async def get_suscripcion_repo(pool: PoolDep) -> SuscripcionRepository:
    return PostgresSuscripcionRepository(pool)


async def get_cliente_repo(pool: PoolDep) -> ClienteRepository:
    return PostgresClienteRepository(pool)


UsuarioRepoDep = Annotated[UsuarioRepository, Depends(get_usuario_repo)]
PaqueteRepoDep = Annotated[PaqueteRepository, Depends(get_paquete_repo)]
PedidoRepoDep = Annotated[PedidoRepository, Depends(get_pedido_repo)]
SuscripcionRepoDep = Annotated[SuscripcionRepository, Depends(get_suscripcion_repo)]
ClienteRepoDep = Annotated[ClienteRepository, Depends(get_cliente_repo)]


async def get_sepomex_repo(pool: PoolDep) -> SepomexRepository:
    return PostgresSepomexRepository(pool)


SepomexRepoDep = Annotated[SepomexRepository, Depends(get_sepomex_repo)]


async def get_health_service() -> HealthService:
    return HealthService(
        [
            SupabaseHealthChecker(),
            MercadoPagoHealthChecker(),
            MetaHealthChecker(),
        ]
    )


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


async def get_pedido_service(
    usuario_repo: UsuarioRepoDep,
    paquete_repo: PaqueteRepoDep,
    pedido_repo: PedidoRepoDep,
    sepomex_repo: SepomexRepoDep,
) -> PedidoService:
    return PedidoService(pedido_repo=pedido_repo, usuario_repo=usuario_repo, paquete_repo=paquete_repo, sepomex_repo=sepomex_repo)


PedidoServiceDep = Annotated[PedidoService, Depends(get_pedido_service)]


async def get_suscripcion_service(
    usuario_repo: UsuarioRepoDep,
    paquete_repo: PaqueteRepoDep,
    pedido_repo: PedidoRepoDep,
    suscripcion_repo: SuscripcionRepoDep,
    sepomex_repo: SepomexRepoDep,
) -> SuscripcionService:
    return SuscripcionService(usuario_repo, paquete_repo, pedido_repo, suscripcion_repo, sepomex_repo)


SuscripcionServiceDep = Annotated[SuscripcionService, Depends(get_suscripcion_service)]


async def get_suscripcion_scheduler(
    suscripcion_repo: SuscripcionRepoDep,
    pedido_repo: PedidoRepoDep,
    paquete_repo: PaqueteRepoDep,
    health_service: HealthServiceDep,
) -> SuscripcionScheduler:
    return SuscripcionScheduler(
        suscripcion_repo, pedido_repo, paquete_repo, health_service
    )


SuscripcionSchedulerDep = Annotated[
    SuscripcionScheduler, Depends(get_suscripcion_scheduler)
]
