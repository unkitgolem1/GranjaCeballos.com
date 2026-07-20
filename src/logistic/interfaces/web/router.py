import os
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.infrastructure.csrf import csrf_context, validate_csrf
from src.infrastructure.limiter import limiter

from ...application.services import LogisticService
from .deps import get_logistic_service

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATES = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter()


def _creds():
    return os.getenv("LOGISTIC_USERNAME", "rodri"), os.getenv("LOGISTIC_PASSWORD")


def _authed(request: Request) -> bool:
    user, _ = _creds()
    return request.session.get("logistic_user") == user


def _nav_ctx(seccion_activa: str, request: Request) -> dict:
    return {
        "seccion_activa": seccion_activa,
        "user": _creds()[0],
        **csrf_context(request),
    }


@router.get("/logistic/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if _authed(request):
        return RedirectResponse(url="/logistic", status_code=302)
    return TEMPLATES.TemplateResponse(
        request=request, name="login.html",
        context={"error": None, **csrf_context(request)},
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
    return TEMPLATES.TemplateResponse(
        request=request, name="login.html",
        context={"error": "Usuario o contraseña incorrectos", **csrf_context(request)},
    )


@router.get("/logistic/logout", response_class=HTMLResponse)
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/logistic/login", status_code=302)


@router.get("/logistic", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    service: LogisticService = Depends(get_logistic_service),
    seccion: str = "todo",
    estatus: str = "pendiente",
):
    if not _authed(request):
        return RedirectResponse(url="/logistic/login", status_code=302)

    hoy = date.today()
    repo = service._pedido_repo
    todo_pedidos = today_pedidos = past_pedidos = []

    if seccion == "todo":
        todo_pedidos = await repo.listar_pedidos(estatus, orden="ASC", limite=25)
    else:
        if seccion in ("", "hoy"):
            today_pedidos = await repo.listar_pedidos(
                estatus, fecha_desde=str(hoy), orden="DESC"
            )
        if seccion in ("", "pasado"):
            past_pedidos = await repo.listar_pedidos(
                estatus, fecha_hasta=str(hoy - timedelta(days=1)), orden="DESC"
            )

    return TEMPLATES.TemplateResponse(
        request=request, name="dashboard.html",
        context={
            "hoy": hoy,
            "seccion": seccion,
            "today_pedidos": [dict(r.__dict__) for r in today_pedidos],
            "past_pedidos": [dict(r.__dict__) for r in past_pedidos],
            "todo_pedidos": [dict(r.__dict__) for r in todo_pedidos],
            "estatus_filter": estatus,
            **_nav_ctx("pedidos", request),
        },
    )


@router.post("/logistic/pedidos/{pedido_id}/estatus")
async def update_pedido_estatus(
    request: Request,
    pedido_id: str,
    estatus: str = Form(...),
    service: LogisticService = Depends(get_logistic_service),
):
    if not _authed(request):
        return RedirectResponse(url="/logistic/login", status_code=302)
    await validate_csrf(request)

    pedido = await service.actualizar_estatus(pedido_id, estatus)
    if pedido is None:
        return HTMLResponse("Pedido no encontrado", status_code=404)
    return RedirectResponse(url="/logistic", status_code=302)


@router.get("/logistic/partial/pedidos", response_class=HTMLResponse)
async def partial_pedidos(
    request: Request,
    service: LogisticService = Depends(get_logistic_service),
    seccion: str = "todo",
    estatus: str = "pendiente",
):
    if not _authed(request):
        return RedirectResponse(url="/logistic/login", status_code=302)

    hoy = date.today()
    repo = service._pedido_repo
    todo_pedidos = today_pedidos = past_pedidos = []

    if seccion == "todo":
        todo_pedidos = await repo.listar_pedidos(estatus, orden="ASC", limite=25)
    else:
        if seccion in ("", "hoy"):
            today_pedidos = await repo.listar_pedidos(
                estatus, fecha_desde=str(hoy), orden="DESC"
            )
        if seccion in ("", "pasado"):
            past_pedidos = await repo.listar_pedidos(
                estatus, fecha_hasta=str(hoy - timedelta(days=1)), orden="DESC"
            )

    return TEMPLATES.TemplateResponse(
        request=request, name="_pedidos_content.html",
        context={
            "hoy": hoy,
            "seccion": seccion,
            "today_pedidos": [dict(r.__dict__) for r in today_pedidos],
            "past_pedidos": [dict(r.__dict__) for r in past_pedidos],
            "todo_pedidos": [dict(r.__dict__) for r in todo_pedidos],
            "estatus_filter": estatus,
            **csrf_context(request),
        },
    )


def _stats_clientes(rows: list) -> dict:
    hoy = date.today()
    total = len(rows)
    nuevos = sum(
        1 for c in rows
        if c.created_at and c.created_at.month == hoy.month and c.created_at.year == hoy.year
    )
    pedidos = sum(c.total_pedidos for c in rows)
    return {"total_clientes": total, "nuevos_este_mes": nuevos, "total_pedidos": pedidos}


@router.get("/logistic/partial/clientes", response_class=HTMLResponse)
async def partial_clientes(
    request: Request,
    service: LogisticService = Depends(get_logistic_service),
):
    if not _authed(request):
        return RedirectResponse(url="/logistic/login", status_code=302)

    rows = await service.listar_clientes()
    clientes = [dict(r.__dict__) for r in rows]
    return TEMPLATES.TemplateResponse(
        request=request, name="_clientes_content.html",
        context={"clientes": clientes},
    )


@router.get("/logistic/clientes", response_class=HTMLResponse)
async def clientes_list(
    request: Request,
    service: LogisticService = Depends(get_logistic_service),
):
    if not _authed(request):
        return RedirectResponse(url="/logistic/login", status_code=302)

    rows = await service.listar_clientes()
    clientes = [dict(r.__dict__) for r in rows]
    return TEMPLATES.TemplateResponse(
        request=request, name="clientes.html",
        context={
            "clientes": clientes,
            **_stats_clientes(rows),
            **_nav_ctx("clientes", request),
        },
    )
