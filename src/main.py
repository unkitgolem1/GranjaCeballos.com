import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.api import router as api_router
from src.infrastructure.cache import MemoryCache
from src.infrastructure.database import create_pool
from src.infrastructure.limiter import limiter
from src.infrastructure.http_cache import CacheControlMiddleware
from src.infrastructure.security import SecurityHeadersMiddleware
from src.pages import router as pages_router
from src.logistic.interfaces.web.router import router as logistic_router

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())
SERVER_MODE = os.getenv("SERVER_MODE", "uvicorn")
ASYNC_DEBUG = os.getenv("ASYNC_DEBUG", "").lower() in ("1", "true", "yes")
_PROD = os.getenv("ENVIRONMENT", "").lower() == "production"

_log = logging.getLogger("uvicorn.access")
_log.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"
))
_log.addHandler(_handler)

logger = logging.getLogger(__name__)


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
                    "t": "http",
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": message.get("status"),
                    "ms": round(elapsed_ms, 2),
                    "server": SERVER_MODE,
                }))
            await send(message)

        await self.app(scope, receive, send_with_metrics)


async def _async_debug_hook(loop: asyncio.AbstractEventLoop, context: dict):
    source = context.get("source_traceback")
    msg = context.get("message", "")
    if source:
        _log.warning(
            "ASYNCIO_BLOCK %.3fs | %s | %s",
            context.get("duration", 0),
            msg,
            "".join(source.format()),
        )
    else:
        _log.warning("ASYNCIO_BLOCK %s", msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("DISABLE_ACCESS_LOG", "0") == "1":
        logging.getLogger("uvicorn.access").disabled = True

    if ASYNC_DEBUG:
        loop = asyncio.get_running_loop()
        loop.slow_callback_duration = 0.05
        loop.set_exception_handler(_async_debug_hook)
        _log.warning(
            "ASYNC_DEBUG=1 loop.slow_callback_duration=0.05s — stack traces on block"
        )

    dsn = os.environ["DATABASE_URL"]
    pool = await create_pool(dsn)
    app.state.db_pool = pool
    app.state.cache = MemoryCache(default_ttl=60)
    yield
    await pool.close()


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": "Error interno del servidor"},
            status_code=500,
        )
    return HTMLResponse("Error interno del servidor", status_code=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[] if _PROD else ["*"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=[],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CacheControlMiddleware)
app.add_middleware(LatencyMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=_PROD,
    same_site="lax",
    session_cookie="session",
    max_age=86400 * 7,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api_router)
app.include_router(pages_router)
app.include_router(logistic_router)
