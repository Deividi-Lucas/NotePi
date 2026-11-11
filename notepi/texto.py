"""Funções pequenas de texto usadas em vários módulos."""

from __future__ import annotations

import re
import unicodedata


def remover_acentos(texto: str) -> str:
    """'Hermenêutica' -> 'Hermeneutica'."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def slug(texto: str, maximo: int = 50) -> str:
    """'Pincel para parede!' -> 'pincel-para-parede'. Nunca devolve vazio."""
    base = re.sub(r"[^a-z0-9]+", "-", remover_acentos(texto).lower()).strip("-")
    return base[:maximo].rstrip("-") or "nota"
