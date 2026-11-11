"""Modelos de nota: arquivos Markdown nesta pasta. Para criar um novo, adicione o .md e o nome em NOMES."""

from __future__ import annotations

from datetime import date
from pathlib import Path

NOMES = {"culto": "Culto", "guia_requisitos": "Guia de requisitos"}

_PASTA = Path(__file__).parent


def carregar(nome: str, hoje: date | None = None) -> str:
    if nome not in NOMES:
        raise KeyError(nome)
    texto = (_PASTA / f"{nome}.md").read_text(encoding="utf-8")
    return texto.replace("{{hoje}}", (hoje or date.today()).strftime("%d/%m/%Y"))
