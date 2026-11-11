"""Cria o app FastAPI. No Pi: uvicorn notepi.app:app --host 127.0.0.1 --port 8000"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from notepi.config import Config, carregar
from notepi.web import rotas
from notepi.web.base import ESTATICOS, templates

log = logging.getLogger("notepi")


def criar_app(config: Config | None = None) -> FastAPI:
    app = FastAPI(title="NotePi", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config or carregar()
    app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")
    app.include_router(rotas.router)

    @app.middleware("http")
    async def protecao(request: Request, call_next):
        origem = request.headers.get("sec-fetch-site")
        if request.method == "POST" and origem is not None and origem not in ("same-origin", "none"):
            resposta = templates.TemplateResponse(
                request, "erro.html", {"mensagem": "Pedido bloqueado: veio de outro site."}, status_code=403
            )
        else:
            resposta = await call_next(request)
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        return resposta

    @app.exception_handler(Exception)
    async def erro_inesperado(request: Request, exc: Exception):
        log.exception("erro inesperado em %s %s", request.method, request.url.path)
        return templates.TemplateResponse(request, "erro.html", {}, status_code=500)

    return app


app = criar_app()
