import re
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
    nota_id = _criar(cliente, titulo="x", conteudo="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in cliente.get(f"/notas/{nota_id}").text


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
