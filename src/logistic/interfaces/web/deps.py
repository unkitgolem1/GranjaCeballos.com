from fastapi import Depends

from src.pages.dependencies import get_db_pool

from ...application.services import LogisticService
from ...infrastructure.repositories import (
    PostgresClienteQueryRepo,
    PostgresPedidoQueryRepo,
)


async def get_logistic_service(
    pool=Depends(get_db_pool),
) -> LogisticService:
    return LogisticService(
        pedido_repo=PostgresPedidoQueryRepo(pool),
        cliente_repo=PostgresClienteQueryRepo(pool),
    )
