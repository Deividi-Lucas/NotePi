"""Tarefa diária (systemd timer às 03:00): esvaziar a lixeira antiga, fazer backup e rotacionar.

Uso: python -m notepi.manutencao
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from notepi import backup, notas
from notepi.config import Config, carregar
from notepi.db import conectar

log = logging.getLogger("notepi.manutencao")


def executar(config: Config) -> Path:
    if config.backup_exigir_montagem and not os.path.ismount(config.backup_dir):
        raise RuntimeError(f"{config.backup_dir} não está montado (o pendrive está conectado?)")
    con = conectar(config.db)
    try:
        removidas = notas.purgar_lixeira(con)
        caminho = backup.fazer_backup(con, config.backup_dir)
        apagados = backup.rotacionar(config.backup_dir)
    finally:
        con.close()
    log.info(
        "lixeira: %d nota(s) apagada(s); backup: %s; backups antigos removidos: %d",
        removidas, caminho, len(apagados),
    )
    return caminho


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        executar(carregar())
    except Exception:
        log.exception("a manutenção falhou")
        sys.exit(1)


if __name__ == "__main__":
    main()
