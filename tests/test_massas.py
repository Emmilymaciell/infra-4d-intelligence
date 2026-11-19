"""Terraplenagem e diagrama de massas (Brückner): casos calculados à mão e as duas obras fictícias."""

import json
import math

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO
from infra4d.dados_sinteticos_rodovia import DATASET_RODOVIA
from infra4d.massas import (ErroMassas, Secao, calcular_massas, coerencia, massas_da_obra, pontos_passagem,
                            volume_no_intervalo)

S10 = Secao(10.0)          # plataforma 10 m, taludes 1:1,5
GREIDE = 100.0


def _perfil(hs, passo_km=0.02):
    """Estacas a cada 20 m com altura h dada (h > 0 aterro): terreno = greide − h."""
    kms = [round(i * passo_km, 9) for i in range(len(hs))]
    return kms, [GREIDE] * len(hs), [GREIDE - h for h in hs]


@pytest.fixture(scope="module")
def tol(limite):
    return limite("tolerancia_volume_m3")


# ------------------------------------------------------------------ seção
def test_secao_trapezoidal(tol):
    assert S10.area(-2.0) == pytest.approx((26.0, 0.0), abs=tol)       # 2 · (10 + 1,5·2)
    assert S10.area(2.0) == pytest.approx((0.0, 26.0), abs=tol)
    assert S10.area(0.0) == (0.0, 0.0)
    s = Secao(10.0, talude_corte_h=1.0, talude_aterro_h=2.0)
    assert s.area(-2.0) == pytest.approx((24.0, 0.0), abs=tol)         # 2 · (10 + 1·2)
    assert s.area(2.0) == pytest.approx((0.0, 28.0), abs=tol)          # 2 · (10 + 2·2)


# ------------------------------------------------------------------ corte puro / aterro puro
def test_corte_puro(tol):
    r = calcular_massas(*_perfil([-2.0] * 6), S10, fh=1.25, empolamento=0.25)
    t = r["total"]
    assert t["volume_corte_m3"] == pytest.approx(2600.0, abs=tol)      # 26 m² × 100 m
    assert t["volume_aterro_m3"] == pytest.approx(0.0, abs=tol)
    assert t["ordenada_final_m3"] == pytest.approx(2600.0, abs=tol)
    assert t["bota_fora_m3"] == pytest.approx(2600.0, abs=tol) and t["emprestimo_m3"] == 0
    assert t["bota_fora_solto_m3"] == pytest.approx(3250.0, abs=tol)   # empolamento 25 %
    assert r["compensacoes"] == [] and t["dmt_media_m"] is None
    assert r["pontos_passagem_km"] == []
    assert [e["ordenada_m3"] for e in r["estacas"]] == pytest.approx([0, 520, 1040, 1560, 2080, 2600], abs=tol)


def test_aterro_puro_com_homogeneizacao(tol):
    r = calcular_massas(*_perfil([2.0] * 6), S10, fh=1.25)
    t = r["total"]
    assert t["volume_aterro_m3"] == pytest.approx(2600.0, abs=tol)
    assert t["volume_aterro_equivalente_corte_m3"] == pytest.approx(3250.0, abs=tol)
    assert t["emprestimo_m3"] == pytest.approx(3250.0, abs=tol) and t["bota_fora_m3"] == 0
    assert r["compensacoes"] == []


# ------------------------------------------------------------------ degrau corte -> aterro
DEGRAU = [-1.0] * 5 + [1.0] * 5     # km 0,00–0,08 corte (h=1), km 0,10–0,18 aterro (h=1); área 11,5 m²


