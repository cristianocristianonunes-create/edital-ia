"""Confere se o trecho que a IA citou existe mesmo no edital, e em qual página."""

from __future__ import annotations

import re
from collections.abc import Sequence

from .modelos import Conferido, Pagina, RespostaConferida, Trecho
from .texto import normal

SEPARADOR = re.compile(r"\n\s*\**TRECHOS:?\**\s*\n?", re.IGNORECASE)
_LINHA = re.compile(r"\[\s*Arq\s*(\d+)\s*p\.?\s*(\d+)\s*\]\s*[“\"]?(.+?)[”\"]?\s*$", re.IGNORECASE)
_REF = re.compile(r"Arq\.?\s*(\d+)\s*,?\s*p(?:ág|ag)?\.?\s*(\d+)", re.IGNORECASE)


def miolo(citacao: str, palavras: int = 12) -> str:
    """Pedaço central da citação: aspas, quebras e reticências costumam atrapalhar as pontas."""
    alvo = [p for p in normal(citacao).replace("...", " ").split(" ") if p]
    meio = len(alvo) // 2
    metade = palavras // 2
    return " ".join(alvo[max(0, meio - metade) : meio + metade])


def conferir_trechos(resposta: str, texto: str, paginas: Sequence[Pagina]) -> RespostaConferida:
    partes = SEPARADOR.split(resposta)
    corpo = partes[0]
    bloco = partes[1] if len(partes) > 1 else ""
    por_pagina = {(p.arq, p.pagina): p for p in paginas}
    texto_normal = normal(texto)

    trechos: list[Trecho] = []
    for linha in bloco.split("\n"):
        m = _LINHA.search(linha)
        if not m:
            continue
        arq, pagina, citacao = int(m.group(1)), int(m.group(2)), m.group(3).strip()
        meio = miolo(citacao)
        pg = por_pagina.get((arq, pagina))
        conferido: Conferido = "nao"
        if meio and pg and meio in normal(texto[pg.ini : pg.fim]):
            conferido = "pagina"
        elif meio and meio in texto_normal:
            conferido = "outra_pagina"
        trechos.append(Trecho(arq=arq, pagina=pagina, citacao=citacao, conferido=conferido))
    return RespostaConferida(corpo=corpo.strip(), trechos=trechos)


def refs_da_ficha(ficha: object) -> list[tuple[int, int]]:
    """Todas as referências (Arq N p. X) que aparecem em qualquer campo da ficha."""
    achadas: list[tuple[int, int]] = []

    def andar(v: object) -> None:
        if isinstance(v, str):
            achadas.extend((int(a), int(p)) for a, p in _REF.findall(v))
        elif isinstance(v, dict):
            for x in v.values():
                andar(x)
        elif isinstance(v, list):
            for x in v:
                andar(x)

    andar(ficha)
    return achadas


def conferir_refs(ficha: object, paginas: Sequence[Pagina]) -> dict[str, object]:
    """Quantas referências da ficha apontam para uma página que existe no texto lido."""
    existentes = {(p.arq, p.pagina) for p in paginas}
    refs = refs_da_ficha(ficha)
    invalidas = sorted({r for r in refs if r not in existentes})
    validas = sum(1 for r in refs if r in existentes)
    return {
        "total": len(refs),
        "validas": validas,
        "invalidas": [f"Arq {a} p. {p}" for a, p in invalidas],
    }
