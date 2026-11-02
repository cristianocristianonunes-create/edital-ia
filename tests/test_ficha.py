import json

import pytest

from edital_ia.ficha import RespostaIA, custo_usd, extrair_json, gerar_ficha
from edital_ia.modelos import Pagina


class ModeloFalso:
    def __init__(self, texto: str, cortado: bool = False) -> None:
        self.texto = texto
        self.cortado = cortado
        self.chamadas: list[dict] = []

    def perguntar(self, *, system, messages, max_tokens):
        self.chamadas.append({"system": system, "messages": messages, "max_tokens": max_tokens})
        return RespostaIA(texto=self.texto, modelo="falso", custo_usd=0.01, cortado=self.cortado)


@pytest.mark.parametrize(
    "bruto",
    ['{"a": 1}', '```json\n{"a": 1}\n```', 'Aqui está a ficha:\n{"a": 1}\nEspero ter ajudado.'],
)
def test_extrair_json(bruto):
    assert extrair_json(bruto) == {"a": 1}


def test_extrair_json_invalido():
    assert extrair_json("não sei") is None
    assert extrair_json("{quebrado") is None


def test_custo():
    assert custo_usd("claude-opus-5-5", {"input_tokens": 1_000_000, "output_tokens": 100_000}) == pytest.approx(6.0)
    # haiku acima de 100 mil tokens de entrada custa 5x
    assert custo_usd("claude-haiku-5-5", {"input_tokens": 200_000}) == pytest.approx(0.1)


def test_gerar_ficha_valida_formato_e_referencias():
    ficha = {
        "resumo": "Compra de cadeiras.",
        "prazos": [{"evento": "entrega", "quando": "30 dias", "ref": "Arq 1 p. 4"}],
    }
    modelo = ModeloFalso(json.dumps(ficha))
    r = gerar_ficha("texto do edital", modelo, [Pagina(arq=1, pagina=1, ini=0, fim=5)])
    assert r.ficha is not None and r.ficha.resumo == "Compra de cadeiras."
    assert r.ficha.habilitacao.juridica == []  # campos ausentes viram listas vazias
    assert r.refs == {"total": 1, "validas": 0, "invalidas": ["Arq 1 p. 4"]}
    conteudo = modelo.chamadas[0]["messages"][0]["content"]
    assert conteudo[0]["cache_control"] == {"type": "ephemeral"}  # edital primeiro, em cache
    assert "texto do edital" in conteudo[0]["text"]


def test_gerar_ficha_resposta_que_nao_e_json():
    r = gerar_ficha("x", ModeloFalso("desculpe, não consegui"))
    assert r.ficha is None and r.erro and "formato esperado" in r.erro


def test_gerar_ficha_sem_resumo():
    r = gerar_ficha("x", ModeloFalso('{"objeto": "cadeiras"}'))
    assert r.ficha is None and r.erro and r.erro.startswith("ficha fora do formato")


def test_gerar_ficha_cortada():
    r = gerar_ficha("x", ModeloFalso('{"resumo": "ok"}', cortado=True))
    assert r.ficha is not None and r.erro == "resposta cortada no limite de tamanho"
