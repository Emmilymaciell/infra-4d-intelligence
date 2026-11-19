"""Tendência de marcos (MTA): fotografia sem dado futuro, série, inclinação, divergência e coerência com o painel."""

import copy
from datetime import timedelta, date

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.calendario import iso, ordinal
from infra4d.cenarios import DATASET_PADRAO, Projeto, executar
from infra4d.tendencia import ErroTendencia, _inclinacao, datas_de_status, fotografia, tendencia

OBRAS = {"ferrovia": DATASET_PADRAO, "rodovia": DATASET_PADRAO.parent / "rodovia_ficticia.json"}


@pytest.fixture(scope="module", params=list(OBRAS))
def obra(request):
    P = Projeto.carregar(OBRAS[request.param])
    return request.param, P, tendencia(P, 7)


# ------------------------------------------------------------------ à mão
def test_inclinacao_a_mao():
    assert _inclinacao([0, 7, 14], [100, 101, 102]) == pytest.approx(1.0)       # 1 dia por semana
    assert _inclinacao([0, 7, 14, 21], [50, 50, 50, 50]) == 0
    assert _inclinacao([0, 7], [10, 3]) == pytest.approx(-7.0)
    assert _inclinacao([5], [1]) is None


def test_datas_de_status_terminam_na_atual_e_andam_pelo_passo(obra):
    nome, P, r = obra
    ds = P.dados["meta"]["data_status"]
    assert r["datas_de_status"][-1] == ds
    ords = [ordinal(x) for x in r["datas_de_status"]]
    assert all(b - a == 7 for a, b in zip(ords, ords[1:]))
    assert ords[0] > ordinal(P.dados["meta"]["inicio_projeto"]) and ords[0] - 7 <= ordinal(P.dados["meta"]["inicio_projeto"])
    assert datas_de_status(P.dados, 28)[-1] == ordinal(ds)


# ------------------------------------------------------------------ fotografia: só o que se sabia em d
def test_fotografia_so_usa_o_que_se_sabia(obra):
    nome, P, r = obra
    d = ordinal(P.dados["meta"]["data_status"]) - 120
    f = fotografia(P.dados, d)
    assert f["meta"]["data_status"] == iso(d) and f is not P.dados
    ativ = {a["id"]: a for a in P.dados["atividades"]}
    soma = {}
    for m in f["medicoes"]:
        a = ativ[m["atividade_id"]]
        fim = min(ordinal(m["semana_inicio"]) + 7, ordinal(P.dados["meta"]["data_status"]))
        if a.get("termino_real"):
            fim = min(fim, ordinal(a["termino_real"]) + 1)
        assert fim <= d                                      # semana terminada até d
        soma[m["atividade_id"]] = soma.get(m["atividade_id"], 0.0) + m["quantidade"]
    for a in f["atividades"]:
        if a.get("inicio_real"):
            assert ordinal(a["inicio_real"]) < d
        if a.get("termino_real"):
            assert ordinal(a["termino_real"]) < d and a["status"] == "concluida"
        if a["status"] == "nao_iniciada":
            assert "inicio_real" not in a
        if a.get("quantidade_total") and a["status"] != "nao_iniciada":
            assert a["quantidade_executada"] == pytest.approx(soma.get(a["id"], 0.0), abs=0.01)
            if a["status"] == "concluida":
                assert a["quantidade_executada"] == pytest.approx(a["quantidade_total"], abs=0.01)
    assert len(f["medicoes"]) < len(P.dados["medicoes"])
    with pytest.raises(ErroTendencia):
        fotografia(P.dados, ordinal(P.dados["meta"]["data_status"]) + 1)


def _futuro_adulterado(dados, d):
    """Mesmo passado, futuro (depois de d) completamente diferente: boletins ×10, datas reais deslocadas."""
    x = copy.deepcopy(dados)
    ativ = {a["id"]: a for a in dados["atividades"]}
    ds = ordinal(dados["meta"]["data_status"])
    for m in x["medicoes"]:
        # período do boletim que ainda não tinha acabado em d (a última semana de uma atividade
        # concluída é curta: termina no dia seguinte ao término real)
        a = ativ[m["atividade_id"]]
        fim = min(ordinal(m["semana_inicio"]) + 7, ds)
        if a.get("termino_real"):
            fim = min(fim, ordinal(a["termino_real"]) + 1)
        if fim > d:
            m["quantidade"] *= 10
    for a in x["atividades"]:
        for k in ("inicio_real", "termino_real"):
            if a.get(k) and ordinal(a[k]) >= d:
                a[k] = iso(ordinal(a[k]) + 3)
        if a.get("quantidade_total") and a.get("status") == "em_andamento":
            a["quantidade_executada"] = a["quantidade_total"] * 0.5
    return x


def test_sem_vazamento_o_futuro_nao_muda_a_fotografia_nem_os_terminos(obra):
    """Teste explícito de não vazamento: adulterar TUDO que é posterior a d não muda nada em d."""
    nome, P, r = obra
    d = ordinal(P.dados["meta"]["data_status"]) - 91
    orig, adult = fotografia(P.dados, d), fotografia(_futuro_adulterado(P.dados, d), d)
    assert [m for m in orig["medicoes"]] == [m for m in adult["medicoes"]]
    for a, b in zip(orig["atividades"], adult["atividades"]):
        assert {k: a.get(k) for k in ("status", "inicio_real", "termino_real", "quantidade_executada")} == \
            {k: b.get(k) for k in ("status", "inicio_real", "termino_real", "quantidade_executada")}, a["id"]
    for c in ("construtora", "independente"):
        assert executar(Projeto(orig), c)["termino"] == executar(Projeto(adult), c)["termino"]


