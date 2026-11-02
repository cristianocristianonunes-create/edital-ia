"""Extração de texto dos anexos: PDF (pdftotext), DOCX, TXT e ZIP com esses formatos dentro."""

from __future__ import annotations

import html
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .texto import fatiar, limpa

_TAGS = re.compile(r"<[^>]+>")

# Proteção contra zip malicioso: tamanho total descompactado e número de arquivos.
MAX_ZIP_BYTES = 500 * 1024 * 1024
MAX_ZIP_ARQUIVOS = 300


@dataclass
class Parte:
    nome: str
    paginas: list[str] = field(default_factory=list)
    obs: str | None = None


def paginas_de_pdf(caminho: Path) -> list[str]:
    r = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(caminho), "-"],
        capture_output=True,
        timeout=180,
        check=True,
    )
    paginas = [limpa(p) for p in r.stdout.decode("utf-8", "replace").split("\f")]
    while paginas and not paginas[-1]:
        paginas.pop()
    return paginas


def texto_de_docx(caminho: Path) -> str:
    with zipfile.ZipFile(caminho) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = xml.replace("</w:p>", "\n").replace("<w:tab/>", " ")
    return limpa(html.unescape(_TAGS.sub("", xml)))


class ZipRecusado(Exception):
    pass


def extrair_zip_seguro(caminho: Path, destino: Path) -> None:
    """Descompacta sem deixar nenhum arquivo sair da pasta de destino (zip slip) e com teto de tamanho."""
    raiz = destino.resolve()
    with zipfile.ZipFile(caminho) as z:
        membros = [m for m in z.infolist() if not m.is_dir()]
        if len(membros) > MAX_ZIP_ARQUIVOS:
            raise ZipRecusado(f"zip com {len(membros)} arquivos (limite {MAX_ZIP_ARQUIVOS})")
        if sum(m.file_size for m in membros) > MAX_ZIP_BYTES:
            raise ZipRecusado("zip grande demais depois de descompactado")
        for m in membros:
            alvo = (raiz / m.filename).resolve()
            if not alvo.is_relative_to(raiz):
                continue  # caminho tipo ../../etc/passwd: ignora
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as origem, alvo.open("wb") as saida:
                saida.write(origem.read())


def _ler_solto(f: Path, nome: str) -> Parte:
    e = f.suffix.lower()
    try:
        if e == ".pdf":
            return Parte(nome, paginas_de_pdf(f))
        if e == ".docx":
            return Parte(nome, fatiar(texto_de_docx(f)))
        if e == ".txt":
            return Parte(nome, fatiar(limpa(f.read_text("utf-8", errors="replace"))))
        return Parte(nome, [], f"formato {e or 'sem extensão'} não lido")
    except Exception as err:
        return Parte(nome, [], f"falha ao ler: {err}")


def extrair_arquivo(caminho: Path, nome_original: str | None, pasta_tmp: Path) -> list[Parte]:
    """Identifica o formato pelo cabeçalho (o nome do PNCP nem sempre tem extensão) e extrai."""
    nome = nome_original or caminho.name
    with caminho.open("rb") as f:
        cab = f.read(8)
    ext = Path(nome).suffix.lower()

    if cab[:4] == b"%PDF":
        return [Parte(nome, paginas_de_pdf(caminho))]
    if cab[:2] == b"PK":
        if ext == ".docx":
            return [Parte(nome, fatiar(texto_de_docx(caminho)))]
        destino = Path(tempfile.mkdtemp(prefix="zip-", dir=pasta_tmp))
        try:
            extrair_zip_seguro(caminho, destino)
        except (zipfile.BadZipFile, ZipRecusado) as err:
            return [Parte(nome, [], f"zip não lido: {err}")]
        soltos = sorted((p for p in destino.rglob("*") if p.is_file()), key=str)
        return [_ler_solto(p, str(p.relative_to(destino))) for p in soltos]
    if cab[:4] == b"Rar!":
        return [Parte(nome, [], "arquivo RAR ainda não é lido")]
    if ext == ".txt":
        return [Parte(nome, fatiar(limpa(caminho.read_text("utf-8", errors="replace"))))]
    return [Parte(nome, [], f"formato não reconhecido ({ext or 'sem extensão'})")]
