"""
Minimal FastAPI app que replica los mismos patrones de nuestra app real:
- Jinja2 template rendering (síncrono)
- LatencyMiddleware
- SlowAPIMiddleware + SessionMiddleware
- Endpoints GET (I/O simulado con asyncio.sleep)
- Endpoint POST (procesamiento de formulario)
- JSON response con datos serializados
- Headers de sesión

Sin dependencia de base de datos — ideal para benchmark Uvicorn vs Granian.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = STATIC_DIR / "templates"

SECRET_KEY = os.getenv("SECRET_KEY", "benchmark-secret-key")
SERVER_MODE = os.getenv("SERVER_MODE", "uvicorn")

_log = logging.getLogger("uvicorn.access")


class LatencyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        async def send_with_metrics(message):
            if message["type"] == "http.response.start":
                elapsed_ms = (time.perf_counter() - start) * 1000
                _log.info(json.dumps({
                    "t": "http", "method": scope.get("method"),
                    "path": scope.get("path"), "status": message.get("status"),
                    "ms": round(elapsed_ms, 2), "server": SERVER_MODE,
                }))
            await send(message)
        await self.app(scope, receive, send_with_metrics)


app = FastAPI()
app.add_middleware(LatencyMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Datos simulados (como los paquetes reales)
PAQUETES = [
    {"id": "1", "nombre": "Paquete Básico", "precio": 150, "tiers": []},
    {"id": "2", "nombre": "Paquete Premium", "precio": 280, "tiers": []},
    {"id": "3", "nombre": "Paquete Familiar", "precio": 420, "tiers": [{"cantidad": 2, "precio": 750}, {"cantidad": 4, "precio": 1400}]},
]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="catalog/index.html",
        context={"paquetes": PAQUETES},
    )


@app.get("/api/paquetes")
async def paquetes():
    await asyncio.sleep(0.002)  # simula query DB (~2ms)
    return JSONResponse(PAQUETES)


@app.post("/checkout", response_class=HTMLResponse)
async def checkout(
    request: Request,
    nombre: str = Form(...),
    telefono: str = Form(...),
    paquete_id: str = Form(...),
    direccion: str = Form(...),
):
    # Simula validación Yucatán + creación (como en la app real)
    if "yucatán" not in direccion.lower():
        return templates.TemplateResponse(
            request=request, name="catalog/index.html",
            context={"paquetes": PAQUETES, "error": "Solo entregamos en Yucatán"},
        )
    await asyncio.sleep(0.005)  # simula INSERT DB (~5ms)
    return templates.TemplateResponse(
        request=request, name="checkout/result.html",
        context={"success": True, "mensaje": "Pedido creado exitosamente"},
    )
