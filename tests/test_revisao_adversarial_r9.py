"""Revisão adversarial — rodada 9 (engenharia): massas.py (diagrama de Brückner) e orcamento.py (5D/EVM).

Mesmo protocolo: esperado calculado à mão no docstring; defeito confirmado fica
``xfail(strict=True, reason="DEFEITO: ...")``.

Fontes: NÃO consultei norma nem livro nesta rodada. Os esperados de massas vêm de (a) geometria da seção
trapezoidal, (b) integral exata do sólido com h linear entre estacas e (c) CONSERVAÇÃO DE VOLUME — que não
depende de fonte: todo corte ou é compensado ou vai para bota-fora, e todo aterro (em volume de corte
equivalente) ou é compensado ou vem de empréstimo. Os de EVM são as definições usuais (CV, SV, CPI, SPI,
EAC = BAC/CPI, ETC, VAC, TCPI), as mesmas que o módulo declara.
"""

import copy
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import orcamento as O
from infra4d.cenarios import Projeto
from infra4d.massas import ErroMassas, Secao, calcular_massas, coerencia, compensar, massas_da_obra

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")
SEC = Secao(12.0)   # plataforma 12 m, taludes 1:1,5 -> área(h) = |h|·(12 + 1,5·|h|); área(2) = 30 m²