def test_perfil_em_degrau_volumes_e_ordenadas(tol):
    r = calcular_massas(*_perfil(DEGRAU), S10, fh=1.0)
    t = r["total"]
    # o intervalo 0,08–0,10 tem a passagem no meio (h de −1 a +1): divide em 10 m + 10 m (revisão r9).
    # corte: 4 × 230 + 11,5/2 × 10 = 977,5 ; aterro idem
    assert t["volume_corte_m3"] == pytest.approx(977.5, abs=tol)
    assert t["volume_aterro_m3"] == pytest.approx(977.5, abs=tol)
    assert [e["ordenada_m3"] for e in r["estacas"]] == pytest.approx(
        [0, 230, 460, 690, 920, 920, 690, 460, 230, 0], abs=tol)
    assert r["pontos_passagem_km"] == pytest.approx([0.09])
    # compensação LOCAL na passagem: min(57,5; 57,5) a (10 + 10)/3 m dos centroides das cunhas
    (loc,) = r["compensacoes_locais"]
    assert loc["volume_m3"] == pytest.approx(57.5, abs=tol) and loc["dmt_m"] == pytest.approx(20 / 3)
    # conservação: corte = compensado (920 longitudinal + 57,5 local) + bota-fora (0)
    assert t["volume_compensado_m3"] == pytest.approx(977.5, abs=tol)


def test_compensacao_e_dmt_conhecidas(tol):
    r = calcular_massas(*_perfil(DEGRAU), S10, fh=1.0)
    (onda,) = r["compensacoes"]
    assert onda["volume_m3"] == pytest.approx(920.0, abs=tol)
    # momento = área sob a curva = 20 × (230+460+690+920+920+690+460+230) = 92.000 m³·m
    assert onda["momento_m3m"] == pytest.approx(92000.0, abs=tol)
    assert onda["dmt_m"] == pytest.approx(100.0, abs=tol / 920)
    assert onda["sentido"] == "km crescente" and not onda["aberta"]
    assert (onda["km_ini"], onda["km_fim"]) == pytest.approx((0.0, 0.18))
    assert r["total"]["bota_fora_m3"] == 0 and r["total"]["emprestimo_m3"] == 0


def test_duas_ondas_em_sentidos_opostos(tol):
    hs = DEGRAU + [1.0] * 5 + [-1.0] * 5          # corte→aterro, depois aterro→corte
    r = calcular_massas(*_perfil(hs), S10, fh=1.0)
    a, b = r["compensacoes"]
    assert a["volume_m3"] == pytest.approx(920.0, abs=tol) and b["volume_m3"] == pytest.approx(920.0, abs=tol)
    assert a["sentido"] == "km crescente" and b["sentido"] == "km decrescente"
    assert b["dmt_m"] == pytest.approx(100.0, abs=tol / 920)
    # 920 + 920 longitudinais + 2 × 57,5 locais (uma passagem no meio de cada intervalo 0,08–0,10 e 0,36–0,38)
    assert r["total"]["volume_compensado_m3"] == pytest.approx(1955.0, abs=tol)
    assert r["total"]["volume_corte_m3"] == pytest.approx(1955.0, abs=tol)        # conservação
    assert r["total"]["momento_transporte_m3km"] == pytest.approx(184.0 + 2 * 57.5 * (20 / 3) / 1000, abs=tol)
    assert r["pontos_passagem_km"] == pytest.approx([0.09, 0.29])


