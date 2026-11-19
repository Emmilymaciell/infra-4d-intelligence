"""Painel: marcos contratuais e sensibilidade à lógica de progresso."""

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.calendario import ordinal
from infra4d.cenarios import Projeto, executar


@pytest.fixture(scope="module")
def painel():
    return TestClient(criar_app(Projeto.carregar())).get("/api/painel").json()


def test_marcos_contratuais_comparam_previsao_com_prazo_da_linha_de_base(painel):
    p = Projeto.carregar()
    lb = executar(p, "linha_base")
    ind = executar(p, "independente")
    marcos = {m["id"]: m for m in painel["marcos_contratuais"]}
    ids = {a["id"] for a in p.dados["atividades"] if a.get("tipo") == "marco_termino"}
    assert set(marcos) == ids
    for mid, m in marcos.items():
        assert m["prazo"] == lb["atividades"][mid]["termino"]
        assert m["independente"] == ind["atividades"][mid]["termino"]
        assert m["desvio_independente"] == ordinal(m["independente"]) - ordinal(m["prazo"])


def test_marco_final_tem_o_termino_da_obra(painel):
    m = next(x for x in painel["marcos_contratuais"] if x["id"] == "M-FIM")
    assert m["independente"] == painel["terminos"]["independente"]


def test_sensibilidade_mostra_as_duas_logicas(painel):
    s = painel["sensibilidade_logica"]
    assert s["sobrepor"] == painel["terminos"]["independente"]
    assert s["retida"] >= s["sobrepor"]  # retida nunca antecipa em relação ao progress override


def test_marcos_filtrados_por_lote():
    c = TestClient(criar_app(Projeto.carregar()))
    m = c.get("/api/painel", params={"lote": "L2"}).json()["marcos_contratuais"]
    assert m and all(x["lote_id"] == "L2" for x in m)
