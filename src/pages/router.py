import asyncio
import json as _json
import os
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.application.schemas import PedidoCreate, SuscripcionCreate
from src.application.services import (
    _calcular_total,
    PedidoService,
    SuscripcionService,
)
from src.domain.models import Paquete
from src.infrastructure.repositories import (
    PostgresPaqueteRepository,
    PostgresPedidoRepository,
    PostgresSuscripcionRepository,
    PostgresUsuarioRepository,
)

from src.infrastructure.limiter import limiter

from .dependencies import ClienteRepoDep, PaqueteRepoDep, get_db_pool

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


class _JSONEncoder(_json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        return super().default(obj)


def _json_filter(obj):
    return _json.dumps(obj, cls=_JSONEncoder)


templates.env.filters["to_json"] = _json_filter

router = APIRouter()
PARTIALS = {"welcome": "catalog/welcome.html"}

_PAQUETES_CACHE: dict[str, list[Paquete]] = {}
_PAQUETES_CACHE_TS: float = 0.0
_PAQUETES_CACHE_TTL = 30
_PAQUETES_CACHE_LOCK = asyncio.Lock()


async def _get_paquetes_cached(repo: PostgresPaqueteRepository) -> list[Paquete]:
    global _PAQUETES_CACHE, _PAQUETES_CACHE_TS
    now = time.time()
    if _PAQUETES_CACHE.get("all") and (now - _PAQUETES_CACHE_TS) < _PAQUETES_CACHE_TTL:
        return _PAQUETES_CACHE["all"]
    async with _PAQUETES_CACHE_LOCK:
        if _PAQUETES_CACHE.get("all") and (now - _PAQUETES_CACHE_TS) < _PAQUETES_CACHE_TTL:
            return _PAQUETES_CACHE["all"]
        data = await repo.list_active()
        _PAQUETES_CACHE["all"] = data
        _PAQUETES_CACHE_TS = now
        return data


def _paquete_from_cache(paquete_id: str) -> Paquete | None:
    paquetes = _PAQUETES_CACHE.get("all")
    if paquetes is None:
        return None
    for p in paquetes:
        if str(p.id) == paquete_id:
            return p
    return None


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    repo: PaqueteRepoDep,
    cliente_repo: ClienteRepoDep,
):
    paquetes = await _get_paquetes_cached(repo)
    clientes = await cliente_repo.list_active()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"paquetes": paquetes, "clientes": clientes},
    )


@router.get("/partial/{name}", response_class=HTMLResponse)
async def partial_view(
    request: Request,
    name: str,
    repo: PaqueteRepoDep,
    cliente_repo: ClienteRepoDep,
):
    if name not in PARTIALS:
        return HTMLResponse("Partial no encontrado", status_code=404)

    paquetes = await _get_paquetes_cached(repo)
    clientes = await cliente_repo.list_active()
    ctx = {"paquetes": paquetes, "clientes": clientes}

    if request.headers.get("HX-Request") != "true":
        ctx["partial_name"] = PARTIALS[name]
        return templates.TemplateResponse(request=request, name="index.html", context=ctx)

    return templates.TemplateResponse(request=request, name=PARTIALS[name], context=ctx)


@router.get("/checkout", response_class=HTMLResponse)
async def checkout_view(
    request: Request,
    repo: PaqueteRepoDep,
    paquete_id: UUID = Query(default=None),
    cantidad: int = Query(default=1),
):
    paquetes = await _get_paquetes_cached(repo)
    return templates.TemplateResponse(
        request=request,
        name="checkout/form.html",
        context={
            "paquetes": paquetes,
            "paquete_id": str(paquete_id) if paquete_id else None,
            "cantidad": cantidad,
            "hoy": datetime.now().isoweekday(),
            "hoy_iso": date.today().isoformat(),
        },
    )


@router.post("/checkout", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def checkout_submit(
    request: Request,
    nombre: str = Form(...),
    telefono: str = Form(...),
    paquete_id: str = Form(...),
    direccion: str = Form(...),
    cantidad: int = Form(default=1, ge=1),
    es_suscripcion: bool = Form(default=False),
    dia_entrega: int = Form(default=1, ge=1, le=7),
    fecha_entrega: date = Form(default=date.today()),
    metodo_pago: str = Form(default="efectivo"),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    usuario_repo = PostgresUsuarioRepository(pool)
    paquete_repo = PostgresPaqueteRepository(pool)
    pedido_repo = PostgresPedidoRepository(pool)
    suscripcion_repo = PostgresSuscripcionRepository(pool)

    paquete = _paquete_from_cache(paquete_id)
    if paquete is None:
        try:
            paquete = await paquete_repo.get_by_id(paquete_id)
        except Exception:
            return templates.TemplateResponse(
                request=request,
                name="partials/_checkout_result.html",
                context={"error": "Error al buscar el paquete. Intenta de nuevo."},
            )

    if paquete is None:
        return templates.TemplateResponse(
            request=request,
            name="partials/_checkout_result.html",
            context={"error": "Paquete no encontrado"},
        )

    try:
        if es_suscripcion:
            service = SuscripcionService(usuario_repo, paquete_repo, pedido_repo, suscripcion_repo)
            datos = SuscripcionCreate(
                nombre=nombre,
                telefono=telefono,
                paquete_id=UUID(paquete_id),
                direccion=direccion,
                cantidad=cantidad,
                metodo_pago=metodo_pago,
                dia_entrega=dia_entrega,
                fecha_inicio=date.today(),
            )
            sub = await service.crear(datos, paquete=paquete)
            total = _calcular_total(paquete, cantidad, envio_gratis=True)
            ctx = {
                "pedido": {
                    "id": sub.id,
                    "usuario_nombre": nombre,
                    "es_suscripcion": True,
                    "paquete_nombre": paquete.nombre,
                    "cantidad": cantidad,
                    "total": f"{total:.0f}",
                    "fecha_entrega": sub.proxima_generacion,
                    "direccion": sub.direccion,
                    "telefono": telefono,
                    "metodo_pago": metodo_pago,
                },
            }
            return templates.TemplateResponse(request=request, name="checkout/_success.html", context=ctx)
        else:
            service = PedidoService(usuario_repo, paquete_repo, pedido_repo)
            datos = PedidoCreate(
                nombre=nombre,
                telefono=telefono,
                paquete_id=UUID(paquete_id),
                direccion=direccion,
                cantidad=cantidad,
                metodo_pago=metodo_pago,
                fecha_usuario=fecha_entrega,
            )
            pedido = await service.crear(datos, paquete=paquete)
            total = _calcular_total(paquete, cantidad)
            ctx = {
                "pedido": {
                    "id": pedido.id,
                    "usuario_nombre": nombre,
                    "es_suscripcion": False,
                    "paquete_nombre": paquete.nombre,
                    "cantidad": pedido.cantidad,
                    "total": f"{total:.0f}",
                    "fecha_entrega": pedido.fecha_entrega,
                    "direccion": pedido.direccion,
                    "telefono": telefono,
                    "metodo_pago": metodo_pago,
                },
            }
            return templates.TemplateResponse(request=request, name="checkout/_success.html", context=ctx)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="partials/_checkout_result.html",
            context={"error": str(e)},
        )
