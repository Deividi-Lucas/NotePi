from notepi import tags
from notepi.db import agora


def _nota(con, conteudo="") -> int:
    momento = agora()
    cur = con.execute(
        "INSERT INTO notas(titulo, conteudo, area, criada_em, editada_em) VALUES ('t', ?, 'geral', ?, ?)",
        (conteudo, momento, momento),
    )
    return cur.lastrowid


def _nomes(con, nota_id):
    return [(t["nome"], t["tipo"], t["origem"]) for t in tags.da_nota(con, nota_id)]


def test_normalizar_e_separar():
    assert tags.normalizar_livre("  #Pintura   Parede ") == "pintura parede"
    assert tags.separar("pintura, compra, , pintura") == ["pintura", "compra"]


def test_manuais_livres_e_versiculo(con):
    nota = _nota(con)
    tags.definir_manuais(con, nota, ["Pintura", "Rm 12:2"])
    assert _nomes(con, nota) == [
        ("Romanos 12:2", "versiculo", "manual"),
        ("pintura", "livre", "manual"),
    ]
    tags.definir_manuais(con, nota, ["compra"])
    assert _nomes(con, nota) == [("compra", "livre", "manual")]


def test_auto_segue_o_texto_e_nao_mexe_nas_manuais(con):
    nota = _nota(con)
    tags.definir_manuais(con, nota, ["culto"])
    tags.sincronizar_auto(con, nota, "Pregação em Jo 3:16 e Sl 23")
    assert _nomes(con, nota) == [
        ("Salmos 23", "versiculo", "auto"),
        ("João 3:16", "versiculo", "auto"),
        ("culto", "livre", "manual"),
    ]
    tags.sincronizar_auto(con, nota, "Agora só Sl 23")
    assert _nomes(con, nota) == [("Salmos 23", "versiculo", "auto"), ("culto", "livre", "manual")]


def test_manual_que_tambem_e_auto_continua_manual(con):
    nota = _nota(con)
    tags.definir_manuais(con, nota, ["Sl 23"])
    tags.sincronizar_auto(con, nota, "Sl 23")
    assert _nomes(con, nota) == [("Salmos 23", "versiculo", "manual")]


def test_mesma_tag_reaproveitada_entre_notas(con):
    a, b = _nota(con), _nota(con)
    tags.definir_manuais(con, a, ["pintura"])
    tags.definir_manuais(con, b, ["pintura"])
    assert con.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 1


def test_listar_com_contagem_e_orfas(con):
    a, b = _nota(con), _nota(con)
    tags.definir_manuais(con, a, ["pintura"])
    tags.definir_manuais(con, b, ["pintura", "compra"])
    contagem = {t["nome"]: t["total"] for t in tags.listar_com_contagem(con)}
    assert contagem == {"pintura": 2, "compra": 1}
    tags.definir_manuais(con, b, [])
    assert tags.remover_orfas(con) == 1  # 'compra' ficou sem nota
