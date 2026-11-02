import pytest
from conftest import docx_simples
from fastapi.testclient import TestClient
from test_ficha import ModeloFalso

from edital_ia.api import app, modelo_ia


@pytest.fixture
def cliente():
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_saude(cliente):
    assert cliente.get("/saude").json()["status"] == "ok"


def test_extrair(cliente):
    arquivos = [
        (
            "arquivos",
            ("Termo de Referencia.docx", docx_simples(["Cadeiras de escritorio"]), "application/octet-stream"),
        ),
        ("arquivos", ("aviso.txt", b"Aviso publicado no DOU", "text/plain")),
    ]
    r = cliente.post("/extrair", files=arquivos)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["texto"].startswith("===== ARQUIVO 1: Termo de Referencia.docx")
    assert [a["arq"] for a in corpo["arquivos"]] == [1, 2]


def test_extrair_sem_texto(cliente):
    r = cliente.post("/extrair", files=[("arquivos", ("foto.png", b"\x89PNG", "image/png"))])
    assert r.status_code == 422


def test_conferir(cliente):
    corpo = {"resposta": 'ok\nTRECHOS:\n[Arq 1 p. 1] "cadeiras azuis"', "texto": "cadeiras azuis", "paginas": []}
    assert cliente.post("/conferir", json=corpo).json()["trechos"][0]["conferido"] == "outra_pagina"


def test_ficha_sem_chave(cliente, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cliente.post("/ficha", json={"texto": "edital"}).status_code == 503


def test_ficha_com_modelo_falso(cliente):
    app.dependency_overrides[modelo_ia] = lambda: ModeloFalso('{"resumo": "Compra de cadeiras."}')
    r = cliente.post("/ficha", json={"texto": "edital"})
    assert r.status_code == 200
    assert r.json()["ficha"]["resumo"] == "Compra de cadeiras."
