"""API HTTP: extrair texto dos anexos, conferir citações e gerar a ficha do edital."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import __version__
from .anexos import ErroEdital, ler_anexos
from .citacoes import conferir_trechos
from .ficha import ErroIA, ModeloAnthropic, ModeloIA, ResultadoFicha, gerar_ficha
from .modelos import Arquivo, Pagina, RespostaConferida, TextoEdital

MAX_BYTES_ARQUIVO = 50 * 1024 * 1024

app = FastAPI(title="Edital IA", version=__version__, description="Leitura e análise de editais de licitação com IA.")


def modelo_ia() -> ModeloIA:
    chave = os.environ.get("ANTHROPIC_API_KEY")
    if not chave:
        raise HTTPException(503, "IA sem chave configurada (ANTHROPIC_API_KEY)")
    return ModeloAnthropic(chave)


class PedidoConferir(BaseModel):
    resposta: str
    texto: str
    paginas: list[Pagina] = Field(default_factory=list)


class PedidoFicha(BaseModel):
    texto: str = Field(min_length=1)
    paginas: list[Pagina] = Field(default_factory=list)


@app.get("/saude")
def saude() -> dict[str, str]:
    return {"status": "ok", "versao": __version__}


@app.post("/extrair", response_model=TextoEdital)
async def extrair(arquivos: list[UploadFile]) -> TextoEdital:
    entradas: list[tuple[Arquivo, bytes]] = []
    for i, f in enumerate(arquivos, start=1):
        dados = await f.read(MAX_BYTES_ARQUIVO + 1)
        if len(dados) > MAX_BYTES_ARQUIVO:
            raise HTTPException(413, f"{f.filename}: arquivo maior que 50 MB")
        entradas.append((Arquivo(seq=i, titulo=f.filename or f"anexo {i}"), dados))
    try:
        return await run_in_threadpool(ler_anexos, entradas)
    except ErroEdital as e:
        raise HTTPException(422, str(e)) from e


@app.post("/conferir", response_model=RespostaConferida)
def conferir(p: PedidoConferir) -> RespostaConferida:
    return conferir_trechos(p.resposta, p.texto, p.paginas)


@app.post("/ficha", response_model=ResultadoFicha)
def ficha(p: PedidoFicha, modelo: Annotated[ModeloIA, Depends(modelo_ia)]) -> ResultadoFicha:
    try:
        return gerar_ficha(p.texto, modelo, p.paginas)
    except ErroIA as e:
        raise HTTPException(502, str(e)) from e
