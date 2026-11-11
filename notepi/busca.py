"""Busca por texto (FTS5) e por versículo, e 'notas relacionadas' por tags em comum."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from markupsafe import Markup, escape

from notepi import tags as tags_mod
from notepi import versiculos
from notepi.versiculos import Referencia

# Marcadores que o snippet() do FTS5 coloca em volta das palavras encontradas.
# Usamos caracteres de controle para poder escapar o HTML antes de trocar por <mark>.
_INI, _FIM = "\x02", "\x03"

_RESUMO = "n.id, n.titulo, n.area, n.modelo, n.editada_em, substr(n.conteudo, 1, 160) AS inicio"


@dataclass(frozen=True)
class Resultado:
    id: int
    titulo: str
    area: str
    editada_em: str
    trecho: Markup


def _consulta_fts(q: str) -> str:
    """'pincel parede' -> '"pincel" "parede"*' (cada termo entre aspas; o último aceita prefixo)."""
    termos = [t for t in q.split() if re.search(r"\w", t)]
    partes = ['"' + t.replace('"', '""') + '"' for t in termos]
    if partes:
        partes[-1] += "*"
    return " ".join(partes)


def _destacar(trecho: str) -> Markup:
    return Markup(str(escape(trecho)).replace(_INI, "<mark>").replace(_FIM, "</mark>"))


def _filtros(area: str | None, modelo: str | None, tag_id: int | None) -> tuple[str, list]:
    sql, params = " AND n.excluida_em IS NULL", []
    if area:
        sql += " AND n.area = ?"
        params.append(area)
    if modelo:
        sql += " AND n.modelo = ?"
        params.append(modelo)
    if tag_id is not None:
        sql += " AND EXISTS (SELECT 1 FROM nota_tags x WHERE x.nota_id = n.id AND x.tag_id = ?)"
        params.append(tag_id)
    return sql, params


def notas_por_versiculo(
    con: sqlite3.Connection,
    ref: Referencia,
    *,
    area: str | None = None,
    modelo: str | None = None,
    tag_id: int | None = None,
) -> list[sqlite3.Row]:
    """Notas com tag de versículo no mesmo capítulo. Se `ref` tem versos, só as que cobrem esses versos
    (ou que citam o capítulo inteiro)."""
    filtro, params = _filtros(area, modelo, tag_id)
    return con.execute(
        f"""SELECT DISTINCT {_RESUMO} FROM notas n
            JOIN nota_tags nt ON nt.nota_id = n.id
            JOIN tags t ON t.id = nt.tag_id
            WHERE t.tipo = 'versiculo' AND t.livro = ? AND t.capitulo = ?
              AND (? IS NULL OR t.verso_inicio IS NULL
                   OR (t.verso_inicio <= ? AND t.verso_fim >= ?))
              {filtro}
            ORDER BY n.editada_em DESC""",
        [ref.livro, ref.capitulo, ref.verso_inicio, ref.verso_fim, ref.verso_inicio, *params],
    ).fetchall()


def buscar(
    con: sqlite3.Connection,
    q: str,
    *,
    area: str | None = None,
    modelo: str | None = None,
    tag_id: int | None = None,
    limite: int = 50,
) -> list[Resultado]:
    q = q.strip()
    filtro, params = _filtros(area, modelo, tag_id)
    if not q:
        linhas = con.execute(
            f"SELECT {_RESUMO} FROM notas n WHERE 1 = 1 {filtro} ORDER BY n.editada_em DESC LIMIT ?",
            [*params, limite],
        ).fetchall()
        return [Resultado(r["id"], r["titulo"], r["area"], r["editada_em"], escape(r["inicio"])) for r in linhas]

    resultados: list[Resultado] = []
    vistos: set[int] = set()
    ref = versiculos.referencia_exata(q)
    if ref is not None:
        marca = Markup("<mark>") + ref.canonica + Markup("</mark>")
        for r in notas_por_versiculo(con, ref, area=area, modelo=modelo, tag_id=tag_id):
            resultados.append(Resultado(r["id"], r["titulo"], r["area"], r["editada_em"], marca))
            vistos.add(r["id"])

    consulta = _consulta_fts(q)
    if consulta:
        try:
            linhas = con.execute(
                f"""SELECT n.id, n.titulo, n.area, n.editada_em,
                           snippet(notas_fts, -1, ?, ?, '…', 12) AS trecho
                    FROM notas_fts JOIN notas n ON n.id = notas_fts.rowid
                    WHERE notas_fts MATCH ? {filtro}
                    ORDER BY bm25(notas_fts) LIMIT ?""",
                [_INI, _FIM, consulta, *params, limite],
            ).fetchall()
        except sqlite3.OperationalError:
            linhas = []  # consulta que o FTS5 não entende: fica só com o que já achou
        for r in linhas:
            if r["id"] not in vistos:
                resultados.append(
                    Resultado(r["id"], r["titulo"], r["area"], r["editada_em"], _destacar(r["trecho"]))
                )
    return resultados[:limite]


def relacionadas(con: sqlite3.Connection, nota_id: int, limite: int = 10) -> list[sqlite3.Row]:
    """Outras notas ordenadas pela quantidade de tags em comum.
    Versículos contam como 'em comum' se forem do mesmo livro e capítulo."""
    return con.execute(
        """WITH minhas AS (
             SELECT t.* FROM tags t JOIN nota_tags nt ON nt.tag_id = t.id WHERE nt.nota_id = :id
           )
           SELECT n.id, n.titulo, n.area, n.editada_em, COUNT(DISTINCT m.id) AS comuns
           FROM notas n
           JOIN nota_tags nt ON nt.nota_id = n.id
           JOIN tags t ON t.id = nt.tag_id
           JOIN minhas m ON m.id = t.id
                OR (m.tipo = 'versiculo' AND t.tipo = 'versiculo'
                    AND m.livro = t.livro AND m.capitulo = t.capitulo)
           WHERE n.id != :id AND n.excluida_em IS NULL
           GROUP BY n.id
           ORDER BY comuns DESC, n.editada_em DESC
           LIMIT :limite""",
        {"id": nota_id, "limite": limite},
    ).fetchall()


def notas_da_tag(con: sqlite3.Connection, tag_id: int) -> list[sqlite3.Row]:
    """Notas de uma tag. Para tag de versículo, todas as notas do capítulo inteiro."""
    tag = tags_mod.obter(con, tag_id)
    if tag is None:
        return []
    if tag["tipo"] == "versiculo":
        return notas_por_versiculo(con, Referencia(tag["livro"], tag["capitulo"]))
    return con.execute(
        f"""SELECT {_RESUMO} FROM notas n JOIN nota_tags nt ON nt.nota_id = n.id
            WHERE nt.tag_id = ? AND n.excluida_em IS NULL ORDER BY n.editada_em DESC""",
        (tag_id,),
    ).fetchall()
