"""Produtividade de terraplenagem pela DMT: ciclo de frota calculado à mão e as duas obras fictícias."""

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO, Ajuste, Projeto, executar
from infra4d.produtividade_terraplenagem import (ErroProdutividade, ParametrosFrota, analisar, ciclo_caminhao_min,
                                                 dmt_de_equilibrio_m, dmt_por_segmento, fator_quantidade,
                                                 producao_frota)

# frota de números redondos: escavadeira 3600/30 × 2 m³ = 240 m³/h; carga do caminhão 10 m³ = 2,5 min
P = ParametrosFrota(cacamba_m3=2.0, ciclo_escavadeira_s=30.0, enchimento=1.0, eficiencia=1.0, horas_dia=10.0,
                    n_caminhoes=2, capacidade_caminhao_m3=10.0, v_carregado_kmh=30.0, v_vazio_kmh=60.0,
                    tempo_fixo_min=2.0, empolamento=0.0)
OBRAS = {"ferrovia": DATASET_PADRAO, "rodovia": DATASET_PADRAO.parent / "rodovia_ficticia.json"}


def test_ciclo_a_mao():
    assert ciclo_caminhao_min(0, P) == pytest.approx(4.5)            # 2,5 carga + 2 fixo
    assert ciclo_caminhao_min(3000, P) == pytest.approx(13.5)        # + 3 km a 30 km/h (6) + 3 km a 60 km/h (3)
    with pytest.raises(ErroProdutividade):
        ciclo_caminhao_min(-1, P)


def test_limite_pela_escavadeira_com_dmt_curta():
    r = producao_frota(0, P)
    assert r["escavadeira_m3_solto_dia"] == pytest.approx(2400.0)    # 240 × 10 h
    assert r["caminhoes_m3_solto_dia"] == pytest.approx(2 * 10 * 60 / 4.5 * 10)   # 2.666,7
    assert r["producao_m3_solto_dia"] == pytest.approx(2400.0) and r["limitante"] == "escavadeira"


def test_limite_pelos_caminhoes_com_dmt_longa():
    r = producao_frota(3000, P)
    assert r["caminhoes_m3_solto_dia"] == pytest.approx(2 * 10 * 60 / 13.5 * 10)  # 888,9
    assert r["producao_m3_solto_dia"] == pytest.approx(888.888, abs=1e-3) and r["limitante"] == "caminhões"


def test_dmt_de_equilibrio_a_mao():
    # ciclo máximo = 2·10·60·10 / 2400 = 5,0 min; folga 0,5 min a 3 min/km => 166,7 m
    assert dmt_de_equilibrio_m(P) == pytest.approx(500 / 3)
    assert producao_frota(166.0, P)["limitante"] == "escavadeira"
    assert producao_frota(167.0, P)["limitante"] == "caminhões"
    # 1 caminhão: ciclo máximo 1·10·60·10/2400 = 2,5 min < ciclo com DMT 0 (4,5): caminhão limita sempre
    assert dmt_de_equilibrio_m(ParametrosFrota(**{**P.__dict__, "n_caminhoes": 1})) == 0.0


def test_empolamento_converte_solto_em_corte():
    p = ParametrosFrota(**{**P.__dict__, "empolamento": 0.25})
    assert producao_frota(0, p)["producao_m3_corte_dia"] == pytest.approx(2400 / 1.25)


def test_monotonicidade_dmt_maior_nunca_produz_mais():
    for p in (P, ParametrosFrota(), ParametrosFrota(n_caminhoes=3)):
        prods = [producao_frota(d, p)["producao_m3_solto_dia"] for d in range(0, 10001, 50)]
        ciclos = [ciclo_caminhao_min(d, p) for d in range(0, 10001, 50)]
        assert all(b <= a + 1e-9 for a, b in zip(prods, prods[1:]))
        assert all(b > a for a, b in zip(ciclos, ciclos[1:]))


@pytest.mark.parametrize("campo, valor", [("eficiencia", 0), ("eficiencia", 1.5), ("n_caminhoes", -1),
                                          ("n_caminhoes", 0), ("cacamba_m3", float("inf")), ("v_vazio_kmh", "25"),
                                          ("n_caminhoes", 2.5), ("v_vazio_kmh", 0), ("empolamento", -0.1),
                                          ("horas_dia", float("nan"))])
def test_parametros_invalidos(campo, valor):
    with pytest.raises(ErroProdutividade):
        ParametrosFrota(**{campo: valor})


def test_fator_quantidade():
    assert fator_quantidade(1000, 800, 1.25) == pytest.approx(1.8)   # (1000+800)/max(1000, 1000)
    assert fator_quantidade(1000, 0, 1.25) == 1.0                    # corte puro
    assert fator_quantidade(0, 1000, 1.25) == pytest.approx(0.8)     # aterro puro: escava 1250 de empréstimo
    assert fator_quantidade(0, 0, 1.25) == 1.0


def test_dmt_por_segmento_a_mao():
    massas = {"total": {"bota_fora_m3": 20.0, "emprestimo_m3": 0.0}, "estacas": [{"km": 0.0}, {"km": 4.0}],
              # bota-fora de 20 m³ localizado no trecho km 2–4 (como massas.volume_livre informa)
              "volume_livre": [{"km_ini": 2.0, "km_fim": 4.0, "volume_m3": 20.0, "tipo": "bota-fora"}],
              "compensacoes": [
                  {"km_ini": 0.0, "km_fim": 2.0, "volume_m3": 100.0, "momento_m3m": 100.0 * 500, "aberta": False},
                  {"km_ini": 2.0, "km_fim": 4.0, "volume_m3": 50.0, "momento_m3m": 50.0 * 1000, "aberta": True}]}
    dados = {"segmentos": [{"id": "S1", "km_ini": 0, "km_fim": 1}, {"id": "S2", "km_ini": 1, "km_fim": 3},
                           {"id": "S3", "km_ini": 4, "km_fim": 3}]}            # S3 invertido de propósito
    r = dmt_por_segmento(dados, massas, ParametrosFrota(dmt_externa_m=3000.0))
    assert r["S1"]["dmt_m"] == pytest.approx(500.0)
    # S2: ½ da onda 1 (50; 25.000) + ½ da onda 2 (25; 25.000) + ½ do bota-fora (10 × 3.000)
    assert r["S2"]["dmt_m"] == pytest.approx(80000 / 85)
    assert r["S3"]["dmt_m"] == pytest.approx(55000 / 35)
    assert r["S2"]["volume_externo_m3"] == pytest.approx(10.0)


