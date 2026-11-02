import pytest
from conftest import docx_simples, pdf_simples, tem_pdftotext, zip_com

from edital_ia.anexos import ErroEdital, familia, ler_anexos, montar_texto, prioridade, versao_mais_nova
from edital_ia.modelos import Arquivo, Lido


def arq(seq: int, titulo: str, tipo: str | None = None) -> Arquivo:
    return Arquivo(seq=seq, titulo=titulo, tipo=tipo)


@pytest.mark.parametrize(
    ("titulo", "tipo", "esperado"),
    [
        ("Edital Pregão 12/2026", "Edital", 0),
        ("Termo de Referência", None, 0),
        ("Anexo I - Planilha de custos", None, 1),
        ("Estudo Técnico Preliminar", None, 1),
        ("Aviso de licitação - DOU", None, 3),
        ("Edital publicado no Diário", None, 3),
        ("Documento qualquer", None, 2),
    ],
)
def test_prioridade(titulo, tipo, esperado):
    assert prioridade(arq(1, titulo, tipo)) == esperado


def test_familia_junta_retificacoes():
    nomes = ["Edital", "Edital_Retificado", "Edital_Segunda Retificação", "Edital (2)", "EDITAL v3"]
    assert {familia(arq(i, n)) for i, n in enumerate(nomes)} == {"edital"}


def test_familia_vazia_usa_seq():
    assert familia(arq(7, "2026")) == "x7"


def test_versao_mais_nova():
    a, b, c = arq(1, "Edital"), arq(2, "Termo de Referência"), arq(3, "Edital Retificado")
    vale, antigos = versao_mais_nova([a, b, c])
    assert vale == [b, c]
    assert antigos == [a]


def test_montar_texto_indices_apontam_para_a_pagina():
    lidos = [
        Lido(arquivo=arq(2, "Anexo I"), nome="Anexo I", paginas=["anexo pagina um"]),
        Lido(arquivo=arq(1, "Edital"), nome="Edital", paginas=["primeira pagina", "", "terceira pagina"]),
    ]
    t = montar_texto(lidos)
    assert t.texto.startswith("===== ARQUIVO 1: Edital")  # edital vem primeiro, sem linhas em branco no início
    assert [(p.arq, p.pagina) for p in t.paginas] == [(1, 1), (1, 3), (2, 1)]
    for p, esperado in zip(t.paginas, ["primeira pagina", "terceira pagina", "anexo pagina um"], strict=True):
        assert t.texto[p.ini : p.fim] == esperado
    assert t.chars == len(t.texto) and not t.truncado


def test_montar_texto_limite():
    lidos = [
        Lido(arquivo=arq(1, "Edital"), nome="Edital", paginas=["a" * 100, "b" * 100]),
        Lido(arquivo=arq(2, "Anexo"), nome="Anexo", paginas=["c" * 100]),
    ]
    t = montar_texto(lidos, limite=150)
    assert t.truncado and t.obs
    assert t.arquivos[0].obs == "lido até a página 1"
    assert t.arquivos[1].obs == "não coube no limite de leitura"
    assert "b" not in t.texto


def test_montar_texto_sem_texto_algum():
    with pytest.raises(ErroEdital, match="digitalizado"):
        montar_texto([Lido(arquivo=arq(1, "Edital"), nome="Edital", paginas=["", ""])])


@tem_pdftotext
def test_ler_anexos_pdf_docx_zip_e_retificacao():
    entradas = [
        (arq(1, "Edital"), pdf_simples(["versao antiga"])),
        (arq(2, "Edital Retificado"), pdf_simples(["Objeto: compra de cadeiras", "Prazo de entrega 30 dias"])),
        (arq(3, "Termo de Referencia.docx"), docx_simples(["Especificacao das cadeiras"])),
        (arq(4, "Anexos.zip"), zip_com({"planilha.txt": b"Item 1 - cadeira", "foto.jpg": b"\xff\xd8"})),
    ]
    t = ler_anexos(entradas)
    assert "versao antiga" not in t.texto
    assert "compra de cadeiras" in t.texto and "Especificacao das cadeiras" in t.texto and "Item 1" in t.texto
    obs = {a.titulo: a.obs for a in t.arquivos}
    assert obs["Edital"] == "versão anterior, substituída por retificação"
    assert obs["Anexos.zip / foto.jpg"] == "formato .jpg não lido"
    pagina2 = next(p for p in t.paginas if p.arq == 1 and p.pagina == 2)
    assert t.texto[pagina2.ini : pagina2.fim] == "Prazo de entrega 30 dias"
