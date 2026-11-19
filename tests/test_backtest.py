"""Backtest da previsão: erros contra duas referências declaradas, sem dado futuro, circularidade medida."""

import copy

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.backtest import FAIXAS, ErroBacktest, backtest, realidade_da_obra
from infra4d.calendario import iso, ordinal
from infra4d.cenarios import DATASET_PADRAO, Projeto
from infra4d.tendencia import tendencia

OBRAS = {"ferrovia": DATASET_PADRAO, "rodovia": DATASET_PADRAO.parent / "rodovia_ficticia.json"}


@pytest.fixture(scope="module", params=list(OBRAS))
def obra(request):
    P = Projeto.carregar(OBRAS[request.param])
    return request.param, P, backtest(P, 7)


def _marco(r, mid):
    return next(m for m in r["marcos"] if m["id"] == mid)


def test_erro_e_previsao_da_mta_menos_referencia(obra):
    """erro(d) = término previsto pela MTA em d − referência, para os dois cenários e as duas referências."""
    nome, P, r = obra
    mta = {m["id"]: m["serie"] for m in tendencia(P, 7)["marcos"]}
    assert r["datas_de_status"] == [p["data_status"] for p in next(iter(mta.values()))]
    for m in r["marcos"]:
        for ref in m["por_referencia"].values():
            for c in ("construtora", "independente"):
                esperado = [ordinal(p[f"termino_{c}"]) - ordinal(ref["referencia"]) for p in mta[m["id"]]]
                assert ref["erro_dias"][c] == esperado


def test_referencia_final_e_circular_e_isso_e_medido(obra):
    nome, P, r = obra
    for m in r["marcos"]:
        fin = m["por_referencia"]["final_independente"]
        assert fin["erro_dias"]["independente"][-1] == 0        # zero POR CONSTRUÇÃO na última data
    s = r["circularidade"]["sobreposicao_boletins"]
    assert all(b >= a for a, b in zip(s, s[1:])) and s[-1] == 1.0 and s[0] < 0.1
    dif = r["circularidade"]["diferenca_referencias_dias"]
    for m in r["marcos"]:
        refs = m["por_referencia"]
        assert dif[m["id"]] == ordinal(refs["final_independente"]["referencia"]) - \
            ordinal(refs["realidade_simulada"]["referencia"])
    assert dif["M-FIM"] != 0             # a referência circular NÃO é a verdade do mundo sintético


def test_realidade_simulada_disponivel_e_coerente(obra):
    nome, P, r = obra
    real, motivo = realidade_da_obra(P.dados)
    assert real is not None and "coerente" in motivo
    # adulterar uma data real concluída: a realidade deixa de corresponder ao dataset e fica indisponível
    d = copy.deepcopy(P.dados)
    a = next(x for x in d["atividades"] if x.get("tipo", "tarefa") == "tarefa" and x.get("termino_real"))
    a["termino_real"] = iso(ordinal(a["termino_real"]) - 1)
    real2, motivo2 = realidade_da_obra(d)
    assert real2 is None and "não corresponde" in motivo2
    d = copy.deepcopy(P.dados)
    d["meta"]["ficticio"] = "sim"
    assert realidade_da_obra(d)[0] is None


