"""Vertical slice: produtividade -> duração -> rede -> término -> painel -> estado 4D.

Exercita o caminho inteiro pela API HTTP (TestClient), como a interface faz.
O critério de aceite e o tempo máximo de recálculo vêm do project.yaml.
"""

import math
import time

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.calendario import ordinal
from infra4d.cenarios import Projeto


@pytest.fixture(scope="module")
def projeto():
    return Projeto.carregar()


@pytest.fixture()
def cliente(projeto):
    return TestClient(criar_app(projeto))


def _critica_por_quantidade(cliente):
    ind = cliente.get("/api/cenarios/independente").json()
    for aid in ind["cadeia_determinante"]:
        a = ind["atividades"][aid]
        if a["status"] == "nao_iniciada" and a["memoria"].get("regra") == "quantidade":
            return ind, aid
    pytest.fail("nenhuma atividade não iniciada por quantidade na cadeia determinante")


def _folgada_por_quantidade(cliente, minimo=30):
    ind = cliente.get("/api/cenarios/independente").json()
    for aid, a in ind["atividades"].items():
        if (a["status"] == "nao_iniciada" and a["memoria"].get("regra") == "quantidade"
                and (a["folga_total"] or 0) >= minimo):
            return ind, aid
    pytest.fail("nenhuma atividade com folga alta")


def test_criterio_de_pronto_esta_declarado(criterio_de_pronto):
    assert "produtividade" in criterio_de_pronto and "4D" in criterio_de_pronto


def test_reduzir_produtividade_de_atividade_critica_atrasa_o_termino_de_forma_justificada(cliente, limite):
    ind, aid = _critica_por_quantidade(cliente)
    mem = ind["atividades"][aid]["memoria"]
    nova = mem["produtividade"] / 2

    t0 = time.perf_counter()
    r = cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": aid, "produtividade": nova}]})
    decorrido = time.perf_counter() - t0
    assert r.status_code == 200, r.text
    assert decorrido < limite("tempo_maximo_recalculo_s")

    cmp = r.json()["comparacao"]
    alt = {m["id"]: m for m in cmp["duracoes_alteradas"]}
    assert set(alt) == {aid}, "só a atividade ajustada pode mudar de duração"
    esperado = math.ceil(mem["quantidade_remanescente"] / (nova * mem["equipes"]) - 1e-9)
    assert alt[aid]["duracao_depois"] == esperado
    delta_dur = esperado - mem["duracao_calculada"]
    assert delta_dur > 0
    # atividade na cadeia determinante (folga 0): o término anda exatamente o acréscimo,
    # medido em dias úteis do calendário da PRÓPRIA atividade, e nunca menos de 1 dia corrido
    assert cmp["delta_dias_corridos"] > 0
    sim = cliente.get("/api/cenarios/simulado").json()
    assert sim["termino"] > ind["termino"]
    assert any(aid in linha for linha in cmp["explicacao"])
    assert any("Término da obra" in linha for linha in cmp["explicacao"])

    # painel reflete a simulação
    painel = cliente.get("/api/painel").json()
    assert painel["simulacao_ativa"] is True
    assert painel["terminos"]["simulado"] == sim["termino"]
    assert painel["terminos"]["independente"] == ind["termino"]

    # estado 4D: numa data entre os dois términos, a obra simulada está menos avançada
    data = ind["atividades"][aid]["termino"]
    e_ind = cliente.get("/api/estado4d", params={"data": data, "cenario": "independente"}).json()
    e_sim = cliente.get("/api/estado4d", params={"data": data, "cenario": "simulado"}).json()
    assert e_sim["atividades"][aid]["fracao"] < e_ind["atividades"][aid]["fracao"]

    # limpar volta ao independente
    r = cliente.delete("/api/simulacao")
    assert r.json()["comparacao"]["delta_dias_corridos"] == 0


