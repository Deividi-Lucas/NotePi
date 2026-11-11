"""Backup do banco (com o app rodando), rotação de 30 dias e exportação em Markdown."""

from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from datetime import date, timedelta
from pathlib import Path

from notepi import notas
from notepi import tags as tags_mod
from notepi.texto import slug

_NOME = re.compile(r"^notas-(\d{4}-\d{2}-\d{2})\.db$")


def verificar(caminho: Path) -> bool:
    """True se o arquivo é um banco SQLite íntegro."""
    if not Path(caminho).exists():
        return False
    con = sqlite3.connect(caminho)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.DatabaseError:
        return False
    finally:
        con.close()


def fazer_backup(con: sqlite3.Connection, destino_dir: Path, *, hoje: date | None = None) -> Path:
    """Copia o banco para destino_dir/notas-AAAA-MM-DD.db. Só fica com o nome final se estiver íntegro."""
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    final = destino_dir / f"notas-{(hoje or date.today()).isoformat()}.db"
    temporario = final.with_name(final.name + ".tmp")
    temporario.unlink(missing_ok=True)
    destino = sqlite3.connect(temporario)
    try:
        con.backup(destino)
        destino.execute("PRAGMA journal_mode=DELETE")
    finally:
        destino.close()
    if not verificar(temporario):
        temporario.unlink(missing_ok=True)
        raise RuntimeError("o backup saiu corrompido (integrity_check falhou)")
    temporario.replace(final)
    return final


def listar(destino_dir: Path) -> list[tuple[date, Path]]:
    """Backups existentes, do mais novo para o mais antigo."""
    destino_dir = Path(destino_dir)
    if not destino_dir.is_dir():
        return []
    achados = []
    for arquivo in destino_dir.iterdir():
        m = _NOME.match(arquivo.name)
        if m:
            achados.append((date.fromisoformat(m.group(1)), arquivo))
    return sorted(achados, reverse=True)


def ultimo(destino_dir: Path) -> Path | None:
    existentes = listar(destino_dir)
    return existentes[0][1] if existentes else None


def rotacionar(destino_dir: Path, *, manter_dias: int = 30, hoje: date | None = None) -> list[Path]:
    """Apaga backups com mais de `manter_dias` dias. Devolve os apagados."""
    corte = (hoje or date.today()) - timedelta(days=manter_dias)
    apagados = []
    for dia, arquivo in listar(destino_dir):
        if dia <= corte:
            arquivo.unlink()
            apagados.append(arquivo)
    return apagados


def _aspas(texto: str) -> str:
    return '"' + texto.replace("\\", "\\\\").replace('"', '\\"') + '"'


def exportar_markdown(con: sqlite3.Connection) -> bytes:
    """Um .zip com um arquivo .md por nota ativa (cabeçalho com área, tags e datas)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipado:
        for nota in notas.todas_ativas(con):
            nomes = [t["nome"] for t in tags_mod.da_nota(con, nota["id"])]
            cabecalho = [
                "---",
                f"titulo: {_aspas(nota['titulo'])}",
                f"area: {nota['area']}",
                f"modelo: {nota['modelo'] or ''}",
                "tags: [" + ", ".join(_aspas(n) for n in nomes) + "]",
                f"criada_em: {nota['criada_em']}",
                f"editada_em: {nota['editada_em']}",
                "---",
                "",
            ]
            nome_arquivo = f"{nota['id']:04d}-{slug(nota['titulo'])}.md"
            zipado.writestr(nome_arquivo, "\n".join(cabecalho) + nota["conteudo"] + "\n")
    return buffer.getvalue()
