from datetime import date, datetime, timedelta, timezone

import pytest

from notepi import modelos, notas, tags


def test_criar_e_obter(con):
    nota_id = notas.criar(con, titulo="Culto domingo", conteudo="Texto-base Rm 12:1-2", area="biblia",
                          modelo="culto", tags=["culto"])
    nota = notas.obter(con, nota_id)
    assert nota["titulo"] == "Culto domingo"
    assert nota["criada_em"] == nota["editada_em"]
    assert [t["nome"] for t in tags.da_nota(con, nota_id)] == ["Romanos 12:1-2", "culto"]


def test_titulo_efetivo():
    assert notas.titulo_efetivo("  Meu título ", "x") == "Meu título"
    assert notas.titulo_efetivo("", "\n## Pincéis bons\nresto") == "Pincéis bons"
    assert notas.titulo_efetivo("", "**Data:** 10/11/2026") == "Data:** 10/11/2026"
    assert notas.titulo_efetivo("", "  ", datetime(2026, 11, 10)) == "Nota de 10/11/2026"


def test_area_e_modelo_validos(con):
    with pytest.raises(ValueError):
        notas.criar(con, titulo="x", conteudo="", area="culinaria")
    with pytest.raises(ValueError):
        notas.criar(con, titulo="x", conteudo="", area="geral", modelo="receita")


def test_editar_com_base_certa(con):
    nota_id = notas.criar(con, titulo="A", conteudo="Jo 3:16", area="geral")
    base = notas.obter(con, nota_id)["editada_em"]
    notas.editar(con, nota_id, titulo="B", conteudo="Sl 23", area="biblia", tags=["fé"], editada_em_base=base)
    nota = notas.obter(con, nota_id)
    assert (nota["titulo"], nota["area"]) == ("B", "biblia")
    assert nota["editada_em"] > base
    assert [t["nome"] for t in tags.da_nota(con, nota_id)] == ["Salmos 23", "fé"]


def test_editar_com_base_antiga_da_conflito(con):
    nota_id = notas.criar(con, titulo="A", conteudo="", area="geral")
    base = notas.obter(con, nota_id)["editada_em"]
    notas.editar(con, nota_id, titulo="Celular", conteudo="", area="geral", tags=[], editada_em_base=base)
    with pytest.raises(notas.ConflitoEdicao) as erro:
        notas.editar(con, nota_id, titulo="PC", conteudo="", area="geral", tags=[], editada_em_base=base)
    assert erro.value.atual["titulo"] == "Celular"
    assert notas.obter(con, nota_id)["titulo"] == "Celular"


def test_lixeira_restaurar(con):
    nota_id = notas.criar(con, titulo="A", conteudo="", area="geral")
    notas.excluir(con, nota_id)
    assert notas.obter(con, nota_id) is None
    assert [n["id"] for n in notas.lixeira(con)] == [nota_id]
    assert notas.recentes(con) == []
    notas.restaurar(con, nota_id)
    assert notas.obter(con, nota_id) is not None
    with pytest.raises(notas.NotaNaoEncontrada):
        notas.restaurar(con, nota_id)


def test_purgar_lixeira_so_apaga_as_antigas(con):
    velha = notas.criar(con, titulo="velha", conteudo="", area="geral", tags=["só-dela"])
    nova = notas.criar(con, titulo="nova", conteudo="", area="geral")
    notas.excluir(con, velha)
    notas.excluir(con, nova)
    agora_utc = datetime.now(timezone.utc)
    # simula que a 'velha' foi para a lixeira há 40 dias (a 'nova' foi agora)
    with con:
        con.execute("UPDATE notas SET excluida_em = ? WHERE id = ?",
                    ((agora_utc - timedelta(days=40)).isoformat(timespec="microseconds"), velha))
    assert notas.purgar_lixeira(con) == 1
    assert notas.obter(con, velha, incluir_excluidas=True) is None
    assert notas.obter(con, nova, incluir_excluidas=True) is not None
    assert con.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0
    assert notas.purgar_lixeira(con, agora_=agora_utc + timedelta(days=31)) == 1


def test_recentes_filtra_por_area(con):
    notas.criar(con, titulo="a", conteudo="", area="biblia")
    notas.criar(con, titulo="b", conteudo="", area="pintura")
    assert [n["titulo"] for n in notas.recentes(con)] == ["b", "a"]
    assert [n["titulo"] for n in notas.recentes(con, area="biblia")] == ["a"]
    assert notas.contar_ativas(con) == 2


def test_modelos():
    culto = modelos.carregar("culto", date(2026, 11, 10))
    assert "**Data:** 10/11/2026" in culto and "**Pregador:**" in culto
    assert "| Critério | O que olhar | Por quê |" in modelos.carregar("guia_requisitos")
    with pytest.raises(KeyError):
        modelos.carregar("receita")


def test_editar_detecta_conflito_mesmo_apos_a_checagem(con, monkeypatch):
    from notepi.db import agora

    nota_id = notas.criar(con, titulo="A", conteudo="", area="geral")
    base = notas.obter(con, nota_id)["editada_em"]
    obter_real = notas.obter
    chamadas = {"n": 0}

    def obter_com_outro_aparelho(con_, nota_id_, **kwargs):
        linha = obter_real(con_, nota_id_, **kwargs)
        if chamadas["n"] == 0:
            # outro aparelho salva entre a checagem e o UPDATE
            con_.execute("UPDATE notas SET editada_em = ? WHERE id = ?", (agora(), nota_id_))
        chamadas["n"] += 1
        return linha

    monkeypatch.setattr(notas, "obter", obter_com_outro_aparelho)
    with pytest.raises(notas.ConflitoEdicao):
        notas.editar(con, nota_id, titulo="PC", conteudo="", area="geral", tags=[], editada_em_base=base)
    monkeypatch.setattr(notas, "obter", obter_real)
    assert notas.obter(con, nota_id)["titulo"] == "A"


def test_remove_caracteres_de_controle_stx_etx(con):
    nid = notas.criar(con, titulo="a\x02b", conteudo="x\x02y\x03z", area="geral")
    n = notas.obter(con, nid)
    assert n["titulo"] == "ab" and n["conteudo"] == "xyz"
    notas.editar(con, nid, titulo="c\x03d", conteudo="p\x02q", area="geral", tags=[], editada_em_base=n["editada_em"])
    n = notas.obter(con, nid)
    assert n["titulo"] == "cd" and n["conteudo"] == "pq"
