"""API multi-obra: descoberta, isolamento entre obras e tolerância a módulos ausentes."""

import json

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app, descobrir_obras
from infra4d.cenarios import DATASET_PADRAO, Projeto


@pytest.fixture(scope="module")
def dados():
    return json.loads(DATASET_PADRAO.read_text(encoding="utf-8"))


def _copia(dados, novo_id, nome):
    d = json.loads(json.dumps(dados))
    d["ferrovia"]["id"] = novo_id
    d["ferrovia"]["nome"] = nome
    return Projeto(d)


@pytest.fixture()
def cliente_duas_obras(dados):
    return TestClient(criar_app(fontes={"ferrovia": Projeto(dados), "outra": _copia(dados, "X", "Outra obra fictícia")}))


def test_descobre_a_ferrovia_primeiro():
    obras = descobrir_obras()
    assert list(obras)[0] == "ferrovia"


def test_lista_obras(cliente_duas_obras):
    r = cliente_duas_obras.get("/api/obras").json()
    assert [o["id"] for o in r] == ["ferrovia", "outra"]
    assert all("FICTÍCIOS" in o["aviso"] for o in r)


def test_obra_desconhecida_404(cliente_duas_obras):
    assert cliente_duas_obras.get("/api/painel", params={"obra": "zz"}).status_code == 404
    assert cliente_duas_obras.get("/api/cenarios/independente", params={"obra": "zz"}).status_code == 404


def test_sem_parametro_usa_a_ferrovia(cliente_duas_obras):
    a = cliente_duas_obras.get("/api/projeto").json()
    b = cliente_duas_obras.get("/api/projeto", params={"obra": "ferrovia"}).json()
    assert a["ferrovia"]["id"] == b["ferrovia"]["id"] == "EF-FIC"


def test_simulacao_e_isolada_por_obra(cliente_duas_obras):
    c = cliente_duas_obras
    ind = c.get("/api/cenarios/independente", params={"obra": "outra"}).json()
    aid = next(i for i in ind["cadeia_determinante"]
               if ind["atividades"][i]["status"] == "nao_iniciada"
               and ind["atividades"][i]["memoria"].get("regra") == "quantidade")
    prod = ind["atividades"][aid]["memoria"]["produtividade"] / 2
    r = c.post("/api/simulacao", params={"obra": "outra"},
               json={"ajustes": [{"atividade_id": aid, "produtividade": prod}]})
    assert r.status_code == 200 and r.json()["comparacao"]["delta_dias_corridos"] > 0
    assert c.get("/api/painel", params={"obra": "outra"}).json()["simulacao_ativa"] is True
    assert c.get("/api/painel", params={"obra": "ferrovia"}).json()["simulacao_ativa"] is False


def test_modulo_com_contrato_de_ligacao_errado_nao_derruba_a_api():
    """Regressão (achado do revisor): `configurar` com assinatura diferente derrubava o import da API."""
    import sys
    import types
    from fastapi import APIRouter
    from infra4d.api import registrar_rotas
    from fastapi import FastAPI

    falso = types.ModuleType("infra4d.relatorio")
    falso.router = APIRouter()
    falso.configurar = lambda a, b: None  # assinatura errada de propósito
    original = sys.modules.get("infra4d.relatorio")
    sys.modules["infra4d.relatorio"] = falso
    try:
        app = FastAPI()
        registrar_rotas(app, lambda obra=None: None)
        assert "relatorio" in app.state.rotas_indisponiveis
        assert "falha ao ligar" in app.state.rotas_indisponiveis["relatorio"]
    finally:
        if original is not None:
            sys.modules["infra4d.relatorio"] = original


def test_monte_carlo_v2_pela_api_e_v1_por_padrao(cliente_duas_obras):
    c = cliente_duas_obras
    v1 = c.get("/api/previsao-probabilistica", params={"iteracoes": 20}).json()
    assert v1["versao"] == "v1"
    v2 = c.get("/api/previsao-probabilistica", params={"iteracoes": 20, "com_riscos": True, "rho": 0.5}).json()
    assert "v2" in v2 and v2["parametros"]["rho"] == 0.5
    assert c.get("/api/previsao-probabilistica", params={"iteracoes": 20, "rho": 2}).status_code == 422
    crit = c.get("/api/previsao-probabilistica", params={"iteracoes": 20, "com_criticidade": True}).json()
    assert crit["criticidade"]["atividades"] and crit["p50"] == v1["p50"]  # criticidade não altera a faixa
    apr = c.get("/api/previsao-probabilistica", params={"iteracoes": 20, "so_aprovados": True}).json()
    assert apr["fonte_boletins"]["usados"] <= apr["fonte_boletins"]["total"]


def test_modulo_de_rotas_ausente_nao_derruba_a_api(cliente_duas_obras):
    app = cliente_duas_obras.app
    assert isinstance(app.state.rotas_ligadas, list)
    assert isinstance(app.state.rotas_indisponiveis, dict)
    assert cliente_duas_obras.get("/api/saude").json()["ok"] is True
