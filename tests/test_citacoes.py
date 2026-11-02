from edital_ia.citacoes import conferir_refs, conferir_trechos
from edital_ia.modelos import Pagina

TEXTO = "===== ARQUIVO 1: Edital =====\n\n[Arq 1 p. 1]\nO prazo de entrega é de 30 (trinta) dias corridos.\n\n[Arq 1 p. 2]\nA multa será de 10% sobre o valor."
P1 = TEXTO.index("O prazo")
P2 = TEXTO.index("A multa")
PAGINAS = [Pagina(arq=1, pagina=1, ini=P1, fim=P2 - 15), Pagina(arq=1, pagina=2, ini=P2, fim=len(TEXTO))]


def test_confere_pagina_outra_pagina_e_inexistente():
    resposta = (
        "O prazo é de 30 dias (Arq 1 p. 1).\n"
        "TRECHOS:\n"
        '[Arq 1 p. 1] "O prazo de entrega é de 30 (trinta) dias corridos."\n'
        '[Arq 1 p. 1] "A multa será de 10% sobre o valor"\n'
        "[Arq 1 p. 2] “garantia de 5 anos”\n"
        "linha sem referência"
    )
    r = conferir_trechos(resposta, TEXTO, PAGINAS)
    assert r.corpo == "O prazo é de 30 dias (Arq 1 p. 1)."
    assert [t.conferido for t in r.trechos] == ["pagina", "outra_pagina", "nao"]
    assert r.trechos[2].citacao == "garantia de 5 anos"


def test_sem_bloco_de_trechos():
    r = conferir_trechos("O edital não trata disso.", TEXTO, PAGINAS)
    assert r.corpo == "O edital não trata disso." and r.trechos == []


def test_trechos_em_negrito_markdown():
    r = conferir_trechos('Resposta\n**TRECHOS:**\n[Arq 1 p. 2] "multa será de 10%"', TEXTO, PAGINAS)
    assert r.trechos[0].conferido == "pagina"


def test_conferir_refs_da_ficha():
    ficha = {"prazos": [{"evento": "entrega", "ref": "Arq 1 p. 1"}], "riscos": [{"ref": "Arq 2 p. 9; Arq 1, pág. 2"}]}
    assert conferir_refs(ficha, PAGINAS) == {"total": 3, "validas": 2, "invalidas": ["Arq 2 p. 9"]}
