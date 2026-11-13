"""Testes da extracao."""
from datetime import datetime

import pytest
import requests

from src.comum import retry
from src.comum.retry import ErroExtracao, pegar_json
from src.extracao.ccee import converter_registro, paginar
from src.extracao.clima import ajustar_usina, normalizar_clima


def test_converter_registro_ccee():
    reg = {"MES_REFERENCIA": 202501, "SUBMERCADO": "SUDESTE", "DIA": 2, "HORA": 5, "PLD_HORA": "123,45"}
    assert converter_registro(reg) == ("SE", datetime(2025, 1, 2, 5), 123.45)


def test_mudanca_de_colunas_gera_erro():
    reg = {"MES_REFERENCIA": 202501, "SUBMERCADO": "SUL", "DIA": 1, "HORA": 0, "PRECO_NOVO_NOME": 10}
    with pytest.raises(ErroExtracao):
        converter_registro(reg)


def test_paginacao_para_no_total():
    chamadas = []

    def buscar(offset, limite):
        chamadas.append(offset)
        return list(range(offset, min(offset + limite, 25))), 25

    paginas = list(paginar(buscar, 10))
    assert [len(p[1]) for p in paginas] == [10, 10, 5]
    assert chamadas == [0, 10, 20]


def test_paginacao_para_em_pagina_vazia():
    def buscar(offset, limite):
        return ([1, 2, 3] if offset == 0 else []), 999  # total mentiroso

    assert len(list(paginar(buscar, 3))) == 1


def test_retry_tenta_de_novo_e_depois_falha(monkeypatch):
    tentativas = []

    def falha(*args, **kwargs):
        tentativas.append(1)
        raise requests.Timeout("tempo esgotado")

    monkeypatch.setattr(retry.requests, "get", falha)
    monkeypatch.setattr(retry.time, "sleep", lambda s: None)
    with pytest.raises(ErroExtracao):
        pegar_json("http://x", {}, tentativas=3)
    assert len(tentativas) == 3


def test_clima_e_cadastro():
    resposta = {"hourly": {"time": ["2025-01-01T00:00", "2025-01-01T01:00"],
                           "temperature_2m": [20.1, 19.8], "shortwave_radiation": [0, 0],
                           "wind_speed_100m": [12.0, 13.5], "precipitation": [0, 0.2]}}
    linhas = normalizar_clima(resposta)
    assert len(linhas) == 2 and linhas[1][0] == datetime(2025, 1, 1, 1)
    with pytest.raises(ErroExtracao):
        normalizar_clima({"hourly": {"time": []}})
    # latitude com sinal trocado e corrigida; cadastro duplicado fica de fora
    assert ajustar_usina("CRE-UFV-004", 15.803, -43.308) == ("CRE-UFV-004", -15.803, -43.308)
    assert ajustar_usina("CRE-EOL-07", -5.537, -35.819) is None