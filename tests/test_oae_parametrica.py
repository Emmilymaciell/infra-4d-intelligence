"""Geometria local ilustrativa: vínculos, contatos e unidades, sem carregar CAD."""
from __future__ import annotations

import copy
import math
from collections import Counter, defaultdict

import pytest

from infra4d.oae_parametrica import preparar_oae


@pytest.fixture
def pacote():
    dados = []
    for aid, unidade, total, executada in (
        ("OAE3-FUN", "un", 24.0, 24.0), ("OAE3-MES", "un", 4.0, 4.0),
        ("OAE3-SUE", "un", 3.0, 3.0), ("L3-S04-LAS", "m3", 10000.0, 5000.0),
        ("L3-S04-DOR", "un", 8335.0, 4000.0), ("L3-S04-GRA", "km", 5.0, 2.0),
    ):
        dados.append({"type": "Feature", "properties": {
            "atividade_id": aid, "unidade": unidade, "quantidade_total": total,
            "quantidade_executada": executada, "pontos_locais_m": [[800, 2000, 50], [1200, 2000, 50]],
        }})
    return {"type": "FeatureCollection", "meta": {"ficticio": True, "source_app": "FreeCAD"}, "features": dados}


def _por_papel(componentes, papel):
    return [c for c in componentes if c["papel"] == papel]


def _pares_interpenetrados(componentes):
    pares = []
    for i, a in enumerate(componentes):
        for b in componentes[i + 1:]:
            intersecao = [min(a["posicao_mm"][j] + a["dimensoes_mm"][j], b["posicao_mm"][j] + b["dimensoes_mm"][j])
                          - max(a["posicao_mm"][j], b["posicao_mm"][j]) for j in range(3)]
            if all(v > 0 for v in intersecao):
                pares.append((a["nome"], b["nome"]))
    return pares


def test_geracao_deterministica_sem_mutar_publicacao(pacote):
    antes = copy.deepcopy(pacote)
    componentes, matriz = preparar_oae(pacote)
    assert pacote == antes
    assert preparar_oae(pacote) == (componentes, matriz)
    assert len(componentes) == 196
    assert matriz == [[1.0, -0.0, 0, 1000.0], [0.0, 1.0, 0, 2000.0],
                      [0, 0, 1, 50.0], [0, 0, 0, 1]]
    assert len({c["nome"] for c in componentes}) == len(componentes)
    assert all(c["nome"].isascii() and c["ilustrativa"] is True and "parcial" in c["abrangencia"] for c in componentes)


def test_detalhes_todos_parametrizaveis_e_vinculados_sem_somar_quantidade_contratual(pacote):
    componentes, _ = preparar_oae(pacote)
    grupos = Counter(c["atividade_id"] for c in componentes)
    assert grupos == {"OAE3-FUN": 28, "OAE3-MES": 24, "OAE3-SUE": 57,
                      "L3-S04-LAS": 9, "L3-S04-DOR": 60, "L3-S04-GRA": 18}
    fonte = {f["properties"]["atividade_id"]: f["properties"] for f in pacote["features"]}
    for c in componentes:
        assert all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in c["dimensoes_mm"])
        assert len(c["dimensoes_mm"]) == len(c["posicao_mm"]) == 3
        assert all(math.isfinite(v) for v in c["posicao_mm"])
        p = fonte[c["atividade_id"]]
        assert (c["quantidade_planejamento"], c["quantidade_executada"], c["unidade_planejamento"]) == (
            p["quantidade_total"], p["quantidade_executada"], p["unidade"])
    # Até uma tesselação por triângulo independente (36 vértices/caixa) cabe no teto.
    assert max(grupos.values()) * 36 < 10000


def test_nao_ha_interpenetracao_volumetrica_entre_caixas(pacote):
    componentes, _ = preparar_oae(pacote)
    assert _pares_interpenetrados(componentes) == []


def test_detector_interpenetracao_acusa_defeito_injetado_apenas_em_copia(pacote):
    componentes, _ = preparar_oae(pacote)
    alterados = copy.deepcopy(componentes)
    alterados[1]["posicao_mm"] = list(alterados[0]["posicao_mm"])
    alterados[1]["dimensoes_mm"] = list(alterados[0]["dimensoes_mm"])
    assert (alterados[0]["nome"], alterados[1]["nome"]) in _pares_interpenetrados(alterados)
    assert componentes[1] != alterados[1]