# ------------------------------------------------------------------ obras
@pytest.fixture(scope="module", params=list(OBRAS))
def analise(request):
    projeto = Projeto.carregar(OBRAS[request.param])
    return projeto, analisar(projeto)


def test_obras_produtividade_e_ajustes(analise):
    projeto, r = analise
    assert "SINTÉTICO" in r["aviso"]
    ter = [a for a in projeto.dados["atividades"] if a.get("servico_id") == "TER"]
    assert len(r["segmentos"]) == len(ter)
    for s in r["segmentos"]:
        assert s["dmt_m"] > 0 and s["produtividade_geometrica"] > 0 and s["produtividade_medida"] > 0
        assert s["produtividade_geometrica"] == pytest.approx(s["producao_m3_corte_dia"] * s["fator_quantidade"])
    pendentes = {a["id"] for a in ter if a["status"] != "concluida"}
    assert {x["atividade_id"] for x in r["ajustes_recomendados"]} == pendentes and pendentes
    # o efeito declarado é reproduzível pela simulação com os mesmos ajustes
    sim = executar(projeto, "simulado", [Ajuste(**x) for x in r["ajustes_recomendados"]])
    assert r["efeito_no_termino"]["termino_pela_geometria"] == sim["termino"]
    assert r["efeito_no_termino"]["termino_independente"] == executar(projeto, "independente")["termino"]


def test_frota_menor_torna_a_dmt_limitante(analise):
    projeto, r = analise
    pequena = analisar(projeto, ParametrosFrota(n_caminhoes=2))
    for a, b in zip(r["segmentos"], pequena["segmentos"]):
        assert b["limitante"] == "caminhões"
        assert b["produtividade_geometrica"] < a["produtividade_geometrica"]


def test_api(analise):
    projeto, r = analise
    c = TestClient(criar_app(fontes={"x": projeto}))
    assert "rotas_produtividade" in c.app.state.rotas_ligadas
    j = c.get("/api/produtividade/terraplenagem", params={"obra": "x"}).json()
    assert j["ajustes_recomendados"] == r["ajustes_recomendados"]
    assert c.get("/api/produtividade/terraplenagem", params={"obra": "zz"}).status_code == 404


# ------------------------------------------------------------------ integração massas -> produtividade (r12)
def test_integracao_volume_livre_vai_para_o_segmento_que_o_gera(tol=1e-6):
    """Fh = 1, estacas de 20 m: h = 0, −2, −2, 0, +2, +2, 0, −2, −2, 0 (plataforma 12 m: área(2) = 30 m²).
    Onda fechada de 1.200 m³ (km 0–0,12) e depois 1.200 m³ de corte sem aterro (km 0,12–0,18) -> bota-fora.
    O volume livre fica onde a curva sobe de 0 a 1.200 pela 1ª vez depois do último toque: km 0,12–0,18.
    S1 (0–0,10): DMT só da onda; S2 (0,10–0,18): recebe os 1.200 m³ externos a 3.000 m."""
    from infra4d.massas import Secao, calcular_massas
    hs = [0, -2, -2, 0, 2, 2, 0, -2, -2, 0]
    m = calcular_massas([i * 0.02 for i in range(len(hs))], hs, [0.0] * len(hs), Secao(12.0), fh=1.0)
    (livre,) = m["volume_livre"]
    assert (livre["km_ini"], livre["km_fim"], livre["volume_m3"], livre["tipo"]) ==         (pytest.approx(0.12), pytest.approx(0.18), pytest.approx(1200.0), "bota-fora")
    dados = {"segmentos": [{"id": "S1", "km_ini": 0.0, "km_fim": 0.10}, {"id": "S2", "km_ini": 0.10, "km_fim": 0.18}]}
    d = dmt_por_segmento(dados, m, ParametrosFrota(dmt_externa_m=3000.0))
    assert d["S1"]["volume_externo_m3"] == 0 and d["S2"]["volume_externo_m3"] == pytest.approx(1200.0)
    # S2: 1/6 da onda (1.200 m³ em 120 m; S2 tem 20 m dela) -> 200 m³ a 60 m, + 1.200 m³ a 3.000 m
    assert d["S2"]["dmt_m"] == pytest.approx((200 * 60 + 1200 * 3000) / 1400)


@pytest.mark.parametrize("arquivo", list(OBRAS.values()), ids=list(OBRAS))
def test_integracao_obras_todo_volume_livre_e_atribuido(arquivo):
    from infra4d.massas import massas_da_obra
    dados = Projeto.carregar(arquivo).dados
    m = massas_da_obra(dados)
    livre = m["total"]["bota_fora_m3"] + m["total"]["emprestimo_m3"]
    assert livre > 0 and sum(t["volume_m3"] for t in m["volume_livre"]) == pytest.approx(livre)
    d = dmt_por_segmento(dados, m)
    assert sum(x["volume_externo_m3"] for x in d.values()) == pytest.approx(livre)
