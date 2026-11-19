"""Curva S física e financeira: realizado = EV/painel, previstos fecham em 100 % e são monotônicos."""

import copy

import pytest
from fastapi.testclient import TestClient

from infra4d import orcamento, painel
from infra4d.api import criar_app
from infra4d.calendario import iso, ordinal
from infra4d.cenarios import DATASET_PADRAO, Projeto, executar
from infra4d.curva_s import CURVAS, ErroCurvaS, curva_s, eventos_realizado, pesos

OBRAS = {"ferrovia": DATASET_PADRAO, "rodovia": DATASET_PADRAO.parent / "rodovia_ficticia.json"}
CEN = ("linha_base", "construtora", "independente")


@pytest.fixture(scope="module", params=list(OBRAS))
def obra(request):
    P = Projeto.carregar(OBRAS[request.param])
    return request.param, P, {c: executar(P, c) for c in CEN}


def _ponto(r, data):
    return next(p for p in r["pontos"] if p["data"] == data)


@pytest.mark.parametrize("lote", [None, "L2"])
def test_realizado_financeiro_bate_com_o_ev_do_orcamento(obra, lote):
    nome, P, res = obra
    r = curva_s(P, res, "financeira", lote)
    evm = orcamento.resumo(P, lote)["evm"]
    assert round(r["realizado_na_data_status"], 2) == pytest.approx(evm["ev"], abs=0.01)
    assert r["total"] == pytest.approx(evm["bac"], abs=0.01)
    assert _ponto(r, r["data_status"])["realizado"] == pytest.approx(100 * evm["ev"] / r["total"], abs=1e-3)


@pytest.mark.parametrize("lote", [None, "L1", "L3"])
def test_realizado_e_planejado_fisicos_batem_com_o_painel(obra, lote):
    nome, P, res = obra
    r = curva_s(P, res, "fisica", lote)
    p = _ponto(r, r["data_status"])
    assert p["realizado"] == pytest.approx(100 * painel.avanco(P, res["independente"], P.data_status, lote), abs=1e-3)
    assert p["planejado"] == pytest.approx(100 * painel.avanco(P, res["linha_base"], P.data_status, lote), abs=1e-3)


@pytest.mark.parametrize("base", ["fisica", "financeira"])
def test_curvas_monotonicas_e_fechamento_em_100(obra, base):
    nome, P, res = obra
    r = curva_s(P, res, base)
    for c in CURVAS:
        serie = [p[c] for p in r["pontos"] if p[c] is not None]
        assert all(b >= a - 1e-9 for a, b in zip(serie, serie[1:])), c
        assert serie[0] >= 0 and serie[-1] <= 100 + 1e-9
    for c, chave in (("linha_base", "planejado"), ("construtora", "previsto_construtora"),
                     ("independente", "previsto_independente")):
        fecha = r["fechamento"][c]
        assert fecha == iso(ordinal(res[c]["termino"]) + 1)
        assert _ponto(r, fecha)[chave] == pytest.approx(100.0, abs=1e-9)
        antes = [p[chave] for p in r["pontos"] if p["data"] <= res[c]["termino"]]
        assert antes and max(antes) < 100.0                 # antes da fronteira do término não fechou
    for p in r["pontos"]:
        if p["data"] <= r["data_status"]:
            assert p["previsto_construtora"] == p["previsto_independente"] == p["realizado"]
        else:
            assert p["realizado"] is None


def test_independente_abaixo_da_construtora_depois_da_data_de_status(obra):
    """A independente usa a produtividade medida (menor que a planejada nas frentes críticas)."""
    nome, P, res = obra
    r = curva_s(P, res, "fisica")
    depois = [p for p in r["pontos"] if p["data"] > r["data_status"]]
    assert all(p["previsto_independente"] <= p["previsto_construtora"] + 1e-9 for p in depois)
    assert any(p["previsto_independente"] < p["previsto_construtora"] - 1 for p in depois)


def test_regra_da_semana_terminada_no_realizado(obra):
    """Boletim conta na fronteira min(semana_inicio + 7, término real + 1, data de status), nunca antes."""
    nome, P, res = obra
    w = pesos(P, "fisica")
    ds = P.data_status
    ev = eventos_realizado(P, w)
    assert all(t <= ds and v > 0 for t, v in ev)
    ativ = P.atividades
    tempos = {t for t, _ in ev}
    for m in P.dados["medicoes"]:
        a = ativ[m["atividade_id"]]
        fim = min(ordinal(m["semana_inicio"]) + 7, ds)
        if a.get("termino_real"):
            fim = min(fim, ordinal(a["termino_real"]) + 1)
        assert fim in tempos
    # nenhum evento de boletim antes do fim da semana do boletim mais antigo
    primeiro = min(ordinal(m["semana_inicio"]) for m in P.dados["medicoes"])
    assert min(tempos) > primeiro


def test_obra_sem_marca_ficticia_nao_tem_curva_financeira(obra):
    nome, P, res = obra
    d = copy.deepcopy(P.dados)
    d["meta"]["ficticio"] = "sim"
    with pytest.raises(ValueError):
        curva_s(Projeto(d), res, "financeira")
    assert curva_s(Projeto(d), res, "fisica")["pontos"]           # a física não depende de preço


@pytest.mark.parametrize("kw", [dict(base="x"), dict(lote="L9"), dict(passo_dias=0), dict(passo_dias=True)])
def test_parametros_invalidos(obra, kw):
    nome, P, res = obra
    with pytest.raises(ErroCurvaS):
        curva_s(P, res, **{"base": "fisica", **kw})


def test_rota(obra):
    nome, P, res = obra
    c = TestClient(criar_app(fontes={nome: P}))
    if "rotas_curva_s" not in c.app.state.rotas_ligadas:          # registro na API é do orquestrador
        from infra4d.rotas_curva_s import ligar
        ligar(c.app, c.app.state.obter_estado)
    j = c.get("/api/curva-s", params={"obra": nome, "base": "financeira", "lote": "L1"})
    assert j.status_code == 200 and j.json()["lote"] == "L1" and j.json()["pontos"]
    assert j.json()["tempo_s"] < 1.0
    for params, codigo in (({"base": "x"}, 422), ({"lote": "L9"}, 404), ({"passo_dias": 0}, 422),
                           ({"obra": "zz"}, 404)):
        assert c.get("/api/curva-s", params={"obra": nome, **params}).status_code == codigo, params


def test_verba_em_andamento_entra_pelo_percentual_executado():
    """Duração fixa em andamento: realizado = peso × % executado, linear nos dias úteis desde o início real."""
    d = copy.deepcopy(Projeto.carregar(OBRAS["rodovia"]).dados)
    a = next(x for x in d["atividades"] if x["id"] == "L1-LIB")
    ds = ordinal(d["meta"]["data_status"])
    a.update(status="em_andamento", inicio_real=iso(ds - 14), percentual_executado=40.0)
    P = Projeto(d)
    w = pesos(P, "fisica")
    ev = [(t, v) for t, v in eventos_realizado(P, {"L1-LIB": w["L1-LIB"]})]
    assert sum(v for _, v in ev) == pytest.approx(0.4 * w["L1-LIB"])          # 15 dias × 40 %
    assert min(t for t, _ in ev) > ds - 14 and max(t for t, _ in ev) <= ds
    a.update(status="concluida", termino_real=iso(ds - 2))
    ev = eventos_realizado(Projeto(d), {"L1-LIB": w["L1-LIB"]})
    assert sum(v for _, v in ev) == pytest.approx(w["L1-LIB"]) and max(t for t, _ in ev) == ds - 1
