# -*- coding: utf-8 -*-
import asyncio
import json as _json
import logging
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote as _urlquote
from uuid import UUID

logger = logging.getLogger(__name__)

import asyncpg
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

import pydantic

from src.api import pdf_service
from src.application.schemas import PedidoCreate, SuscripcionCreate
from src.application.services import (
    _calcular_precio_unitario,
    _calcular_total,
    PedidoService,
    SuscripcionService,
)
from src.domain.models import Paquete
from src.infrastructure.profiling import profile
from src.infrastructure.repositories import (
    PostgresPaqueteRepository,
    PostgresPedidoRepository,
    PostgresSuscripcionRepository,
    PostgresUsuarioRepository,
)
from src.infrastructure.sepomex_repository import PostgresSepomexRepository

from src.infrastructure.csrf import csrf_context, validate_csrf
from src.infrastructure.limiter import limiter

from .dependencies import ClienteRepoDep, PaqueteRepoDep, get_db_pool

_WHATSAPP_PHONE = os.getenv("WHATSAPP_BUSINESS_PHONE", "")

_EMOJI_CHICKEN = "\U0001F414"
_EMOJI_ID = "\U0001F194"
_EMOJI_EGG = "\U0001F95A"
_EMOJI_CALENDAR = "\U0001F4C5"
_EMOJI_PIN = "\U0001F4CD"
_EMOJI_MONEY = "\U0001F4B0"
_EMOJI_CLIP = "\U0001F4CE"

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


def _urlencode_filter(val):
    return _urlquote(val or "", safe="")


templates.env.filters["urlencode"] = _urlencode_filter


def _precio_unitario_filter(paquete, cantidad=1):
    return f"{_calcular_precio_unitario(paquete, cantidad):.0f}"


templates.env.filters["precio_unitario"] = _precio_unitario_filter

router = APIRouter()
PARTIALS = {"welcome": "catalog/welcome.html"}
_PARTIALS_NEED_PAQUETES = {"welcome", "pricing"}
_PARTIALS_NEED_CLIENTES = {"welcome", "clientes"}


async def _get_cached_paquetes(request: Request, repo: PaqueteRepoDep) -> list[Paquete]:
    cache = request.app.state.cache
    return await cache.get_or_load("paquetes", loader=repo.list_active, ttl=60)


async def _get_cached_paquete_by_id(request: Request, repo: PaqueteRepoDep, paquete_id: str) -> Paquete | None:
    paquetes = await _get_cached_paquetes(request, repo)
    for p in paquetes:
        if str(p.id) == paquete_id:
            return p
    return None


async def _get_cached_clientes(request: Request, cliente_repo: ClienteRepoDep) -> list:
    cache = request.app.state.cache
    return await cache.get_or_load("clientes", loader=cliente_repo.list_active, ttl=120)


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return PlainTextResponse(
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# AI crawlers\n"
        "User-agent: GPTBot\n"
        "Allow: /\n"
        "\n"
        "User-agent: PerplexityBot\n"
        "Allow: /\n"
        "\n"
        "User-agent: ClaudeBot\n"
        "Allow: /\n"
        "\n"
        "User-agent: Google-Extended\n"
        "Allow: /\n"
        "\n"
        "Sitemap: https://granjaceballos.com/sitemap.xml\n"
    )


@router.get("/sitemap.xml", response_class=FileResponse)
async def sitemap_xml():
    return FileResponse(str(_TEMPLATES_DIR.parent / "sitemap.xml"), media_type="application/xml")


@router.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt():
    return PlainTextResponse(
        "# Granja Ceballos - Huevo Fresco de Libre Pastoreo en Mérida, Yucatán\n"
        "\n"
        "> Granja Ceballos es el productor y distribuidor principal de huevo fresco "
        "de libre pastoreo (free-range) en Mérida, Yucatán.\n"
        "\n"
        "## Productos y Precios\n"
        "- **Cartón de Huevo Fresco de Libre Pastoreo**: $120 MXN (30 piezas)\n"
        "- **Calidad**: Gallinas criadas al libre pastoreo, alimentación natural, sin hormonas.\n"
        "\n"
        "## Cobertura y Entregas\n"
        "- **Ubicación principal**: Mérida, Yucatán, México.\n"
        "- **Zonas de entrega**: Altabrisa, Norte de Mérida, y zonas conurbadas.\n"
        "- **Sistema de pedidos**: Venta directa y suscripciones semanales/quincenales vía Web y WhatsApp.\n"
        "\n"
        "## Contacto y Compras\n"
        "- Sitio Oficial: https://granjaceballos.com\n"
        "- Pedidos y Suscripciones: https://granjaceballos.com/checkout\n"
        "- Catálogo de Paquetes: https://granjaceballos.com/#productos\n"
        "- Preguntas Frecuentes: https://granjaceballos.com/#faq\n"
        "- WhatsApp: https://wa.me/5219995050854\n"
    )


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    repo: PaqueteRepoDep,
    cliente_repo: ClienteRepoDep,
):
    paquetes = await _get_cached_paquetes(request, repo)
    clientes = await _get_cached_clientes(request, cliente_repo)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "paquetes": paquetes,
            "clientes": clientes,
            "whatsapp_phone": _WHATSAPP_PHONE,
        },
    )


