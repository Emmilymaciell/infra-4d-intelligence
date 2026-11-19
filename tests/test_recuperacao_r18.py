"""r18 (defeito 4): prazo vazio na recuperação = padrão; prazo inválido = erro claro; fator_max validado."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import Projeto
from infra4d.recuperacao import recuperar


@pytest.fixture(scope="module")
def projeto():
    return Projeto.carregar()


def test_prazo_vazio_e_o_padrao(projeto):
    r = recuperar(projeto, prazo="  ", folga_max=0)
    assert r["prazo"] == projeto.dados["meta"]["termino_linha_base"]


@pytest.mark.parametrize("prazo", ["abc", "2026-02-30", "30/03/2027"])
def test_prazo_invalido_e_value_error(projeto, prazo):
    with pytest.raises(ValueError, match="prazo inválido"):
        recuperar(projeto, prazo=prazo)


@pytest.mark.parametrize("fator", [math.nan, math.inf, 0, -1, 0.5, True, "2"])
def test_fator_max_invalido(projeto, fator):
    with pytest.raises(ValueError, match="fator_max"):
        recuperar(projeto, fator_max=fator)


def test_rota_prazo_vazio_200_e_invalido_422(projeto):
    c = TestClient(criar_app(projeto), raise_server_exceptions=False)
    r = c.get("/api/recuperacao", params={"prazo": ""})
    assert r.status_code == 200 and r.json()["prazo"] == projeto.dados["meta"]["termino_linha_base"]
    for ruim in ("abc", "2026-02-30"):
        assert c.get("/api/recuperacao", params={"prazo": ruim}).status_code == 422
