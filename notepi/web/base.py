"""Templates Jinja2, filtros e variáveis globais usadas nas páginas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from markupsafe import Markup

from notepi.modelos import NOMES as MODELOS
from notepi.notas import AREAS

_PASTA = Path(__file__).parent
ESTATICOS = _PASTA / "static"

templates = Jinja2Templates(directory=_PASTA / "templates")

# html=False: qualquer HTML digitado na nota aparece como texto, nunca é executado.
# breaks=True: uma quebra de linha simples vira quebra de verdade (como se escreve no celular).
_md = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable("table").enable("strikethrough")


def renderizar_markdown(texto: str) -> Markup:
    return Markup(_md.render(texto or ""))


def data_br(iso: str | None) -> str:
    """'2026-11-10T13:05:00+00:00' -> '10/11/2026 10:05' (no fuso do servidor)."""
    if not iso:
        return ""
    return datetime.fromisoformat(iso).astimezone().strftime("%d/%m/%Y %H:%M")


templates.env.filters["markdown"] = renderizar_markdown
templates.env.filters["data_br"] = data_br
templates.env.globals["AREAS"] = AREAS
templates.env.globals["MODELOS"] = MODELOS
# Muda quando o CSS muda, para o celular não continuar com a versão antiga em cache.
templates.env.globals["VERSAO_CSS"] = int((ESTATICOS / "estilo.css").stat().st_mtime)
