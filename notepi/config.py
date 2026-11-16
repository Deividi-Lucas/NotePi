"""Configuração lida das variáveis de ambiente (no Pi: /etc/notepi.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    db: Path
    backup_dir: Path
    backup_exigir_montagem: bool = False
    hosts: tuple[str, ...] = ("127.0.0.1", "localhost")


def _lista(nome: str) -> tuple[str, ...]:
    bruto = os.environ.get(nome, "")
    return tuple(item.strip() for item in bruto.split(",") if item.strip())


def carregar() -> Config:
    dados = Path(os.environ.get("NOTEPI_DADOS", "dados"))
    return Config(
        db=Path(os.environ.get("NOTEPI_DB", dados / "notas.db")),
        backup_dir=Path(os.environ.get("NOTEPI_BACKUP_DIR", dados / "backup")),
        backup_exigir_montagem=os.environ.get("NOTEPI_BACKUP_EXIGIR_MONTAGEM") == "1",
        # lista vazia viraria "qualquer host" no Starlette; por isso cai no padrão
        hosts=_lista("NOTEPI_HOSTS") or ("127.0.0.1", "localhost"),
    )
