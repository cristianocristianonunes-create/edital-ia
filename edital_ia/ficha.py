"""Ficha de análise do edital gerada pela IA (Claude), com validação do formato e das referências."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .citacoes import conferir_refs
from .modelos import Pagina, TextoEdital

# Prompts fixos: o cache da API depende de o começo da mensagem ser idêntico entre chamadas.
SISTEMA = """Você é analista de licitações públicas no Brasil (Lei 14.133/2021, Lei 10.520/2002, LC 123/2006 e normas correlatas) e trabalha para uma empresa fornecedora que avalia se vai participar.
Você recebe o texto extraído dos anexos de um edital publicado no PNCP. Cada página vem marcada como [Arq N p. X].
Regras:
- Responda só com base no texto do edital. Se a informação não estiver lá, diga claramente que o edital não traz isso.
- Sempre aponte onde está cada informação no formato (Arq N p. X).
- Escreva em português do Brasil, linguagem simples e direta, sem enrolação.
- Prazo, valor, exigência de documento e penalidade são os pontos que mais importam ao fornecedor: seja exato neles."""

PEDIDO_FICHA = """Monte a ficha de análise deste edital. Responda SOMENTE com um objeto JSON válido (sem texto antes ou depois, sem cercas de código), neste formato:
{
 "resumo": "3 a 5 frases: o que está sendo comprado, por quem, como será a disputa e o ponto mais importante para decidir participar",
 "objeto": "objeto da licitação",
 "orgao": "órgão/unidade compradora",
 "modalidade": "modalidade e número",
 "criterio_julgamento": "menor preço por item/lote/global, maior desconto etc.",
 "modo_disputa": "aberto, fechado, aberto-fechado...",
 "registro_de_precos": "sim/não e prazo da ata, se houver",
 "valor_estimado": "valor ou 'sigiloso' ou 'não informado'",
 "beneficio_me_epp": "exclusivo, cota reservada, nenhum... com os itens afetados",
 "prazos": [{"evento": "ex.: abertura das propostas, sessão pública, impugnação, esclarecimentos, entrega, vigência", "quando": "data/hora ou prazo", "ref": "Arq N p. X"}],
 "habilitacao": {
   "juridica": [{"item": "documento exigido", "ref": "Arq N p. X"}],
   "fiscal_trabalhista": [{"item": "...", "ref": "..."}],
   "economico_financeira": [{"item": "...", "ref": "..."}],
   "tecnica": [{"item": "...", "ref": "..."}],
   "outros": [{"item": "declarações e demais exigências", "ref": "..."}]
 },
 "proposta": [{"item": "o que a proposta precisa conter (validade, marca/modelo, amostra, catálogo, garantia...)", "ref": "..."}],
 "execucao": [{"item": "prazo e local de entrega, forma e prazo de pagamento, reajuste, garantia contratual", "ref": "..."}],
 "penalidades": [{"item": "multa ou sanção com percentual/prazo", "ref": "..."}],
 "riscos": [{"risco": "o que pode prejudicar o fornecedor ou desclassificá-lo", "gravidade": "alta|media|baixa", "ref": "..."}],
 "pontos_de_atencao": ["exigências incomuns, possíveis direcionamentos, contradições entre anexos, itens que merecem pedido de esclarecimento ou impugnação"],
 "itens_principais": [{"item": "nº e descrição curta", "quantidade": "...", "valor_unitario_estimado": "..."}]
}
Use listas vazias quando não houver informação. Seja conciso: cada item com no máximo 30 palavras, sem repetir o mesmo dado em seções diferentes; em itens_principais, no máximo 15; em prazos, só os que o fornecedor precisa cumprir ou acompanhar."""


# ---------- formato esperado (tolerante: campos extras são aceitos, campos que faltam ficam vazios) ----------
class _Livre(BaseModel):
    model_config = ConfigDict(extra="allow")


class ItemRef(_Livre):
    item: str = ""
    ref: str = ""


class Prazo(_Livre):
    evento: str = ""
    quando: str = ""
    ref: str = ""


class Risco(_Livre):
    risco: str = ""
    gravidade: str = ""
    ref: str = ""


class Habilitacao(_Livre):
    juridica: list[ItemRef] = Field(default_factory=list)
    fiscal_trabalhista: list[ItemRef] = Field(default_factory=list)
    economico_financeira: list[ItemRef] = Field(default_factory=list)
    tecnica: list[ItemRef] = Field(default_factory=list)
    outros: list[ItemRef] = Field(default_factory=list)


class Ficha(_Livre):
    resumo: str
    objeto: str = ""
    orgao: str = ""
    modalidade: str = ""
    criterio_julgamento: str = ""
    modo_disputa: str = ""
    registro_de_precos: str = ""
    valor_estimado: str = ""
    beneficio_me_epp: str = ""
    prazos: list[Prazo] = Field(default_factory=list)
    habilitacao: Habilitacao = Field(default_factory=Habilitacao)
    proposta: list[ItemRef] = Field(default_factory=list)
    execucao: list[ItemRef] = Field(default_factory=list)
    penalidades: list[ItemRef] = Field(default_factory=list)
    riscos: list[Risco] = Field(default_factory=list)
    pontos_de_atencao: list[str] = Field(default_factory=list)
    itens_principais: list[dict[str, Any]] = Field(default_factory=list)


# ---------- acesso à IA ----------
@dataclass
class RespostaIA:
    texto: str
    modelo: str
    custo_usd: float
    cortado: bool = False


class ModeloIA(Protocol):
    def perguntar(self, *, system: str, messages: list[dict[str, Any]], max_tokens: int) -> RespostaIA: ...


class ErroIA(Exception):
    pass


# US$ por milhão de tokens: entrada, saída, leitura de cache, escrita de cache.
PRECOS: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4, 20, 0.20, 5),
    "claude-sonnet-5-5": (2, 10, 0.20, 2.5),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-fable-5-1": (10, 50, 0.25, 12.5),
}


def custo_usd(modelo: str, uso: dict[str, Any]) -> float:
    ent, sai, lei, esc = PRECOS.get(modelo, PRECOS["claude-opus-5-5"])
    entrada = int(uso.get("input_tokens") or 0)
    saida = int(uso.get("output_tokens") or 0)
    lida = int(uso.get("cache_read_input_tokens") or 0)
    criada = int(uso.get("cache_creation_input_tokens") or 0)
    if modelo == "claude-haiku-5-5" and entrada + lida + criada > 100_000:
        ent, sai, lei, esc = ent * 5, sai * 5, lei * 5, esc * 5
    return (entrada * ent + saida * sai + lida * lei + criada * esc) / 1e6


class ModeloAnthropic:
    """Implementação real, pela API da Anthropic (streaming, porque o edital pode ser grande)."""

    def __init__(self, chave: str, modelo: str | None = None, effort: str | None = "medium") -> None:
        import anthropic

        self._cli = anthropic.Anthropic(api_key=chave, max_retries=3, timeout=15 * 60)
        self.modelo = modelo or os.environ.get("MODELO_IA", "claude-opus-5-5")
        self.effort = effort

    def perguntar(self, *, system: str, messages: list[dict[str, Any]], max_tokens: int) -> RespostaIA:
        extra = {"output_config": {"effort": self.effort}} if self.effort else None
        with self._cli.messages.stream(
            model=self.modelo,
            max_tokens=max_tokens,
            system=system,
            messages=cast(Any, messages),
            extra_body=extra,
        ) as fluxo:
            msg = fluxo.get_final_message()
        if msg.stop_reason == "refusal":
            raise ErroIA("a IA recusou responder este pedido")
        texto = "".join(getattr(b, "text", "") for b in msg.content if b.type == "text")
        return RespostaIA(
            texto=texto,
            modelo=msg.model,
            custo_usd=custo_usd(msg.model, msg.usage.model_dump()),
            cortado=msg.stop_reason == "max_tokens",
        )


# ---------- geração ----------
_CERCA_INICIO = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_CERCA_FIM = re.compile(r"```\s*$")


def extrair_json(s: str) -> Any:
    """A IA às vezes cerca o JSON com ``` ou põe uma frase antes; tenta recuperar o objeto."""
    t = _CERCA_FIM.sub("", _CERCA_INICIO.sub("", s)).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    i, f = t.find("{"), t.rfind("}")
    if i >= 0 and f > i:
        try:
            return json.loads(t[i : f + 1])
        except ValueError:
            return None
    return None


def bloco_edital(texto: str) -> dict[str, Any]:
    return {"type": "text", "text": f"<edital>\n{texto}\n</edital>", "cache_control": {"type": "ephemeral"}}


class ResultadoFicha(BaseModel):
    ficha: Ficha | None
    bruto: str
    modelo: str
    custo_usd: float
    erro: str | None = None
    refs: dict[str, Any] | None = None


def gerar_ficha(edital: TextoEdital | str, modelo: ModeloIA, paginas: list[Pagina] | None = None) -> ResultadoFicha:
    if isinstance(edital, TextoEdital):
        texto, paginas = edital.texto, edital.paginas
    else:
        texto = edital
    r = modelo.perguntar(
        system=SISTEMA,
        max_tokens=32000,
        messages=[{"role": "user", "content": [bloco_edital(texto), {"type": "text", "text": PEDIDO_FICHA}]}],
    )
    dados = extrair_json(r.texto)
    if dados is None:
        erro = "a IA não devolveu a ficha no formato esperado (texto bruto guardado)"
        return ResultadoFicha(ficha=None, bruto=r.texto, modelo=r.modelo, custo_usd=r.custo_usd, erro=erro)
    try:
        ficha = Ficha.model_validate(dados)
    except ValidationError as e:
        erro = f"ficha fora do formato: {e.error_count()} problema(s)"
        return ResultadoFicha(ficha=None, bruto=r.texto, modelo=r.modelo, custo_usd=r.custo_usd, erro=erro)
    refs = conferir_refs(dados, paginas) if paginas else None
    aviso = "resposta cortada no limite de tamanho" if r.cortado else None
    return ResultadoFicha(ficha=ficha, bruto=r.texto, modelo=r.modelo, custo_usd=r.custo_usd, erro=aviso, refs=refs)
