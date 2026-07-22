import asyncio
import io
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

import asyncpg
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

_TICKET_TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "static" / "templates"
)
_jinja_env = Environment(loader=FileSystemLoader(str(_TICKET_TEMPLATES_DIR)))


def render_ticket_html(pedido: dict, whatsapp_phone: str) -> str:
    tmpl = _jinja_env.get_template("checkout/_ticket_pdf.html")
    return tmpl.render(pedido=pedido, whatsapp_phone=whatsapp_phone)


def _generar_pdf_sync(html: str) -> Optional[bytes]:
    try:
        import weasyprint as _w
        return _w.HTML(string=html).write_pdf()
    except (ImportError, OSError, RuntimeError):
        try:
            from xhtml2pdf import pisa
            buf = io.BytesIO()
            pisa.CreatePDF(io.StringIO(html), dest=buf)
            return buf.getvalue()
        except (ImportError, OSError, RuntimeError) as e2:
            logger.warning(
                "PDF no disponible (weasyprint + xhtml2pdf fallaron). %s", e2
            )
            return None


async def generar_pdf(html: str, pool: asyncpg.Pool, ticket_id: UUID) -> Optional[bytes]:
    loop = asyncio.get_running_loop()
    pdf_bytes = await loop.run_in_executor(None, _generar_pdf_sync, html)
    if pdf_bytes is not None:
        await _store(pool, ticket_id, pdf_bytes)
    return pdf_bytes


async def get_cached(pool: asyncpg.Pool, ticket_id: UUID) -> Optional[bytes]:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT pdf_bytes FROM pdf_cache WHERE ticket_id = $1",
            ticket_id,
        )


async def _store(pool: asyncpg.Pool, ticket_id: UUID, pdf_bytes: bytes) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO pdf_cache (ticket_id, pdf_bytes)
               VALUES ($1, $2)
               ON CONFLICT (ticket_id) DO NOTHING""",
            ticket_id,
            pdf_bytes,
        )


async def pre_generar_background(
    pool: asyncpg.Pool, pedido: dict, whatsapp_phone: str
) -> None:
    try:
        html = render_ticket_html(pedido, whatsapp_phone)
        loop = asyncio.get_running_loop()
        pdf_bytes = await loop.run_in_executor(None, _generar_pdf_sync, html)
        if pdf_bytes:
            await _store(pool, UUID(pedido["id"]), pdf_bytes)
            logger.info("PDF pre-generado para ticket %s", pedido["id"])
    except Exception:
        logger.exception("Error pre-generando PDF para ticket %s", pedido["id"])
