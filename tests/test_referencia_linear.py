"""Referência linear: km <-> estaca, km -> (x, y, cota, rumo), (x, y) -> km + afastamento, km -> obra.

Resultados à mão em eixos sintéticos (reto e em L) e conferência nas duas obras fictícias.
"""

import json
import math

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO
from infra4d.dados_sinteticos_rodovia import DATASET_RODOVIA
from infra4d.referencia_linear import Eixo, ErroReferencia, cobertura, estaca_para_km, km_para_estaca

RETO = [[0, 0, 0, 0], [1, 1000, 0, 10]]                        # para leste, 1 km, sobe 10 m
EM_L = [[0, 0, 0, 0], [1, 1000, 0, 0], [2, 1000, 1000, 0]]     # leste 1 km, depois norte 1 km


@pytest.fixture(scope="module")
def obras():
    return {"ferrovia": json.loads(DATASET_PADRAO.read_text(encoding="utf-8")),
            "rodovia": json.loads(DATASET_RODOVIA.read_text(encoding="utf-8"))}


# ------------------------------------------------------------------ estaca
@pytest.mark.parametrize("km, origem, esperado", [
    (0.0, 0, "0+00,00"),
    (24.695, 0, "1234+15,00"),
    (4.0, 0, "200+00,00"),
    (0.01999, 0, "0+19,99"),
    (0.0199999, 0, "1+00,00"),   # 19,9999 m arredonda para 20,00 e fecha a estaca
    (0.019996, 0, "1+00,00"),
    (3.9999999999, 0, "200+00,00"),
    (0.0, 500, "500+00,00"),
    (1.2345, 0, "61+14,50"),
])
def test_km_para_estaca(km, origem, esperado):
    assert km_para_estaca(km, origem) == esperado


@pytest.mark.parametrize("estaca, origem, km", [
    ("1234+15,00", 0, 24.695), ("1234 + 15.5", 0, 24.6955), ("0+00", 0, 0.0), ("500+00,00", 500, 0.0),
    ("61+14,50", 0, 1.2345),
])
def test_estaca_para_km(estaca, origem, km):
    assert estaca_para_km(estaca, origem) == pytest.approx(km, abs=1e-9)


@pytest.mark.parametrize("ruim", ["1234+20,00", "abc", "1234", "12+-3", ""])
def test_estaca_invalida_da_erro_claro(ruim):
    with pytest.raises(ErroReferencia, match="estaca inválida"):
        estaca_para_km(ruim)


def test_ida_e_volta_estaca():
    for i in range(0, 60001, 37):
        km = i / 1000
        assert estaca_para_km(km_para_estaca(km)) == pytest.approx(km, abs=1e-6)


# ------------------------------------------------------------------ km -> ponto
def test_ponto_em_eixo_reto():
    p = Eixo(RETO).ponto_em(0.25)
    assert (p["x"], p["y"], p["cota"], p["rumo_graus"]) == pytest.approx((250, 0, 2.5, 90))
    assert p["estaca"] == "12+10,00"


def test_ponto_em_eixo_em_l_e_rumo():
    e = Eixo(EM_L)
    assert e.ponto_em(1.5)["x"] == pytest.approx(1000) and e.ponto_em(1.5)["y"] == pytest.approx(500)
    assert e.ponto_em(0.5)["rumo_graus"] == pytest.approx(90)
    assert e.ponto_em(1.5)["rumo_graus"] == pytest.approx(0)
    assert e.ponto_em(2.0)["y"] == pytest.approx(1000)  # km final pertence ao último trecho


@pytest.mark.parametrize("km", [-0.001, 2.001, float("nan")])
def test_km_fora_do_eixo_e_erro(km):
    with pytest.raises(ErroReferencia, match="fora do eixo"):
        Eixo(EM_L).ponto_em(km)


@pytest.mark.parametrize("pontos", [[[0, 0, 0, 0]], [[0, 0, 0, 0], [0, 10, 0, 0]], [[0, 0, 0, 0], [1, 0, 0, 0]]])
def test_alinhamento_invalido(pontos):
    with pytest.raises(ErroReferencia):
        Eixo(pontos)