def test_sem_vazamento_previsao_em_d_nao_depende_do_futuro(obra):
    """Boletins cuja semana termina depois de d0 ×10: previsões até d0 idênticas (referência à parte)."""
    nome, P, r = obra
    ds = ordinal(P.dados["meta"]["data_status"])
    d0 = ds - 91
    x = copy.deepcopy(P.dados)
    ativ = {a["id"]: a for a in x["atividades"]}
    for m in x["medicoes"]:
        a = ativ[m["atividade_id"]]
        fim = min(ordinal(m["semana_inicio"]) + 7, ds)
        if a.get("termino_real"):
            fim = min(fim, ordinal(a["termino_real"]) + 1)
        if fim > d0:
            m["quantidade"] *= 10
    r2 = backtest(Projeto(x), 7)
    k = max(i for i, dd in enumerate(r["datas_de_status"]) if ordinal(dd) <= d0)
    # o dataset adulterado deixa de ser "o mundo do gerador" (boletins não fecham): a realidade fica indisponível
    # (r16) — compara-se a PREVISÃO (referência + erro), que não depende da referência
    assert "realidade_simulada" not in r2["marcos"][0]["por_referencia"]
    for m1, m2 in zip(r["marcos"], r2["marcos"]):
        a, b = m1["por_referencia"]["final_independente"], m2["por_referencia"]["final_independente"]
        for c in ("construtora", "independente", "es_pf1", "es_spi"):
            prev = lambda x: [None if e is None else ordinal(x["referencia"]) + e for e in x["erro_dias"][c]]  # noqa: E731
            assert prev(a)[: k + 1] == prev(b)[: k + 1], (m1["id"], c)
        assert m1["por_referencia"]["final_independente"]["erro_dias"]["independente"][-1] == 0


def test_faixas_de_fracao_concluida(obra):
    nome, P, r = obra
    av = r["avanco_fisico"]
    assert all(b >= a - 1e-9 for a, b in zip(av, av[1:]))
    for m in r["marcos"]:
        for ref in m["por_referencia"].values():
            for f in FAIXAS:
                x = ref["por_fracao_concluida"][f"{f}%"]
                k = next((i for i, v in enumerate(av) if v >= f), None)
                if k is None:
                    assert x is None
                else:
                    assert x["data_status"] == r["datas_de_status"][k]
                    assert (x["construtora"], x["independente"]) == (ref["erro_dias"]["construtora"][k],
                                                                     ref["erro_dias"]["independente"][k])
    assert r["marcos"][0]["por_referencia"]["realidade_simulada"]["por_fracao_concluida"]["70%"] is not None


def test_independente_melhor_desde_segue_a_definicao(obra):
    nome, P, r = obra
    datas = r["datas_de_status"]
    for m in r["marcos"]:
        for ref in m["por_referencia"].values():
            e_i, e_c = ref["erro_dias"]["independente"], ref["erro_dias"]["construtora"]
            desde = ref["independente_melhor_desde"]
            if desde is None:
                assert abs(e_i[-1]) > abs(e_c[-1])
                continue
            k = datas.index(desde)
            assert all(abs(e_i[i]) <= abs(e_c[i]) for i in range(k, len(datas)))
            assert k == 0 or abs(e_i[k - 1]) > abs(e_c[k - 1])


def test_narrativa_independente_mais_acurada_no_termino_da_obra(obra):
    nome, P, r = obra
    fim = _marco(r, "M-FIM")["por_referencia"]
    for ref in fim.values():                       # vale nas DUAS referências (não é efeito da circularidade)
        assert ref["mae_dias"]["independente"] < ref["mae_dias"]["construtora"]
        assert ref["independente_melhor_desde"] is not None


@pytest.mark.parametrize("passo", [0, 92, True])
def test_parametros_invalidos(passo):
    with pytest.raises(ErroBacktest):
        backtest(Projeto.carregar(OBRAS["rodovia"]), passo)


def test_rota():
    P = Projeto.carregar(OBRAS["rodovia"])
    c = TestClient(criar_app(fontes={"rodovia": P}))
    if "rotas_backtest" not in c.app.state.rotas_ligadas:        # registro na API é do orquestrador
        from infra4d.rotas_backtest import ligar
        ligar(c.app, c.app.state.obter_estado)
    r1 = c.get("/api/backtest", params={"obra": "rodovia", "passo_dias": 28}).json()
    r2 = c.get("/api/backtest", params={"obra": "rodovia", "passo_dias": 28}).json()
    assert r1["cache"] is False and r2["cache"] is True and r1["marcos"] == r2["marcos"] and r1["tempo_s"] > 0
    for params, codigo in (({"passo_dias": 0}, 422), ({"passo_dias": 92}, 422), ({"obra": "zz"}, 404)):
        assert c.get("/api/backtest", params={"obra": "rodovia", **params}).status_code == codigo


