"""Rotas HTML do NotePi."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from notepi import busca, modelos, notas
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
