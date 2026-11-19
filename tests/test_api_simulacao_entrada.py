"""POST /api/simulacao recusa número não finito, booleano e texto com 422, nunca 500 (achado da r20)."""

import pytest
from fastapi.testclient import TestClient

from infra4d import api

ATIV = "L3-S04-TER"


@pytest.fixture(scope="module")
def cliente():
    return TestClient(api.criar_app(), raise_server_exceptions=False)


@pytest.mark.parametrize("corpo", [
    '{"ajustes":[{"atividade_id":"%s","produtividade":NaN}]}' % ATIV,
    '{"ajustes":[{"atividade_id":"%s","produtividade":-Infinity}]}' % ATIV,
    '{"ajustes":[{"atividade_id":"%s","produtividade":Infinity}]}' % ATIV,
    '{"ajustes":[{"atividade_id":"%s","equipes":1e400}]}' % ATIV,
    '{"ajustes":[{"atividade_id":"%s","produtividade":true}]}' % ATIV,
    '{"ajustes":[{"atividade_id":"%s","equipes":"3"}]}' % ATIV,
    '{"ajustes":[{"atividade_id":"%s","equipes":2.5}]}' % ATIV,
])
def test_entrada_invalida_e_422(cliente, corpo):
    r = cliente.post("/api/simulacao", content=corpo, headers={"content-type": "application/json"})
    assert r.status_code == 422, (corpo, r.status_code, r.text[:200])


def test_entrada_valida_continua_aceita(cliente):
    r = cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": ATIV, "produtividade": 1500}]})
    assert r.status_code == 200
    r = cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": ATIV, "equipes": 3}]})
    assert r.status_code == 200
    cliente.delete("/api/simulacao")
