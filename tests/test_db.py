from notepi.db import VERSAO_ESQUEMA, agora, conectar
from notepi.texto import remover_acentos, slug


def test_cria_esquema_e_versao(tmp_path):
    con = conectar(tmp_path / "dados" / "notas.db")
    assert con.execute("PRAGMA user_version").fetchone()[0] == VERSAO_ESQUEMA
    nomes = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    assert {"notas", "tags", "nota_tags", "notas_fts"} <= nomes
    con.close()


def test_wal_e_chaves_estrangeiras(tmp_path):
    con = conectar(tmp_path / "notas.db")
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    con.close()


def test_reabrir_nao_reaplica_migracao(tmp_path):
    conectar(tmp_path / "notas.db").close()
    con = conectar(tmp_path / "notas.db")
    assert con.execute("PRAGMA user_version").fetchone()[0] == VERSAO_ESQUEMA
    con.close()


def test_fts_ignora_acentos_e_acompanha_a_tabela(con):
    momento = agora()
    con.execute(
        "INSERT INTO notas(titulo, conteudo, area, criada_em, editada_em) VALUES (?,?,?,?,?)",
        ("Estudo", "Hermenêutica e exegese", "biblia", momento, momento),
    )
    achou = con.execute("SELECT rowid FROM notas_fts WHERE notas_fts MATCH 'hermeneutica'").fetchall()
    assert len(achou) == 1
    con.execute("UPDATE notas SET conteudo = 'outra coisa' WHERE id = 1")
    assert con.execute("SELECT rowid FROM notas_fts WHERE notas_fts MATCH 'hermeneutica'").fetchall() == []


def test_agora_ordena_como_texto():
    a = agora()
    b = agora()
    assert a <= b and a.endswith("+00:00")


def test_texto():
    assert remover_acentos("Êxodo, João, Hermenêutica") == "Exodo, Joao, Hermeneutica"
    assert slug("Pincel para parede!") == "pincel-para-parede"
    assert slug("???") == "nota"