@pytest.fixture(scope="module")
def obras():
    return {o: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json") for o in OBRAS}


def massas(kms, hs, fh=1.25):
    """Perfil dado pelas alturas no eixo: greide = h, terreno = 0 (h > 0 aterro, h < 0 corte)."""
    return calcular_massas(kms, hs, [0.0] * len(kms), SEC, fh=fh)


# =============================================================================
# 1. massas — o que está certo
# =============================================================================
def test_secao_onda_simples_dmt_e_sentido():
    """Estacas a cada 20 m, h = 0, −2, −2, 0, +2, +2, 0 (corte e depois aterro), Fh = 1.
    Área(2) = 2·(12 + 3) = 30 m². Corte: 300 + 600 + 300 = 1200 m³; aterro igual.
    Ordenadas: 0, 300, 900, 1200, 900, 300, 0 -> uma onda fechada, volume 1200 m³.
    Momento = área sob a curva = 20·(150 + 600 + 1050 + 1050 + 600 + 150) = 72.000 m³·m -> DMT = 60 m
    (distância entre os centros de massa do corte, x = 30 m, e do aterro, x = 90 m).
    Corte ANTES do aterro: transporte no sentido do km crescente. Um ponto de passagem, no km 0,06."""
    r = massas([0, .02, .04, .06, .08, .10, .12], [0, -2, -2, 0, 2, 2, 0], fh=1.0)
    t = r["total"]
    A = pytest.approx
    assert (t["volume_corte_m3"], t["volume_aterro_m3"], t["volume_compensado_m3"]) == A((1200.0, 1200.0, 1200.0))
    assert (t["bota_fora_m3"], t["emprestimo_m3"], t["ordenada_final_m3"]) == A((0.0, 0.0, 0.0), abs=1e-6)
    onda, = r["compensacoes"]
    assert (onda["momento_m3m"], onda["dmt_m"]) == A((72000.0, 60.0))
    assert (onda["sentido"], onda["aberta"]) == ("km crescente", False)
    assert r["pontos_passagem_km"] == [0.06]
    # espelho: aterro antes do corte -> mesmos volumes e DMT, sentido contrário
    e = massas([0, .02, .04, .06, .08, .10, .12], [0, 2, 2, 0, -2, -2, 0], fh=1.0)
    onda_e, = e["compensacoes"]
    assert (onda_e["volume_m3"], onda_e["dmt_m"]) == A((1200.0, 60.0)) and onda_e["sentido"] == "km decrescente"


def test_fator_de_homogeneizacao_empolamento_bota_fora_e_emprestimo():
    """Mesma onda com Fh = 1,25: aterro equivalente = 1,25 × 1200 = 1500 m³ > corte 1200 m³:
    ordenada final = −300 -> EMPRÉSTIMO de 300 m³, bota-fora 0.
    Só corte (h = 0, −2, −2, 0): 1200 m³ de sobra -> bota-fora 1200 m³ in situ e 1200 × 1,25 = 1500 m³
    solto (empolamento 25 %); nada compensado, DMT indefinida (None)."""
    t = massas([0, .02, .04, .06, .08, .10, .12], [0, -2, -2, 0, 2, 2, 0], fh=1.25)["total"]
    A = pytest.approx
    assert (t["volume_aterro_equivalente_corte_m3"], t["ordenada_final_m3"]) == A((1500.0, -300.0))
    assert (t["emprestimo_m3"], t["bota_fora_m3"]) == A((300.0, 0.0))
    c = massas([0, .02, .04, .06], [0, -2, -2, 0])["total"]
    assert (c["bota_fora_m3"], c["bota_fora_solto_m3"], c["emprestimo_m3"]) == A((1200.0, 1500.0, 0.0))
    assert (c["volume_compensado_m3"], c["dmt_media_m"]) == (0, None)


def test_perfil_plano_e_cruzamento_exatamente_numa_estaca():
    """Greide = terreno em todo o trecho: tudo zero, sem ponto de passagem, sem onda, DMT None.
    h = −2, 0, +2 com a passagem exatamente na estaca do meio: um ponto de passagem, no km 0,05."""
    r = massas([0, .02, .04], [0, 0, 0])
    assert r["total"]["volume_corte_m3"] == r["total"]["volume_aterro_m3"] == 0.0
    assert (r["pontos_passagem_km"], r["compensacoes"], r["total"]["dmt_media_m"]) == ([], [], None)
    assert massas([0, .05, .10], [-2, 0, 2])["pontos_passagem_km"] == [0.05]
    assert massas([0, .10], [-2, 2])["pontos_passagem_km"] == [0.05]


def test_dmt_de_cada_onda_fica_entre_zero_e_o_comprimento_da_onda():
    """300 perfis aleatórios (semente fixa): toda onda tem volume > 0, momento >= 0 e
    0 <= DMT <= comprimento da onda; a ordenada final = corte − Fh × aterro; e
    bota-fora − empréstimo = ordenada final (só um dos dois é não nulo)."""
    rng = random.Random(4)
    for _ in range(300):
        n = rng.randint(3, 40)
        kms = [i * 0.02 for i in range(n)]
        hs = [rng.uniform(-4, 4) if rng.random() > 0.1 else 0.0 for _ in range(n)]
        fh = rng.choice([1.0, 1.25])
        r = massas(kms, hs, fh=fh)
        t = r["total"]
        assert t["ordenada_final_m3"] == pytest.approx(t["volume_corte_m3"] - fh * t["volume_aterro_m3"], abs=1e-6)
        assert t["bota_fora_m3"] - t["emprestimo_m3"] == pytest.approx(t["ordenada_final_m3"], abs=1e-6)
        assert min(t["bota_fora_m3"], t["emprestimo_m3"]) == 0.0
        for o in r["compensacoes"]:
            assert o["volume_m3"] > 0 and o["momento_m3m"] >= 0
            assert 0 <= o["dmt_m"] <= (o["km_fim"] - o["km_ini"]) * 1000 + 1e-6


def test_entradas_invalidas_e_rota_com_passo_nos_extremos(obras):
    """NaN no perfil, km repetido e uma estaca só -> ErroMassas. Pela API: passo 1 m e 1000 m respondem
    200 (60 km -> 60.001 e 61 estacas na ferrovia); 0,5, 1001, nan e texto -> 422; obra desconhecida -> 404."""
    for kw in (dict(kms=[0, .02], greide=[0, float("nan")], terreno=[0, 0]),
               dict(kms=[0, 0], greide=[0, 0], terreno=[0, 0]), dict(kms=[0], greide=[0], terreno=[0])):
        with pytest.raises(ErroMassas):
            calcular_massas(secao=SEC, **kw)
    from infra4d.api import criar_app
    c = TestClient(criar_app(), raise_server_exceptions=False)
    assert len(c.get("/api/massas/diagrama", params={"passo_m": 1000}).json()["estacas"]) == 61
    assert len(c.get("/api/massas/diagrama", params={"passo_m": 1}).json()["estacas"]) == 60001
    for passo in ("0.5", "1001", "nan", "x", "-20"):
        assert c.get("/api/massas/diagrama", params={"passo_m": passo}).status_code == 422, passo
    assert c.get("/api/massas/diagrama", params={"obra": "zz"}).status_code == 404
    assert c.get("/api/massas/coerencia", params={"obra": "rodovia"}).status_code == 200


# =============================================================================
# 1b. massas — defeitos da rodada 9, hoje regressão
# =============================================================================
def test_onda_composta_compensa_a_soma_das_subidas():
    """Ordenadas 0, 100, 50, 120, 0 (a cada 100 m): corte = subidas = 100 + 70 = 170 m³; aterro = descidas
    = 50 + 120 = 170 m³. Tudo é compensado: volume da onda = 170 m³. Momento = área sob a curva =
    100·(50 + 75 + 85 + 60) = 27.000 m³·m -> DMT = 27.000 ÷ 170 = 158,8 m.
    O módulo devolve volume 120 m³ (o pico) e DMT 225 m."""
    ondas, final = compensar([0, 100, 200, 300, 400], [0, 100, 50, 120, 0])
    assert final == 0.0 and sum(o["momento_m3m"] for o in ondas) == 27000.0
    assert sum(o["volume_m3"] for o in ondas) == pytest.approx(170.0)
    assert sum(o["momento_m3m"] for o in ondas) / sum(o["volume_m3"] for o in ondas) == pytest.approx(158.82, abs=0.01)


@pytest.mark.parametrize("caso", ["perfis aleatorios", "ferrovia", "rodovia"])
def test_conservacao_de_volume(obras, caso):
    """Todo corte é compensado ou vai para bota-fora; todo aterro (× Fh) é compensado ou vem de empréstimo:
        corte = compensado + bota-fora          Fh·aterro = compensado + empréstimo
    com tolerância de 1 m³ por milhão. Vale para qualquer perfil, por balanço de massa."""
    if caso == "perfis aleatorios":
        rng = random.Random(4)
        totais = []
        for _ in range(200):
            n = rng.randint(3, 40)
            hs = [rng.uniform(-4, 4) if rng.random() > 0.1 else 0.0 for _ in range(n)]
            totais.append(massas([i * 0.02 for i in range(n)], hs)["total"])
    else:
        totais = [massas_da_obra(obras[caso].dados, 20.0)["total"]]
    for t in totais:
        tol = 1e-6 * max(1.0, t["volume_corte_m3"])
        assert t["volume_corte_m3"] == pytest.approx(t["volume_compensado_m3"] + t["bota_fora_m3"], abs=tol)
        assert t["volume_aterro_equivalente_corte_m3"] == pytest.approx(
            t["volume_compensado_m3"] + t["emprestimo_m3"], abs=tol)


def test_perfil_espelhado_compensa_o_mesmo_volume():
    """h = 0, −2, −3, −1, +1, +3, +2, −1, 0 a cada 20 m, Fh = 1; A(1) = 13,5, A(2) = 30, A(3) = 49,5 m².
    Média das áreas, DIVIDINDO o intervalo no ponto de passagem (conta refeita à mão, intervalo a intervalo):
      1) 0→−2: corte (0 + 30)/2 × 20 = 300          2) −2→−3: corte (30 + 49,5)/2 × 20 = 795
      3) −3→−1: corte (49,5 + 13,5)/2 × 20 = 630
      4) −1→+1: passagem a 10 m: corte 13,5/2 × 10 = 67,5; aterro 13,5/2 × 10 = 67,5
      5) +1→+3: aterro (13,5 + 49,5)/2 × 20 = 630    6) +3→+2: aterro (49,5 + 30)/2 × 20 = 795
      7) +2→−1: passagem a 13,333 m: aterro 30/2 × 13,333 = 200; corte 13,5/2 × 6,667 = 45
      8) −1→0: corte 13,5/2 × 20 = 135
    Corte = 300 + 795 + 630 + 67,5 + 45 + 135 = 1.972,5 m³; aterro = 67,5 + 630 + 795 + 200 = 1.692,5 m³;
    sobra de corte (bota-fora) = 280 m³. Sobra corte: TODO o aterro é compensado -> 1.692,5 m³, e o mesmo
    perfil percorrido ao contrário dá exatamente os mesmos números.
    (A 1ª versão deste teste esperava 2.130 / 1.860 / 270, pela média das áreas no intervalo INTEIRO nas
    passagens — o método que o teste do ponto de passagem, logo abaixo, rejeita. O esperado antigo estava
    errado; corrigido na rodada de fechamento.)"""
    kms = [i * 0.02 for i in range(9)]
    hs = [0, -2, -3, -1, 1, 3, 2, -1, 0]
    ida, volta = massas(kms, hs, fh=1.0)["total"], massas(kms, hs[::-1], fh=1.0)["total"]
    for t in (ida, volta):
        assert (t["volume_corte_m3"], t["volume_aterro_m3"], t["bota_fora_m3"]) == pytest.approx((1972.5, 1692.5, 280.0))
        assert t["volume_compensado_m3"] == pytest.approx(1692.5)
        assert t["emprestimo_m3"] == pytest.approx(0.0, abs=1e-6)


def test_volume_no_intervalo_com_passagem_usa_o_ponto_de_passagem():
    """Duas estacas a 100 m, h = −2 e +2 (linear): a passagem fica a 50 m.
    Média das áreas até a passagem: corte = (30 + 0)/2 × 50 = 750 m³; aterro idem.
    Integral exata do sólido: ∫(12h + 1,5h²)dx em 50 m, h de 2 a 0 = 600 + 100 = 700 m³.
    Esperado: entre 700 e 750 m³ de cada tipo, e igual (até 1 m³) ao resultado com 3 estacas (−2, 0, +2).
    O módulo dá 1500 m³ de cada."""
    duas = massas([0, .10], [-2, 2], fh=1.0)["total"]
    tres = massas([0, .05, .10], [-2, 0, 2], fh=1.0)["total"]
    assert (tres["volume_corte_m3"], tres["volume_aterro_m3"]) == pytest.approx((750.0, 750.0))
    assert 700.0 <= duas["volume_corte_m3"] <= 750.0 and 700.0 <= duas["volume_aterro_m3"] <= 750.0


@pytest.mark.parametrize("secao", [dict(largura_plataforma_m=-5.0), dict(largura_plataforma_m=12.0, talude_corte_h=-3.0)])
def test_secao_com_parametro_negativo_e_recusada(secao):
    """Largura de plataforma <= 0 ou talude < 0 não é seção de terraplenagem: ErroMassas na construção ou
    no cálculo; em nenhum caso área negativa."""
    try:
        s = Secao(**secao)
        r = calcular_massas([0, .02], [1.0, 1.0], [0.0, 11.0], s)
    except ErroMassas:
        return
    assert all(e["area_corte_m2"] >= 0 and e["area_aterro_m2"] >= 0 for e in r["estacas"])


def test_coerencia_com_quantidade_zero_na_atividade_ter(obras):
    """Uma atividade TER com quantidade 0 tem de aparecer com situação própria (ex.: 'sem quantidade'),
    e os demais segmentos continuam sendo comparados."""
    d = copy.deepcopy(obras["rodovia"].dados)
    next(a for a in d["atividades"] if a["id"].endswith("-TER"))["quantidade_total"] = 0
    c = coerencia(d)
    assert c["total"]["n_segmentos"] == len(d["segmentos"])


# =============================================================================
# 2. orçamento / EVM (inclui os defeitos da rodada 9, hoje regressão)
# =============================================================================
def proj(ativs, ficticio=True, medicoes=(), ds="2026-01-19"):
    return Projeto({
        "meta": {"inicio_projeto": "2026-01-05", "data_status": ds, "calendario_obra": "c5", "aviso": "x",
                 "ficticio": ficticio, "tipo_obra": "ferrovia"},
        "calendarios": [{"id": "c5", "nome": "c5", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []}],
        "atividades": list(ativs), "relacoes": [], "medicoes": list(medicoes), "servicos": [],
        "lotes": [{"id": "L1"}, {"id": "L2"}]})


def ter(qt=1000.0, qe=0.0, un="m³", **k):
    """Terraplenagem fictícia: composição FIC-FER-TER-001, custo direto 18,50 R$/m³, BDI 25 % -> 23,125 R$/m³.
    Linha de base de 05/01 a 16/01 (10 dias úteis)."""
    d = {"id": "A", "nome": "A", "tipo": "tarefa", "calendario": "c5", "servico_id": "TER", "lote_id": "L1",
         "unidade": un, "quantidade_total": qt, "quantidade_executada": qe, "produtividade_planejada": 100.0,
         "equipes": 1, "status": "nao_iniciada", "inicio_lb": "2026-01-05", "termino_lb": "2026-01-16"}
    d.update(k)
    return d


BOLETINS = [{"atividade_id": "A", "semana_inicio": "2026-01-05", "quantidade": 250.0, "equipes_dias": 5},
            {"atividade_id": "A", "semana_inicio": "2026-01-12", "quantidade": 150.0, "equipes_dias": 5}]
EM_ANDAMENTO = dict(qe=400.0, status="em_andamento", inicio_real="2026-01-05")


def test_evm_calculado_a_mao():
    """BDI explícito de 25 % (18,50 × 1,25): 1000 m³ a 23,125 R$/m³ -> BAC = 23.125,00. Status 19/01, depois do fim da LB -> PV = BAC.
    Executado 400 m³ (boletins de 250 e 150) -> EV = 9.250,00; SPI = 0,4; SV = −13.875,00.
    AC = EV × fator fictício f do par (L1, TER). Daí, pelas definições:
    CV = EV − AC; CPI = EV/AC = 1/f; EAC = BAC/CPI = BAC × f; ETC = EAC − AC; VAC = BAC − EAC;
    TCPI = (BAC − EV)/(BAC − AC); % físico-financeiro = EV/BAC = 0,4."""
    p = proj([ter(**EM_ANDAMENTO)], medicoes=BOLETINS)
    e = O.resumo(p, bdi=0.25)["evm"]
    f = O.fator_custo(0, "L1", "TER")
    assert O.FAIXA_FATOR_CUSTO[0] <= f <= O.FAIXA_FATOR_CUSTO[1]
    assert (e["bac"], e["pv"], e["ev"], e["spi"], e["sv"], e["percentual_fisico_financeiro"]) == \
           (23125.0, 23125.0, 9250.0, 0.4, -13875.0, 0.4)
    ac = round(9250.0 * f, 2)
    assert e["ac"] == ac and e["cv"] == round(9250.0 - 9250.0 * f, 2)
    assert e["cpi"] == round(1 / f, 4)
    assert e["eac"] == pytest.approx(23125.0 * f, abs=0.01)
    assert e["etc"] == pytest.approx(23125.0 * f - 9250.0 * f, abs=0.01)
    assert e["vac"] == pytest.approx(23125.0 - 23125.0 * f, abs=0.01)
    assert e["tcpi"] == round((23125.0 - 9250.0) / (23125.0 - 9250.0 * f), 4)


def test_evm_sem_divisao_por_zero():
    """Nada executado (EV = AC = 0): CPI, EAC, ETC e VAC são None; SPI = 0; TCPI = (BAC − 0)/(BAC − 0) = 1.
    Obra sem nada orçável (só um marco: BAC = PV = EV = AC = 0): todos os índices None, sem exceção.
    (Na rodada 9 o BAC = 0 era obtido com BDI de −100 %; desde a rodada 17 BDI negativo, NaN ou infinito é
    recusado com ErroOrcamento — conferido aqui. BDI 0 vale: BAC = custo direto = 1000 × 18,50.)"""
    e = O.resumo(proj([ter()]))["evm"]
    assert (e["cpi"], e["eac"], e["etc"], e["vac"], e["spi"], e["tcpi"]) == (None, None, None, None, 0.0, 1.0)
    marco = {"id": "M", "nome": "M", "tipo": "marco_termino", "calendario": "c5", "status": "nao_iniciada",
             "inicio_lb": "2026-01-16", "termino_lb": "2026-01-16"}
    z = O.resumo(proj([marco]))["evm"]
    assert (z["bac"], z["pv"], z["ev"], z["ac"]) == (0, 0, 0, 0)
    assert (z["cpi"], z["spi"], z["eac"], z["tcpi"], z["percentual_fisico_financeiro"]) == (None, None, None, None, None)
    for ruim in (-1.0, -0.01, float("nan"), float("inf")):
        with pytest.raises(O.ErroOrcamento):
            O.resumo(proj([ter(**EM_ANDAMENTO)], medicoes=BOLETINS), bdi=ruim)
    assert O.resumo(proj([ter()]), bdi=0.0)["evm"]["bac"] == 18500.0


@pytest.mark.parametrize("unidade", ["m3", "M³", " m³", "t", None])
def test_unidade_divergente_e_recusada(unidade):
    """A composição de TER é em 'm³'. 'm3', 'M³', ' m³' (com espaço), 't' e unidade ausente são recusadas
    com ErroOrcamento que cita a atividade — nunca conversão implícita."""
    with pytest.raises(O.ErroOrcamento, match="A: unidade"):
        O.resumo(proj([ter(un=unidade)]))


@pytest.mark.parametrize("marca", [False, None, "true", 1, "sim"])
def test_trava_de_obra_ficticia_cobre_resumo_e_curva_s(marca):
    """Só ``meta.ficticio is True`` libera. False, ausente, texto 'true', 1 e 'sim' -> ErroOrcamento em
    resumo() e em curva_s(), as duas funções que devolvem AC."""
    p = proj([ter(**EM_ANDAMENTO)], ficticio=marca, medicoes=BOLETINS)
    for fn in (O.resumo, O.curva_s):
        with pytest.raises(O.ErroOrcamento, match="meta.ficticio"):
            fn(p)


def test_rotas_de_orcamento_obra_sem_marca_lote_vazio_e_coerencia_das_somas(obras):
    """Pela API: obra sem a marca -> 422 em /resumo e /curva-s-financeira (e /composicoes continua 200,
    pois não devolve AC); lote cadastrado sem atividade orçada -> 422; lote inexistente -> 404.
    Nas duas obras fictícias: Σ BAC e Σ EV dos lotes = total; Σ EV por serviço = EV; a curva S termina em
    PV = BAC, nunca decresce, e EV/AC na data de status = os do resumo."""
    from infra4d.api import criar_app
    real = proj([ter(**EM_ANDAMENTO)], ficticio=False, medicoes=BOLETINS)
    vazio = proj([ter(**EM_ANDAMENTO)], medicoes=BOLETINS)
    c = TestClient(criar_app(fontes={"real": real, "vazio": vazio, **obras}), raise_server_exceptions=False)
    for rota in ("resumo", "curva-s-financeira"):
        assert c.get(f"/api/orcamento/{rota}", params={"obra": "real"}).status_code == 422, rota
    assert c.get("/api/orcamento/composicoes", params={"obra": "real"}).status_code == 200
    assert c.get("/api/orcamento/resumo", params={"obra": "vazio", "lote": "L2"}).status_code == 422
    assert c.get("/api/orcamento/resumo", params={"obra": "vazio", "lote": "L9"}).status_code == 404
    for obra in OBRAS:
        r = c.get("/api/orcamento/resumo", params={"obra": obra}).json()
        e = r["evm"]
        assert sum(x["bac"] for x in r["por_lote"]) == pytest.approx(e["bac"], abs=0.05)
        assert sum(x["ev"] for x in r["por_lote"]) == pytest.approx(e["ev"], abs=0.05)
        assert sum(x["ev"] for x in r["por_servico"]) == pytest.approx(e["ev"], abs=0.05)
        cs = c.get("/api/orcamento/curva-s-financeira", params={"obra": obra}).json()
        pts = cs["pontos"]
        assert pts[-1]["pv"] == cs["bac"] == e["bac"]
        assert all(b["pv"] >= a["pv"] for a, b in zip(pts, pts[1:]))
        no_status = next(x for x in pts if x["data"] == cs["data_status"])
        assert (no_status["ev"], no_status["ac"]) == (e["ev"], e["ac"])


@pytest.mark.parametrize("caso", ["boletins somam 300 de 400", "executado sem boletim", "verba concluida sem inicio real"])
def test_ev_do_evm_e_o_executado_vezes_o_preco(caso):
    """(a) 400 m³ executados, boletins de 250 + 50: EV esperado 400 × 23,125 = 9.250,00 (o módulo dá 6.937,50).
    (b) 400 m³ executados, sem boletim: 9.250,00 (o módulo dá 0,00).
    (c) verba SIN concluída (100 %) sem inicio_real: EV esperado = BAC = 6.000.000,00 (o módulo dá 0,00).
    Em todos, EV do EVM = Σ EV por serviço."""
    if caso == "verba concluida sem inicio real":
        p = proj([{"id": "S", "nome": "S", "tipo": "tarefa", "calendario": "c5", "servico_id": "SIN", "lote_id": "L1",
                   "duracao_fixa": 5, "status": "concluida", "inicio_lb": "2026-01-05", "termino_lb": "2026-01-09"}])
        esperado = 6000000.0
    else:
        med = [BOLETINS[0], {**BOLETINS[1], "quantidade": 50.0}] if caso.startswith("boletins") else []
        p = proj([ter(**EM_ANDAMENTO)], medicoes=med)
        esperado = 9250.0
    r = O.resumo(p, bdi=0.25)
    assert sum(x["ev"] for x in r["por_servico"]) == esperado
    assert r["evm"]["ev"] == esperado


@pytest.mark.parametrize("lb", [None, ("2026-01-16", "2026-01-05"), ("2026-01-10", "2026-01-11")])
def test_atividade_sem_linha_de_base_utilizavel_e_recusada(lb):
    """Sem as datas da LB, com término antes do início, ou com a LB inteira num fim de semana:
    esperado ErroOrcamento citando a atividade (ou PV final = BAC). Nunca KeyError nem PV = 0 com BAC > 0."""
    a = ter()
    if lb is None:
        del a["inicio_lb"], a["termino_lb"]
    else:
        a["inicio_lb"], a["termino_lb"] = lb
    try:
        cs = O.curva_s(proj([a]))
    except O.ErroOrcamento:
        return
    assert cs["pontos"][-1]["pv"] == cs["bac"] == 23125.0
