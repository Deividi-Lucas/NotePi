"""Encontra referências bíblicas ("Jo 3:16", "1Co 13:4-7", "Sl 23") dentro de um texto."""

from __future__ import annotations

import re
from dataclasses import dataclass

from notepi import livros
from notepi.texto import remover_acentos

# Abreviações que também são palavras comuns em português ("os 3 pontos", "na 2ª").
# Sem versículo ("Os 6"), elas NÃO viram referência; com versículo ("Os 6:6"), viram.
PALAVRAS_COMUNS = frozenset({"os", "na", "ne", "et", "at", "am", "is", "ag", "ed"})


@dataclass(frozen=True)
class Referencia:
    livro: int
    capitulo: int
    verso_inicio: int | None = None  # None = capítulo inteiro
    verso_fim: int | None = None

    @property
    def canonica(self) -> str:
        """Forma única usada como nome da tag: 'Romanos 12:1-2', 'João 3:16', 'Salmos 23'."""
        nome = livros.por_numero(self.livro).nome
        if self.verso_inicio is None:
            return f"{nome} {self.capitulo}"
        if self.verso_fim == self.verso_inicio:
            return f"{nome} {self.capitulo}:{self.verso_inicio}"
        return f"{nome} {self.capitulo}:{self.verso_inicio}-{self.verso_fim}"


_PADRAO = re.compile(
    r"""
    (?<!\w)
    (?:(?P<num>[123])\s*|(?P<rom>I{1,3})\s+)?     # 1, 2, 3 ou I, II, III
    (?P<livro>[^\W\d_]{2,})\.?                      # nome ou abreviação (só letras)
    \s*
    (?P<cap>\d{1,3})
    (?:\s*[:.]\s*
       (?P<versos>\d{1,3}(?:\s*[-–]\s*\d{1,3})?(?:\s*,\s*\d{1,3}(?:\s*[-–]\s*\d{1,3})?)*)
    )?
    (?!\w)
    """,
    re.VERBOSE,
)
_INICIO_DE_PALAVRA = re.compile(r"(?<!\w)\w")


def _intervalos(versos: str) -> list[tuple[int, int]]:
    """'1,2,5-7' -> [(1, 2), (5, 7)]: junta versos seguidos e descarta intervalos inválidos."""
    brutos = []
    for parte in versos.replace("–", "-").split(","):
        inicio, _, fim = parte.partition("-")
        a, b = int(inicio), int(fim) if fim.strip() else int(inicio)
        if 1 <= a <= b:
            brutos.append((a, b))
    brutos.sort()
    juntos: list[tuple[int, int]] = []
    for a, b in brutos:
        if juntos and a <= juntos[-1][1] + 1:
            juntos[-1] = (juntos[-1][0], max(b, juntos[-1][1]))
        else:
            juntos.append((a, b))
    return juntos


def _interpretar(m: re.Match[str], *, permitir_ambiguas: bool) -> list[Referencia] | None:
    """None = não é uma referência (continua procurando); [] = é, mas inválida."""
    prefixo = m["num"] or (str(len(m["rom"])) if m["rom"] else "")
    livro = livros.buscar_livro(prefixo, m["livro"])
    if livro is None:
        return None
    capitulo = int(m["cap"])
    if m["versos"] is None:
        comum = remover_acentos(m["livro"]).lower() in PALAVRAS_COMUNS
        if comum and not prefixo and not permitir_ambiguas:
            return None
        if not 1 <= capitulo <= livro.capitulos:
            return []
        return [Referencia(livro.numero, capitulo)]
    if not 1 <= capitulo <= livro.capitulos:
        return []
    return [Referencia(livro.numero, capitulo, a, b) for a, b in _intervalos(m["versos"])]


def encontrar(texto: str) -> list[Referencia]:
    """Todas as referências do texto, sem repetição, na ordem em que aparecem."""
    resultado: list[Referencia] = []
    fim_ultimo = 0
    for inicio in _INICIO_DE_PALAVRA.finditer(texto):
        if inicio.start() < fim_ultimo:
            continue
        m = _PADRAO.match(texto, inicio.start())
        if not m:
            continue
        refs = _interpretar(m, permitir_ambiguas=False)
        if refs is None:
            continue
        fim_ultimo = m.end()
        for ref in refs:
            if ref not in resultado:
                resultado.append(ref)
    return resultado


def referencia_exata(texto: str) -> Referencia | None:
    """Se o texto inteiro for UMA referência ('Romanos 12', 'Rm 12:2'), devolve ela."""
    m = _PADRAO.fullmatch(texto.strip())
    if not m:
        return None
    refs = _interpretar(m, permitir_ambiguas=True)
    return refs[0] if refs and len(refs) == 1 else None
