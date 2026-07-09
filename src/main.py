import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "static" / "templates"
STATIC_DIR = BASE_DIR / "static"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(),
)

PARTIALS = {
    "welcome": "catalog/welcome.html",
    "swiss": "swiss/welcome.html",
}


def _render(template_name: str, context: dict) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(context)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///granja.db")
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


async def _gather_context() -> dict:
    return {}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    html = _render("index.html", {"request": request})
    return HTMLResponse(html)


@app.get("/partial/{name}", response_class=HTMLResponse)
async def partial_view(request: Request, name: str):
    if name not in PARTIALS:
        return HTMLResponse("Partial no encontrado", status_code=404)
    ctx = await _gather_context()
    ctx["request"] = request
    if request.headers.get("HX-Request") != "true":
        ctx["partial_name"] = PARTIALS[name]
        html = _render("index.html", ctx)
        return HTMLResponse(html)
    html = _render(PARTIALS[name], ctx)
    return HTMLResponse(html)


@app.get("/checkout", response_class=HTMLResponse)
async def checkout_view(request: Request):
    ctx = {"request": request}
    html = _render("checkout/form.html", ctx)
    return HTMLResponse(html)