def test_via_contatos_verticais_bitola_e_espacamento(pacote):
    c, _ = preparar_oae(pacote)
    tabuleiro = _por_papel(c, "tabuleiro")[0]
    lastro = sorted(_por_papel(c, "lastro")[:3], key=lambda x: x["posicao_mm"][2])
    dormente = _por_papel(c, "dormente")[0]
    patim = _por_papel(c, "trilho_patim")[0]
    alma = _por_papel(c, "trilho_alma")[0]
    boleto = _por_papel(c, "trilho_boleto")[0]
    topo = lambda obj: obj["posicao_mm"][2] + obj["dimensoes_mm"][2]
    assert topo(tabuleiro) == lastro[0]["posicao_mm"][2]
    assert topo(lastro[0]) == lastro[1]["posicao_mm"][2]
    assert topo(lastro[1]) == lastro[2]["posicao_mm"][2]
    assert topo(lastro[2]) == dormente["posicao_mm"][2]
    assert topo(dormente) == patim["posicao_mm"][2]
    assert topo(patim) == alma["posicao_mm"][2]
    assert topo(alma) == boleto["posicao_mm"][2]
    boletos = sorted(_por_papel(c, "trilho_boleto")[:2], key=lambda x: x["posicao_mm"][1])
    assert boletos[1]["posicao_mm"][1] - (boletos[0]["posicao_mm"][1] + boletos[0]["dimensoes_mm"][1]) == 1600
    centros = sorted(d["posicao_mm"][0] + d["dimensoes_mm"][0] / 2 for d in _por_papel(c, "dormente"))
    assert all(b - a == 600 for a, b in zip(centros, centros[1:]))


def test_guarda_corpos_assentam_no_passeio_e_nao_flutuam(pacote):
    c, _ = preparar_oae(pacote)
    passeio = _por_papel(c, "passeio")[0]
    postes = _por_papel(c, "poste_guarda_corpo")
    corrimaos = _por_papel(c, "corrimao")
    assert all(p["posicao_mm"][2] == passeio["posicao_mm"][2] + passeio["dimensoes_mm"][2] for p in postes)
    assert all(r["posicao_mm"][2] == postes[0]["posicao_mm"][2] + postes[0]["dimensoes_mm"][2] for r in corrimaos)


def test_qto_geometrico_analitico_separado_do_planejamento(pacote, limite):
    c, _ = preparar_oae(pacote)
    volumes = defaultdict(float)
    for d in c:
        volumes[d["papel"]] += math.prod(d["dimensoes_mm"]) / 1e9
    # Três lajes 11,9 x 7,5 x 0,6 m: conta geométrica, NÃO quantidade SUE em un.
    assert volumes["tabuleiro"] == pytest.approx(3 * 11.9 * 7.5 * 0.6, abs=limite("tolerancia_volume_cad_m3"))
    assert _por_papel(c, "tabuleiro")[0]["quantidade_planejamento"] == 3.0
    # Envelope local de 36 m mais o bloco de extremidade de 2 m para cada lado.
    minimo_x = min(d["posicao_mm"][0] for d in c)
    maximo_x = max(d["posicao_mm"][0] + d["dimensoes_mm"][0] for d in c)
    assert (minimo_x, maximo_x) == (-20000, 20000)


@pytest.mark.parametrize("aid", ("OAE3-FUN", "OAE3-MES", "OAE3-SUE", "L3-S04-LAS", "L3-S04-DOR", "L3-S04-GRA"))
def test_nao_inventa_vinculo_para_atividade_ausente(pacote, aid):
    pacote["features"] = [f for f in pacote["features"] if f["properties"]["atividade_id"] != aid]
    with pytest.raises(ValueError):
        preparar_oae(pacote)


@pytest.mark.parametrize("marca", (False, "true", 1, None))
def test_so_ficticio_booleano(pacote, marca):
    pacote["meta"]["ficticio"] = marca
    with pytest.raises(ValueError):
        preparar_oae(pacote)


@pytest.mark.parametrize("valor", (float("nan"), float("inf"), -1, True, "24"))
def test_quantidade_invalida_nao_se_perde_na_autoria(pacote, valor):
    pacote["features"][0]["properties"]["quantidade_total"] = valor
    with pytest.raises(ValueError):
        preparar_oae(pacote)


def test_matriz_invalida_ou_ids_duplicados_sao_recusados(pacote):
    duplicado = copy.deepcopy(pacote)
    duplicado["features"].append(copy.deepcopy(duplicado["features"][0]))
    with pytest.raises(ValueError, match="duplicado"):
        preparar_oae(duplicado)
    next(f for f in pacote["features"] if f["properties"]["atividade_id"] == "OAE3-SUE")["properties"]["pontos_locais_m"][0][0] = float("nan")
    with pytest.raises(ValueError, match="finita"):
        preparar_oae(pacote)
