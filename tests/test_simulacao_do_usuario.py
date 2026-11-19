"""Campo ``simulacao_do_usuario`` nas rotas de análise que usam o cenário independente de propósito."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.aviso_simulacao import simulacao_do_usuario
from infra4d.cenarios import Projeto

ROTAS = [("/api/aceleracao", {}), ("/api/clima", {"intensidade": 0.3}), ("/api/previsao/earned-schedule", {}),
         ("/api/recuperacao", {}), ("/api/riscos", {"rapido": True})]
VARIAVEIS = ("simulacao_do_usuario", "tempo_s", "cache")  # 'cache' muda de False para True em /api/riscos


@pytest.fixture(scope="module")
def cliente():
    return TestClient(criar_app(Projeto.carregar()))


def test_texto_sem_e_com_simulacao():
    class Est:
        ajustes = []
    assert simulacao_do_usuario(Est).startswith("não aplicada: não há simulação ativa")
    Est.ajustes = [object(), object()]
    t = simulacao_do_usuario(Est)
    assert t.startswith("não aplicada: há 2 ajuste(s)") and "cenário independente" in t


@pytest.mark.parametrize("rota,params", ROTAS)
def test_rota_declara_que_a_simulacao_nao_foi_aplicada(cliente, rota, params):
    cliente.delete("/api/simulacao")
    r1 = cliente.get(rota, params=params)
    assert r1.status_code == 200, r1.text[:200]
    assert r1.json()["simulacao_do_usuario"].startswith("não aplicada: não há simulação ativa")
    ind = cliente.get("/api/cenarios/independente").json()
    aid = next(a for a, x in ind["atividades"].items() if x["memoria"].get("regra") == "quantidade"
               and x["status"] != "concluida")
    assert cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": aid, "equipes": 3}]}).status_code == 200
    r2 = cliente.get(rota, params=params).json()  # pode vir do cache: o aviso reflete o estado ATUAL
    assert r2["simulacao_do_usuario"].startswith("não aplicada: há 1 ajuste(s)")
    assert {k: v for k, v in r2.items() if k not in VARIAVEIS} == \
        {k: v for k, v in r1.json().items() if k not in VARIAVEIS}
    cliente.delete("/api/simulacao")


def test_prazo_vazio_na_aceleracao_usa_o_padrao(cliente):
    a = cliente.get("/api/aceleracao", params={"prazo": ""})
    assert a.status_code == 200 and a.json()["prazo"] == Projeto.carregar().dados["meta"]["termino_linha_base"]
    assert cliente.get("/api/aceleracao", params={"prazo": "abc"}).status_code == 422
