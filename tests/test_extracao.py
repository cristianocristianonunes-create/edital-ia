from pathlib import Path

from conftest import docx_simples, pdf_simples, tem_pdftotext, zip_com

from edital_ia.extracao import extrair_arquivo


def gravar(pasta: Path, nome: str, dados: bytes) -> Path:
    p = pasta / nome
    p.write_bytes(dados)
    return p


@tem_pdftotext
def test_pdf_por_cabecalho_mesmo_sem_extensao(tmp_path):
    partes = extrair_arquivo(gravar(tmp_path, "a1", pdf_simples(["Pagina um", "Pagina dois"])), "edital", tmp_path)
    assert partes[0].paginas == ["Pagina um", "Pagina dois"]


def test_docx(tmp_path):
    partes = extrair_arquivo(gravar(tmp_path, "a1", docx_simples(["Um &amp; dois", "tres"])), "tr.docx", tmp_path)
    assert partes[0].paginas == ["Um & dois\ntres"]


def test_zip_ignora_caminho_que_sai_da_pasta(tmp_path):
    dados = zip_com({"../../fora.txt": b"perigo", "dentro/ok.txt": b"conteudo"})
    partes = extrair_arquivo(gravar(tmp_path, "a1", dados), "anexos.zip", tmp_path)
    assert [(p.nome, p.paginas) for p in partes] == [("dentro/ok.txt", ["conteudo"])]
    assert not (tmp_path.parent / "fora.txt").exists()


def test_zip_corrompido(tmp_path):
    partes = extrair_arquivo(gravar(tmp_path, "a1", b"PK\x03\x04lixo"), "anexos.zip", tmp_path)
    assert partes[0].obs and partes[0].obs.startswith("zip não lido")


def test_rar_e_desconhecido(tmp_path):
    assert (
        extrair_arquivo(gravar(tmp_path, "a1", b"Rar!\x1a\x07"), "x.rar", tmp_path)[0].obs
        == "arquivo RAR ainda não é lido"
    )
    assert (
        extrair_arquivo(gravar(tmp_path, "a2", b"\x00\x01"), "x.bin", tmp_path)[0].obs
        == "formato não reconhecido (.bin)"
    )
