"""Testes da etapa de qualidade (não precisam de banco nem de internet)."""
import pandas as pd

from src.qualidade.limpeza import Registro, pior, trechos_de_horas
from src.qualidade.regras import REGRAS, configuracao


def test_sao_32_regras_nas_7_dimensoes():
    assert len(REGRAS) == 32
    assert len({r.nome for r in REGRAS}) == 32  # nomes únicos
    assert {r.dimensao for r in REGRAS} == {
        "Completude", "Unicidade", "Validade", "Consistência", "Acurácia", "Integridade referencial", "Atualidade"}
    assert {r.decisao for r in REGRAS} <= {"CORRIGIR", "DESCARTAR", "QUARENTENA", "SINALIZAR"}


def test_config_mistura_padroes_com_o_yaml():
    conf = configuracao({"qualidade": {"sla_atraso_horas": 48, "faixas_clima": {"vento_100m_kmh": [0, 150]}}})
    assert conf["sla_atraso_horas"] == 48
    assert conf["faixas_clima"]["vento_100m_kmh"] == [0, 150]
    assert conf["faixas_clima"]["radiacao_wm2"] == [0, 1400]  # o que não foi dito continua no padrão
    assert configuracao({})["travado_min_horas"] == 12


def test_trechos_de_horas_agrupa_buracos_continuos():
    h = pd.date_range("2025-11-10 00:00", periods=24, freq="h").tolist() + [pd.Timestamp("2025-12-29 00:00")]
    assert trechos_de_horas(h) == [(h[0], h[23], 24), (h[24], h[24], 1)]
    assert trechos_de_horas([]) == []


def test_status_vale_o_mais_grave():
    assert pior("OK", "SINALIZADO") == "SINALIZADO"
    assert pior("CORRIGIDO", "SINALIZADO") == "CORRIGIDO"
    assert pior("CORRIGIDO", "ANULADO") == "ANULADO"


def test_quarentena_tambem_vira_tratamento():
    reg = Registro()
    reg.quarentenar("medicao_geracao", "medicao_sem_usina", "sem usina", {"id_medicao": 1, "energia": float("nan")}, "x")
    assert reg.quarentena[0][3]["energia"] is None  # NaN vira null no JSON
    assert reg.tratamentos[0][3] == "QUARENTENA"
