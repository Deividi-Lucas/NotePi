"""Cria o app FastAPI. No Pi: uvicorn notepi.app:app --host 127.0.0.1 --port 8000"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from notepi.config import Config, carregar
from notepi.web import rotas
from notepi.web.base import ESTATICOS, templates
from notepi.web.limites import LimiteDeTamanho

log = logging.getLogger("notepi")


CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


def _cabecalhos_de_seguranca(resposta) -> None:
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Content-Security-Policy"] = CSP
    resposta.headers["Referrer-Policy"] = "no-referrer"


def _veio_de_outro_site(request: Request) -> bool:
    """CSRF: POST que o navegador diz (Sec-Fetch-Site ou Origin) ter saído de outro site."""
    if request.method != "POST":
        return False
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site not in ("same-origin", "none")
    origem = request.headers.get("origin")
    if origem is not None:  # "null" também cai aqui: netloc vazio nunca é igual ao Host
        return urlsplit(origem).netloc != request.headers.get("host", "")
    return False


def criar_app(config: Config | None = None) -> FastAPI:
    app = FastAPI(title="NotePi", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config or carregar()
    app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")
    app.include_router(rotas.router)

    @app.middleware("http")
    async def protecao(request: Request, call_next):
        usuarios = request.app.state.config.usuarios
        if usuarios and not request.url.path.startswith("/static/") and (
            request.headers.get("tailscale-user-login") not in usuarios
        ):
            resposta = templates.TemplateResponse(
                request, "erro.html", {"mensagem": "Acesso não autorizado."}, status_code=403
            )
        elif _veio_de_outro_site(request):
            resposta = templates.TemplateResponse(
                request, "erro.html", {"mensagem": "Pedido bloqueado: veio de outro site."}, status_code=403
            )
        else:
            resposta = await call_next(request)
        _cabecalhos_de_seguranca(resposta)
        return resposta

    # Registrado por último = mais externo: confere o Host antes de qualquer outra coisa (DNS rebinding).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(app.state.config.hosts))
    app.add_middleware(LimiteDeTamanho)

    @app.exception_handler(Exception)
    async def erro_inesperado(request: Request, exc: Exception):
        log.exception("erro inesperado em %s %s", request.method, request.url.path)
        resposta = templates.TemplateResponse(request, "erro.html", {}, status_code=500)
        _cabecalhos_de_seguranca(resposta)  # este handler roda fora do middleware acima
        return resposta

    return app


app = criar_app()