def test_atraso_dentro_da_folga_nao_move_o_termino(cliente):
    ind, aid = _folgada_por_quantidade(cliente)
    a = ind["atividades"][aid]
    mem = a["memoria"]
    folga = a["folga_total"]
    # acréscimo menor que a folga: escolhe produtividade que gera +folga//2 dias
    alvo_dur = mem["duracao_calculada"] + max(1, folga // 2)
    prod = mem["quantidade_remanescente"] / (mem["equipes"] * alvo_dur)
    r = cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": aid, "produtividade": prod}]})
    cmp = r.json()["comparacao"]
    assert cmp["duracoes_alteradas"][0]["delta_duracao"] > 0
    assert cmp["delta_dias_corridos"] == 0
    assert any("absorvido" in l for l in cmp["explicacao"])


def test_aumentar_equipes_no_caminho_critico_antecipa(cliente):
    ind, aid = _critica_por_quantidade(cliente)
    mem = ind["atividades"][aid]["memoria"]
    r = cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": aid, "equipes": mem["equipes"] + 2}]})
    assert r.json()["comparacao"]["delta_dias_corridos"] < 0


def test_ajuste_por_servico_e_lote(cliente, projeto):
    r = cliente.post("/api/simulacao", json={"ajustes": [{"servico_id": "TER", "lote_id": "L3", "produtividade": 3000}]})
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()["comparacao"]["duracoes_alteradas"]}
    assert ids and all(i.startswith("L3-") and i.endswith("-TER") for i in ids)


@pytest.mark.parametrize("corpo", [
    {"ajustes": [{"atividade_id": "L1-S01-TER", "produtividade": 0}]},
    {"ajustes": [{"atividade_id": "L1-S01-TER", "produtividade": -5}]},
    {"ajustes": [{"atividade_id": "L1-S01-TER", "equipes": 0}]},
    {"ajustes": [{"atividade_id": "NAO-EXISTE", "produtividade": 10}]},
    {"ajustes": [{"produtividade": 10}]},
    {"ajustes": [{"atividade_id": "L1-S01-TER"}]},
])
def test_ajustes_invalidos_sao_recusados_com_422(cliente, corpo):
    assert cliente.post("/api/simulacao", json=corpo).status_code == 422


def test_erros_claros_de_parametro(cliente):
    assert cliente.get("/api/cenarios/xyz").status_code == 404
    assert cliente.get("/api/estado4d", params={"data": "ontem"}).status_code == 422
    assert cliente.get("/api/painel", params={"lote": "L9"}).status_code == 404


def test_interface_e_servida(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "INFRA 4D" in r.text


def test_previsoes_construtora_e_independente_divergem_e_sao_explicadas(cliente):
    cmp = cliente.get("/api/comparacao", params={"ref": "construtora", "alvo": "independente"}).json()
    assert cmp["delta_dias_corridos"] > 0
    assert all("fonte_produtividade" in m["memoria_depois"] for m in cmp["duracoes_alteradas"]
               if m["memoria_depois"].get("regra") == "quantidade")


def test_painel_por_lote(cliente):
    p = cliente.get("/api/painel", params={"lote": "L2"}).json()
    assert 0 < p["avanco_real"] < 100
    assert p["terminos"]["independente"] is not None
    assert all(x["lote_id"] == "L2" for x in p["produtividades"])


def test_regressao_4d_usa_o_real_ate_a_data_de_status(projeto, cliente):
    """Regressão: progresso_em ignorava a data de status (lia a chave do lugar errado)
    e mostrava previsão onde devia mostrar o real."""
    ds = projeto.dados["meta"]["data_status"]
    e = cliente.get("/api/estado4d", params={"data": ds, "cenario": "independente"}).json()["atividades"]
    for a in projeto.dados["atividades"]:
        if a.get("tipo") != "tarefa":
            continue
        if a["status"] == "nao_iniciada":
            assert e[a["id"]]["fracao"] == 0, a["id"]
        elif a["status"] == "em_andamento" and a.get("quantidade_total"):
            assert e[a["id"]]["fracao"] == pytest.approx(a["quantidade_executada"] / a["quantidade_total"], abs=1e-4)


def test_avanco_real_bate_com_executado_na_data_de_status(projeto, cliente):
    """O avanço do painel na data de status é a média ponderada do executado medido."""
    from infra4d.painel import peso
    num = den = 0.0
    for a in projeto.dados["atividades"]:
        w = peso(a)
        if not w:
            continue
        if a.get("status") == "concluida":
            f = 1.0
        elif a.get("quantidade_total"):
            f = a.get("quantidade_executada", 0) / a["quantidade_total"]
        else:
            f = a.get("percentual_executado", 0) / 100
        num += w * f
        den += w
    p = cliente.get("/api/painel").json()
    assert p["avanco_real"] == pytest.approx(100 * num / den, abs=0.01)
    assert ordinal(p["data_status"]) == projeto.data_status
