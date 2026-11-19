"""/api/previsao-probabilistica expõe o modo P4 (incerteza alargada para frente sem medição) sem mudar o padrão."""

from fastapi.testclient import TestClient

from infra4d import api
from infra4d.cenarios import Projeto
from infra4d.montecarlo import simular


def test_padrao_continua_igual_a_v1():
    c = TestClient(api.criar_app())
    r = c.get("/api/previsao-probabilistica?iteracoes=30&semente=3").json()
    assert "incerteza_sem_medicao" not in r or not r["incerteza_sem_medicao"].get("ativo")


def test_modo_ligado_chega_ao_modulo_e_tem_cache_proprio():
    c = TestClient(api.criar_app())
    base = c.get("/api/previsao-probabilistica?iteracoes=30&semente=3&obra=rodovia").json()
    lig = c.get("/api/previsao-probabilistica?iteracoes=30&semente=3&obra=rodovia"
                "&incerteza_sem_medicao=true&por_marco=true&alargamento=0.2").json()
    assert lig["incerteza_sem_medicao"]["ativo"] is True
    assert "marcos" in lig
    direto = simular(Projeto.carregar(api.descobrir_obras()["rodovia"]), 30, 3,
                     incerteza_sem_medicao=True, por_marco=True, alargamento=0.2)
    assert lig["p80"] == direto["p80"] and lig["marcos"] == direto["marcos"]
    # a chamada sem o modo não foi contaminada pelo cache da chamada com o modo
    de_novo = c.get("/api/previsao-probabilistica?iteracoes=30&semente=3&obra=rodovia").json()
    assert de_novo == base


TODAS = "&com_criticidade=true&com_chuva=true&com_riscos=true&incerteza_sem_medicao=true&por_marco=true"


def test_monte_carlo_pesado_demais_e_422_com_o_maximo_sugerido():
    """P10: o pedido que levou 22,9 s na r20 é recusado antes de rodar, com o número de iterações que cabe."""
    c = TestClient(api.criar_app())
    r = c.get("/api/previsao-probabilistica?iteracoes=2000" + TODAS)
    assert r.status_code == 422 and "iteracoes <= 1142" in r.json()["detail"]
    # o padrão simples continua cabendo inteiro
    assert 2000 * 1 <= api.ORCAMENTO_MC


def test_alargamento_fora_da_faixa_e_422():
    c = TestClient(api.criar_app())
    assert c.get("/api/previsao-probabilistica?incerteza_sem_medicao=true&alargamento=2").status_code == 422
