import io
import re
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from notepi.app import criar_app
from notepi.config import Config


@pytest.fixture
def cliente(tmp_path):
    config = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "backup")
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
    config = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "backup")

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
    config = Config(db=db, backup_dir=tmp_path / "bk")
    with TestClient(criar_app(config), raise_server_exceptions=False) as c:
        r = c.get("/saude")
    assert r.status_code == 503
    assert "PROBLEMA" in r.text