# ------------------------------------------------------------------ R12: Earned Schedule, MAPE, ±10 %, sementes
def test_metricas_a_mao():
    from infra4d.backtest import _metricas
    m = _metricas([10, -20, None, 0], [5, 40, 50, 90], 100)
    assert (m["n"], m["mape"], m["acerto_10pct"], m["vies_dias"], m["sem_previsao"]) == (3, 0.1, round(2 / 3, 4), -3.33, 1)
    assert m["por_fase"]["0-30%"] == {"n": 1, "mape": 0.1, "acerto_10pct": 1.0}
    assert m["por_fase"]["30-70%"] == {"n": 1, "mape": 0.2, "acerto_10pct": 0.0}
    assert m["por_fase"]["70-100%"] == {"n": 1, "mape": 0.0, "acerto_10pct": 1.0}


def test_es_no_backtest_e_o_do_previsao_es(obra):
    """Na última data (o dataset atual), o término ES é o de previsao_es.earned_schedule, por marco/lote."""
    from infra4d.cenarios import executar
    from infra4d.previsao_es import earned_schedule
    nome, P, r = obra
    lb, ind = executar(P, "linha_base"), executar(P, "independente")
    for m in r["marcos"]:
        ref = m["por_referencia"]["realidade_simulada"]
        es = earned_schedule(P, lb, ind, P.atividades[m["id"]].get("lote_id"))
        for k, campo in (("es_pf1", "IEAC_pf1_termino"), ("es_spi", "IEAC_spi_termino")):
            assert ref["erro_dias"][k][-1] == ordinal(es[campo]) - ordinal(ref["referencia"])


def test_mape_acerto_e_ganho_seguem_a_definicao(obra):
    nome, P, r = obra
    for m in r["marcos"]:
        ref = m["por_referencia"]["realidade_simulada"]
        dur = ordinal(ref["referencia"]) - ordinal(P.dados["meta"]["inicio_projeto"]) + 1
        assert ref["duracao_referencia_dias"] == dur
        for c, es in ref["erro_dias"].items():
            v = [e for e in es if e is not None]
            met = ref["metricas"][c]
            assert met["mape"] == pytest.approx(sum(abs(e) for e in v) / len(v) / dur, abs=1e-4)
            assert met["acerto_10pct"] == pytest.approx(sum(abs(e) <= 0.1 * dur for e in v) / len(v), abs=1e-4)
            assert sum(f["n"] for f in met["por_fase"].values()) == met["n"]
        for c, g in ref["ganho_independente_sobre"].items():
            assert g == pytest.approx(1 - ref["mae_dias"]["independente"] / ref["mae_dias"][c], abs=1e-4)


def test_varias_sementes_em_memoria_sem_tocar_nos_json():
    from infra4d.backtest import backtest_sementes
    import hashlib
    antes = {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in OBRAS.items()}
    r = backtest_sementes("rodovia", n=2, passo_dias=28)
    assert {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in OBRAS.items()} == antes
    assert len(r["por_semente"]) == 2 and r["sementes"][1] == r["sementes"][0] + 1
    # o 1º mundo é o publicado: mesmas métricas do backtest do JSON versionado
    pub = backtest(Projeto.carregar(OBRAS["rodovia"]), 28)
    ref = next(m for m in pub["marcos"] if m["id"] == "M-FIM")["por_referencia"]["realidade_simulada"]
    assert r["por_semente"][0]["mae_dias"] == ref["mae_dias"]
    assert r["por_semente"][0]["referencia"] != r["por_semente"][1]["referencia"] or \
        r["por_semente"][0]["mae_dias"] != r["por_semente"][1]["mae_dias"]       # mundos diferentes
    d = r["distribuicao"]["mae_dias"]["independente"]
    assert d["n"] == 2 and d["min"] <= d["mediana"] <= d["max"]
    with pytest.raises(ErroBacktest):
        backtest_sementes("canal", 2)
    with pytest.raises(ErroBacktest):
        backtest_sementes("rodovia", 0)


