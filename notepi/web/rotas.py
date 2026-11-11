"""Rotas HTML do NotePi."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from notepi import backup, busca, livros, modelos, notas, versiculos
from notepi import tags as tags_mod
from notepi.db import conectar
from notepi.web.base import templates

router = APIRouter(default_response_class=HTMLResponse)


def obter_con(request: Request):
    con = conectar(request.app.state.config.db)
    try:
        yield con
    finally:
        con.close()


Con = Annotated[sqlite3.Connection, Depends(obter_con)]
Campo = Annotated[str, Form()]


def _pagina(request: Request, nome: str, contexto: dict | None = None, status: int = 200):
    return templates.TemplateResponse(request, nome, contexto or {}, status_code=status)


def _nao_encontrada(request: Request):
    return _pagina(request, "erro.html", {"mensagem": "Nota não encontrada."}, 404)


def _ir_para(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _area_ou(area: str | None, padrao: str) -> str:
    return area if area in notas.AREAS else padrao


def _contexto_form(*, nota_id, titulo, conteudo, area, modelo, tags_texto, editada_em_base, chave) -> dict:
    return {
        "nota_id": nota_id,
        "titulo": titulo,
        "conteudo": conteudo,
        "area": area,
        "modelo": modelo,
        "tags_texto": tags_texto,
        "editada_em_base": editada_em_base,
        "chave_rascunho": chave,
    }


# ---------- início e notas ----------


@router.get("/")
def inicio(request: Request, con: Con, area: str | None = None):
    area = area if area in notas.AREAS else None
    return _pagina(request, "inicio.html", {"notas": notas.recentes(con, area=area), "area": area})


@router.get("/notas/nova")
def nova(request: Request, modelo: str | None = None, area: str | None = None):
    modelo = modelo if modelo in modelos.NOMES else None
    contexto = _contexto_form(
        nota_id=None,
        titulo="",
        conteudo=modelos.carregar(modelo) if modelo else "",
        area=_area_ou(area, "biblia" if modelo == "culto" else "geral"),
        modelo=modelo,
        tags_texto="",
        editada_em_base="",
        chave="nova",
    )
    return _pagina(request, "nota_form.html", contexto)


@router.post("/notas")
def criar(request: Request, con: Con, titulo: Campo = "", conteudo: Campo = "", area: Campo = "geral",
          modelo: Campo = "", tags: Campo = ""):
    nota_id = notas.criar(
        con,
        titulo=titulo,
        conteudo=conteudo,
        area=_area_ou(area, "geral"),
        modelo=modelo if modelo in modelos.NOMES else None,
        tags=tags_mod.separar(tags),
    )
    return _ir_para(f"/notas/{nota_id}")


@router.get("/notas/{nota_id}")
def ver(request: Request, con: Con, nota_id: int):
    nota = notas.obter(con, nota_id)
    if nota is None:
        return _nao_encontrada(request)
    return _pagina(request, "nota_ver.html", {
        "nota": nota,
        "tags": tags_mod.da_nota(con, nota_id),
        "relacionadas": busca.relacionadas(con, nota_id),
    })


@router.get("/notas/{nota_id}/editar")
def editar_form(request: Request, con: Con, nota_id: int):
    nota = notas.obter(con, nota_id)
    if nota is None:
        return _nao_encontrada(request)
    contexto = _contexto_form(
        nota_id=nota_id,
        titulo=nota["titulo"],
        conteudo=nota["conteudo"],
        area=nota["area"],
        modelo=nota["modelo"],
        tags_texto=", ".join(tags_mod.nomes_manuais(con, nota_id)),
        editada_em_base=nota["editada_em"],
        chave=f"editar-{nota_id}",
    )
    return _pagina(request, "nota_form.html", contexto)


@router.post("/notas/{nota_id}")
def salvar(request: Request, con: Con, nota_id: int, titulo: Campo = "", conteudo: Campo = "",
           area: Campo = "geral", tags: Campo = "", editada_em_base: Campo = ""):
    area = _area_ou(area, "geral")
    try:
        notas.editar(con, nota_id, titulo=titulo, conteudo=conteudo, area=area,
                     tags=tags_mod.separar(tags), editada_em_base=editada_em_base)
    except notas.NotaNaoEncontrada:
        return _nao_encontrada(request)
    except notas.ConflitoEdicao as conflito:
        contexto = _contexto_form(
            nota_id=nota_id,
            titulo=titulo,
            conteudo=conteudo,
            area=area,
            modelo=conflito.atual["modelo"],
            tags_texto=tags,
            editada_em_base=conflito.atual["editada_em"],  # salvar de novo sobrescreve, de propósito
            chave=f"editar-{nota_id}",
        )
        contexto["atual"] = conflito.atual
        return _pagina(request, "conflito.html", contexto, 409)
    return _ir_para(f"/notas/{nota_id}")


@router.post("/notas/{nota_id}/excluir")
def excluir(request: Request, con: Con, nota_id: int):
    try:
        notas.excluir(con, nota_id)
    except notas.NotaNaoEncontrada:
        return _nao_encontrada(request)
    return _ir_para("/")


@router.post("/notas/{nota_id}/restaurar")
def restaurar(request: Request, con: Con, nota_id: int):
    try:
        notas.restaurar(con, nota_id)
    except notas.NotaNaoEncontrada:
        return _nao_encontrada(request)
    return _ir_para(f"/notas/{nota_id}")


# ---------- busca, tags, lixeira, prévia, saúde e exportação ----------


@router.get("/busca")
def pagina_busca(request: Request, con: Con, q: str = "", area: str | None = None,
                 modelo: str | None = None, tag: str | None = None):
    area = area if area in notas.AREAS else None
    modelo = modelo if modelo in modelos.NOMES else None
    tag_obj = tags_mod.obter(con, int(tag)) if tag and tag.isascii() and tag.isdigit() else None
    filtrando = bool(q.strip() or area or modelo or tag_obj)
    resultados = (
        busca.buscar(con, q, area=area, modelo=modelo, tag_id=tag_obj["id"] if tag_obj else None)
        if filtrando else []
    )
    return _pagina(request, "busca.html", {
        "q": q, "area": area, "modelo": modelo, "tag": tag_obj,
        "filtrando": filtrando, "resultados": resultados,
    })


@router.get("/tags")
def pagina_tags(request: Request, con: Con):
    livres, por_livro = [], {}
    for t in tags_mod.listar_com_contagem(con):
        if t["tipo"] == "livre":
            livres.append(t)
        else:
            por_livro.setdefault(livros.por_numero(t["livro"]).nome, []).append(t)
    return _pagina(request, "tags.html", {"livres": livres, "por_livro": por_livro})


@router.get("/tags/{tag_id}")
def pagina_tag(request: Request, con: Con, tag_id: int):
    tag = tags_mod.obter(con, tag_id)
    if tag is None:
        return _pagina(request, "erro.html", {"mensagem": "Tag não encontrada."}, 404)
    if tag["tipo"] == "versiculo":
        cabecalho = f"{livros.por_numero(tag['livro']).nome} {tag['capitulo']}"
    else:
        cabecalho = tag["nome"]
    return _pagina(request, "tag.html", {
        "tag": tag, "cabecalho": cabecalho, "notas": busca.notas_da_tag(con, tag_id),
    })


@router.get("/lixeira")
def pagina_lixeira(request: Request, con: Con):
    return _pagina(request, "lixeira.html", {"notas": notas.lixeira(con)})


@router.post("/versiculos/previa")
def previa_versiculos(request: Request, titulo: Campo = "", conteudo: Campo = ""):
    refs = versiculos.encontrar(f"{titulo}\n{conteudo}")
    return _pagina(request, "partials/_previa_versiculos.html", {"refs": refs})


@router.get("/saude")
def saude(request: Request):
    config = request.app.state.config
    try:
        con = conectar(config.db)
        try:
            banco_ok = con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            total_notas = notas.contar_ativas(con) if banco_ok else 0
        finally:
            con.close()
    except sqlite3.Error:
        banco_ok, total_notas = False, 0
    ultimo = backup.ultimo(config.backup_dir)
    livre = shutil.disk_usage(Path(config.db).resolve().parent).free
    return _pagina(request, "saude.html", {
        "banco_ok": banco_ok,
        "total_notas": total_notas,
        "ultimo_backup": ultimo.name if ultimo else None,
        "livre_gb": livre / 1_000_000_000,
    }, 200 if banco_ok else 503)


@router.get("/exportar")
def exportar(con: Con):
    nome = f"notepi-{date.today().isoformat()}.zip"
    return Response(
        content=backup.exportar_markdown(con),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