@router.get("/partial/{name}", response_class=HTMLResponse)
@profile(threshold_ms=15)
async def partial_view(
    request: Request,
    name: str,
    repo: PaqueteRepoDep,
    cliente_repo: ClienteRepoDep,
):
    if name not in PARTIALS:
        return HTMLResponse("Partial no encontrado", status_code=404)

    ctx: dict = {"whatsapp_phone": _WHATSAPP_PHONE}
    if name in _PARTIALS_NEED_PAQUETES:
        ctx["paquetes"] = await _get_cached_paquetes(request, repo)
    if name in _PARTIALS_NEED_CLIENTES:
        ctx["clientes"] = await _get_cached_clientes(request, cliente_repo)

    if request.headers.get("HX-Request") != "true":
        ctx["partial_name"] = PARTIALS[name]
        return templates.TemplateResponse(request=request, name="index.html", context=ctx)

    return templates.TemplateResponse(request=request, name=PARTIALS[name], context=ctx)


@router.get("/checkout", response_class=HTMLResponse)
async def checkout_view(
    request: Request,
    repo: PaqueteRepoDep,
    paquete_id: UUID = Query(default=None),
    cantidad: int = Query(default=4),
):
    paquetes = await _get_cached_paquetes(request, repo)
    paquete_selected = next(
        (p for p in paquetes if str(p.id) == str(paquete_id)), None
    ) if paquete_id else None

    logger.info("Checkout form abierto | paquete_id=%s cantidad=%s", paquete_id, cantidad)

    if paquete_selected:
        envio = float(paquete_selected.costo_envio or 0)
        total = float(_calcular_total(paquete_selected, cantidad))
        if paquete_selected.es_customizable:
            unitario = float(_calcular_precio_unitario(paquete_selected, cantidad))
        else:
            unitario = float(paquete_selected.precio)
    else:
        unitario = 0
        total = 0

    return templates.TemplateResponse(
        request=request,
        name="checkout/form.html",
        context={
            "paquetes": paquetes,
            "paquete_id": str(paquete_id) if paquete_id else None,
            "paquete_selected": paquete_selected,
            "cantidad": cantidad,
            "precio_unitario": unitario,
            "precio_total": total,
            "hoy": datetime.now().isoweekday(),
            "hoy_iso": date.today().isoformat(),
            **csrf_context(request),
        },
    )


