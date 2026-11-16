import io
import re
import zipfile
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from notepi.app import criar_app
from notepi.config import Config


@pytest.fixture
def cliente(tmp_path):
    config = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "backup", hosts=("testserver",))
    with TestClient(criar_app(config), raise_server_exceptions=False) as c:
        yield c


def _criar(cliente, **campos):
    dados = {"titulo": "", "conteudo": "", "area": "geral", "modelo": "", "tags": ""} | campos
    r = cliente.post("/notas", data=dados, follow_redirects=False)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def _base(cliente, nota_id):
    html = cliente.get(f"/notas/{nota_id}/editar").text
    return re.search(r'name="editada_em_base" value="([^"]+)"', html).group(1)


def test_inicio(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "NotePi" in r.text and "+ Culto" in r.text


def test_nova_com_modelo_culto(cliente):
    r = cliente.get("/notas/nova?modelo=culto")
    assert "**Pregador:**" in r.text
    assert date.today().strftime("%d/%m/%Y") in r.text
    assert '<option value="biblia" selected>' in r.text


def test_criar_e_ver_com_versiculo_e_tags(cliente):
    nota_id = _criar(cliente, titulo="Culto", conteudo="Texto-base: Rm 12:2", area="biblia", tags="mordomia")
    r = cliente.get(f"/notas/{nota_id}")
    assert r.status_code == 200
    assert "Romanos 12:2" in r.text and "mordomia" in r.text
    assert "<p>Texto-base: Rm 12:2</p>" in r.text


def test_markdown_nao_executa_html(cliente):
    nota_id = _criar(cliente, titulo="<b>t</b>", conteudo="<script>alert(1)</script>")
    html = cliente.get(f"/notas/{nota_id}").text
    assert "<script>alert(1)</script>" not in html
    assert "<b>t</b>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;" in html


def test_conflito_escapa_html(cliente):
    nota_id = _criar(cliente, titulo="Original")
    base = _base(cliente, nota_id)
    campos = {"titulo": "<b>x</b>", "conteudo": "<script>x()</script>", "area": "geral", "tags": "",
              "editada_em_base": base}
    assert cliente.post(f"/notas/{nota_id}", data=campos, follow_redirects=False).status_code == 303
    campos["titulo"] = "Do PC"
    r = cliente.post(f"/notas/{nota_id}", data=campos)
    assert r.status_code == 409
    assert "<script>x()" not in r.text
    assert "<b>x</b>" not in r.text
    assert "&lt;script&gt;" in r.text
    assert "&lt;b&gt;x" in r.text


def test_erro_inesperado_mostra_pagina_amigavel(tmp_path, monkeypatch):
    config = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "backup", hosts=("testserver",))

    def quebrar(*args, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("notepi.notas.recentes", quebrar)
    with TestClient(criar_app(config), raise_server_exceptions=False) as c:
        r = c.get("/")
    assert r.status_code == 500
    assert "Algo deu errado" in r.text


def test_404_em_editar_salvar_e_restaurar(cliente):
    assert cliente.get("/notas/999/editar").status_code == 404
    campos = {"titulo": "x", "conteudo": "", "area": "geral", "tags": "", "editada_em_base": "qualquer"}
    assert cliente.post("/notas/999", data=campos).status_code == 404
    assert cliente.post("/notas/999/restaurar").status_code == 404


def test_area_e_modelo_invalidos_viram_padrao(cliente):
    nota_id = _criar(cliente, titulo="Sem modelo", conteudo="x", area="xyz", modelo="receita")
    html = cliente.get(f"/notas/{nota_id}").text
    assert "Geral" in html
    assert "receita" not in html
    r = cliente.get("/notas/nova?modelo=receita&area=xyz")
    assert r.status_code == 200
    assert '<option value="geral" selected>' in r.text


def test_relacionadas_aparecem(cliente):
    a = _criar(cliente, titulo="A", conteudo="Rm 12:2")
    _criar(cliente, titulo="B", conteudo="Rm 12:9")
    assert "1 tag(s) em comum" in cliente.get(f"/notas/{a}").text


def test_editar_e_conflito(cliente):
    nota_id = _criar(cliente, titulo="Original")
    base = _base(cliente, nota_id)
    campos = {"titulo": "Do celular", "conteudo": "", "area": "geral", "tags": "", "editada_em_base": base}
    assert cliente.post(f"/notas/{nota_id}", data=campos, follow_redirects=False).status_code == 303
    campos["titulo"] = "Do PC"
    r = cliente.post(f"/notas/{nota_id}", data=campos)
    assert r.status_code == 409
    assert "alterada em outro aparelho" in r.text
    assert "Do celular" in r.text and 'value="Do PC"' in r.text
    nova_base = re.search(r'name="editada_em_base" value="([^"]+)"', r.text).group(1)
    campos["editada_em_base"] = nova_base
    assert cliente.post(f"/notas/{nota_id}", data=campos, follow_redirects=False).status_code == 303
    assert "Do PC" in cliente.get(f"/notas/{nota_id}").text


def test_nota_inexistente(cliente):
    assert cliente.get("/notas/999").status_code == 404
    assert cliente.post("/notas/999/excluir").status_code == 404


def test_estaticos_basicos(cliente):
    assert cliente.get("/static/htmx.min.js").status_code == 200
    assert cliente.get("/static/estilo.css").status_code == 200


def test_excluir_e_restaurar(cliente):
    nota_id = _criar(cliente, titulo="Some e volta")
    cliente.post(f"/notas/{nota_id}/excluir")
    assert "Some e volta" not in cliente.get("/").text
    assert "Some e volta" in cliente.get("/lixeira").text
    assert cliente.get(f"/notas/{nota_id}").status_code == 404
    cliente.post(f"/notas/{nota_id}/restaurar")
    assert cliente.get(f"/notas/{nota_id}").status_code == 200


def test_busca_texto_e_versiculo(cliente):
    _criar(cliente, titulo="Estudo", conteudo="Princípios de hermenêutica")
    _criar(cliente, titulo="Culto", conteudo="Rm 12:2")
    r = cliente.get("/busca", params={"q": "hermeneutica"})
    assert "1 resultado(s)" in r.text and "<mark>hermenêutica</mark>" in r.text
    r = cliente.get("/busca", params={"q": "Romanos 12"})
    assert "Culto" in r.text and "<mark>Romanos 12</mark>" in r.text


def test_busca_com_filtros_vazios(cliente):
    r = cliente.get("/busca", params={"q": "", "area": "", "modelo": "", "tag": ""})
    assert r.status_code == 200 and "resultado(s)" not in r.text


def test_paginas_de_tags(cliente):
    _criar(cliente, titulo="A", conteudo="Rm 12:2", tags="pintura")
    r = cliente.get("/tags")
    assert "Romanos" in r.text and "Romanos 12:2" in r.text and "pintura" in r.text
    tag_id = re.search(r'href="/tags/(\d+)">Romanos 12:2', r.text).group(1)
    r = cliente.get(f"/tags/{tag_id}")
    assert "<h1>Romanos 12</h1>" in r.text and "A" in r.text
    assert cliente.get("/tags/999").status_code == 404


def test_previa_de_versiculos(cliente):
    r = cliente.post("/versiculos/previa", data={"titulo": "", "conteudo": "Leia Jo 3:16 e Sl 23"})
    assert "João 3:16" in r.text and "Salmos 23" in r.text
    assert cliente.post("/versiculos/previa", data={"conteudo": "nada"}).text.strip() == ""


def test_saude(cliente):
    r = cliente.get("/saude")
    assert r.status_code == 200
    assert "Banco OK" in r.text and "nenhum backup encontrado" in r.text


def test_exportar(cliente):
    _criar(cliente, titulo="Pincel", conteudo="trincha")
    r = cliente.get("/exportar")
    assert r.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == ["0001-pincel.md"]


def test_busca_tag_com_digito_unicode_ignora_filtro(cliente):
    r = cliente.get("/busca", params={"q": "x", "tag": "²"})
    assert r.status_code == 200


def test_saude_com_banco_corrompido_responde_503(tmp_path):
    db = tmp_path / "notas.db"
    db.write_bytes(b"isto nao e um banco" * 100)
    config = Config(db=db, backup_dir=tmp_path / "bk", hosts=("testserver",))
    with TestClient(criar_app(config), raise_server_exceptions=False) as c:
        r = c.get("/saude")
    assert r.status_code == 503
    assert "PROBLEMA" in r.text


def test_script_de_rascunho(cliente):
    r = cliente.get("/static/rascunho.js")
    assert r.status_code == 200
    assert "notepi:rascunho:" in r.text
    assert "Sem conexão: rascunho salvo neste aparelho" in r.text
    assert "Servidor fora do ar" in r.text
    assert "editada_em_base" in r.text
    assert "15000" in r.text
    assert "409" in r.text
    assert "Descartar rascunho" in r.text
    assert "redirected" in r.text
    assert "enviando" in r.text


def test_chave_de_rascunho_depende_do_modelo(cliente):
    assert 'data-chave-rascunho="nova-culto"' in cliente.get("/notas/nova?modelo=culto").text
    assert 'data-chave-rascunho="nova-livre"' in cliente.get("/notas/nova").text


def test_post_de_outro_site_e_bloqueado(cliente):
    r = cliente.post("/notas", data={"titulo": "x"}, headers={"Sec-Fetch-Site": "cross-site"},
                     follow_redirects=False)
    assert r.status_code == 403
    assert "Pedido bloqueado: veio de outro site." in r.text
    assert "Nenhuma nota" in cliente.get("/").text


def test_post_do_mesmo_site_ou_sem_cabecalho_passa(cliente):
    r = cliente.post("/notas", data={"titulo": "x"}, headers={"Sec-Fetch-Site": "same-origin"},
                     follow_redirects=False)
    assert r.status_code == 303
    r = cliente.post("/notas", data={"titulo": "y"}, follow_redirects=False)
    assert r.status_code == 303


def test_cabecalhos_de_seguranca(cliente):
    r = cliente.get("/")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"


def _saude_com_backup(tmp_path, dias=None, **cfg):
    bk = tmp_path / "bk"
    bk.mkdir()
    if dias is not None:
        (bk / f"notas-{(date.today() - timedelta(days=dias)).isoformat()}.db").write_bytes(b"")
    config = Config(db=tmp_path / "notas.db", backup_dir=bk, hosts=("testserver",), **cfg)
    with TestClient(criar_app(config), raise_server_exceptions=False) as c:
        return c.get("/saude")


def test_saude_backup_de_hoje(tmp_path):
    r = _saude_com_backup(tmp_path, 0)
    assert r.status_code == 200 and "hoje" in r.text and "atrasado" not in r.text


def test_saude_backup_antigo_avisa(tmp_path):
    r = _saude_com_backup(tmp_path, 5)
    assert "há 5 dia(s)" in r.text and "atrasado" in r.text


def test_saude_sem_backup_avisa(tmp_path):
    assert "atrasado" in _saude_com_backup(tmp_path).text


def test_saude_pendrive_ausente_avisa(tmp_path):
    r = _saude_com_backup(tmp_path, 0, backup_exigir_montagem=True)
    assert "não está montado" in r.text


def test_post_com_origin_de_outro_site_sem_sec_fetch_e_bloqueado(cliente):
    r = cliente.post("/notas", data={"titulo": "x"}, headers={"Origin": "https://evil.example"},
                     follow_redirects=False)
    assert r.status_code == 403
    assert "Pedido bloqueado" in r.text
    assert "Nenhuma nota" in cliente.get("/").text


def test_post_com_origin_do_proprio_host_passa(cliente):
    r = cliente.post("/notas", data={"titulo": "x"}, headers={"Origin": "http://testserver"},
                     follow_redirects=False)
    assert r.status_code == 303


def test_post_com_origin_null_e_bloqueado(cliente):
    r = cliente.post("/notas", data={"titulo": "x"}, headers={"Origin": "null"}, follow_redirects=False)
    assert r.status_code == 403


def test_host_invalido_e_recusado(cliente):
    assert cliente.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert cliente.get("/").status_code == 200


def test_carregar_le_hosts_do_ambiente(monkeypatch):
    from notepi.config import carregar

    monkeypatch.delenv("NOTEPI_HOSTS", raising=False)
    assert carregar().hosts == ("127.0.0.1", "localhost")
    monkeypatch.setenv("NOTEPI_HOSTS", "pi.tail1234.ts.net, 127.0.0.1")
    assert carregar().hosts == ("pi.tail1234.ts.net", "127.0.0.1")


def _cliente_com_usuarios(tmp_path, usuarios):
    config = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "backup", hosts=("testserver",),
                    usuarios=usuarios)
    return TestClient(criar_app(config), raise_server_exceptions=False)


