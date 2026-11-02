"""Escolha dos anexos (prioridade e retificações) e montagem do texto com mapa de páginas."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .extracao import extrair_arquivo
from .modelos import Arquivo, InfoArquivo, Lido, Pagina, TextoEdital
from .texto import normal

# ~170 mil tokens (texto de PDF dá ~1,9 caractere por token)
LIMITE = int(os.environ.get("LIMITE_EDITAL_CHARS", "320000"))
MAX_ARQUIVOS = 15

_PRINCIPAL = re.compile(r"termo de referencia|edital|projeto basico")
_DIARIO = re.compile(r"\b(dou|doe|dom|diario|aviso|publicacao|extrato)\b")
_ANEXO = re.compile(r"anexo|minuta|planilha|especifica|estudo tecnico|etp")
_DIARIO_AMPLO = re.compile(r"\b(dou|doe|dom|diario|aviso|publicacao|extrato|jornal|jgc)\b")
_ORDINAIS = re.compile(r"\b(primeira|segunda|terceira|quarta|quinta|1a|2a|3a)\b")
_VERSAO = re.compile(
    r"retifica\w*|republica\w*|alterad\w*|atualizad\w*|versao\s*\d*|\bv\d+\b|\(\s*\d+\s*\)|\b\d+\b|[_.()-]"
)


class ErroEdital(Exception):
    pass


def prioridade(a: Arquivo) -> int:
    """0 = edital/termo de referência, 1 = anexos técnicos, 2 = outros, 3 = publicação em diário."""
    t = normal(f"{a.titulo} {a.tipo or ''}")
    if _PRINCIPAL.search(t) and not _DIARIO.search(t):
        return 0
    if _ANEXO.search(t):
        return 1
    if _DIARIO_AMPLO.search(t):
        return 3
    return 2


def familia(a: Arquivo) -> str:
    """ "Edital", "Edital_Retificado" e "Edital_Segunda Retificação" são o mesmo documento."""
    t = _ORDINAIS.sub(" ", normal(a.titulo))
    t = _VERSAO.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or f"x{a.seq}"


def versao_mais_nova(arqs: Sequence[Arquivo]) -> tuple[list[Arquivo], list[Arquivo]]:
    """Separa a versão mais nova de cada documento (vale) das versões substituídas (antigos)."""
    ultimo: dict[str, Arquivo] = {}
    for a in arqs:
        f = familia(a)
        if f not in ultimo or ultimo[f].seq < a.seq:
            ultimo[f] = a
    vale = [a for a in arqs if ultimo[familia(a)] is a]
    antigos = [a for a in arqs if ultimo[familia(a)] is not a]
    return vale, antigos


def montar_texto(lidos: Sequence[Lido], limite: int = LIMITE) -> TextoEdital:
    """Junta as partes em ordem de prioridade até o limite, marcando cada página como [Arq N p. X]."""
    ordenados = sorted(lidos, key=lambda x: (prioridade(x.arquivo), x.arquivo.seq))
    texto = ""
    truncado = False
    n = 0
    paginas: list[Pagina] = []
    arquivos: list[InfoArquivo] = []

    for lido in ordenados:
        chars = sum(len(p) for p in lido.paginas)
        titulo = lido.arquivo.titulo
        if lido.nome and lido.nome != lido.arquivo.titulo:
            titulo += f" / {lido.nome}"
        info = InfoArquivo(
            seq=lido.arquivo.seq,
            titulo=titulo,
            tipo=lido.arquivo.tipo,
            paginas=len(lido.paginas),
            chars=chars,
            obs=lido.obs,
        )
        if not chars:
            info.obs = info.obs or "sem texto (provavelmente digitalizado como imagem)"
            arquivos.append(info)
            continue
        if info.obs:
            arquivos.append(info)
            continue
        if len(texto) >= limite:
            info.obs = "não coube no limite de leitura"
            truncado = True
            arquivos.append(info)
            continue

        n += 1
        info.arq = n
        texto += f"\n\n===== ARQUIVO {n}: {titulo} ({lido.arquivo.tipo or 'anexo'}) =====\n"
        for i, pg in enumerate(lido.paginas):
            if len(texto) >= limite:
                truncado = True
                info.obs = f"lido até a página {i}"
                break
            if not pg:
                continue
            texto += f"\n[Arq {n} p. {i + 1}]\n"
            ini = len(texto)
            texto += pg[: limite - len(texto) + 2000]
            paginas.append(Pagina(arq=n, pagina=i + 1, ini=ini, fim=len(texto)))
        arquivos.append(info)

    # Tira os espaços das pontas e corrige os índices. (A versão em Node aparava o texto depois de
    # calcular os índices, e todas as páginas ficavam deslocadas em 2 caracteres.)
    corte = len(texto) - len(texto.lstrip())
    texto = texto.strip()
    for p in paginas:
        p.ini = max(0, p.ini - corte)
        p.fim = min(len(texto), p.fim - corte)

    if not texto:
        detalhes = "; ".join(f"{a.titulo}: {a.obs}" for a in arquivos)
        raise ErroEdital(f"não consegui ler texto nos anexos ({detalhes})")
    obs = "Edital muito grande: parte dos anexos não foi lida (veja a lista de arquivos)." if truncado else None
    return TextoEdital(texto=texto, paginas=paginas, arquivos=arquivos, chars=len(texto), truncado=truncado, obs=obs)


def ler_anexos(entradas: Sequence[tuple[Arquivo, bytes]], limite: int = LIMITE) -> TextoEdital:
    """Do conteúdo bruto dos anexos ao texto pronto para a IA."""
    if not entradas:
        raise ErroEdital("nenhum anexo enviado")
    conteudo = {a.seq: dados for a, dados in entradas}
    vale, antigos = versao_mais_nova([a for a, _ in entradas])
    lidos = [Lido(arquivo=a, nome=a.titulo, obs="versão anterior, substituída por retificação") for a in antigos]
    escolhidos = sorted(vale, key=lambda a: (prioridade(a), -a.seq))[:MAX_ARQUIVOS]

    pasta = Path(tempfile.mkdtemp(prefix="edital-"))
    try:
        for a in escolhidos:
            local = pasta / f"a{a.seq}"
            local.write_bytes(conteudo[a.seq])
            try:
                partes = extrair_arquivo(local, a.titulo, pasta)
            except Exception as err:
                lidos.append(Lido(arquivo=a, nome=a.titulo, obs=f"falha ao ler: {err}"))
                continue
            lidos.extend(Lido(arquivo=a, nome=p.nome, paginas=p.paginas, obs=p.obs) for p in partes)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return montar_texto(lidos, limite)
