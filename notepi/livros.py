"""Os 66 livros da Bíblia: nome, abreviações em português e número de capítulos."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from notepi.texto import remover_acentos


@dataclass(frozen=True)
class Livro:
    numero: int
    nome: str
    capitulos: int
    abreviacoes: tuple[str, ...]


_DADOS: list[tuple[int, str, int, tuple[str, ...]]] = [
    (1, "Gênesis", 50, ("Gn", "Gên")),
    (2, "Êxodo", 40, ("Êx", "Ex")),
    (3, "Levítico", 27, ("Lv", "Lev")),
    (4, "Números", 36, ("Nm", "Núm")),
    (5, "Deuteronômio", 34, ("Dt", "Deut")),
    (6, "Josué", 24, ("Js",)),
    (7, "Juízes", 21, ("Jz",)),
    (8, "Rute", 4, ("Rt",)),
    (9, "1 Samuel", 31, ("1Sm", "1Sam")),
    (10, "2 Samuel", 24, ("2Sm", "2Sam")),
    (11, "1 Reis", 22, ("1Rs",)),
    (12, "2 Reis", 25, ("2Rs",)),
    (13, "1 Crônicas", 29, ("1Cr", "1Crô")),
    (14, "2 Crônicas", 36, ("2Cr", "2Crô")),
    (15, "Esdras", 10, ("Ed",)),
    (16, "Neemias", 13, ("Ne",)),
    (17, "Ester", 10, ("Et",)),
    (18, "Jó", 42, ()),  # tratado à parte: só é reconhecido COM acento (ver _SO_COM_ACENTO)
    (19, "Salmos", 150, ("Sl", "Sal", "Salmo")),
    (20, "Provérbios", 31, ("Pv", "Prov")),
    (21, "Eclesiastes", 12, ("Ec", "Ecl")),
    (22, "Cânticos", 8, ("Ct", "Cânt", "Cantares")),
    (23, "Isaías", 66, ("Is",)),
    (24, "Jeremias", 52, ("Jr", "Jer")),
    (25, "Lamentações", 5, ("Lm",)),
    (26, "Ezequiel", 48, ("Ez",)),
    (27, "Daniel", 12, ("Dn",)),
    (28, "Oseias", 14, ("Os", "Oséias")),
    (29, "Joel", 3, ("Jl",)),
    (30, "Amós", 9, ("Am",)),
    (31, "Obadias", 1, ("Ob",)),
    (32, "Jonas", 4, ("Jn",)),
    (33, "Miqueias", 7, ("Mq", "Miquéias")),
    (34, "Naum", 3, ("Na",)),
    (35, "Habacuque", 3, ("Hc",)),
    (36, "Sofonias", 3, ("Sf",)),
    (37, "Ageu", 2, ("Ag",)),
    (38, "Zacarias", 14, ("Zc",)),
    (39, "Malaquias", 4, ("Ml",)),
    (40, "Mateus", 28, ("Mt",)),
    (41, "Marcos", 16, ("Mc",)),
    (42, "Lucas", 24, ("Lc",)),
    (43, "João", 21, ("Jo",)),
    (44, "Atos", 28, ("At",)),
    (45, "Romanos", 16, ("Rm", "Rom")),
    (46, "1 Coríntios", 16, ("1Co", "1Cor")),
    (47, "2 Coríntios", 13, ("2Co", "2Cor")),
    (48, "Gálatas", 6, ("Gl", "Gál")),
    (49, "Efésios", 6, ("Ef",)),
    (50, "Filipenses", 4, ("Fp", "Fl")),
    (51, "Colossenses", 4, ("Cl", "Col")),
    (52, "1 Tessalonicenses", 5, ("1Ts",)),
    (53, "2 Tessalonicenses", 3, ("2Ts",)),
    (54, "1 Timóteo", 6, ("1Tm", "1Tim")),
    (55, "2 Timóteo", 4, ("2Tm", "2Tim")),
    (56, "Tito", 3, ("Tt",)),
    (57, "Filemom", 1, ("Fm",)),
    (58, "Hebreus", 13, ("Hb",)),
    (59, "Tiago", 5, ("Tg",)),
    (60, "1 Pedro", 5, ("1Pe", "1Pd")),
    (61, "2 Pedro", 3, ("2Pe", "2Pd")),
    (62, "1 João", 5, ("1Jo",)),
    (63, "2 João", 1, ("2Jo",)),
    (64, "3 João", 1, ("3Jo",)),
    (65, "Judas", 1, ("Jd",)),
    (66, "Apocalipse", 22, ("Ap",)),
]

LIVROS: tuple[Livro, ...] = tuple(Livro(n, nome, caps, abrevs) for n, nome, caps, abrevs in _DADOS)
_POR_NUMERO = {livro.numero: livro for livro in LIVROS}

# "Jó" (livro 18) e "Jo" (João) ficariam iguais sem acento.
# Regra: "Jó" com acento é Jó; "Jo" sem acento é sempre João.
_SO_COM_ACENTO = {"jó": 18}


def _chave(texto: str) -> str:
    """'1 Coríntios' -> '1corintios'; 'Êx.' -> 'ex'."""
    return remover_acentos(texto).lower().replace(" ", "").replace(".", "")


def _montar_indice() -> dict[str, int]:
    indice: dict[str, int] = {}
    for livro in LIVROS:
        if livro.numero in _SO_COM_ACENTO.values():
            continue
        for forma in (livro.nome, *livro.abreviacoes):
            chave = _chave(forma)
            if indice.get(chave, livro.numero) != livro.numero:
                raise ValueError(f"abreviação repetida: {forma!r}")
            indice[chave] = livro.numero
    return indice


_INDICE = _montar_indice()


def por_numero(numero: int) -> Livro:
    return _POR_NUMERO[numero]


def buscar_livro(prefixo: str, nome: str) -> Livro | None:
    """Encontra o livro pelo prefixo numérico ('', '1', '2', '3') e pelo nome ou abreviação.

    >>> buscar_livro("1", "Co").nome
    '1 Coríntios'
    """
    nome = unicodedata.normalize("NFC", nome).lower()
    if not prefixo and nome in _SO_COM_ACENTO:
        return _POR_NUMERO[_SO_COM_ACENTO[nome]]
    numero = _INDICE.get(prefixo + _chave(nome))
    return _POR_NUMERO[numero] if numero else None
