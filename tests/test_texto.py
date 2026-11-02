from edital_ia.texto import fatiar, limpa, normal


def test_limpa_espacos_e_linhas():
    assert limpa("  a   b \r\n\n\n\n  c  ") == "a b\n\nc"


def test_limpa_vazio():
    assert limpa(None) == ""


def test_normal_tira_acento_aspas_e_hifen_de_quebra():
    assert normal("Licita-\n  ção “Pública”  nº 10/2026") == "licitacao publica n 10/2026"


def test_normal_mantem_pontuacao_util():
    assert normal("R$ 1.500,00 (10%)") == "r$ 1.500,00 (10%)"


def test_fatiar():
    assert fatiar("abcdefg", 3) == ["abc", "def", "g"]
    assert fatiar("") == [""]
