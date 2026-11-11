from notepi import busca, notas, tags


def _criar(con, titulo, conteudo="", area="geral", modelo=None, tags_=()):
    return notas.criar(con, titulo=titulo, conteudo=conteudo, area=area, modelo=modelo, tags=list(tags_))


def test_busca_ignora_acentos_e_destaca(con):
    nota = _criar(con, "Estudo", "Regras de hermenêutica e exegese")
    [r] = busca.buscar(con, "hermeneutica")
    assert r.id == nota
    assert "<mark>hermenêutica</mark>" in str(r.trecho)


def test_busca_escapa_html(con):
    _criar(con, "x", "<script>alert(1)</script> pincel")
    [r] = busca.buscar(con, "pincel")
    assert "<script>" not in str(r.trecho)


def test_ultimo_termo_aceita_prefixo(con):
    nota = _criar(con, "Monitor", "taxa de atualização 144Hz")
    assert [r.id for r in busca.buscar(con, "atualiz")] == [nota]


def test_busca_com_caracteres_estranhos_nao_quebra(con):
    _criar(con, "Monitor", "texto")
    assert busca.buscar(con, '"* AND (') == []


def test_filtros(con):
    a = _criar(con, "pincel parede", area="pintura", tags_=["compra"])
    _criar(con, "pincel quadro", area="geral")
    assert [r.id for r in busca.buscar(con, "pincel", area="pintura")] == [a]
    tag_id = tags.da_nota(con, a)[0]["id"]
    assert [r.id for r in busca.buscar(con, "pincel", tag_id=tag_id)] == [a]
    assert len(busca.buscar(con, "", area="pintura")) == 1


def test_busca_por_versiculo_capitulo_e_verso(con):
    v2 = _criar(con, "Culto A", "Texto: Rm 12:2")
    v1_3 = _criar(con, "Estudo B", "Rm 12:1-3")
    cap = _criar(con, "Leitura C", "Li Romanos 12 inteiro")
    _criar(con, "Outro", "Rm 8:28")
    capitulo = {r.id for r in busca.buscar(con, "Romanos 12")}
    assert capitulo == {v2, v1_3, cap}
    verso1 = {r.id for r in busca.buscar(con, "Rm 12:1")}
    assert verso1 == {v1_3, cap}


def test_excluidas_nao_aparecem(con):
    nota = _criar(con, "pincel")
    notas.excluir(con, nota)
    assert busca.buscar(con, "pincel") == []


def test_relacionadas_por_tags_em_comum(con):
    base = _criar(con, "Base", "Rm 12:2", tags_=["finanças", "mordomia"])
    duas = _criar(con, "Duas", "Rm 12:9", tags_=["mordomia"])  # mesmo capítulo + mordomia
    uma = _criar(con, "Uma", tags_=["finanças"])
    _criar(con, "Nenhuma", tags_=["pintura"])
    rel = busca.relacionadas(con, base)
    assert [(r["id"], r["comuns"]) for r in rel] == [(duas, 2), (uma, 1)]


def test_notas_da_tag_de_versiculo_traz_o_capitulo(con):
    a = _criar(con, "A", "Rm 12:2")
    b = _criar(con, "B", "Rm 12:9")
    tag_id = tags.da_nota(con, a)[0]["id"]
    assert {r["id"] for r in busca.notas_da_tag(con, tag_id)} == {a, b}
    assert busca.notas_da_tag(con, 9999) == []
