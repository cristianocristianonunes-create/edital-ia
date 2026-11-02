"""Compara esta versão com a versão em Node usando dados reais do banco (somente leitura).

1. Citações: refaz a conferência dos trechos de cada resposta guardada e compara com o que o Node gravou.
2. Fichas: mede quantas referências (Arq N p. X) das fichas apontam para páginas que existem.

Uso: PGHOST=... PGPORT=... PGUSER=... PGPASSWORD=... PGDATABASE=... python scripts/paridade.py [limite]
"""

from __future__ import annotations

import bisect
import sys
from collections.abc import Callable

import psycopg

from edital_ia.citacoes import conferir_refs, conferir_trechos
from edital_ia.modelos import Pagina


def indice_utf16(texto: str) -> Callable[[int], int]:
    """O Node guarda posições em unidades UTF-16; o Python conta caracteres. Converte quando há emoji etc."""
    if all(ord(c) < 0x10000 for c in texto):
        return lambda u: u
    pos, acc = [], 0
    for c in texto:
        pos.append(acc)
        acc += 2 if ord(c) > 0xFFFF else 1
    pos.append(acc)
    return lambda u: bisect.bisect_left(pos, u)


def paginas_python(texto: str, brutas: list[dict[str, int]]) -> list[Pagina]:
    conv = indice_utf16(texto)
    return [Pagina(arq=p["arq"], pagina=p["pagina"], ini=conv(p["ini"]), fim=conv(p["fim"])) for p in brutas]


def main() -> None:
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    with psycopg.connect() as con:
        con.read_only = True
        respostas = con.execute(
            """select c.id, c.resposta, c.trechos, t.texto, t.paginas from edital_chat c
               join edital_textos t using (edital_id) where c.resposta is not null order by c.id desc limit %s""",
            (limite,),
        ).fetchall()
        fichas = con.execute(
            """select f.edital_id, f.ficha, t.texto, t.paginas from edital_fichas f
               join edital_textos t using (edital_id) where f.ficha is not null order by f.edital_id desc limit %s""",
            (limite,),
        ).fetchall()

    iguais, diferentes, contagem = 0, [], {"pagina": 0, "outra_pagina": 0, "nao": 0}
    for cid, resposta, trechos_node, texto, paginas in respostas:
        py = conferir_trechos(resposta, texto, paginas_python(texto, paginas))
        a = [(t.arq, t.pagina, t.conferido) for t in py.trechos]
        b = [(t["arq"], t["pagina"], t["conferido"]) for t in (trechos_node or [])]
        for t in py.trechos:
            contagem[t.conferido] += 1
        if a == b:
            iguais += 1
        else:
            diferentes.append((cid, b, a))

    print(f"CITAÇÕES: {len(respostas)} respostas comparadas, {iguais} iguais ao Node, {len(diferentes)} diferentes")
    total = sum(contagem.values()) or 1
    print(
        "  trechos achados na página citada: {:.0%} | em outra página: {:.0%} | não achados: {:.0%}".format(
            contagem["pagina"] / total, contagem["outra_pagina"] / total, contagem["nao"] / total
        )
    )
    for cid, b, a in diferentes[:10]:
        print(f"  resposta {cid}: node={b} python={a}")

    soma_total = soma_validas = 0
    for _eid, ficha, texto, paginas in fichas:
        r = conferir_refs(ficha, paginas_python(texto, paginas))
        soma_total += int(r["total"])  # type: ignore[call-overload]
        soma_validas += int(r["validas"])  # type: ignore[call-overload]
    print(
        f"FICHAS: {len(fichas)} fichas, {soma_total} referências, "
        f"{soma_validas / (soma_total or 1):.1%} apontam para página que existe no texto lido"
    )


if __name__ == "__main__":
    main()
