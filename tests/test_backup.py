import io
import sqlite3
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest

from notepi import backup, manutencao, notas
from notepi.config import Config
from notepi.db import conectar


def test_backup_gera_copia_integra(tmp_path):
    con = conectar(tmp_path / "notas.db")
    notas.criar(con, titulo="A", conteudo="Jo 3:16", area="biblia")
    caminho = backup.fazer_backup(con, tmp_path / "bk", hoje=date(2026, 11, 10))
    assert caminho.name == "notas-2026-11-10.db"
    assert backup.verificar(caminho)
    copia = sqlite3.connect(caminho)
    assert copia.execute("SELECT titulo FROM notas").fetchone()[0] == "A"
    copia.close()
    con.close()


def test_verificar_arquivo_ruim(tmp_path):
    ruim = tmp_path / "ruim.db"
    ruim.write_bytes(b"isto nao e um banco")
    assert backup.verificar(ruim) is False


def test_rotacao_mantem_30_dias(tmp_path):
    for dia in ("2026-10-11", "2026-10-12", "2026-11-10"):
        (tmp_path / f"notas-{dia}.db").write_bytes(b"")
    (tmp_path / "outro-arquivo.txt").write_text("fica")
    apagados = backup.rotacionar(tmp_path, hoje=date(2026, 11, 10))
    assert [p.name for p in apagados] == ["notas-2026-10-11.db"]
    assert backup.ultimo(tmp_path).name == "notas-2026-11-10.db"
    assert (tmp_path / "outro-arquivo.txt").exists()


def test_exportar_markdown(con):
    notas.criar(con, titulo='Pincel "bom"', conteudo="Use **trincha**", area="pintura", tags=["compra"])
    zipado = zipfile.ZipFile(io.BytesIO(backup.exportar_markdown(con)))
    [nome] = zipado.namelist()
    assert nome == "0001-pincel-bom.md"
    texto = zipado.read(nome).decode("utf-8")
    assert 'titulo: "Pincel \\"bom\\""' in texto
    assert 'tags: ["compra"]' in texto
    assert texto.endswith("Use **trincha**\n")


def test_manutencao(tmp_path):
    cfg = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "bk")
    con = conectar(cfg.db)
    notas.criar(con, titulo="A", conteudo="", area="geral")
    con.close()
    caminho = manutencao.executar(cfg)
    assert caminho.exists() and backup.verificar(caminho)


def test_manutencao_exige_pendrive(tmp_path):
    cfg = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "bk", backup_exigir_montagem=True)
    with pytest.raises(RuntimeError, match="não está montado"):
        manutencao.executar(cfg)


def test_exportar_markdown_campos_e_lixeira(con):
    nota_id = notas.criar(con, titulo="Tinta", conteudo="Fosca", area="pintura", tags=["compra"])
    lixo_id = notas.criar(con, titulo="Descartada", conteudo="sumir", area="geral")
    notas.excluir(con, lixo_id)
    nota = notas.obter(con, nota_id)
    zipado = zipfile.ZipFile(io.BytesIO(backup.exportar_markdown(con)))
    nomes = zipado.namelist()
    assert nomes == [f"{nota_id:04d}-tinta.md"]
    linhas = zipado.read(nomes[0]).decode("utf-8").splitlines()
    assert "area: pintura" in linhas
    assert "modelo: " in linhas
    assert f"criada_em: {nota['criada_em']}" in linhas
    assert f"editada_em: {nota['editada_em']}" in linhas


def test_main_sai_com_codigo_1_quando_falha(tmp_path, monkeypatch):
    cfg = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "bk", backup_exigir_montagem=True)
    monkeypatch.setattr(manutencao, "carregar", lambda: cfg)
    with pytest.raises(SystemExit) as info:
        manutencao.main()
    assert info.value.code == 1


def test_main_sucesso(tmp_path, monkeypatch):
    cfg = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "bk")
    monkeypatch.setattr(manutencao, "carregar", lambda: cfg)
    manutencao.main()
    assert list((tmp_path / "bk").glob("notas-*.db"))


def test_manutencao_esvazia_lixeira_antiga(tmp_path):
    cfg = Config(db=tmp_path / "notas.db", backup_dir=tmp_path / "bk")
    con = conectar(cfg.db)
    try:
        nota_id = notas.criar(con, titulo="Velha", conteudo="", area="geral")
        notas.excluir(con, nota_id)
        antigo = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="microseconds")
        with con:
            con.execute("UPDATE notas SET excluida_em = ? WHERE id = ?", (antigo, nota_id))
    finally:
        con.close()
    manutencao.executar(cfg)
    con = conectar(cfg.db)
    try:
        assert notas.obter(con, nota_id, incluir_excluidas=True) is None
    finally:
        con.close()


def test_verificar_inexistente_nao_cria_arquivo(tmp_path):
    alvo = tmp_path / "nao-existe.db"
    assert backup.verificar(alvo) is False
    assert not alvo.exists()


def test_backup_fica_em_arquivo_unico(tmp_path):
    con = conectar(tmp_path / "notas.db")
    caminho = backup.fazer_backup(con, tmp_path / "bk")
    copia = sqlite3.connect(caminho)
    assert copia.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    copia.close()
    con.close()
