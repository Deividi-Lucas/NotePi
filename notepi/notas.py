"""Criar, ler, editar, excluir (lixeira) e restaurar notas."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from notepi import modelos
from notepi import tags as tags_mod
from notepi.db import agora

AREAS = {
    "biblia": "Bíblia",
    "tecnologia": "Tecnologia",
    "financas": "Finanças",
    "casa_obra": "Casa e obra",
    "pintura": "Pintura",
    "geral": "Geral",
}

_RESUMO = "id, titulo, area, modelo, editada_em, excluida_em, substr(conteudo, 1, 160) AS inicio"


#  e  quebram a busca (FTS5) e não têm uso em texto de nota.
_CONTROLE = str.maketrans("", "", "")


class NotaNaoEncontrada(LookupError):
    pass


class ConflitoEdicao(Exception):
    """A nota foi salva em outro aparelho depois que este formulário foi aberto."""

    def __init__(self, atual: sqlite3.Row) -> None:
        super().__init__("nota alterada em outro lugar")
        self.atual = atual


def titulo_efetivo(titulo: str, conteudo: str, momento: datetime | None = None) -> str:
    """Título digitado; se vazio, a primeira linha com texto; se nada, 'Nota de dd/mm/aaaa'."""
    if titulo.strip():
        return titulo.strip()
    for linha in conteudo.splitlines():
        limpa = linha.strip().strip("#*_ ").strip()
        if limpa:
            return limpa[:120]
    return f"Nota de {(momento or datetime.now()):%d/%m/%Y}"


def _validar(area: str, modelo: str | None) -> None:
    if area not in AREAS:
        raise ValueError(f"área inválida: {area!r}")
    if modelo is not None and modelo not in modelos.NOMES:
        raise ValueError(f"modelo inválido: {modelo!r}")


def criar(
    con: sqlite3.Connection,
    *,
    titulo: str,
    conteudo: str,
    area: str,
    modelo: str | None = None,
    tags: list[str] | tuple[str, ...] = (),
) -> int:
    _validar(area, modelo)
    titulo, conteudo = titulo.translate(_CONTROLE), conteudo.translate(_CONTROLE)
    momento = agora()
    titulo_final = titulo_efetivo(titulo, conteudo)
    with con:
        cur = con.execute(
            """INSERT INTO notas(titulo, conteudo, area, modelo, criada_em, editada_em)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (titulo_final, conteudo, area, modelo, momento, momento),
        )
        nota_id = cur.lastrowid
        tags_mod.definir_manuais(con, nota_id, tags)
        tags_mod.sincronizar_auto(con, nota_id, f"{titulo_final}\n{conteudo}")
    return nota_id


def obter(con: sqlite3.Connection, nota_id: int, *, incluir_excluidas: bool = False) -> sqlite3.Row | None:
    sql = "SELECT * FROM notas WHERE id = ?"
    if not incluir_excluidas:
        sql += " AND excluida_em IS NULL"
    return con.execute(sql, (nota_id,)).fetchone()


def editar(
    con: sqlite3.Connection,
    nota_id: int,
    *,
    titulo: str,
    conteudo: str,
    area: str,
    tags: list[str] | tuple[str, ...],
    editada_em_base: str,
) -> None:
    """Salva a edição. `editada_em_base` é o editada_em que o formulário carregou."""
    titulo, conteudo = titulo.translate(_CONTROLE), conteudo.translate(_CONTROLE)
    with con:
        atual = obter(con, nota_id)
        if atual is None:
            raise NotaNaoEncontrada(nota_id)
        _validar(area, atual["modelo"])
        if atual["editada_em"] != editada_em_base:
            raise ConflitoEdicao(atual)
        titulo_final = titulo_efetivo(titulo, conteudo)
        cur = con.execute(
            "UPDATE notas SET titulo = ?, conteudo = ?, area = ?, editada_em = ? WHERE id = ? AND editada_em = ?",
            (titulo_final, conteudo, area, agora(), nota_id, editada_em_base),
        )
        if cur.rowcount == 0:
            # outro aparelho salvou entre a checagem acima e este UPDATE
            raise ConflitoEdicao(obter(con, nota_id))
        tags_mod.definir_manuais(con, nota_id, tags)
        tags_mod.sincronizar_auto(con, nota_id, f"{titulo_final}\n{conteudo}")


def excluir(con: sqlite3.Connection, nota_id: int) -> None:
    with con:
        cur = con.execute(
            "UPDATE notas SET excluida_em = ? WHERE id = ? AND excluida_em IS NULL", (agora(), nota_id)
        )
    if cur.rowcount == 0:
        raise NotaNaoEncontrada(nota_id)


def restaurar(con: sqlite3.Connection, nota_id: int) -> None:
    with con:
        cur = con.execute(
            "UPDATE notas SET excluida_em = NULL WHERE id = ? AND excluida_em IS NOT NULL", (nota_id,)
        )
    if cur.rowcount == 0:
        raise NotaNaoEncontrada(nota_id)


def recentes(con: sqlite3.Connection, *, area: str | None = None, limite: int = 30) -> list[sqlite3.Row]:
    return con.execute(
        f"""SELECT {_RESUMO} FROM notas
            WHERE excluida_em IS NULL AND (? IS NULL OR area = ?)
            ORDER BY editada_em DESC LIMIT ?""",
        (area, area, limite),
    ).fetchall()


def lixeira(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        f"SELECT {_RESUMO} FROM notas WHERE excluida_em IS NOT NULL ORDER BY excluida_em DESC"
    ).fetchall()


def purgar_lixeira(con: sqlite3.Connection, *, dias: int = 30, agora_: datetime | None = None) -> int:
    """Apaga de vez as notas que estão na lixeira há mais de `dias` dias. Devolve quantas."""
    limite = ((agora_ or datetime.now(timezone.utc)) - timedelta(days=dias)).isoformat(
        timespec="microseconds"
    )
    with con:
        cur = con.execute(
            "DELETE FROM notas WHERE excluida_em IS NOT NULL AND excluida_em < ?", (limite,)
        )
        tags_mod.remover_orfas(con)
    return cur.rowcount


def todas_ativas(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM notas WHERE excluida_em IS NULL ORDER BY id").fetchall()


def contar_ativas(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM notas WHERE excluida_em IS NULL").fetchone()[0]
