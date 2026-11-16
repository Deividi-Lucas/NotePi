import pytest

from notepi.versiculos import Referencia, encontrar, referencia_exata


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Jo 3:16", ["João 3:16"]),
        ("Jo 3.16", ["João 3:16"]),
        ("João 3:16", ["João 3:16"]),
        ("joao 3:16", ["João 3:16"]),
        ("1Co 13:4-7", ["1 Coríntios 13:4-7"]),
        ("1 Co 13:4-7", ["1 Coríntios 13:4-7"]),
        ("I Coríntios 13", ["1 Coríntios 13"]),
        ("II Timóteo 3:16", ["2 Timóteo 3:16"]),
        ("Sl 23", ["Salmos 23"]),
        ("Salmos 119:105", ["Salmos 119:105"]),
        ("Salmo 1", ["Salmos 1"]),
        ("Rm 12:1,2", ["Romanos 12:1-2"]),
        ("Rm 12:1-2", ["Romanos 12:1-2"]),
        ("Rm 12:1,3", ["Romanos 12:1", "Romanos 12:3"]),
        ("rm 8:28", ["Romanos 8:28"]),
        ("Jó 1:21", ["Jó 1:21"]),
        ("Jo 1:1", ["João 1:1"]),
        ("Isaías 53:5", ["Isaías 53:5"]),
        ("Ex 20", ["Êxodo 20"]),
        ("Êx 20:3", ["Êxodo 20:3"]),
        ("Joel 2:28", ["Joel 2:28"]),
        ("Os 6:6", ["Oseias 6:6"]),
        ("ver Gn 1:1; Ap 22:21.", ["Gênesis 1:1", "Apocalipse 22:21"]),
        ("na 1 Coríntios 13", ["1 Coríntios 13"]),
        ("lemos de 1 Coríntios 13 hoje", ["1 Coríntios 13"]),
        ("Jo 3:16 e de novo João 3:16", ["João 3:16"]),
        ("3 Jo 1:4", ["3 João 1:4"]),
    ],
)
def test_encontra_referencias(texto, esperado):
    assert [r.canonica for r in encontrar(texto)] == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "Rm 99:1",  # Romanos só tem 16 capítulos
        "Rm 12:5-3",  # intervalo invertido
        "Ob 2",  # Obadias só tem 1 capítulo
        "os 3 pontos principais",  # palavra comum sem versículo
        "Na 2 semana",
        "em 2020 fizemos",
        "hermenêutica e exegese",
        "Isaque",
    ],
)
def test_ignora_o_que_nao_e_referencia(texto):
    assert encontrar(texto) == []


def test_referencia_guarda_numeros():
    assert encontrar("1Co 13:4-7") == [Referencia(46, 13, 4, 7)]
    assert encontrar("Sl 23") == [Referencia(19, 23, None, None)]


def test_referencia_exata():
    assert referencia_exata("Romanos 12") == Referencia(45, 12)
    assert referencia_exata("  Rm 12:2 ") == Referencia(45, 12, 2, 2)
    assert referencia_exata("Os 6") == Referencia(28, 6)  # na busca, aceita abreviação ambígua
    assert referencia_exata("Romanos 12 e algo") is None
    assert referencia_exata("hermenêutica") is None
    assert referencia_exata("Rm 12:1,3") is None  # mais de uma referência


def test_limite_de_referencias_e_rapido():
    import time

    texto = " ".join(f"Sl {c}:{v}" for c in range(1, 151) for v in range(1, 15))
    inicio = time.perf_counter()
    refs = encontrar(texto)
    assert len(refs) == 500
    assert len({r for r in refs}) == 500
    assert time.perf_counter() - inicio < 1


def test_ordem_e_deduplicacao_com_limite():
    refs = encontrar("Jo 3:16 Rm 8 Jo 3:16 Sl 23")
    assert [r.canonica for r in refs] == ["João 3:16", "Romanos 8", "Salmos 23"]
