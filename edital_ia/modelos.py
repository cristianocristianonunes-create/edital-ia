"""Tipos de dados compartilhados pela extração, pela citação e pela API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Arquivo(BaseModel):
    """Anexo do edital como o PNCP lista (seq é o sequencial do documento)."""

    seq: int
    titulo: str
    tipo: str | None = None


class Lido(BaseModel):
    """Uma parte extraída de um anexo (um zip pode gerar várias)."""

    arquivo: Arquivo
    nome: str
    paginas: list[str] = Field(default_factory=list)
    obs: str | None = None


class Pagina(BaseModel):
    """Onde a página X do arquivo N está dentro do texto montado (índices de texto[ini:fim])."""

    arq: int
    pagina: int
    ini: int
    fim: int


class InfoArquivo(BaseModel):
    seq: int
    titulo: str
    tipo: str | None
    paginas: int
    chars: int
    obs: str | None = None
    arq: int | None = None


class TextoEdital(BaseModel):
    texto: str
    paginas: list[Pagina]
    arquivos: list[InfoArquivo]
    chars: int
    truncado: bool
    obs: str | None = None


Conferido = Literal["pagina", "outra_pagina", "nao"]


class Trecho(BaseModel):
    arq: int
    pagina: int
    citacao: str
    conferido: Conferido


class RespostaConferida(BaseModel):
    corpo: str
    trechos: list[Trecho]
