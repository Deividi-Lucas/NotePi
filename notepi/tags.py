"""Tags livres (digitadas) e de versículo (detectadas no texto ou digitadas).

As funções que alteram dados NÃO fazem commit: quem chama (notas.py) abre a transação.
"""

from __future__ import annotations

import re
import sqlite3

from notepi import versiculos
from notepi.versiculos import Referencia


def normalizar_livre(nome: str) -> str:
    """' #Pintura  Parede ' -> 'pintura parede'."""
    return re.sub(r"\s+", " ", nome.strip().lstrip("#").strip()).lower()


def separar(texto: str) -> list[str]:
    """'pintura, compra, pintura' -> ['pintura', 'compra'] (sem vazios nem repetidos)."""
    nomes: list[str] = []
    for parte in texto.split(","):
        parte = parte.strip()
        if parte and parte not in nomes:
            nomes.append(parte)
    return nomes


def _id_livre(con: sqlite3.Connection, nome: str) -> int:
    con.execute(
        "INSERT INTO tags(nome, tipo) VALUES (?, 'livre') ON CONFLICT(nome) DO NOTHING", (nome,)
    )
    return con.execute("SELECT id FROM tags WHERE nome = ?", (nome,)).fetchone()["id"]


def _id_versiculo(con: sqlite3.Connection, ref: Referencia) -> int:
    con.execute(
        """INSERT INTO tags(nome, tipo, livro, capitulo, verso_inicio, verso_fim)
           VALUES (?, 'versiculo', ?, ?, ?, ?) ON CONFLICT(nome) DO NOTHING""",
        (ref.canonica, ref.livro, ref.capitulo, ref.verso_inicio, ref.verso_fim),
    )
    return con.execute("SELECT id FROM tags WHERE nome = ?", (ref.canonica,)).fetchone()["id"]


def _id_para_nome(con: sqlite3.Connection, nome: str) -> int | None:
    ref = versiculos.referencia_exata(nome)
    if ref is not None:
        return _id_versiculo(con, ref)
    livre = normalizar_livre(nome)
    return _id_livre(con, livre) if livre else None


def definir_manuais(con: sqlite3.Connection, nota_id: int, nomes: list[str] | tuple[str, ...]) -> None:
    """Troca as tags manuais da nota por `nomes`. Um nome que é versículo vira tag de versículo."""
    con.execute("DELETE FROM nota_tags WHERE nota_id = ? AND origem = 'manual'", (nota_id,))
    for nome in nomes:
        tag_id = _id_para_nome(con, nome)
        if tag_id is None:
            continue
        con.execute(
            """INSERT INTO nota_tags(nota_id, tag_id, origem) VALUES (?, ?, 'manual')
               ON CONFLICT(nota_id, tag_id) DO UPDATE SET origem = 'manual'""",
            (nota_id, tag_id),
        )


def sincronizar_auto(con: sqlite3.Connection, nota_id: int, texto: str) -> None:
    """Recalcula as tags automáticas (versículos achados no texto). Tags manuais ficam como estão."""
    ids = [_id_versiculo(con, ref) for ref in versiculos.encontrar(texto)]
    marcas = ",".join("?" * len(ids))
    con.execute(
        f"DELETE FROM nota_tags WHERE nota_id = ? AND origem = 'auto' AND tag_id NOT IN ({marcas})",
        (nota_id, *ids),
    )
    for tag_id in ids:
        con.execute(
            """INSERT INTO nota_tags(nota_id, tag_id, origem) VALUES (?, ?, 'auto')
               ON CONFLICT(nota_id, tag_id) DO NOTHING""",
            (nota_id, tag_id),
        )


_ORDEM = "t.tipo = 'livre', t.livro, t.capitulo, t.verso_inicio, t.nome"


def da_nota(con: sqlite3.Connection, nota_id: int) -> list[sqlite3.Row]:
    """Tags da nota: versículos primeiro (em ordem bíblica), depois as livres."""
    return con.execute(
        f"""SELECT t.id, t.nome, t.tipo, nt.origem FROM tags t
            JOIN nota_tags nt ON nt.tag_id = t.id
            WHERE nt.nota_id = ? ORDER BY {_ORDEM}""",
        (nota_id,),
    ).fetchall()


def nomes_manuais(con: sqlite3.Connection, nota_id: int) -> list[str]:
    return [t["nome"] for t in da_nota(con, nota_id) if t["origem"] == "manual"]


def obter(con: sqlite3.Connection, tag_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM tags WHERE id = ?", (tag_id,)).fetchone()


def listar_com_contagem(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Tags usadas por pelo menos uma nota ativa, com a quantidade de notas."""
    return con.execute(
        f"""SELECT t.*, COUNT(n.id) AS total FROM tags t
            JOIN nota_tags nt ON nt.tag_id = t.id
            JOIN notas n ON n.id = nt.nota_id AND n.excluida_em IS NULL
            GROUP BY t.id ORDER BY {_ORDEM}"""
    ).fetchall()


def remover_orfas(con: sqlite3.Connection) -> int:
    cur = con.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM nota_tags)")
    return cur.rowcount
