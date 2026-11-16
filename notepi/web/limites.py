"""Middleware ASGI que recusa pedidos com corpo grande demais (413)."""

from __future__ import annotations

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LIMITE_CORPO = 1_000_000  # bytes; uma nota de texto nunca chega perto disso


class LimiteDeTamanho:
    def __init__(self, app: ASGIApp, limite: int = LIMITE_CORPO) -> None:
        self.app = app
        self.limite = limite

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        resposta = PlainTextResponse("Pedido grande demais.", status_code=413)
        declarado = dict(scope["headers"]).get(b"content-length", b"")
        if declarado.isdigit() and int(declarado) > self.limite:
            await resposta(scope, receive, send)
            return

        recebidos = 0
        iniciou = False
        estourou = False

        async def contar() -> Message:
            # Ao estourar o limite, responde 413 na hora e faz o app ver o cliente "desconectar"
            # (o FastAPI trocaria uma exceção aqui por um 400 genérico).
            nonlocal recebidos, estourou
            if estourou:
                return {"type": "http.disconnect"}
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebidos += len(mensagem.get("body", b""))
                if recebidos > self.limite:
                    estourou = True
                    if not iniciou:
                        await resposta(scope, receive, send)
                    return {"type": "http.disconnect"}
            return mensagem

        async def enviar(mensagem: Message) -> None:
            nonlocal iniciou
            if estourou:
                return
            iniciou = True
            await send(mensagem)

        await self.app(scope, contar, enviar)
