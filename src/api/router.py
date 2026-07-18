import os
from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
import weasyprint

from src.application.schemas import (
    PedidoCreate,
    PedidoUpdateEstatus,
    SuscripcionCreate,
    SuscripcionUpdate,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "templates"
_ticket_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
from src.application.services import _calcular_precio_unitario, _calcular_total

from .dependencies import (
    ClienteRepoDep,
    PaqueteRepoDep,
    PedidoRepoDep,
    PedidoServiceDep,
    PoolDep,
    SuscripcionRepoDep,
    SuscripcionSchedulerDep,
    SuscripcionServiceDep,
)

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/paquetes/precio-html")
async def preview_precio_html(
    repo: PaqueteRepoDep,
    paquete_id: UUID = Query(...),
    cantidad: int = Query(default=1, ge=1),
    envio_gratis: bool = Query(default=False),
):
    paquete = await repo.get_by_id(str(paquete_id))
    if paquete is None:
        return HTMLResponse('<p class="text-white/50 text-xs">Selecciona un paquete</p>')
    unitario = _calcular_precio_unitario(paquete, cantidad)
    total = _calcular_total(paquete, cantidad, envio_gratis=envio_gratis)
    ahorro = paquete.precio - unitario
    html = f'<p class="text-baroque text-lg font-bold">${total:.0f} MXN</p>'
    html += f'<p class="text-white/50 text-xs">${unitario:.0f} por cartón</p>'
    if ahorro > 0:
        ahorro_total = ahorro * cantidad
        html += f'<p class="text-[#90BDB5] text-xs mt-1">✨ Ahorras ${ahorro:.0f} por cartón</p>'
    html += '<p class="text-[#90BDB5]/70 text-xs mt-1">🚚 Envío incluido</p>'
    return HTMLResponse(html)


@router.get("/paquetes")
async def listar_paquetes(repo: PaqueteRepoDep):
    return await repo.list_active()


@router.get("/paquetes/{paquete_id}")
async def obtener_paquete(paquete_id: UUID, repo: PaqueteRepoDep):
    paquete = await repo.get_by_id(str(paquete_id))
    if paquete is None:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    return paquete


@router.get("/paquetes/{paquete_id}/precio")
async def calcular_precio(
    paquete_id: UUID,
    repo: PaqueteRepoDep,
    cantidad: int = Query(default=1, ge=1),
):
    paquete = await repo.get_by_id(str(paquete_id))
    if paquete is None:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    unitario = _calcular_precio_unitario(paquete, cantidad)
    total = _calcular_total(paquete, cantidad)
    return {
        "precio_unitario": str(unitario),
        "subtotal": str(unitario * cantidad),
        "envio": str(paquete.costo_envio or 0),
        "total": str(total),
    }


@router.post("/pedidos")
async def crear_pedido(payload: PedidoCreate, service: PedidoServiceDep):
    try:
        return await service.crear(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/pedidos")
async def listar_pedidos(fecha: date, repo: PedidoRepoDep):
    return await repo.list_by_fecha(fecha)


@router.get("/pedidos/{pedido_id}")
async def obtener_pedido(pedido_id: UUID, repo: PedidoRepoDep):
    pedido = await repo.get_by_id(str(pedido_id))
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return pedido


@router.patch("/pedidos/{pedido_id}/estatus")
async def actualizar_estatus(
    pedido_id: UUID, payload: PedidoUpdateEstatus, repo: PedidoRepoDep
):
    pedido = await repo.update_estatus(str(pedido_id), payload.estatus)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return pedido


@router.get("/pedidos/clusters")
async def detectar_clusters(fecha: date, repo: PedidoRepoDep):
    return await repo.count_by_direccion_y_fecha(fecha)


@router.get("/clientes")
async def listar_clientes(repo: ClienteRepoDep):
    return await repo.list_active()


@router.post("/suscripciones")
async def crear_suscripcion(
    payload: SuscripcionCreate, service: SuscripcionServiceDep
):
    try:
        return await service.crear(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/suscripciones")
async def listar_suscripciones(repo: SuscripcionRepoDep):
    return await repo.list_vencidas()


@router.get("/suscripciones/{suscripcion_id}")
async def obtener_suscripcion(
    suscripcion_id: UUID, repo: SuscripcionRepoDep
):
    sub = await repo.get_by_id(str(suscripcion_id))
    if sub is None:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    return sub


@router.patch("/suscripciones/{suscripcion_id}")
async def actualizar_suscripcion(
    suscripcion_id: UUID,
    payload: SuscripcionUpdate,
    service: SuscripcionServiceDep,
):
    try:
        if payload.dia_entrega is not None:
            return await service.cambiar_dia_entrega(
                str(suscripcion_id), payload.dia_entrega
            )
        raise HTTPException(status_code=400, detail="Sin campos para actualizar")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/ticket/{order_id}.pdf")
async def descargar_ticket(
    order_id: UUID,
    pool: PoolDep,
):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT p.id, p.usuario_id, p.paquete_id, p.direccion, p.cantidad,
                      p.total, p.metodo_pago, p.fecha_entrega, u.nombre, u.telefono,
                      paq.nombre as paquete_nombre
               FROM pedidos p
               JOIN usuarios u ON u.id = p.usuario_id
               JOIN paquetes paq ON paq.id = p.paquete_id
               WHERE p.id = $1""",
            order_id,
        )
        if row is None:
            row = await conn.fetchrow(
                """SELECT s.id, s.usuario_id, s.paquete_id, s.direccion, s.cantidad,
                          0 as total, 'efectivo' as metodo_pago,
                          s.proxima_generacion as fecha_entrega,
                          u.nombre, u.telefono, paq.nombre as paquete_nombre
                   FROM suscripciones s
                   JOIN usuarios u ON u.id = s.usuario_id
                   JOIN paquetes paq ON paq.id = s.paquete_id
                   WHERE s.id = $1""",
                order_id,
            )
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")

    pedido = {
        "id": str(row["id"]),
        "usuario_nombre": row["nombre"],
        "telefono": row["telefono"],
        "paquete_nombre": row["paquete_nombre"],
        "cantidad": row["cantidad"],
        "total": f"{row['total']:.0f}",
        "fecha_entrega": row["fecha_entrega"],
        "direccion": row["direccion"],
        "metodo_pago": row["metodo_pago"],
        "es_suscripcion": False,
    }

    html = _ticket_templates.get_template("checkout/_ticket_pdf.html").render(pedido=pedido)
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ticket_{pedido["id"]}.pdf"'},
    )


@router.post("/suscripciones/procesar")
async def procesar_suscripciones(
    scheduler: SuscripcionSchedulerDep,
):
    generados = await scheduler.procesar_vencidas()
    return {"pedidos_generados": generados}
