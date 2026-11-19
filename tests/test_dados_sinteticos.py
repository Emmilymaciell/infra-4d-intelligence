"""Base sintética: determinística, coerente e rastreável."""

import json
from collections import defaultdict

import pytest

from infra4d.cenarios import DATASET_PADRAO, Projeto, executar
from infra4d.dados_sinteticos import gerar


@pytest.fixture(scope="module")
def dados():
    return json.loads(DATASET_PADRAO.read_text(encoding="utf-8"))


def test_arquivo_versionado_e_identico_ao_gerador(dados):
    """Se o gerador mudar e o JSON não for regenerado, este teste falha."""
    assert gerar() == dados, "rode: python -m infra4d.dados_sinteticos"


def test_dados_marcados_como_ficticios(dados):
    assert "FICTÍCIOS" in dados["meta"]["aviso"]
    assert dados["meta"]["ficticio"] is True  # ADR-0005: marca booleana, não texto
    assert all(m["origem"].startswith("SINTÉTICA") for m in dados["medicoes"])


def test_hierarquia_de_ids_consistente(dados):
    lotes = {l["id"] for l in dados["lotes"]}
    segs = {s["id"]: s for s in dados["segmentos"]}
    assert all(s["lote_id"] in lotes for s in segs.values())
    for a in dados["atividades"]:
        if a.get("segmento_id"):
            assert segs[a["segmento_id"]]["lote_id"] == a["lote_id"]
            if a.get("servico_id") and not a["servico_id"].startswith("OAE"):
                assert a["id"] == f"{a['segmento_id']}-{a['servico_id']}"


def test_executado_e_a_soma_dos_boletins(dados):
    soma = defaultdict(float)
    for m in dados["medicoes"]:
        soma[m["atividade_id"]] += m["quantidade"]
    for a in dados["atividades"]:
        if a.get("quantidade_total") and a["status"] != "nao_iniciada":
            assert a["quantidade_executada"] == pytest.approx(soma[a["id"]], abs=0.01)
            assert a["quantidade_executada"] <= a["quantidade_total"] + 1e-6


def test_status_coerente_com_data_de_status(dados):
    ds = dados["meta"]["data_status"]
    for a in dados["atividades"]:
        if a["status"] == "concluida":
            assert a["termino_real"] < ds
        if a["status"] != "nao_iniciada":
            assert a["inicio_real"] < ds


def test_cenarios_rodam_e_mostram_atraso_independente(dados):
    p = Projeto(dados)
    t = {c: executar(p, c)["termino"] for c in ("linha_base", "construtora", "independente")}
    assert t["linha_base"] <= t["construtora"] <= t["independente"]