# ------------------------------------------------------------------ ponto -> km
def test_localizar_eixo_reto_com_lado():
    e = Eixo(RETO)
    esq = e.localizar(500, 30)       # norte de um eixo que vai para leste = esquerda
    assert (esq["km"], esq["afastamento_m"], esq["lado"]) == (pytest.approx(0.5), pytest.approx(-30), "esquerdo")
    dire = e.localizar(500, -30)
    assert (dire["km"], dire["afastamento_m"], dire["lado"]) == (pytest.approx(0.5), pytest.approx(30), "direito")
    assert e.localizar(500, 0)["lado"] == "eixo" and e.localizar(500, 0)["aviso"] is None


def test_localizar_eixo_em_l():
    e = Eixo(EM_L)
    a = e.localizar(1200, 500)       # eixo indo para o norte; x maior = direita
    assert a["km"] == pytest.approx(1.5) and a["afastamento_m"] == pytest.approx(200) and a["lado"] == "direito"
    b = e.localizar(900, -50)        # mais perto do 1º trecho (50 m) que do canto (111,8 m)
    assert b["km"] == pytest.approx(0.9) and b["afastamento_m"] == pytest.approx(50)
    c = e.localizar(1100, -100)      # fora do canto: projeta no vértice
    assert c["km"] == pytest.approx(1.0) and c["distancia_m"] == pytest.approx(math.hypot(100, 100))
    assert c["aviso"] is None


def test_localizar_antes_do_inicio_e_depois_do_fim_projeta_no_extremo_com_aviso():
    e = Eixo(EM_L)
    a = e.localizar(-100, 20)
    assert a["km"] == 0 and "antes do início" in a["aviso"]
    assert a["distancia_m"] == pytest.approx(math.hypot(100, 20)) and a["lado"] == "esquerdo"
    b = e.localizar(1000, 1300)
    assert b["km"] == 2 and "depois do fim" in b["aviso"] and b["lado"] == "eixo"


def test_ida_e_volta_xy_km_xy_em_l():
    e = Eixo(EM_L)
    for km in [0.0, 0.1, 0.77, 1.0, 1.33, 2.0]:
        p = e.ponto_em(km)
        loc = e.localizar(p["x"], p["y"])
        assert loc["km"] == pytest.approx(km, abs=1e-9) and loc["afastamento_m"] == pytest.approx(0, abs=1e-9)


# ------------------------------------------------------------------ obras fictícias
@pytest.mark.parametrize("obra", ["ferrovia", "rodovia"])
def test_ida_e_volta_nas_obras_com_afastamento(obras, obra):
    e = Eixo.da_obra(obras[obra])
    assert e.km_inicial == 0
    for i in range(0, int(e.km_final * 10)):
        km = i / 10 + 0.05                          # meio de cada trecho de 0,1 km
        p = e.ponto_em(km)
        loc = e.localizar(p["x"], p["y"])
        assert loc["km"] == pytest.approx(km, abs=1e-6) and abs(loc["afastamento_m"]) < 1e-6
        th = math.radians(p["rumo_graus"])          # normal à direita: (cos θ, −sen θ)
        loc = e.localizar(p["x"] + 15 * math.cos(th), p["y"] - 15 * math.sin(th))
        assert loc["km"] == pytest.approx(km, abs=1e-6), (obra, km)
        assert loc["afastamento_m"] == pytest.approx(15, abs=1e-6) and loc["lado"] == "direito"


@pytest.mark.parametrize("obra, km, lote, seg, contem", [
    ("ferrovia", 12.4, "L1", "L1-S03", {"L1-S03-TER", "OAE1-FUN", "L1-SIN"}),
    ("ferrovia", 20.0, "L2", "L2-S01", {"L2-S01-SUP"}),
    ("ferrovia", 60.0, "L3", "L3-S04", {"L3-S04-SOL"}),
    ("rodovia", 25.4, "L2", "L2-S03", {"L2-S03-CBU", "OAE2-SUE", "L2-LIB"}),
    ("rodovia", 48.0, "L3", "L3-S04", {"L3-S04-DEF"}),
])
def test_cobertura_km_para_obra(obras, obra, km, lote, seg, contem):
    c = cobertura(obras[obra], km)
    assert c["lote"]["id"] == lote and c["segmento"]["id"] == seg
    ids = {a["id"] for a in c["atividades"]}
    assert contem <= ids
    assert all(a.get("segmento_id") in (seg, None) for a in c["atividades"])