def test_sem_lista_de_usuarios_o_acesso_e_livre(cliente):
    assert cliente.get("/").status_code == 200


def test_lista_de_usuarios_exige_cabecalho_do_tailscale(tmp_path):
    with _cliente_com_usuarios(tmp_path, ("eu@x",)) as c:
        assert c.get("/", headers={"Tailscale-User-Login": "eu@x"}).status_code == 200
        r = c.get("/")
        assert r.status_code == 403 and "Acesso não autorizado." in r.text
        r = c.get("/", headers={"Tailscale-User-Login": "outro@x"})
        assert r.status_code == 403
        r = c.post("/notas", data={"titulo": "x"}, follow_redirects=False)
        assert r.status_code == 403
        assert c.get("/static/estilo.css").status_code == 200


def test_carregar_le_usuarios_do_ambiente(monkeypatch):
    from notepi.config import carregar

    monkeypatch.delenv("NOTEPI_USUARIOS", raising=False)
    assert carregar().usuarios == ()
    monkeypatch.setenv("NOTEPI_USUARIOS", "eu@x, ela@y")
    assert carregar().usuarios == ("eu@x", "ela@y")


def test_pedido_grande_demais_e_recusado(cliente):
    r = cliente.post("/notas", data={"titulo": "x", "conteudo": "a" * 4_200_000}, follow_redirects=False)
    assert r.status_code == 413
    r = cliente.post("/notas", data={"titulo": "x", "conteudo": "a" * 100_000}, follow_redirects=False)
    assert r.status_code == 303


