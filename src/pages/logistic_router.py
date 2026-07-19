import os
from datetime import date
from pathlib import Path

import asyncpg
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.infrastructure.csrf import csrf_context, validate_csrf
from src.infrastructure.limiter import limiter
from src.infrastructure.repositories import PostgresPedidoRepository

from .dependencies import get_db_pool

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter()


def _creds():
    return os.getenv("LOGISTIC_USERNAME", "rodri"), os.getenv("LOGISTIC_PASSWORD")


def _authed(request: Request) -> bool:
    user, _ = _creds()
    return request.session.get("logistic_user") == user


@router.get("/logistic/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if _authed(request):
        return RedirectResponse(url="/logistic", status_code=302)
    return templates.TemplateResponse(
        request=request, name="logistic/login.html", context={"error": None, **csrf_context(request)}
    )


@router.post("/logistic/login", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    await validate_csrf(request)
    user, pw = _creds()
    if username == user and password == pw:
        request.session["logistic_user"] = username
        return RedirectResponse(url="/logistic", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="logistic/login.html",
        context={"error": "Usuario o contraseña incorrectos", **csrf_context(request)},
    )


@router.get("/logistic/logout", response_class=HTMLResponse)
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/logistic/login", status_code=302)


@router.get("/logistic", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    pool: asyncpg.Pool = Depends(get_db_pool),
    seccion: str = "",
    estatus: str = "",
):
    if not _authed(request):
        return RedirectResponse(url="/logistic/login", status_code=302)

    ORDERS_SQL = """SELECT
                        p.id, p.usuario_id, p.paquete_id,
                        p.direccion, p.codigo_postal, p.cantidad, p.total,
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

    async with pool.acquire() as conn:
        hoy = await conn.fetchval("SELECT CURRENT_DATE")
        today_rows, past_rows = [], []
        if seccion in ("", "hoy"):
            today_rows = await conn.fetch(
                ORDERS_SQL + """
                AND p.fecha_entrega = $2
                ORDER BY
                  CASE p.estatus
                    WHEN 'pendiente' THEN 0
                    WHEN 'aceptado'  THEN 1
                    WHEN 'entregado' THEN 2
                    ELSE 3
                  END,
                  p.created_at DESC
                """,
                estatus, hoy,
            )
        if seccion in ("", "pasado"):
            past_rows = await conn.fetch(
                ORDERS_SQL + """
                AND p.fecha_entrega < $2
                ORDER BY
                  CASE p.estatus
                    WHEN 'pendiente' THEN 0
                    WHEN 'aceptado'  THEN 1
                    WHEN 'entregado' THEN 2
                    ELSE 3
                  END,
                  p.created_at DESC
                """,
                estatus, hoy,
            )

    return templates.TemplateResponse(
        request=request,
        name="logistic/dashboard.html",
        context={
            "hoy": hoy,
            "seccion": seccion,
            "today_pedidos": [dict(r) for r in today_rows],
            "past_pedidos": [dict(r) for r in past_rows],
            "estatus_filter": estatus,
            "user": _creds()[0],
            **csrf_context(request),
        },
    )


@router.post("/logistic/pedidos/{pedido_id}/estatus")
async def update_pedido_estatus(
    request: Request,
    pedido_id: str,
    estatus: str = Form(...),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    if not _authed(request):
        return RedirectResponse(url="/logistic/login", status_code=302)
    await validate_csrf(request)

    repo = PostgresPedidoRepository(pool)
    pedido = await repo.update_estatus(pedido_id, estatus)
    if pedido is None:
        return HTMLResponse("Pedido no encontrado", status_code=404)
    return RedirectResponse(url="/logistic", status_code=302)