def test_rota_sementes():
    P = Projeto.carregar(OBRAS["ferrovia"])
    c = TestClient(criar_app(fontes={"ferrovia": P}))
    if "rotas_backtest" not in c.app.state.rotas_ligadas:
        from infra4d.rotas_backtest import ligar
        ligar(c.app, c.app.state.obter_estado)
    j = c.get("/api/backtest/sementes", params={"obra": "ferrovia", "n": 1, "passo_dias": 28})
    assert j.status_code == 200 and j.json()["n"] == 1 and j.json()["cache"] is False
    assert c.get("/api/backtest/sementes", params={"obra": "ferrovia", "n": 1, "passo_dias": 28}).json()["cache"] is True
    for params, codigo in (({"n": 0}, 422), ({"n": 31}, 422), ({"marco": "M-NADA", "n": 1, "passo_dias": 91}, 422),
                           ({"obra": "zz"}, 404)):
        assert c.get("/api/backtest/sementes", params={"obra": "ferrovia", **params}).status_code == codigo, params


# ------------------------------------------------------------------ r16
def test_realidade_exige_marcos_e_boletins_coerentes(obra):
    nome, P, r = obra
    d = copy.deepcopy(P.dados)
    d["medicoes"] = []                                   # sem boletins: não é o mundo do gerador
    real, motivo = realidade_da_obra(d)
    assert real is None and "boletins" in motivo
    d = copy.deepcopy(P.dados)
    d["atividades"].append({**next(a for a in d["atividades"] if a["id"] == "M-FIM"), "id": "M-EXTRA"})
    real, motivo = realidade_da_obra(d)
    assert real is None and "M-EXTRA" in motivo
    assert all("limitacoes" in r and any("chuva" in x for x in r["limitacoes"]) for _ in [0])


def test_backtest_sem_data_passada_devolve_vazio_declarado():
    P = Projeto.carregar(OBRAS["rodovia"])
    d = copy.deepcopy(P.dados)
    d["meta"]["data_status"] = d["meta"]["inicio_projeto"]
    r = backtest(Projeto(d), 7)
    assert r["datas_de_status"] == [] and r["marcos"] == [] and "nada a medir" in r["aviso"]


# ------------------------------------------------------------------ r18: sementes só na obra sintética + orçamento
def test_sementes_exige_a_obra_sintetica_e_respeita_o_orcamento():
    from infra4d.backtest import ORCAMENTO_MUNDOS_X_DATAS, passo_minimo, tipo_sintetico
    from infra4d.tendencia import datas_de_status
    P = Projeto.carregar(OBRAS["rodovia"])
    assert tipo_sintetico(P.dados) == "rodovia"
    d = copy.deepcopy(P.dados)
    d["meta"]["gerador"] = "outro.py"
    with pytest.raises(ErroBacktest, match="obras sintéticas"):
        tipo_sintetico(d)
    p = passo_minimo(P.dados, 30)
    assert 30 * len(datas_de_status(P.dados, p)) <= ORCAMENTO_MUNDOS_X_DATAS < 30 * len(datas_de_status(P.dados, p - 1))
    from infra4d.backtest import backtest_sementes
    with pytest.raises(ErroBacktest, match=f"use passo_dias >= {p}"):
        backtest_sementes("rodovia", 30, 1)
    c = TestClient(criar_app(fontes={"rodovia": P, "real": Projeto({**d, "meta": {**d["meta"], "ficticio": False}})}))
    if "rotas_backtest" not in c.app.state.rotas_ligadas:
        from infra4d.rotas_backtest import ligar
        ligar(c.app, c.app.state.obter_estado)
    r = c.get("/api/backtest/sementes", params={"obra": "rodovia", "n": 30, "passo_dias": 1})
    assert r.status_code == 422 and "passo_dias >=" in r.json()["detail"]
    assert c.get("/api/backtest/sementes", params={"obra": "real", "n": 1, "passo_dias": 91}).status_code == 422