async def checkout_submit_impl(
    request: Request,
    nombre: str = Form(...),
    telefono: str = Form(...),
    paquete_id: str = Form(...),
    direccion: str = Form(default=""),
    codigo_postal: str = Form(default=""),
    estado: str = Form(default=""),
    ciudad: str = Form(default=""),
    colonia: str = Form(default=""),
    cantidad: int = Form(default=1, ge=1),
    es_suscripcion: bool = Form(default=False),
    dia_entrega: int = Form(default=1, ge=1, le=7),
    fecha_entrega: date = Form(default=date.today()),
    metodo_pago: str = Form(default="efectivo"),
    csrf_token: str = Form(default=""),
    pool: asyncpg.Pool = Depends(get_db_pool),
):
    await validate_csrf(request, token=csrf_token)
    telefono_masked = telefono[:3] + "***" + telefono[-3:] if len(telefono) > 6 else "***"
    logger.info(
        "Checkout POST | nombre=%s telefono=%s paquete=%s cp=%s",
        nombre, telefono_masked, paquete_id, codigo_postal,
    )

    paquete_repo = PostgresPaqueteRepository(pool)
    paquete = await _get_cached_paquete_by_id(request, paquete_repo, paquete_id)
    if paquete is None:
        return templates.TemplateResponse(
            request=request,
            name="partials/_checkout_result.html",
            context={"error": "Paquete no encontrado"},
        )

    try:
        if es_suscripcion:
            usuario_repo = PostgresUsuarioRepository(pool)
            pedido_repo = PostgresPedidoRepository(pool)
            suscripcion_repo = PostgresSuscripcionRepository(pool)
            sepomex_repo = PostgresSepomexRepository(pool)
            service = SuscripcionService(usuario_repo, paquete_repo, pedido_repo, suscripcion_repo, sepomex_repo)
            datos = SuscripcionCreate(
                nombre=nombre,
                telefono=telefono,
                paquete_id=UUID(paquete_id),
                direccion=direccion,
                codigo_postal=codigo_postal,
                estado=estado,
                ciudad=ciudad,
                colonia=colonia,
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
                    "codigo_postal": codigo_postal or "",
                    "telefono": telefono,
                    "metodo_pago": metodo_pago,
                },
            }
            logger.info("Suscripcion creada | id=%s telefono=%s", sub.id, telefono_masked)
            ticket_url = str(request.base_url) + f"api/ticket/{ctx['pedido']['id']}.pdf"
            p = ctx["pedido"]
            fecha_str = p["fecha_entrega"].strftime("%d/%m/%Y") if p["fecha_entrega"] else "Por confirmar"
            mensaje_texto = (
                f"Hola, soy *{p['usuario_nombre']}*, ya hice esta compra {_EMOJI_CHICKEN}\n"
                f"{_EMOJI_ID} Pedido *{p['id']}*\n"
                f"{_EMOJI_EGG} *{p['paquete_nombre']}*\n"
                f"{_EMOJI_CALENDAR} Entrega: *{fecha_str}*\n"
                f"{_EMOJI_PIN} *{p['direccion']}*\n"
                f"{_EMOJI_MONEY} *${p['total']} MXN*\n\n"
                f"{_EMOJI_CLIP} Ticket: {ticket_url}"
            )
            texto_codificado = _urlquote(mensaje_texto)
            wa_url = f"https://api.whatsapp.com/send?phone={_WHATSAPP_PHONE}&text={texto_codificado}"
            asyncio.create_task(
                pdf_service.pre_generar_background(pool, ctx["pedido"], _WHATSAPP_PHONE, ticket_url, wa_url)
            )
            return templates.TemplateResponse(
                request=request, name="checkout/_success.html",
                context={**ctx, "whatsapp_phone": _WHATSAPP_PHONE, "wa_url": wa_url},
            )
        else:
            pedido_repo = PostgresPedidoRepository(pool)
            service = PedidoService(pedido_repo=pedido_repo)
            datos = PedidoCreate(
                nombre=nombre,
                telefono=telefono,
                paquete_id=UUID(paquete_id),
                direccion=direccion,
                codigo_postal=codigo_postal,
                estado=estado,
                ciudad=ciudad,
                colonia=colonia,
                cantidad=cantidad,
                metodo_pago=metodo_pago,
                fecha_usuario=fecha_entrega,
            )
            pedido = await service.crear_atomic(datos, paquete=paquete)
            ctx = {
                "pedido": {
                    "id": pedido.id,
                    "usuario_nombre": nombre,
                    "es_suscripcion": False,
                    "paquete_nombre": paquete.nombre,
                    "cantidad": pedido.cantidad,
                    "total": f"{pedido.total:.0f}",
                    "fecha_entrega": pedido.fecha_entrega,
                    "direccion": pedido.direccion,
                    "codigo_postal": codigo_postal or "",
                    "telefono": telefono,
                    "metodo_pago": metodo_pago,
                },
            }
            logger.info("Pedido creado | id=%s total=%s telefono=%s", pedido.id, pedido.total, telefono_masked)
            ticket_url = str(request.base_url) + f"api/ticket/{ctx['pedido']['id']}.pdf"
            p = ctx["pedido"]
            fecha_str = p["fecha_entrega"].strftime("%d/%m/%Y") if p["fecha_entrega"] else "Por confirmar"
            mensaje_texto = (
                f"Hola, soy *{p['usuario_nombre']}*, ya hice esta compra {_EMOJI_CHICKEN}\n"
                f"{_EMOJI_ID} Pedido *{p['id']}*\n"
                f"{_EMOJI_EGG} *{p['paquete_nombre']}*\n"
                f"{_EMOJI_CALENDAR} Entrega: *{fecha_str}*\n"
                f"{_EMOJI_PIN} *{p['direccion']}*\n"
                f"{_EMOJI_MONEY} *${p['total']} MXN*\n\n"
                f"{_EMOJI_CLIP} Ticket: {ticket_url}"
            )
            texto_codificado = _urlquote(mensaje_texto)
            wa_url = f"https://api.whatsapp.com/send?phone={_WHATSAPP_PHONE}&text={texto_codificado}"
            asyncio.create_task(
                pdf_service.pre_generar_background(pool, ctx["pedido"], _WHATSAPP_PHONE, ticket_url, wa_url)
            )
            return templates.TemplateResponse(
                request=request, name="checkout/_success.html",
                context={**ctx, "whatsapp_phone": _WHATSAPP_PHONE, "wa_url": wa_url},
            )
    except pydantic.ValidationError as e:
        campo = e.errors()[0]["loc"][-1] if e.errors() else "campo"
        friendly = {
            "telefono": "El número de teléfono no es válido. Debe ser 10 dígitos (ej. 9991234567).",
            "nombre": "El nombre es obligatorio.",
            "email": "El correo electrónico no es válido.",
            "paquete_id": "El paquete seleccionado no es válido.",
            "cantidad": "La cantidad debe ser al menos 1.",
            "metodo_pago": "El método de pago no es válido.",
            "codigo_postal": "El código postal no es válido.",
        }.get(campo, f"El campo '{campo}' no es válido.")
        logger.warning("Checkout validacion pydantic | campo=%s error=%s telefono=%s", campo, e, telefono_masked)
        return templates.TemplateResponse(
            request=request,
            name="partials/_checkout_result.html",
            context={"error": friendly},
        )
    except ValueError as e:
        msg = str(e)
        if "pendiente" in msg:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT p.id, p.paquete_id, p.direccion, p.codigo_postal,
                              p.cantidad, p.total, p.metodo_pago, p.fecha_entrega,
                              u.nombre, u.telefono, paq.nombre as paquete_nombre
                       FROM pedidos p
                       JOIN usuarios u ON u.id = p.usuario_id
                       JOIN paquetes paq ON paq.id = p.paquete_id
                       WHERE u.telefono = $1 AND p.estatus = 'pendiente'
                       ORDER BY p.created_at DESC
                       LIMIT 1""",
                    telefono,
                )
            if row:
                ctx = {
                    "pedido": {
                        "id": row["id"],
                        "usuario_nombre": row["nombre"],
                        "es_suscripcion": False,
                        "paquete_nombre": row["paquete_nombre"],
                        "cantidad": row["cantidad"],
                        "total": f"{row['total']:.0f}",
                        "fecha_entrega": row["fecha_entrega"],
                        "direccion": row["direccion"],
                        "codigo_postal": row["codigo_postal"] or "",
                        "telefono": row["telefono"],
                        "metodo_pago": row["metodo_pago"],
                    },
                }
                logger.info("Redirigiendo a WhatsApp con pedido pendiente | id=%s telefono=%s", row["id"], telefono_masked)
                ticket_url = str(request.base_url) + f"api/ticket/{ctx['pedido']['id']}.pdf"
                p = ctx["pedido"]
                fecha_str = p["fecha_entrega"].strftime("%d/%m/%Y") if p["fecha_entrega"] else "Por confirmar"
                mensaje_texto = (
                    f"Hola, soy *{p['usuario_nombre']}*, ya hice esta compra {_EMOJI_CHICKEN}\n"
                    f"{_EMOJI_ID} Pedido *{p['id']}*\n"
                    f"{_EMOJI_EGG} *{p['paquete_nombre']}*\n"
                    f"{_EMOJI_CALENDAR} Entrega: *{fecha_str}*\n"
                    f"{_EMOJI_PIN} *{p['direccion']}*\n"
                    f"{_EMOJI_MONEY} *${p['total']} MXN*\n\n"
                    f"{_EMOJI_CLIP} Ticket: {ticket_url}"
                )
                texto_codificado = _urlquote(mensaje_texto)
                wa_url = f"https://api.whatsapp.com/send?phone={_WHATSAPP_PHONE}&text={texto_codificado}"
                asyncio.create_task(
                    pdf_service.pre_generar_background(pool, ctx["pedido"], _WHATSAPP_PHONE, ticket_url, wa_url)
                )
                return templates.TemplateResponse(
                    request=request, name="checkout/_success.html",
                    context={**ctx, "whatsapp_phone": _WHATSAPP_PHONE, "wa_url": wa_url},
                )
        logger.warning("Checkout validacion fallo | error=%s paquete=%s telefono=%s", e, paquete_id, telefono_masked)
        return templates.TemplateResponse(
            request=request,
            name="partials/_checkout_result.html",
            context={"error": msg},
        )
    except Exception:
        logger.exception("Checkout error inesperado | paquete=%s telefono=%s", paquete_id, telefono_masked)
        return templates.TemplateResponse(
            request=request,
            name="partials/_checkout_result.html",
            context={"error": "Ocurrió un error inesperado. Intenta de nuevo."},
        )


if os.getenv("LOAD_TEST") != "1":
    router.post("/checkout", response_class=HTMLResponse)(limiter.limit("10/minute")(checkout_submit_impl))
else:
    router.post("/checkout", response_class=HTMLResponse)(checkout_submit_impl)
