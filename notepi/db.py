"""Conexão com o SQLite, ajustes (PRAGMAs) e migrações do esquema."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VERSAO_ESQUEMA = 1

_MIGRACOES: dict[int, str] = {
    1: """
CREATE TABLE notas (
  id          INTEGER PRIMARY KEY,
  titulo      TEXT NOT NULL,
  conteudo    TEXT NOT NULL DEFAULT '',
  area        TEXT NOT NULL CHECK (area IN
              ('biblia','tecnologia','financas','casa_obra','pintura','geral')),
  modelo      TEXT,
  criada_em   TEXT NOT NULL,
  editada_em  TEXT NOT NULL,
  excluida_em TEXT
);

CREATE TABLE tags (
  id           INTEGER PRIMARY KEY,
  nome         TEXT NOT NULL UNIQUE,
  tipo         TEXT NOT NULL CHECK (tipo IN ('livre','versiculo')),
  livro        INTEGER,
  capitulo     INTEGER,
  verso_inicio INTEGER,
  verso_fim    INTEGER
);

CREATE TABLE nota_tags (
  nota_id INTEGER NOT NULL REFERENCES notas(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
  origem  TEXT NOT NULL CHECK (origem IN ('manual','auto')),
  PRIMARY KEY (nota_id, tag_id)
);

CREATE INDEX idx_nota_tags_tag ON nota_tags(tag_id);
CREATE INDEX idx_tags_versiculo ON tags(livro, capitulo) WHERE tipo = 'versiculo';
CREATE INDEX idx_notas_editada ON notas(editada_em);

CREATE VIRTUAL TABLE notas_fts USING fts5(
  titulo, conteudo,
  content='notas', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER notas_ai AFTER INSERT ON notas BEGIN
  INSERT INTO notas_fts(rowid, titulo, conteudo) VALUES (new.id, new.titulo, new.conteudo);
END;
CREATE TRIGGER notas_ad AFTER DELETE ON notas BEGIN
  INSERT INTO notas_fts(notas_fts, rowid, titulo, conteudo)
  VALUES ('delete', old.id, old.titulo, old.conteudo);
END;
CREATE TRIGGER notas_au AFTER UPDATE OF titulo, conteudo ON notas BEGIN
  INSERT INTO notas_fts(notas_fts, rowid, titulo, conteudo)
  VALUES ('delete', old.id, old.titulo, old.conteudo);
  INSERT INTO notas_fts(rowid, titulo, conteudo) VALUES (new.id, new.titulo, new.conteudo);
END;
""",
}


def agora() -> str:
    """Momento atual em UTC, ISO 8601 com microssegundos (ordena como texto)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def conectar(caminho: str | Path) -> sqlite3.Connection:
    caminho = str(caminho)
    em_memoria = caminho == ":memory:"
    if not em_memoria:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    if not em_memoria:
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
    migrar(con)
    return con


def migrar(con: sqlite3.Connection) -> None:
    atual = con.execute("PRAGMA user_version").fetchone()[0]
    for versao in range(atual + 1, VERSAO_ESQUEMA + 1):
        con.executescript(
            f"BEGIN;\n{_MIGRACOES[versao]}\nPRAGMA user_version = {versao};\nCOMMIT;"
        )
