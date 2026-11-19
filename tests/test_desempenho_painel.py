"""Otimização do painel: equivalência EXATA com o cálculo anterior e limite de tempo do /api/painel.

A otimização (``cenarios.preparar_progresso`` + ``progresso_preparado`` e a curva S com pesos e datas
pré-calculados) não pode mudar nenhum número. O oráculo abaixo é uma cópia CONGELADA de ``progresso_em``
e da curva S de antes da otimização; a comparação é por igualdade (==), não por tolerância.
"""

import time
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient

from infra4d import painel
from infra4d.api import criar_app
from infra4d.calendario import iso, ordinal
from infra4d.cenarios import CENARIOS, DATASET_PADRAO, Ajuste, Projeto, executar, progresso_em

OBRAS = {"ferrovia": DATASET_PADRAO, "rodovia": DATASET_PADRAO.parent / "rodovia_ficticia.json"}


def _oraculo_progresso(projeto, a, r, t, data_status):
    """Cópia congelada de cenarios.progresso_em ANTES da otimização (2026-11-12)."""
    cal = projeto.calendarios[a["calendario"]]
    tipo = a.get("tipo", "tarefa")
    if tipo != "tarefa":
        return 1.0 if t > ordinal(r["termino"]) or (t >= ordinal(r["inicio"]) and tipo == "marco_inicio") else 0.0
    ds = data_status
    total = a.get("quantidade_total")
    exec_ds = (a.get("quantidade_executada", 0) / total) if total else a.get("percentual_executado", 0) / 100
    if r["status"] == "concluida":
        exec_ds = 1.0
    es, ef = ordinal(r["es"]), ordinal(r["ef"])
    if ds is not None and t <= ds and r["status"] != "nao_iniciada":
        ini = ordinal(a["inicio_real"])
        fim = ordinal(a["termino_real"]) + 1 if r["status"] == "concluida" else ds
        if t <= ini:
            return 0.0
        if t >= fim:
            return exec_ds
        return exec_ds * cal.dias_uteis_entre(ini, t) / max(1, cal.dias_uteis_entre(ini, fim))
    if ds is not None and t <= ds:
        return 0.0
    if r["status"] == "nao_iniciada" or ds is None:
        if t <= es:
            return 0.0
        if t >= ef:
            return 1.0
        return cal.dias_uteis_entre(es, t) / max(1, cal.dias_uteis_entre(es, ef))
    if t >= ef:
        return 1.0
    ini_rem = max(ds, es)
    return exec_ds + (1 - exec_ds) * cal.dias_uteis_entre(ini_rem, t) / max(1, cal.dias_uteis_entre(ini_rem, ef))


def _oraculo_avanco(projeto, resultado, t, lote=None):
    num = den = 0.0
    ds = ordinal(resultado["data_status"]) if resultado.get("data_status") else None
    for a in projeto.dados["atividades"]:
        if lote and a.get("lote_id") != lote:
            continue
        w = painel.peso(a)
        if w:
            num += w * _oraculo_progresso(projeto, a, resultado["atividades"][a["id"]], t, ds)
            den += w
    return num / den if den else 0.0


def _oraculo_curva_s(projeto, resultados, lote=None, passo_dias=14):
    ini = projeto.inicio_projeto
    fim = max(ordinal(r["termino"]) for r in resultados.values()) + passo_dias
    datas, series = [], defaultdict(list)
    t = ini
    while t <= fim:
        datas.append(iso(t))
        for nome, r in resultados.items():
            series[nome].append(round(100 * _oraculo_avanco(projeto, r, t, lote), 2))
        t += passo_dias
    return {"datas": datas, "series": dict(series)}


@pytest.fixture(scope="module", params=list(OBRAS))
def obra(request):
    P = Projeto.carregar(OBRAS[request.param])
    res = {c: executar(P, c) for c in CENARIOS}
    # cenário simulado não trivial, para cobrir também a previsão com ajuste
    alvo = next(a for a in P.dados["atividades"] if a.get("status") == "em_andamento" and a.get("quantidade_total"))
    res["simulado"] = executar(P, "simulado", [Ajuste(produtividade=alvo["produtividade_planejada"] * 0.7,
                                                      atividade_id=alvo["id"])])
    return P, res


def test_progresso_identico_ao_oraculo_em_todas_as_datas(obra):
    P, res = obra
    t0, t1 = P.inicio_projeto - 10, max(ordinal(r["termino"]) for r in res.values()) + 20
    n = 0
    for nome, r in res.items():
        ds = ordinal(r["data_status"]) if r.get("data_status") else None
        for a in P.dados["atividades"]:
            ra = r["atividades"][a["id"]]
            for t in range(t0, t1, 3):
                assert progresso_em(P, a, ra, t, ds) == _oraculo_progresso(P, a, ra, t, ds), (nome, a["id"], t)
                n += 1
    assert n > 100_000


@pytest.mark.parametrize("lote", [None, "L1", "L3"])
def test_curva_s_e_avanco_identicos_ao_oraculo(obra, lote):
    P, res = obra
    assert painel.curva_s(P, res, lote) == _oraculo_curva_s(P, res, lote)
    for r in res.values():
        for t in (P.inicio_projeto, P.data_status, P.data_status + 1, ordinal(r["termino"])):
            assert painel.avanco(P, r, t, lote) == _oraculo_avanco(P, r, t, lote)


@pytest.mark.parametrize("arquivo", list(OBRAS.values()), ids=list(OBRAS))
def test_painel_frio_dentro_do_limite_do_manifesto(limite, arquivo):
    """1ª chamada num app novo (calcula os cinco cenários, inclusive a lógica retida, e todo o painel)."""
    c = TestClient(criar_app(fontes={"x": Projeto.carregar(arquivo)}))
    t = time.perf_counter()
    r = c.get("/api/painel", params={"obra": "x"})
    dt = time.perf_counter() - t
    assert r.status_code == 200
    assert dt <= limite("tempo_maximo_painel_s"), f"/api/painel frio levou {dt:.3f} s"
