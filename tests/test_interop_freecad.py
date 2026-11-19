"""Contrato CAD externo: unidades, autoria legítima e revisão sem inferência de quantidade."""
import copy
import math

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import Projeto
from infra4d.interop import ErroInterop, aplicar_revisao, exportar_pacote, reconciliar_revisao
from infra4d.interop_freecad import malha_em_metros, preparar_componentes


@pytest.fixture(scope="module")
def base():
    return exportar_pacote(Projeto.carregar(), "FreeCAD")


def test_componentes_sao_fragmento_vinculado_em_mm(base, limite):
    componentes, matriz = preparar_componentes(base)
    assert {c["atividade_id"] for c in componentes} == {"OAE3-FUN", "OAE3-MES", "OAE3-SUE"}
    assert componentes[-1]["dimensoes_mm"] == [12000, 8000, 1000]
    assert componentes[-1]["unidade_planejamento"] == "un"
    assert componentes[-1]["quantidade_planejamento"] == 3
    assert matriz[3] == [0, 0, 0, 1]
    assert abs(matriz[0][0] ** 2 + matriz[1][0] ** 2 - 1) < 1e-12
    assert 0 < limite("tolerancia_volume_cad_m3") <= 1e-6


@pytest.mark.parametrize("campo,valor", [("ficticio", False), ("ficticio", "true"), ("source_app", "Blender")])
def test_preparacao_recusa_origem_nao_declarada(base, campo, valor):
    ruim = copy.deepcopy(base)
    ruim["meta"][campo] = valor
    with pytest.raises(ValueError, match="publicação fictícia"):
        preparar_componentes(ruim)


def test_atividades_obrigatorias_ausentes_nao_criam_fragmento(base):
    incompleto = copy.deepcopy(base)
    incompleto["features"] = [f for f in incompleto["features"] if f["properties"]["atividade_id"] != "OAE3-SUE"]
    with pytest.raises(ValueError, match="OAE3"):
        preparar_componentes(incompleto)


def test_conversao_mm_para_m_uma_vez_sem_duplicar_placement():
    matriz = [[1, 0, 0, 100], [0, 1, 0, 200], [0, 0, 1, 300], [0, 0, 0, 1]]
    m = malha_em_metros([[2000, 3000, 0], [3000, 3000, 0], [2000, 4000, 1250]], [[0, 1, 2]], matriz)
    assert m["vertices"][2] == [2, 4, 1.25]
    assert m["matrix_world"] == matriz
    with pytest.raises(ValueError, match="não finito"):
        malha_em_metros([[math.inf, 0, 0]], [], matriz)


def test_malha_freecad_recalcula_copia_sem_alterar_quantidades(base):
    r = copy.deepcopy(base)
    r["meta"]["revision"] = "freecad-r1"
    alvo = next(f for f in r["features"] if f["properties"]["atividade_id"] == "OAE3-SUE")
    _, matriz = preparar_componentes(base)
    alvo["properties"]["geometria_local_m"] = malha_em_metros(
        [[0, 0, 0], [12000, 0, 0], [0, 8000, 1250]], [[0, 1, 2]], matriz)
    projeto = Projeto.carregar()
    novo, rel = aplicar_revisao(projeto, base, r)
    assert novo.dados == projeto.dados
    assert rel["termino_antes"] == rel["termino_depois"]
    assert rel["ids_preservados"] == 108
    assert [m["campo"] for m in rel["mudancas"]] == ["geometria_local_m"]
    # O mesmo payload não pode se declarar QGIS para atravessar a autoridade de malha.
    qgis = exportar_pacote(projeto, "QGIS")
    retorno = copy.deepcopy(qgis)
    retorno["meta"]["revision"] = "qgis-r1"
    next(f for f in retorno["features"] if f["properties"]["atividade_id"] == "OAE3-SUE")["properties"]["geometria_local_m"] = alvo["properties"]["geometria_local_m"]
    with pytest.raises(ErroInterop, match="adaptadores"):
        reconciliar_revisao(projeto, qgis, retorno)


def test_api_exporta_freecad_e_publica_copia(base):
    c = TestClient(criar_app())
    exportado = c.get("/api/federacao/exportar?source_app=FreeCAD")
    assert exportado.status_code == 200 and exportado.json() == base
    r = copy.deepcopy(base)
    r["meta"]["revision"] = "freecad-r1"
    resposta = c.post("/api/federacao/revisoes?publicar=true", json={"baseline": base, "revisao": r})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["source_app"] == "FreeCAD"
    assert resposta.json()["delta_dias_corridos"] == 0