def test_estaca_dos_segmentos_bate_com_o_km(obras):
    for dados in obras.values():
        for s in dados["segmentos"]:
            assert km_para_estaca(s["km_ini"]) == f"{s['estaca_ini']}+00,00"


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def cliente():
    return TestClient(criar_app())


def test_api_km(cliente):
    r = cliente.get("/api/referencia/km", params={"km": 12.4, "obra": "ferrovia"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["estaca"] == "620+00,00" and j["lote"]["id"] == "L1" and j["segmento"]["id"] == "L1-S03"
    a = next(x for x in j["atividades"] if x["id"] == "L1-S03-TER")
    assert {"status", "inicio", "termino", "critica", "folga_total"} <= set(a)
    r2 = cliente.get("/api/referencia/km", params={"estaca": "1270+00,00", "obra": "rodovia"})
    assert r2.status_code == 200 and r2.json()["km"] == pytest.approx(25.4)
    assert r2.json()["tipo_obra"] == "rodovia"


@pytest.mark.parametrize("params, codigo", [
    ({"km": 99, "obra": "ferrovia"}, 422),
    ({"km": 1, "estaca": "50+00", "obra": "ferrovia"}, 422),
    ({"obra": "ferrovia"}, 422),
    ({"estaca": "xx", "obra": "rodovia"}, 422),
    ({"km": 1, "obra": "inexistente"}, 404),
])
def test_api_km_erros(cliente, params, codigo):
    r = cliente.get("/api/referencia/km", params=params)
    assert r.status_code == codigo, r.text
    assert r.json()["detail"]


def test_api_ponto_ida_e_volta(cliente):
    p = cliente.get("/api/referencia/km", params={"km": 33.85, "obra": "rodovia"}).json()["ponto"]
    j = cliente.get("/api/referencia/ponto", params={"x": p["x"], "y": p["y"], "obra": "rodovia"}).json()
    assert j["km"] == pytest.approx(33.85, abs=1e-6) and j["estaca"] == "1692+10,00" and j["aviso"] is None
    fora = cliente.get("/api/referencia/ponto", params={"x": -500, "y": 0, "obra": "ferrovia"}).json()
    assert fora["km"] == 0 and fora["aviso"]


# ------------------------------------------------------------------ Estaca e equações de estacas (R05 E5)
import random  # noqa: E402

from infra4d.referencia_linear import Estaca, Estaqueamento  # noqa: E402

EQ_RECUO = [{"km": 2.0, "estaca": "99+10,00"}]      # no km 2,000 a estaca passa a valer 99+10 (1.990 m)
EQ_SALTO = [(2.0, 2050.0)]                           # no km 2,000 a estaca passa a valer 102+10 (2.050 m)


def test_estaca_tipo_e_texto():
    e = Estaca(125, 10.0)
    assert e.metros == 2510.0 and str(e) == "125+10,00"
    assert Estaca.de_texto("125+10,00") == Estaca(125, 10.0)
    assert Estaca.de_metros(2510.0) == Estaca(125, 10.0)
    assert Estaca(3, 19.996).texto() == "4+00,00"
    for ruim in [(1, 20.0), (1, -0.1), (1, float("nan"))]:
        with pytest.raises(ErroReferencia):
            Estaca(*ruim)
    with pytest.raises(ErroReferencia):
        Estaca(1.5, 0.0)


def test_estaca_125_mais_10_e_2510_m_sem_equacao(limite):
    tol = limite("tolerancia_estaca_m")
    st = Estaqueamento()
    assert st.estaca_para_km(Estaca(125, 10.0)) * 1000 == pytest.approx(2510.0, abs=tol)
    e = st.km_para_estaca(2.51)
    assert (e.numero, e.trecho) == (125, 0) and e.mais_m == pytest.approx(10.0, abs=tol)


@pytest.mark.parametrize("equacoes", [None, EQ_RECUO, EQ_SALTO], ids=["sem", "recuo", "salto"])
def test_ida_e_volta_km_estaca_km_em_1000_pontos(limite, equacoes):
    tol = limite("tolerancia_estaca_m")
    st = Estaqueamento(0, equacoes)
    rng = random.Random(55)
    kms = [rng.uniform(0.0, 4.0) for _ in range(990)] + [0.0, 1.99, 1.995, 1.9999999, 2.0, 2.0000001, 2.005,
                                                         2.01, 3.9999, 4.0]
    for km in kms:
        e = st.km_para_estaca(km)
        assert 0 <= e.mais_m < 20
        assert abs(st.estaca_para_km(e) - km) * 1000 <= tol, (km, e)
        # pelo texto (arredondado ao cm) + trecho: volta ao km com erro <= 0,5 cm
        assert abs(st.estaca_para_km(e.texto(), e.trecho) - km) * 1000 <= 0.005 + tol


def test_ida_e_volta_estaca_km_estaca_em_1000_pontos(limite):
    tol = limite("tolerancia_estaca_m")
    st = Estaqueamento(0, EQ_RECUO)
    for i in range(1000):
        s_m = i * 4.0037                     # 0 a ~4.000 m de estaqueamento
        for trecho in (0, 1):
            e = Estaca.de_metros(s_m, trecho)
            try:
                km = st.estaca_para_km(e)
            except ErroReferencia:
                continue                     # estaca não existe nesse trecho
            volta = st.km_para_estaca(km)
            assert abs(volta.metros - s_m) <= tol
            if not (trecho == 0 and abs(km - 2.0) < 1e-12):   # a estaca "atrás" no ponto exato vira a "à frente"
                assert volta.trecho == trecho


def test_equacao_que_recua_regras_de_ambiguidade(limite):
    tol = limite("tolerancia_estaca_m") / 1000
    st = Estaqueamento(0, EQ_RECUO)
    assert str(st.km_para_estaca(1.995)) == "99+15,00" and st.km_para_estaca(1.995).trecho == 0
    assert str(st.km_para_estaca(2.0)) == "99+10,00" and st.km_para_estaca(2.0).trecho == 1   # ponto da equação: trecho novo
    assert str(st.km_para_estaca(2.005)) == "99+15,00" and st.km_para_estaca(2.005).trecho == 1
    with pytest.raises(ErroReferencia, match="ambígua.*trecho 0 → km 1.995.*trecho 1 → km 2.005"):
        st.estaca_para_km("99+15,00")
    assert st.estaca_para_km("99+15,00", trecho=0) == pytest.approx(1.995, abs=tol)
    assert st.estaca_para_km("99+15,00", trecho=1) == pytest.approx(2.005, abs=tol)
    # a estaca "atrás" do ponto da equação (100+00): sem trecho é a do trecho novo; com trecho 0, o ponto da equação
    assert st.estaca_para_km("100+00,00") == pytest.approx(2.010, abs=tol)
    assert st.estaca_para_km("100+00,00", trecho=0) == pytest.approx(2.000, abs=tol)
    assert st.estaca_para_km("50+00,00") == pytest.approx(1.0, abs=tol)
    assert st.estaca_para_km("150+00,00") == pytest.approx(3.010, abs=tol)
    with pytest.raises(ErroReferencia, match="não existe no trecho 0"):
        st.estaca_para_km("150+00,00", trecho=0)
    with pytest.raises(ErroReferencia, match="trecho de estaqueamento inexistente"):
        st.estaca_para_km("10+00,00", trecho=2)


def test_equacao_que_avanca_cria_salto(limite):
    tol = limite("tolerancia_estaca_m") / 1000
    st = Estaqueamento(0, EQ_SALTO)
    with pytest.raises(ErroReferencia, match="salto"):
        st.estaca_para_km("101+00,00")           # 2.020 m: entre 2.000 (atrás) e 2.050 (à frente)
    assert st.estaca_para_km("102+10,00") == pytest.approx(2.0, abs=tol)
    assert st.estaca_para_km("99+00,00") == pytest.approx(1.98, abs=tol)


def test_equacoes_invalidas():
    for eqs in ([(2.0, 1990.0), (2.0, 2500.0)], [(2.0, 1990.0), (1.0, 500.0)], [{"km": 1.0}], [(float("nan"), 1.0)]):
        with pytest.raises(ErroReferencia):
            Estaqueamento(0, eqs)


def test_estaca_origem_com_equacao(limite):
    tol = limite("tolerancia_estaca_m") / 1000
    st = Estaqueamento(500, [{"km": 1.0, "estaca": "600+00,00"}])
    assert str(st.km_para_estaca(0.0)) == "500+00,00"
    assert str(st.km_para_estaca(1.5)) == "625+00,00"
    assert st.estaca_para_km("625+00,00") == pytest.approx(1.5, abs=tol)
    with pytest.raises(ErroReferencia, match="salto"):
        st.estaca_para_km("580+00,00")


def test_eixo_com_equacao_na_meta(obras):
    dados = dict(obras["rodovia"])
    dados["meta"] = {**dados["meta"], "equacoes_estaca": EQ_RECUO}
    e = Eixo.da_obra(dados)
    p = e.ponto_em(2.005)
    assert p["estaca"] == "99+15,00" and p["estaca_trecho"] == 1
    loc = e.localizar(p["x"], p["y"])
    assert loc["estaca"] == "99+15,00" and loc["estaca_trecho"] == 1
    assert "estaca_trecho" not in Eixo.da_obra(obras["rodovia"]).ponto_em(2.005)


def test_api_estaca_ambigua_e_trecho(obras):
    from infra4d.cenarios import Projeto
    dados = json.loads(json.dumps(obras["rodovia"]))
    dados["meta"]["equacoes_estaca"] = EQ_RECUO
    c = TestClient(criar_app(fontes={"rodovia": Projeto(dados)}))
    r = c.get("/api/referencia/km", params={"estaca": "99+15,00", "obra": "rodovia"})
    assert r.status_code == 422 and "ambígua" in r.json()["detail"]
    r = c.get("/api/referencia/km", params={"estaca": "99+15,00", "trecho": 1, "obra": "rodovia"})
    assert r.status_code == 200 and r.json()["km"] == pytest.approx(2.005) and r.json()["estaca_trecho"] == 1
    assert c.get("/api/referencia/km", params={"estaca": "99+15,00", "trecho": 7, "obra": "rodovia"}).status_code == 422


# ------------------------------------------------------------------ revisão r6 (complementos)
@pytest.mark.parametrize("sentido", [1, -1], ids=["curva à esquerda", "curva à direita"])
def test_lado_no_vertice_segue_a_deflexao(sentido):
    """Deflexão de 135°: o ponto de fora projeta no vértice e fica do lado de FORA da curva."""
    e = Eixo([[0, 0, 0], [10, 10, 0], [10 + math.sqrt(50), 5, 5 * sentido]])
    loc = e.localizar(11, -0.5 * sentido * -1)
    assert loc["km"] == 10.0
    assert loc["lado"] == ("direito" if sentido == 1 else "esquerdo")
    assert abs(loc["afastamento_m"]) == pytest.approx(math.sqrt(1.25))


@pytest.mark.parametrize("texto", ["9" * 10 + "+1", "1+" + "9" * 3, "1+1," + "1" * 10])
def test_estaca_com_digitos_demais_e_invalida(texto):
    with pytest.raises(ErroReferencia, match="estaca inválida"):
        Estaca.de_texto(texto)


def test_estaca_e_metros_fora_do_limite():
    with pytest.raises(ErroReferencia):
        Estaca(10 ** 400, 0.0)
    with pytest.raises(ErroReferencia):
        Estaca.de_metros(1e300)


def test_api_virgula_decimal_na_query_e_422(cliente):
    assert cliente.get("/api/referencia/km", params={"km": "12,5", "obra": "ferrovia"}).status_code == 422
    assert cliente.get("/api/referencia/km", params={"km": "12.5", "obra": "ferrovia"}).status_code == 200


def test_cobertura_de_trecho_invertido_e_km_max():
    d = {"lotes": [{"id": "L1", "km_ini": 20, "km_fim": 0}], "segmentos": [],
         "atividades": [{"id": "A", "km_ini": 10, "km_fim": 5}, {"id": "Z", "km_ini": 20, "km_fim": 15}]}
    assert [a["id"] for a in cobertura(d, 7)["atividades"]] == ["A"]
    c = cobertura(d, 20)                      # km final da obra (lote invertido) pertence ao último trecho
    assert c["lote"]["id"] == "L1" and [a["id"] for a in c["atividades"]] == ["Z"]
