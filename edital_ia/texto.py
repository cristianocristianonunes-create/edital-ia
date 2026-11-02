"""Limpeza e normalização de texto extraído de editais."""

from __future__ import annotations

import re
import unicodedata

_ESPACOS = re.compile(r"[ \t ]+")
_QUEBRA = re.compile(r" *\n *")
_LINHAS_VAZIAS = re.compile(r"\n{3,}")
_COMBINANTES = re.compile(r"[̀-ͯ]")
_HIFEN_QUEBRADO = re.compile(r"-\s*\n\s*")
_ASPAS = re.compile(r"[“”\"«»'‘’]")
_FORA = re.compile(r"[^a-z0-9%$,.;:/()-]+")
_BRANCOS = re.compile(r"\s+")

TAMANHO_FATIA = 3500


def limpa(s: str | None) -> str:
    """Tira espaços repetidos e linhas vazias em excesso, mantendo as quebras de parágrafo."""
    t = (s or "").replace("\r", "")
    t = _ESPACOS.sub(" ", t)
    t = _QUEBRA.sub("\n", t)
    t = _LINHAS_VAZIAS.sub("\n\n", t)
    return t.strip()


def normal(s: str | None) -> str:
    """Forma comparável: minúsculas, sem acento, sem aspas, palavra hifenizada na quebra de linha reunida."""
    t = unicodedata.normalize("NFD", (s or "").lower())
    t = _COMBINANTES.sub("", t)
    t = _HIFEN_QUEBRADO.sub("", t)
    t = _ASPAS.sub("", t)
    t = _FORA.sub(" ", t)
    return _BRANCOS.sub(" ", t).strip()


def fatiar(t: str, tamanho: int = TAMANHO_FATIA) -> list[str]:
    """Texto sem paginação (docx, txt) vira "páginas" de tamanho fixo, para a citação ter onde apontar."""
    partes = [t[i : i + tamanho] for i in range(0, len(t), tamanho)]
    return partes or [""]
