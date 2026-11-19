"""numeros_demo: roda pela API em memória e devolve as chaves que o roteiro (docs/DEMO-PESSOA-A.md) cita."""

import os

import pytest

from infra4d import numeros_demo as N

CHAVES = {"obra", "painel", "earned_schedule", "monte_carlo", "simulacao", "linha_de_balanco",
          "cronograma_construtora", "historico", "recuperacao", "dcma_construtora", "sensibilidade", "ifc",
          "fiscalizacao", "orcamento_ficticio", "massas", "produtividade_dmt", "exportacao_bi"}


@pytest.fixture(scope="module")
def numeros():
    antes = os.environ.get("INFRA4D_BANCO")
    d = N.coletar(iteracoes_mc=20, validar_ifc=False)   # rápido: o IFC é coberto por tests/test_ifc.py
    assert os.environ.get("INFRA4D_BANCO") == antes      # variável de ambiente restaurada
    return d


def test_devolve_as_chaves_do_roteiro_nas_duas_obras(numeros):
    assert set(numeros["obras"]) == {"ferrovia", "rodovia"}
    for obra, n in numeros["obras"].items():
        assert set(n) == CHAVES, obra
        assert n["obra"]["ficticio"] is True and n["obra"]["tipo"] == obra
        assert n["painel"]["termino_independente"] and n["monte_carlo"]["iteracoes"] == 20
        assert len(n["simulacao"]) >= 2 and all("delta_dias_corridos" in s for s in n["simulacao"])
        assert n["historico"]["construtora_repetiu"]["n"] >= 1
        assert n["recuperacao"]["dias_alem_do_prazo"] >= 0
        assert n["ifc"]["disponivel"] is False


def test_saida_em_texto_cita_as_obras(numeros, capsys):
    print(N._texto(numeros))
    out = capsys.readouterr().out
    assert "=== ferrovia ===" in out and "=== rodovia ===" in out and "FICTÍCIOS" in out