def test_homogeneizacao_compensa_aterro_menor(tol):
    """Fh = 1,25: aterro com área 11,5/1,25 = 9,2 m² compensa exatamente o corte de 11,5 m²."""
    h_at = (-10 + math.sqrt(100 + 4 * 1.5 * 9.2)) / (2 * 1.5)     # h·(10 + 1,5h) = 9,2
    assert S10.area(h_at)[1] == pytest.approx(9.2, abs=1e-9)
    hs = [-1.0] * 5 + [0.0] + [h_at] * 5        # estaca com h = 0 na passagem: sem intervalo misto
    r = calcular_massas(*_perfil(hs), S10, fh=1.25)
    t = r["total"]
    # corte = 4 × 230 + 11,5/2 × 20 = 1.035 ; aterro = 9,2/2 × 20 + 4 × 184 = 828 ; 1,25 × 828 = 1.035
    assert t["volume_corte_m3"] == pytest.approx(1035.0, abs=tol)
    assert t["volume_aterro_equivalente_corte_m3"] == pytest.approx(1035.0, abs=tol)
    assert [e["ordenada_m3"] for e in r["estacas"]] == pytest.approx(
        [0, 230, 460, 690, 920, 1035, 920, 690, 460, 230, 0], abs=tol)
    assert t["ordenada_final_m3"] == pytest.approx(0.0, abs=tol) and t["volume_compensado_m3"] == pytest.approx(1035.0)
    # momento = 20 × (230+460+690+920+1035+920+690+460+230) = 112.700 m³·m
    (onda,) = r["compensacoes"]
    assert onda["momento_m3m"] == pytest.approx(112700.0, abs=tol)
    assert onda["dmt_m"] == pytest.approx(112700.0 / 1035.0)


def test_passagem_assimetrica_divide_no_ponto_de_passagem(tol):
    """h de −1 a +0,8193 em 20 m: passagem a d1 = 20·1/1,8193 m. corte = 11,5/2·d1, aterro = 9,2/2·d2."""
    h_at = (-10 + math.sqrt(100 + 4 * 1.5 * 9.2)) / (2 * 1.5)
    r = calcular_massas([0.0, 0.02], [GREIDE, GREIDE], [GREIDE + 1.0, GREIDE - h_at], S10, fh=1.25)
    d1 = 20 / (1 + h_at)
    assert r["total"]["volume_corte_m3"] == pytest.approx(11.5 / 2 * d1, abs=tol)
    assert r["total"]["volume_aterro_m3"] == pytest.approx(9.2 / 2 * (20 - d1), abs=tol)
    (loc,) = r["compensacoes_locais"]
    assert loc["volume_m3"] == pytest.approx(min(11.5 / 2 * d1, 1.25 * 9.2 / 2 * (20 - d1)), abs=tol)


def test_onda_composta_volume_e_a_soma_das_subidas(tol):
    """Ordenadas 0, 100, 50, 120, 0 a cada 100 m: volume = 100 + 70 = 170 (não o pico 120);
    momento = 100·(50 + 75 + 85 + 60) = 27.000 -> DMT 158,8 m."""
    from infra4d.massas import compensar
    (onda,), final = compensar([0, 100, 200, 300, 400], [0, 100, 50, 120, 0])
    assert final == 0 and onda["volume_m3"] == pytest.approx(170.0, abs=tol)
    assert onda["momento_m3m"] == pytest.approx(27000.0, abs=tol) and onda["dmt_m"] == pytest.approx(27000 / 170)


def test_conservacao_em_perfis_aleatorios(tol):
    import random
    rng = random.Random(9)
    for _ in range(300):
        n = rng.randint(2, 40)
        hs = [rng.uniform(-4, 4) if rng.random() > 0.1 else 0.0 for _ in range(n)]
        fh = rng.choice([1.0, 1.25, 1.4])
        t = calcular_massas(*_perfil(hs), S10, fh=fh)["total"]
        assert t["volume_corte_m3"] == pytest.approx(t["volume_compensado_m3"] + t["bota_fora_m3"], abs=tol)
        assert fh * t["volume_aterro_m3"] == pytest.approx(t["volume_compensado_m3"] + t["emprestimo_m3"], abs=tol)
        livre = calcular_massas(*_perfil(hs), S10, fh=fh)["volume_livre"]
        assert sum(x["volume_m3"] for x in livre) == pytest.approx(t["bota_fora_m3"] + t["emprestimo_m3"], abs=tol)
        assert all(x["km_fim"] >= x["km_ini"] and x["volume_m3"] > 0 for x in livre)
        ida = t["volume_compensado_m3"]
        assert calcular_massas(*_perfil(hs[::-1]), S10, fh=fh)["total"]["volume_compensado_m3"] == pytest.approx(
            ida, abs=tol)                               # espelhado: mesmo volume compensado


