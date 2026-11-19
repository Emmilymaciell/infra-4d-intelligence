"""Revisão independente da federação: metadados e fidelidade de unidades.

Reprodução em cópia; nenhum arquivo de produção é mutado pelos testes.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import Projeto
from infra4d.interop import ErroInterop, exportar_pacote, reconciliar_revisao


@pytest.fixture(scope="module")
def origem():
    projeto = Projeto.carregar()
    return projeto, exportar_pacote(projeto)


@pytest.mark.parametrize("meta", [None, [], "metadado inválido"])
def test_upload_com_meta_nao_objeto_e_422_em_vez_de_500(origem, meta):
    projeto, baseline = origem
    revisao = copy.deepcopy(baseline)
    revisao["meta"] = meta
    with TestClient(criar_app(projeto), raise_server_exceptions=False) as cliente:
        resposta = cliente.post("/api/federacao/revisoes", json={"baseline": baseline, "revisao": revisao})
    assert resposta.status_code == 422, resposta.text


def test_revisao_nao_pode_mudar_unidades_do_contrato_sem_conflito(origem):
    projeto, baseline = origem
    revisao = copy.deepcopy(baseline)
    revisao["meta"]["revision"] = "r22-unidades"
    revisao["meta"]["units"] = "coordenadas GIS e autoria local em pés; quantidade em libras"
    with pytest.raises(ErroInterop):
        reconciliar_revisao(projeto, baseline, revisao)


def test_revisao_so_geometrica_preserva_quantidade_e_declara_diff(origem):
    projeto, baseline = origem
    revisao = copy.deepcopy(baseline)
    revisao["meta"]["revision"] = "r22-geometria"
    revisao["features"][0]["geometry"]["coordinates"][0][0] += .00001
    relatorio = reconciliar_revisao(projeto, baseline, revisao)
    assert {m["campo"] for m in relatorio["mudancas"]} == {"geometry"}
    assert relatorio["dataset_original_alterado"] is False
    assert relatorio["aprovacao_necessaria"] is True


def test_json_aninhado_excessivo_e_recusado_sem_500(origem):
    projeto, _ = origem
    corpo = b'{"baseline":{},"revisao":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}"
    with TestClient(criar_app(projeto), raise_server_exceptions=False) as cliente:
        resposta = cliente.post("/api/federacao/revisoes", content=corpo,
                                headers={"Content-Type": "application/json"})
    assert resposta.status_code in (400, 422), resposta.text