# ------------------------------------------------------------------ série
def test_ultima_data_bate_com_o_painel_atual(obra):
    nome, P, r = obra
    c = TestClient(criar_app(fontes={nome: P}))
    painel = {m["id"]: m for m in c.get("/api/painel", params={"obra": nome}).json()["marcos_contratuais"]}
    assert {m["id"] for m in r["marcos"]} == set(painel)
    for m in r["marcos"]:
        ult = m["serie"][-1]
        assert ult["termino_construtora"] == painel[m["id"]]["construtora"]
        assert ult["termino_independente"] == painel[m["id"]]["independente"]


def test_inclinacao_e_divergencia_seguem_a_serie(obra):
    nome, P, r = obra
    lim = r["limiar_divergencia_dias"]
    for m in r["marcos"]:
        s = m["serie"]
        assert len(s) == len(r["datas_de_status"])
        xs = [ordinal(p["data_status"]) for p in s]
        for c in ("construtora", "independente"):
            esperado = _inclinacao(xs, [ordinal(p[f"termino_{c}"]) for p in s])
            assert m["inclinacao_dias_por_semana"][c] == pytest.approx(esperado, abs=1e-3)
        difs = [ordinal(p["termino_independente"]) - ordinal(p["termino_construtora"]) for p in s]
        k = next((i for i, x in enumerate(difs) if x > lim), None)
        assert m["divergencia_desde"] == (None if k is None else s[k]["data_status"])
    sem = tendencia(P, 28, limiar_divergencia_dias=100000)
    assert all(m["divergencia_desde"] is None for m in sem["marcos"])


def test_narrativa_a_independente_desliza_mais_no_marco_final(obra):
    nome, P, r = obra
    fim = next(m for m in r["marcos"] if m["id"] == "M-FIM")
    assert fim["inclinacao_dias_por_semana"]["independente"] > fim["inclinacao_dias_por_semana"]["construtora"] > 0
    assert fim["divergencia_desde"] is not None


@pytest.mark.parametrize("passo, lim", [(0, 15), (92, 15), (True, 15), (7, -1)])
def test_parametros_invalidos(passo, lim):
    with pytest.raises(ErroTendencia):
        tendencia(Projeto.carregar(OBRAS["rodovia"]), passo, lim)


# ------------------------------------------------------------------ rota
def test_rota_com_cache_tempo_e_erros():
    P = Projeto.carregar(OBRAS["rodovia"])
    c = TestClient(criar_app(fontes={"rodovia": P}))
    if "rotas_tendencia" not in c.app.state.rotas_ligadas:      # registro na API é do orquestrador
        from infra4d.rotas_tendencia import ligar
        ligar(c.app, c.app.state.obter_estado)
    r1 = c.get("/api/tendencia", params={"obra": "rodovia", "passo_dias": 28}).json()
    r2 = c.get("/api/tendencia", params={"obra": "rodovia", "passo_dias": 28}).json()
    assert r1["cache"] is False and r2["cache"] is True and r1["marcos"] == r2["marcos"] and r1["tempo_s"] > 0
    for params, codigo in (({"passo_dias": 0}, 422), ({"passo_dias": 92}, 422), ({"limiar_dias": -1}, 422),
                           ({"obra": "zz"}, 404)):
        assert c.get("/api/tendencia", params={"obra": "rodovia", **params}).status_code == codigo, params


# ------------------------------------------------------------------ R12: restrições sem dado futuro
def test_restricao_liberada_depois_de_d_nao_vaza(obra):
    """Em d, uma restrição que só libera depois de d está PENDENTE com a data PREVISTA; a data real de liberação
    (futura) não pode influir: adulterá-la não muda a fotografia nem os términos em d."""
    nome, P, r = obra
    datas = sorted(ordinal(x["data_liberacao"]) for x in P.dados["restricoes"])
    d = datas[1] - 10                                     # antes da 2ª liberação
    pend = [x["id"] for x in P.dados["restricoes"] if ordinal(x["data_liberacao"]) > d]
    assert pend
    f = fotografia(P.dados, d)
    for x in f["restricoes"]:
        if x["id"] in pend:
            assert x["situacao"] == "pendente" and ordinal(x["data_liberacao"]) >= d
    x = copy.deepcopy(P.dados)                            # o futuro muda: liberação real 30 dias depois
    for rr in x["restricoes"]:
        if rr["id"] in pend:
            rr["data_liberacao"] = iso(ordinal(rr["data_liberacao"]) + 30)
            a = next(a for a in x["atividades"] if a["id"] == rr["atividade_id"])
            a["restricao_inicio"] = rr["data_liberacao"]
    g = fotografia(x, d)
    assert [(y["id"], y["situacao"], y["data_liberacao"]) for y in g["restricoes"]] == \
        [(y["id"], y["situacao"], y["data_liberacao"]) for y in f["restricoes"]]
    assert [a.get("restricao_inicio") for a in g["atividades"]] == [a.get("restricao_inicio") for a in f["atividades"]]
    for c in ("construtora", "independente"):
        assert executar(Projeto(f), c)["termino"] == executar(Projeto(g), c)["termino"]


def test_restricao_ja_liberada_em_d_usa_a_data_real(obra):
    nome, P, r = obra
    x = max(P.dados["restricoes"], key=lambda y: y["data_liberacao"] if y["situacao"] == "liberada" else "")
    d = ordinal(x["data_liberacao"]) + 3
    f = fotografia(P.dados, d)
    y = next(y for y in f["restricoes"] if y["id"] == x["id"])
    assert y["situacao"] == "liberada" and y["data_liberacao"] == x["data_liberacao"]