def test_ponta_final_aberta_vira_bota_fora(tol):
    hs = [-1.0] * 5 + [1.0] * 3                  # aterro não absorve todo o corte
    r = calcular_massas(*_perfil(hs), S10, fh=1.0)
    t = r["total"]
    # ordenadas 0,230,460,690,920,920,690,460 → sobra 460 de corte
    assert t["bota_fora_m3"] == pytest.approx(460.0, abs=tol)
    (onda,) = r["compensacoes"]
    assert onda["aberta"] and onda["volume_m3"] == pytest.approx(460.0, abs=tol)
    # linha secundária em 460: área = 20 × (230 + 460 + 460 + 230) = 27.600 → DMT 60 m
    assert onda["momento_m3m"] == pytest.approx(27600.0, abs=tol)
    assert onda["dmt_m"] == pytest.approx(60.0, abs=tol / 460)


def test_pontos_de_passagem_com_zero_na_estaca():
    assert pontos_passagem([0, 1, 2, 3], [-1, 0, 2, 3]) == [1]
    assert pontos_passagem([0, 1, 2], [-1, 3, 0]) == pytest.approx([0.25])
    assert pontos_passagem([0, 1, 2], [0, 0, 0]) == []


@pytest.mark.parametrize("args", [
    ([0.0], [1.0], [1.0]),
    ([0.0, 0.0], [1.0, 1.0], [1.0, 1.0]),
    ([0.0, 0.1], [1.0], [1.0, 1.0]),
    ([0.0, 0.1], [1.0, float("nan")], [1.0, 1.0]),
])
def test_entradas_invalidas(args):
    with pytest.raises(ErroMassas):
        calcular_massas(*args, S10)


def test_volume_no_intervalo_proporcional(tol):
    r = calcular_massas(*_perfil([-2.0] * 6), S10)
    vc, va = volume_no_intervalo(r["estacas"], 0.01, 0.05)       # 40 m de corte de 26 m²
    assert vc == pytest.approx(1040.0, abs=tol) and va == 0


# ------------------------------------------------------------------ obras fictícias
@pytest.fixture(scope="module")
def obras():
    return {"ferrovia": json.loads(DATASET_PADRAO.read_text(encoding="utf-8")),
            "rodovia": json.loads(DATASET_RODOVIA.read_text(encoding="utf-8"))}


@pytest.mark.parametrize("obra", ["ferrovia", "rodovia"])
def test_obras_balanco_e_coerencia(obras, obra, tol):
    dados = obras[obra]
    r = massas_da_obra(dados)
    t = r["total"]
    assert "SINTÉTICO" in r["aviso"]
    assert len(r["estacas"]) == round(dados["ferrovia"]["extensao_km"] * 50) + 1
    assert r["estacas"][0]["estaca"] == "0+00,00"
    # conservação: a ordenada final é o que sobra (bota-fora) ou falta (empréstimo)
    assert t["ordenada_final_m3"] == pytest.approx(t["bota_fora_m3"] - t["emprestimo_m3"], abs=tol)
    assert t["ordenada_final_m3"] == pytest.approx(t["volume_corte_m3"] - 1.25 * t["volume_aterro_m3"], abs=tol)
    assert 0 < t["volume_compensado_m3"] <= t["volume_corte_m3"] + tol
    assert len(r["compensacoes"]) > 10 and 0 < t["dmt_media_m"] < 5000
    assert all(o["dmt_m"] > 0 for o in r["compensacoes"])
    c = coerencia(dados, massas=r)
    assert len(c["segmentos"]) == len(dados["segmentos"]) and all(s["atividade_id"] for s in c["segmentos"])
    soma = sum(s["volume_geometrico_m3"] for s in c["segmentos"])
    assert soma == pytest.approx(t["volume_corte_m3"] + t["volume_aterro_m3"], abs=tol * len(c["segmentos"]))
    for s in c["segmentos"]:
        assert s["diferenca_m3"] == pytest.approx(s["volume_geometrico_m3"] - s["quantidade_dataset_m3"], abs=tol)
    # o confronto não altera o dataset
    assert dados == json.loads((DATASET_PADRAO if obra == "ferrovia" else DATASET_RODOVIA).read_text(encoding="utf-8"))


