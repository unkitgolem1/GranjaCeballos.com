import secrets
from fastapi import HTTPException, Request


def _get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        request.session["csrf_token"] = token
    return token


def csrf_context(request: Request) -> dict:
    return {"csrf_token": _get_csrf_token(request)}


async def validate_csrf(request: Request) -> None:
    token = request.session.get("csrf_token")
    form = await request.form()
    form_token = form.get("csrf_token")
    if not token or not form_token or not secrets.compare_digest(token, form_token):
        raise HTTPException(status_code=403, detail="CSRF token inválido")
