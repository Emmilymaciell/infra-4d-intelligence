"""Earned Schedule: curvas montadas à mão (valores calculados à mão) e fumaça nas duas obras."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infra4d import rotas_previsao
from infra4d.cenarios import DATASET_PADRAO, Projeto, executar
from infra4d.previsao_es import earned_schedule, previsao

RODOVIA = DATASET_PADRAO.parent / "rodovia_ficticia.json"


def _obra(pct, dias=(0, 1, 2, 3, 4, 5, 6), dur=100, inicio="2026-01-01", status="2026-02-10"):
    """Uma tarefa de duração fixa, em andamento desde o início, com ``pct`` % executado na data de status."""
    return Projeto({
        "meta": {"inicio_projeto": inicio, "data_status": status, "calendario_obra": "C"},
        "lotes": [{"id": "L1"}],
        "calendarios": [{"id": "C", "nome": "C", "dias_semana": list(dias), "nao_uteis": []}],
        "servicos": [],
        "atividades": [{"id": "A", "nome": "A", "tipo": "tarefa", "lote_id": "L1", "servico_id": "X",
                        "duracao_fixa": dur, "calendario": "C", "status": "em_andamento",
                        "inicio_real": inicio, "percentual_executado": pct}],
        "relacoes": [],
    })


def _es(P, lote=None):
    return earned_schedule(P, executar(P, "linha_base"), executar(P, "independente"), lote,
                           executar(P, "construtora"))


# Calendário corrido, 100 dias a partir de 01/01/2026 => LB termina 10/04/2026 e PV(t) = (t − início)/100.
# Data de status 10/02/2026 => AT = 40 dias.

def test_curva_linear_no_plano():
    r = _es(_obra(40))
    assert (r["PD_dias"], r["AT_dias"], r["termino_linha_base"]) == (100, 40, "2026-04-10")
    assert r["PV_em_AT"] == pytest.approx(0.4) and r["EV"] == pytest.approx(0.4)
    assert r["ES_dias"] == pytest.approx(40) and r["SV_dias"] == pytest.approx(0) and r["SPI"] == pytest.approx(1)
    assert r["IEAC_pf1_termino"] == r["IEAC_spi_termino"] == "2026-04-10"
    # CPM: 60 dias remanescentes a partir de 10/02 => último dia 10/04 (o mesmo)
    assert r["cpm_independente_termino"] == "2026-04-10"
    assert r["diferenca_es_spi_vs_cpm_independente_dias"] == 0 and "concordam" in r["explicacao"]


def test_atraso_constante_de_10_dias():
    # 30 % em 40 dias: a LB tinha 30 % no dia 30 => ES 30, SV −10, SPI 0,75.
    # IEAC(PF=1) = 40 + 70 = 110 => 01/01 + 109 = 20/04. IEAC(SPI) = 40 + 70/0,75 = 133,33 => ⌈⌉ 134 => 14/05.
    r = _es(_obra(30))
    assert r["ES_dias"] == pytest.approx(30) and r["SV_dias"] == pytest.approx(-10)
    assert r["SPI"] == pytest.approx(0.75)
    assert r["IEAC_pf1_dias"] == pytest.approx(110) and r["IEAC_pf1_termino"] == "2026-04-20"
    assert r["IEAC_spi_dias"] == pytest.approx(133.333, abs=1e-3) and r["IEAC_spi_termino"] == "2026-05-14"
    # CPM: 70 % de 100 = 70 dias a partir de 10/02 => último dia 20/04 (coincide com PF=1)
    assert r["cpm_independente_termino"] == "2026-04-20"
    assert r["diferenca_es_spi_vs_cpm_independente_dias"] == 24 and "DEPOIS" in r["explicacao"]


def test_interpolacao_fracionaria():
    r = _es(_obra(35.5))
    assert r["ES_dias"] == pytest.approx(35.5)
    assert r["SPI"] == pytest.approx(35.5 / 40, abs=1e-4)


def test_patamar_do_fim_de_semana_regra_de_lipke():
    # seg–sex, 10 dias úteis a partir de seg 05/01: PV = 0,5 de sáb 10 a seg 12 (patamar).
    # Status seg 12/01 (AT 7) com 50 %: C = último dia com PV <= EV = 12/01 => ES = 7, SPI = 1.
    P = _obra(50, dias=(0, 1, 2, 3, 4), dur=10, inicio="2026-01-05", status="2026-01-12")
    r = _es(P)
    assert r["AT_dias"] == 7 and r["ES_dias"] == pytest.approx(7) and r["SPI"] == pytest.approx(1)


def test_sem_avanco_nao_projeta_pelo_spi():
    r = _es(_obra(0))
    assert r["ES_dias"] == pytest.approx(0) and r["SPI"] == 0
    assert r["IEAC_spi_termino"] is None and r["IEAC_pf1_termino"] == "2026-05-20"  # 40 + 100 = 140


def test_lote_desconhecido_recusado():
    with pytest.raises(ValueError):
        previsao(_obra(40), "L9")


@pytest.mark.parametrize("arquivo", [DATASET_PADRAO, RODOVIA])
def test_obras_reais_consistentes(arquivo):
    P = Projeto.carregar(arquivo)
    r = previsao(P)
    lotes = [l["id"] for l in P.dados["lotes"]]
    assert [x["lote"] for x in r["resultados"]] == [None] + lotes
    ind = executar(P, "independente")
    for x in r["resultados"]:
        assert 0 < x["EV"] <= 1 and 0 < x["PV_em_AT"] <= 1
        assert 0 <= x["ES_dias"] <= x["PD_dias"]
        assert x["SV_dias"] == pytest.approx(x["ES_dias"] - x["AT_dias"], abs=1e-3)
        assert x["SPI"] == pytest.approx(x["ES_dias"] / x["AT_dias"], abs=1e-4)
        # atrás do plano (EV < PV) <=> ES < AT <=> IEAC(SPI) depois de IEAC(PF=1) depois da LB
        if x["EV"] < x["PV_em_AT"]:
            assert x["SV_dias"] < 0 and x["termino_linha_base"] <= x["IEAC_pf1_termino"] <= x["IEAC_spi_termino"]
        assert x["explicacao"].startswith("O Earned Schedule")
    assert r["resultados"][0]["cpm_independente_termino"] == ind["termino"]
    assert r["referencia_verificada"] is True and "R05" in r["nota"] and "earnedschedule.com" in r["nota"]
    # forma curta de Lipke: IEAC(t) = PD / SPI(t), idêntica à longa com PF = SPI
    for x in r["resultados"]:
        assert x["IEAC_spi_dias"] == pytest.approx(x["PD_dias"] / x["SPI"], rel=1e-3)


def test_rota_earned_schedule():
    P = Projeto.carregar()
    res = {c: executar(P, c) for c in ("linha_base", "construtora", "independente")}

    class Est:
        projeto = P

        @staticmethod
        def resultado(c):
            return res[c]

    def obter_estado(obra):
        if obra not in (None, "ferrovia"):
            from fastapi import HTTPException
            raise HTTPException(404, "obra desconhecida")
        return Est

    vazio = FastAPI()
    vazio.include_router(rotas_previsao.router)
    assert TestClient(vazio).get("/api/previsao/earned-schedule").status_code == 503
    app = FastAPI()
    rotas_previsao.ligar(app, obter_estado)
    c = TestClient(app)
    r = c.get("/api/previsao/earned-schedule", params={"obra": "ferrovia", "lote": "L3"})
    assert r.status_code == 200 and [x["lote"] for x in r.json()["resultados"]] == ["L3"]
    assert c.get("/api/previsao/earned-schedule").json()["resultados"][0]["lote"] is None
    assert c.get("/api/previsao/earned-schedule", params={"lote": "L9"}).status_code == 404
    assert c.get("/api/previsao/earned-schedule", params={"obra": "marte"}).status_code == 404