def test_coerencia_relata_divergencia_da_ferrovia_e_acordo_da_rodovia(obras):
    fer = coerencia(obras["ferrovia"])["total"]
    rod = coerencia(obras["rodovia"])["total"]
    assert fer["n_coerentes"] < fer["n_segmentos"] and fer["diferenca_relativa"] < -0.2
    assert rod["n_coerentes"] == rod["n_segmentos"]


def test_volume_converge_com_o_passo(obras):
    v20 = massas_da_obra(obras["rodovia"], 20.0)["total"]
    v10 = massas_da_obra(obras["rodovia"], 10.0)["total"]
    for k in ("volume_corte_m3", "volume_aterro_m3"):
        assert abs(v20[k] - v10[k]) / v10[k] < 0.01


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def cliente():
    return TestClient(criar_app())


def test_api_diagrama_e_coerencia(cliente):
    assert "rotas_massas" in cliente.app.state.rotas_ligadas
    r = cliente.get("/api/massas/diagrama", params={"obra": "rodovia", "passo_m": 20})
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["estacas"]) == 2401 and j["compensacoes"] and j["pontos_passagem_km"]
    assert {"km", "estaca", "ordenada_m3", "volume_corte_m3", "volume_aterro_m3"} <= set(j["estacas"][0])
    c = cliente.get("/api/massas/coerencia", params={"obra": "ferrovia"}).json()
    assert len(c["segmentos"]) == 12 and "criterio" in c


@pytest.mark.parametrize("params, codigo", [
    ({"obra": "rodovia", "passo_m": 0.5}, 422), ({"obra": "rodovia", "passo_m": "x"}, 422),
    ({"obra": "inexistente"}, 404),
])
def test_api_erros(cliente, params, codigo):
    assert cliente.get("/api/massas/diagrama", params=params).status_code == codigo


def test_onda_aberta_com_nivel_cruzado_no_meio_do_trecho(tol):
    """Ordenadas 0 → 10 → 4: sobra 4; linha secundária em 4 cruzada em x = 4 m.
    Área acima de 4: triângulo 6×6/2 = 18 + triângulo 6×10/2 = 30 → 48 m³·m; volume 6 → DMT 8 m."""
    from infra4d.massas import compensar
    (onda,), final = compensar([0.0, 10.0, 20.0], [0.0, 10.0, 4.0])
    assert final == 4.0 and onda["aberta"]
    assert onda["volume_m3"] == pytest.approx(6.0, abs=tol)
    assert onda["momento_m3m"] == pytest.approx(48.0, abs=tol)
    assert onda["dmt_m"] == pytest.approx(8.0, abs=tol)


@pytest.mark.parametrize("kw", [dict(largura_plataforma_m=0.0), dict(largura_plataforma_m=-5.0),
                                dict(largura_plataforma_m=12.0, talude_corte_h=-1.0),
                                dict(largura_plataforma_m=12.0, talude_aterro_h=float("nan"))])
def test_secao_invalida_e_recusada(kw):
    with pytest.raises(ErroMassas):
        Secao(**kw)


def test_coerencia_com_quantidade_zero(obras):
    import copy
    d = copy.deepcopy(obras["rodovia"])
    a = next(x for x in d["atividades"] if x["id"] == "L1-S01-TER")
    a["quantidade_total"] = 0
    c = coerencia(d)
    s = next(x for x in c["segmentos"] if x["segmento_id"] == "L1-S01")
    assert s["situacao"] == "sem quantidade" and s["diferenca_relativa"] is None
    assert c["total"]["n_segmentos"] == len(d["segmentos"])