def test_pedido_grande_sem_content_length_e_recusado(cliente):
    def corpo():
        for _ in range(42):
            yield b"conteudo=" + b"a" * 100_000

    r = cliente.post("/notas", content=corpo(), headers={"Content-Type": "application/x-www-form-urlencoded"},
                     follow_redirects=False)
    assert r.status_code == 413


def test_csp_e_referrer_policy(cliente):
    r = cliente.get("/")
    assert r.headers["referrer-policy"] == "no-referrer"
    csp = r.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp and "form-action 'self'" in csp
    assert "img-src 'self' data:" in csp and "base-uri 'none'" in csp


def test_pagina_da_nota_sem_javascript_inline(cliente):
    nota_id = _criar(cliente, titulo="x")
    html = cliente.get(f"/notas/{nota_id}").text
    assert "onsubmit=" not in html
    assert 'data-confirmar="Mover esta nota para a lixeira?"' in html
    assert "/static/confirmar.js" in html
    js = cliente.get("/static/confirmar.js")
    assert js.status_code == 200 and "data-confirmar" in js.text


def test_resposta_500_tem_cabecalhos_de_seguranca(tmp_path, monkeypatch):
    config = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "backup", hosts=("testserver",))

    def quebrar(*args, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("notepi.notas.recentes", quebrar)
    with TestClient(criar_app(config), raise_server_exceptions=False) as c:
        r = c.get("/")
    assert r.status_code == 500
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_htmx_configurado_de_forma_restrita(cliente):
    html = cliente.get("/").text
    assert 'name="htmx-config"' in html
    assert '"allowEval":false' in html


def test_rotas_inexistentes_e_ids_invalidos_dao_404_amigavel(cliente):
    for caminho in ("/notas/abc", "/qualquer-coisa", "/notas/0", "/notas/99999999999999999999",
                    "/tags/99999999999999999999", "/notas/99999999999999999999/editar"):
        r = cliente.get(caminho)
        assert r.status_code == 404, caminho
        assert "text/html" in r.headers["content-type"] and "Ops" in r.text, caminho


def test_metodo_nao_permitido_e_pagina_amigavel(cliente):
    r = cliente.post("/")
    assert r.status_code == 405 and "Ops" in r.text


def test_busca_com_tag_gigante_ignora_o_filtro(cliente):
    r = cliente.get("/busca", params={"q": "x", "tag": "99999999999999999999"})
    assert r.status_code == 200
    r = cliente.get("/busca", params={"q": "x", "tag": "9" * 5000})
    assert r.status_code == 200


def test_caracteres_de_controle_stx_etx_sao_removidos(cliente):
    nota_id = _criar(cliente, titulo="a\x02b", conteudo="x\x02y\x03z")
    html = cliente.get(f"/notas/{nota_id}/editar").text
    assert "\x02" not in html and "\x03" not in html
    assert "xyz" in html


def test_nota_grande_com_acentos_enviada_como_o_rascunho_passa(cliente):
    # rascunho.js envia multipart (FormData); 900 mil caracteres com acentos (~940 KB; o Starlette
    # limita cada campo multipart a 1 MiB)
    r = cliente.post("/notas", data={"titulo": "x"}, files={"conteudo": (None, ("a" * 19 + "ç ") * 45_000)},
                     follow_redirects=False)
    assert r.status_code == 303


def test_saude_sem_marcador_do_pendrive_avisa(tmp_path):
    r = _saude_com_backup(tmp_path, 0, backup_marcador=True)
    assert "não está montado" in r.text


def test_saude_com_marcador_do_pendrive_nao_avisa(tmp_path):
    (tmp_path / "bk").mkdir()
    (tmp_path / "bk" / ".notepi-pendrive").write_text("")
    config = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "bk", hosts=("testserver",),
                    backup_marcador=True)
    with TestClient(criar_app(config), raise_server_exceptions=False) as c:
        assert "não está montado" not in c.get("/saude").text


def test_carregar_le_backup_marcador(monkeypatch):
    from notepi.config import carregar

    monkeypatch.setenv("NOTEPI_BACKUP_MARCADOR", "1")
    assert carregar().backup_marcador is True
    monkeypatch.delenv("NOTEPI_BACKUP_MARCADOR")
    assert carregar().backup_marcador is False
