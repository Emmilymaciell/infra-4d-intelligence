"""Revisões publicadas são isoladas; upload não vira alteração silenciosa da demo."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app


@pytest.fixture()
def cliente():
    return TestClient(criar_app())


def pacote(cliente, obra="ferrovia"):
    resposta = cliente.get("/api/federacao/exportar", params={"obra": obra})
    assert resposta.status_code == 200, resposta.text
    base = resposta.json()
    rev = copy.deepcopy(base)
    rev["meta"]["revision"] = "r1-qgis"
    return {"baseline": base, "revisao": rev}


def test_previa_publicacao_consulta_e_reinicio_preservam_referencia(cliente):
    corpo = pacote(cliente)
    original = cliente.get("/api/cenarios/independente").json()
    alvo = next(f for f in corpo["revisao"]["features"] if f["properties"]["atividade_id"] == "L3-S04-TER")
    alvo["properties"]["quantidade_total"] *= 1.5
    alvo["geometry"]["coordinates"][0][0] += 0.00001
    previo = cliente.post("/api/federacao/revisoes", json=corpo)
    assert previo.status_code == 200, previo.text
    p = previo.json()
    assert p["publicado"] is False
    assert p["delta_dias_corridos"] > 0
    assert cliente.get("/api/federacao/revisoes").json()["revisoes"] == []
    publicado = cliente.post("/api/federacao/revisoes?publicar=true", json=corpo)
    assert publicado.status_code == 200, publicado.text
    r = publicado.json()
    assert r["publicado"] and not r["persistido"]
    assert cliente.get("/api/federacao/revisoes/" + r["id"]).json()["geojson"] == corpo["revisao"]
    assert len(r["linhas_locais"]) == len(corpo["revisao"]["features"])
    assert r["resultado_4d"]["termino"] == r["termino_depois"]
    assert cliente.get("/api/cenarios/independente").json() == original
    assert not cliente.get("/api/painel").json()["simulacao_ativa"]
    # A consulta exige a mesma obra, e cada app/processo tem acervo próprio.
    assert cliente.get("/api/federacao/revisoes/" + r["id"] + "?obra=rodovia").status_code == 404
    assert TestClient(criar_app()).get("/api/federacao/revisoes/" + r["id"]).status_code == 404
    # Repetir a publicação é idempotente, sem perder a revisão anterior.
    assert cliente.post("/api/federacao/revisoes?publicar=true", json=corpo).json()["id"] == r["id"]
    assert len(cliente.get("/api/federacao/revisoes").json()["revisoes"]) == 1


@pytest.mark.parametrize("obra", ["ferrovia", "rodovia"])
def test_geometria_revisada_nao_inventa_quantidade(cliente, obra):
    corpo = pacote(cliente, obra)
    corpo["revisao"]["features"][0]["geometry"]["coordinates"][0][0] += 0.00001
    r = cliente.post("/api/federacao/revisoes", params={"obra": obra}, json=corpo)
    assert r.status_code == 200, r.text
    assert r.json()["delta_dias_corridos"] == 0
    assert all(m["campo"] != "quantidade_total" for m in r.json()["relatorio"]["mudancas"])


@pytest.mark.parametrize("alterar", ["id", "unidade", "marca", "baseline", "crs", "duplicada", "negativo"])
def test_conflitos_recusados_sem_publicar(cliente, alterar):
    corpo = pacote(cliente)
    p = corpo["revisao"]["features"][0]["properties"]
    if alterar == "id":
        p["atividade_id"] = "inexistente"
    elif alterar == "unidade":
        p["unidade"] = "outra"
    elif alterar == "marca":
        corpo["revisao"]["meta"]["ficticio"] = False
    elif alterar == "baseline":
        corpo["baseline"]["features"][0]["properties"]["quantidade_total"] = 12345
        p["quantidade_total"] = 12345
    elif alterar == "crs":
        corpo["revisao"]["meta"]["crs"] = "EPSG:3857"
    elif alterar == "duplicada":
        corpo["revisao"]["features"].append(copy.deepcopy(corpo["revisao"]["features"][0]))
    else:
        p["quantidade_total"] = -1
    assert cliente.post("/api/federacao/revisoes?publicar=true", json=corpo).status_code == 422
    assert cliente.get("/api/federacao/revisoes").json()["revisoes"] == []


@pytest.mark.parametrize("corpo", [b"", b"{", b'{"x":NaN}', b'{"x":1,"x":2}', b'\xff'])
def test_json_invalido_e_400(cliente, corpo):
    assert cliente.post("/api/federacao/revisoes", content=corpo).status_code == 400


def test_teto_upload_e_404_documentado(cliente):
    from infra4d.rotas_federacao import MAX_BYTES
    assert cliente.post("/api/federacao/revisoes", content=b" " * (MAX_BYTES + 1)).status_code == 413
    assert cliente.get("/api/federacao/exportar?obra=ausente").status_code == 404
    assert cliente.get("/api/federacao/revisoes?obra=ausente").status_code == 404
    assert cliente.get("/api/federacao/exportar?source_app=Revit").status_code == 422


def test_obra_padrao_rodoviaria_nao_recebe_rotulo_ferrovia():
    from pathlib import Path
    from infra4d.cenarios import Projeto
    fonte = Path(__file__).resolve().parents[1] / "examples/synthetic/rodovia_ficticia.json"
    cliente = TestClient(criar_app(fontes={"rodovia": Projeto.carregar(fonte)}))
    base = cliente.get("/api/federacao/exportar").json()
    revisao = copy.deepcopy(base)
    revisao["meta"]["revision"] = "r1"
    resposta = cliente.post("/api/federacao/revisoes?publicar=true",
                            json={"baseline": base, "revisao": revisao})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["obra"] == "rodovia"
    assert cliente.get("/api/federacao/revisoes").json()["revisoes"][0]["obra"] == "rodovia"
