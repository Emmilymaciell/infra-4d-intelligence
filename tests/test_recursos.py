"""Recursos: histograma, sobrealocação, nivelamento (SGS serial) e conflitos de linha de balanço.

Os números esperados das redes pequenas foram calculados À MÃO (comentados em cada teste).
Calendários: 2026-01-05 é segunda-feira; 2026-01-01 é quinta-feira.
"""

from __future__ import annotations

from collections import defaultdict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infra4d import recursos as R
from infra4d import rotas_recursos
from infra4d.calendario import iso, ordinal
from infra4d.cenarios import Projeto, executar
from infra4d.motor import AtividadeCPM, Relacao, calcular

SEG_SEX = [0, 1, 2, 3, 4]
SEG_SAB = [0, 1, 2, 3, 4, 5]
TODOS = [0, 1, 2, 3, 4, 5, 6]


def _ativ(aid, serv, dur, lote="L1", eq=1, seg="S1", km=None, **extra):
    a = {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": lote, "segmento_id": seg, "servico_id": serv,
         "duracao_fixa": dur, "equipes": eq, "calendario": "C", "status": "nao_iniciada"}
    if km:
        a["km_ini"], a["km_fim"] = km
    a.update(extra)
    return a


def _projeto(atividades, relacoes=(), dias=SEG_SEX, nao_uteis=(), inicio="2026-01-05", status="2026-01-05"):
    return Projeto({
        "meta": {"inicio_projeto": inicio, "data_status": status, "calendario_obra": "C"},
        "lotes": [{"id": "L1"}, {"id": "L2"}],
        "calendarios": [{"id": "C", "nome": "C", "dias_semana": list(dias), "nao_uteis": list(nao_uteis)}],
        "servicos": [{"id": "TER", "equipamentos": ["Escavadeira", "2 caminhões"]},
                     {"id": "SUB", "equipamentos": ["Rolo"]}],
        "atividades": list(atividades),
        "relacoes": [{"predecessora": p, "sucessora": s, "tipo": t, "lag": l} for p, s, t, l in relacoes],
    })


def _d(texto):
    return ordinal(texto)


def _uso_bruto(projeto, resultado):
    """Contagem INDEPENDENTE do módulo: varre dia a dia [ES, EF) de cada atividade."""
    uso = defaultdict(lambda: defaultdict(int))
    ds = ordinal(resultado["data_status"]) if resultado.get("data_status") else None
    for aid, r in resultado["atividades"].items():
        a = projeto.atividades[aid]
        if a.get("tipo", "tarefa") != "tarefa" or not a.get("servico_id") or r["status"] == "concluida":
            continue
        cal = projeto.calendarios[a["calendario"]]
        ini = _d(r["es"]) if r["status"] == "nao_iniciada" else max(_d(r["es"]), ds)
        q = (r["memoria"].get("equipes") or a.get("equipes") or 1)
        d = ini
        while d < _d(r["ef"]):
            if cal.eh_util(d):
                uso[f"{a.get('lote_id')}/{a['servico_id']}"][d] += q
            d += 1
    return uso


# =========================================================================== rede 1 (seg–sex)
# A1, A2: TER, 3 dias, 1 equipe, sem relação entre si. B: SUB, 2 dias, FS de A2.
# CPM: A1 = A2 = seg 05..qua 07 (EF 08); B = qui 08..sex 09 (EF sáb 10); término 09/01.
# Folga total: A2 = 0 (determina B); A1 = dias úteis em [08, 10) = 2.
def _rede1():
    return _projeto([_ativ("A1", "TER", 3), _ativ("A2", "TER", 3), _ativ("B", "SUB", 2)],
                    [("A2", "B", "FS", 0)])


def test_histograma_diario_contagem_exata_em_dias_uteis():
    P = _rede1()
    r = executar(P, "linha_base")
    h = R.histograma(P, r, agrupar="dia")
    ser = {s["recurso"]: s for s in h["series"]}
    assert [(p["periodo"], p["equipes"]) for p in ser["L1/TER"]["periodos"]] == [
        ("2026-01-05", 2), ("2026-01-06", 2), ("2026-01-07", 2)]
    assert [(p["periodo"], p["equipes"]) for p in ser["L1/SUB"]["periodos"]] == [
        ("2026-01-08", 1), ("2026-01-09", 1)]
    assert [(p["periodo"], p["equipes"]) for p in h["total"]["periodos"]] == [
        ("2026-01-05", 2), ("2026-01-06", 2), ("2026-01-07", 2), ("2026-01-08", 1), ("2026-01-09", 1)]
    eq = {e["tipo"]: e for e in h["equipamentos"]}
    # TER: 1 escavadeira + 2 caminhões por equipe; 2 equipes => 2 e 4
    assert eq["Escavadeira"]["pico"] == 2 and eq["caminhões"]["pico"] == 4
    assert [p["quantidade"] for p in eq["caminhões"]["periodos"]] == [4, 4, 4]
    assert eq["Rolo"]["pico"] == 1 and len(eq["Rolo"]["periodos"]) == 2
    assert ser["L1/TER"]["capacidade"] == 1 and ser["L1/TER"]["dias_sobrealocados"] == 3


def test_histograma_semanal_pico_e_soma():
    P = _rede1()
    h = R.histograma(P, executar(P, "linha_base"), agrupar="semana")
    ter = next(s for s in h["series"] if s["recurso"] == "L1/TER")
    assert ter["periodos"] == [{"periodo": "2026-01-05", "equipes": 2, "equipes_dia": 6}]
    assert h["total"]["periodos"] == [{"periodo": "2026-01-05", "equipes": 2, "equipes_dia": 8}]


def test_sobrealocacao_lista_dias_e_atividades():
    P = _rede1()
    s = R.sobrealocacao(P, executar(P, "linha_base"))
    ter = next(x for x in s["recursos"] if x["recurso"] == "L1/TER")
    assert ter["pico"] == 2 and ter["capacidade"] == 1 and ter["data_pico"] == "2026-01-05"
    assert [d["data"] for d in ter["sobrealocacao"]] == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert ter["sobrealocacao"][0]["atividades"] == ["A1", "A2"]
    assert s["total_dias_sobrealocados"] == 3


def test_nivelamento_empurra_a_de_maior_folga_e_mantem_relacoes():
    # Prioridade = menor folga: A2 (0) antes de A1 (2), apesar do id. A2 fica em 05..07;
    # A1 vai para o 1º dia com capacidade: qui 08, sex 09, seg 12 => término 12/01.
    P = _rede1()
    r = executar(P, "linha_base")
    n = R.nivelar(P, r)
    assert n["termino_cpm"] == "2026-01-09"
    assert n["termino_nivelado"] == "2026-01-12"
    assert n["delta_dias_corridos"] == 3
    assert n["delta_dias_uteis_obra"] == 1
    assert [(a["id"], a["es_cpm"], a["es_nivelado"], a["atraso_dias_uteis"], a["atraso_dias_corridos"], a["motivo"])
            for a in n["atividades_atrasadas"]] == [("A1", "2026-01-05", "2026-01-08", 3, 3, "recurso")]
    assert n["atividades_atrasadas"][0]["termino_nivelado"] == "2026-01-12"
    assert n["prova_capacidade"]["ok"] and n["prova_capacidade"]["picos"]["L1/TER"] == {"pico": 1, "capacidade": 1}
    assert n["prova_relacoes"] == {"ok": True, "relacoes_verificadas": 1, "relacoes_ignoradas_progresso": 0,
                                   "violacoes": []}
    assert n["prova_snet"]["ok"]
    # contagem independente do módulo sobre o resultado nivelado
    uso = _uso_bruto(P, n["_resultado"])
    assert dict(uso["L1/TER"]) == {_d(x): 1 for x in ("2026-01-05", "2026-01-06", "2026-01-07",
                                                       "2026-01-08", "2026-01-09", "2026-01-12")}
    # histograma do nivelado, semanal: semana 05 => 5 equipe·dia; semana 12 => 1
    h = R.histograma(P, n["_resultado"], agrupar="semana")
    ter = next(s for s in h["series"] if s["recurso"] == "L1/TER")
    assert [(p["periodo"], p["equipes"], p["equipes_dia"]) for p in ter["periodos"]] == [
        ("2026-01-05", 1, 5), ("2026-01-12", 1, 1)]
    nb = n["_resultado"]["atividades"]["B"]
    assert (nb["inicio"], nb["termino"]) == ("2026-01-08", "2026-01-09")  # B não muda


def test_sem_sobrealocacao_nivelamento_nao_muda_nada():
    P = _rede1()
    r = executar(P, "linha_base")
    n = R.nivelar(P, r, {"L1/TER": 2})
    assert n["atividades_atrasadas"] == [] and n["termino_nivelado"] == n["termino_cpm"] == r["termino"]
    assert n["prova_capacidade"]["ok"] and n["prova_capacidade"]["picos"]["L1/TER"] == {"pico": 2, "capacidade": 2}
    for aid, x in r["atividades"].items():
        assert (n["_resultado"]["atividades"][aid]["es"], n["_resultado"]["atividades"][aid]["ef"]) == (x["es"], x["ef"])


def test_capacidade_aceita_tupla_e_texto():
    P = _rede1()
    r = executar(P, "linha_base")
    assert R.nivelar(P, r, {("L1", "TER"): 2})["atividades_atrasadas"] == []
    with pytest.raises(ValueError):
        R.nivelar(P, r, {"L1/TER": -1})


# =========================================================================== calendário 6 dias
def test_calendario_seis_dias_com_feriado():
    # seg–sáb, feriado seg 12/01. A1, A2: 4 dias, folga 0 as duas => desempate ES, depois id: A1 primeiro.
    # A1 = seg 05..qui 08. A2 = sex 09, sáb 10, (dom 11 não útil, seg 12 feriado), ter 13, qua 14.
    P = _projeto([_ativ("A1", "TER", 4), _ativ("A2", "TER", 4)], dias=SEG_SAB, nao_uteis=["2026-01-12"])
    r = executar(P, "linha_base")
    assert r["termino"] == "2026-01-08"
    s = R.sobrealocacao(P, r)
    assert [d["data"] for d in s["recursos"][0]["sobrealocacao"]] == [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    n = R.nivelar(P, r)
    assert n["termino_nivelado"] == "2026-01-14"
    a2 = n["atividades_atrasadas"]
    assert [(a["id"], a["es_nivelado"], a["atraso_dias_uteis"], a["atraso_dias_corridos"]) for a in a2] == [
        ("A2", "2026-01-09", 4, 4)]
    h = R.histograma(P, n["_resultado"], agrupar="dia")
    dias = [p["periodo"] for p in h["series"][0]["periodos"]]
    assert dias == ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-10",
                    "2026-01-13", "2026-01-14"]  # sábado conta; domingo e feriado não
    assert n["prova_capacidade"]["ok"] and n["prova_relacoes"]["ok"]


# =========================================================================== em andamento
def test_em_andamento_consome_a_partir_da_data_de_status_e_nao_e_movida():
    # status qua 14/01. A em andamento desde 05/01, 10 dias fixos, 50% => 5 remanescentes:
    # qua 14, qui 15, sex 16, seg 19, ter 20 (EF 21). B não iniciada, 2 dias, mesmo recurso, ES = 14.
    # Histograma: 14 e 15 => 2; 16, 19, 20 => 1; nada antes de 14.
    # Nivelamento (cap 1): A fica; B vai para qua 21, qui 22.
    P = _projeto([_ativ("A", "TER", 10, status="em_andamento", inicio_real="2026-01-05", percentual_executado=50),
                  _ativ("B", "TER", 2)], status="2026-01-14")
    r = executar(P, "construtora")
    h = R.histograma(P, r, agrupar="dia")
    assert [(p["periodo"], p["equipes"]) for p in h["series"][0]["periodos"]] == [
        ("2026-01-14", 2), ("2026-01-15", 2), ("2026-01-16", 1), ("2026-01-19", 1), ("2026-01-20", 1)]
    n = R.nivelar(P, r)
    assert [(a["id"], a["es_nivelado"]) for a in n["atividades_atrasadas"]] == [("B", "2026-01-21")]
    assert n["termino_nivelado"] == "2026-01-22"
    assert n["_resultado"]["atividades"]["A"]["ef"] == r["atividades"]["A"]["ef"]
    assert n["prova_capacidade"]["ok"]


def test_em_andamento_acima_da_capacidade_e_irredutivel():
    P = _projeto([_ativ("A", "TER", 10, status="em_andamento", inicio_real="2026-01-05", percentual_executado=50),
                  _ativ("C", "TER", 10, status="em_andamento", inicio_real="2026-01-06", percentual_executado=50)],
                 status="2026-01-14")
    n = R.nivelar(P, executar(P, "construtora"))
    pc = n["prova_capacidade"]
    assert pc["ok"] and pc["violacoes"] == [] and len(pc["sobrecarga_irredutivel"]) == 5
    assert n["atividades_atrasadas"] == []


def test_pool_de_servico_entre_lotes():
    # A em L1, B em L2, mesmo serviço; frota única "*/TER" = 1 => B depois de A.
    P = _projeto([_ativ("A", "TER", 3, lote="L1"), _ativ("B", "TER", 3, lote="L2")])
    r = executar(P, "linha_base")
    assert R.nivelar(P, r)["atividades_atrasadas"] == []  # por lote: sem conflito
    n = R.nivelar(P, r, {"*/TER": 1})
    assert [(a["id"], a["es_nivelado"]) for a in n["atividades_atrasadas"]] == [("B", "2026-01-08")]
    assert n["prova_capacidade"]["picos"]["*/TER"] == {"pico": 1, "capacidade": 1}


def test_nivelamento_respeita_ss_ff_com_lag():
    # X (TER, 5) --SS+2--> Y (SUB, 3) e X --FF+1--> Y; Z (SUB, 4) sem relação, folga maior.
    # Cap SUB = 1. Deve terminar com relações satisfeitas e pico <= 1.
    P = _projeto([_ativ("X", "TER", 5), _ativ("Y", "SUB", 3), _ativ("Z", "SUB", 4)],
                 [("X", "Y", "SS", 2), ("X", "Y", "FF", 1)])
    r = executar(P, "linha_base")
    n = R.nivelar(P, r)
    assert n["prova_relacoes"]["ok"] and n["prova_relacoes"]["relacoes_verificadas"] == 2
    assert n["prova_capacidade"]["ok"]
    assert max(_uso_bruto(P, n["_resultado"])["L1/SUB"].values()) == 1
    y = n["_resultado"]["atividades"]["Y"]
    # Y: SS+2 => ES >= qua 07; FF+1 de X (EF sáb 10 → +1 útil = seg 12) => termina >= seg 12
    assert _d(y["ef"]) >= _d("2026-01-13") and _d(y["es"]) >= _d("2026-01-07")


def test_verificador_de_relacoes_detecta_violacao():
    """O detector precisa ser visto falhando: rede calculada com FS+0, conferida contra FS+2."""
    cals = _rede1().calendarios
    ativs = [AtividadeCPM("P", 3, "C"), AtividadeCPM("S", 2, "C")]
    res = calcular(ativs, [Relacao("P", "S", "FS", 0)], cals, _d("2026-01-05"))
    assert R.verificar_relacoes(ativs, [Relacao("P", "S", "FS", 0)], cals, res)["ok"]
    v = R.verificar_relacoes(ativs, [Relacao("P", "S", "FS", 2)], cals, res)
    assert not v["ok"] and v["violacoes"][0]["minimo"] == "2026-01-12" and v["violacoes"][0]["obtido"] == "2026-01-08"
    v = R.verificar_relacoes(ativs, [Relacao("P", "S", "FF", 3)], cals, res)
    assert not v["ok"] and v["violacoes"][0]["campo"] == "EF"


# =========================================================================== linha de balanço
# Calendário corrido (7 dias), início qui 01/01. A: TER km 0→10 em 10 dias (ES 01, EF 11) => 1 km/dia.
def _rede_balanco(dur_b):
    return _projeto([_ativ("A", "TER", 10, km=(0.0, 10.0)), _ativ("B", "SUB", dur_b, km=(0.0, 10.0))],
                    [("A", "B", "SS", 2)], dias=TODOS, inicio="2026-01-01", status="2026-01-01")


def test_balanco_distancia_constante():
    # B: SS+2, 10 dias (ES 03, EF 13), 1 km/dia => distância 2 km e folga 2 dias em [03, 11): 8 dias.
    P = _rede_balanco(10)
    r = executar(P, "linha_base")
    c = R.conflitos_balanco(P, r, buffer_km=3)
    assert c["pares"] == [["TER", "SUB"]]
    assert c["n_conflitos"] == 1
    e = c["conflitos"][0]
    assert (e["lote"], e["segmento"], e["servicos"], e["data"], e["data_fim"], e["dias"]) == (
        "L1", "S1", ["TER", "SUB"], "2026-01-03", "2026-01-10", 8)
    assert e["distancia_km_min"] == pytest.approx(2.0) and e["folga_dias_min"] == pytest.approx(2.0)
    assert e["espacial"] and not e["temporal"] and not e["ultrapassagem"]
    assert R.conflitos_balanco(P, r, buffer_km=1)["n_conflitos"] == 0
    assert R.conflitos_balanco(P, r, buffer_km=2)["n_conflitos"] == 0  # exatamente no buffer: não alerta
    t = R.conflitos_balanco(P, r, buffer_km=0, buffer_dias=3)
    assert t["n_conflitos"] == 1 and t["conflitos"][0]["temporal"] and not t["conflitos"][0]["espacial"]
    assert R.conflitos_balanco(P, r, buffer_km=0, buffer_dias=2)["n_conflitos"] == 0  # 2 < 2 é falso


def test_balanco_ultrapassagem():
    # B: 5 dias (ES 03, EF 08), 2 km/dia. Distância A−B por dia: 03→2, 04→1, 05→0, 06→−1, 07→−2.
    # buffer 0,5 km: alerta 05..07 (3 dias), pior em 07 com B no km 8 e A no km 6.
    # Folga no pior dia: A passou no km 8 em 09/01 => 07 − 09 = −2 dias.
    P = _rede_balanco(5)
    c = R.conflitos_balanco(P, executar(P, "linha_base"), buffer_km=0.5)
    assert c["n_conflitos"] == 1
    e = c["conflitos"][0]
    assert (e["data"], e["data_fim"], e["dias"], e["data_pior"]) == ("2026-01-05", "2026-01-07", 3, "2026-01-07")
    assert (e["km"], e["km_antecessora"], e["distancia_km_min"]) == (8.0, 6.0, -2.0)
    assert e["ultrapassagem"] and e["folga_dias_min"] == pytest.approx(-2.0)


def test_balanco_ignora_segmentos_diferentes_e_respeita_data_de_status():
    P = _projeto([_ativ("A", "TER", 10, km=(0.0, 10.0)), _ativ("B", "SUB", 10, km=(0.0, 10.0), seg="S2"),
                  _ativ("A2", "TER", 10, km=(0.0, 10.0), seg="S2")],
                 [("A", "B", "SS", 2), ("A2", "B", "SS", 2)], dias=TODOS, inicio="2026-01-01", status="2026-01-01")
    c = R.conflitos_balanco(P, executar(P, "linha_base"), buffer_km=3)
    assert [x["atividades"] for x in c["conflitos"]] == [["A2", "B"]]  # A (S1) não é par de B (S2)
    with pytest.raises(ValueError):
        R.conflitos_balanco(P, executar(P, "linha_base"), buffer_km=-1)
    # data de status 08/01 (construtora): só amostra de 08 a 10 => 3 dias
    P2 = _projeto([_ativ("A", "TER", 10, km=(0.0, 10.0)), _ativ("B", "SUB", 10, km=(0.0, 10.0))],
                  [("A", "B", "SS", 2)], dias=TODOS, inicio="2026-01-08", status="2026-01-08")
    c2 = R.conflitos_balanco(P2, executar(P2, "construtora"), buffer_km=3)
    assert c2["conflitos"][0]["data"] == "2026-01-10"  # ES de B = 08 + 2


# =========================================================================== dataset real (fumaça)
@pytest.fixture(scope="module")
def real():
    P = Projeto.carregar()
    return P, {c: executar(P, c) for c in ("linha_base", "independente")}


def test_dataset_real_histograma_bate_com_contagem_independente(real):
    P, res = real
    r = res["independente"]
    h = R.histograma(P, r, agrupar="dia")
    bruto = _uso_bruto(P, r)
    for s in h["series"]:
        assert {_d(p["periodo"]): p["equipes"] for p in s["periodos"]} == dict(bruto[s["recurso"]])
    tot = defaultdict(int)
    for serie in bruto.values():
        for d, v in serie.items():
            tot[d] += v
    assert h["total"]["pico"] == max(tot.values())
    assert all(_d(p["periodo"]) >= P.data_status for p in h["total"]["periodos"])
    hs = R.histograma(P, r, agrupar="semana")
    assert sum(p["equipes_dia"] for p in hs["total"]["periodos"]) == sum(tot.values())
    assert R.histograma(P, r, lote="L2")["series"] and all(s["lote"] == "L2" for s in R.histograma(P, r, lote="L2")["series"])


def test_dataset_real_nivelamento_consistente(real):
    P, res = real
    for cen, caps in (("independente", None), ("independente", {"*/SUB": 1}), ("linha_base", {"*/TER": 2})):
        r = res[cen]
        n = R.nivelar(P, r, caps)
        assert n["termino_cpm"] == r["termino"]
        assert n["termino_nivelado"] >= n["termino_cpm"]
        assert n["prova_capacidade"]["ok"], n["prova_capacidade"]["violacoes"][:3]
        assert n["prova_relacoes"]["ok"], n["prova_relacoes"]["violacoes"][:3]
        assert n["prova_snet"]["ok"]
        for a in n["atividades_atrasadas"]:
            assert a["atraso_dias_corridos"] > 0
        # concluídas e em andamento nunca se movem
        for aid, x in r["atividades"].items():
            if x["status"] != "nao_iniciada":
                assert n["_resultado"]["atividades"][aid]["es"] == x["es"]
                assert n["_resultado"]["atividades"][aid]["ef"] == x["ef"]
    # pool de TER na linha de base precisa atrasar o término (há sobrecarga de verdade)
    n = R.nivelar(P, res["linha_base"], {"*/TER": 2})
    assert n["n_atrasadas_por_recurso"] > 0 and n["termino_nivelado"] > n["termino_cpm"]


def test_dataset_real_conflitos_de_balanco(real):
    P, res = real
    c = R.conflitos_balanco(P, res["independente"], buffer_km=1.0)
    assert ["TER", "SUB"] in c["pares"] and ["GRA", "LAS"] in c["pares"]
    ds = P.data_status
    for e in c["conflitos"]:
        assert _d(e["data"]) >= ds and e["dias"] >= 1
        assert e["distancia_km_min"] < 1.0 or e["temporal"]
        a, b = (P.atividades[x] for x in e["atividades"])
        assert a["segmento_id"] == b["segmento_id"] and a["lote_id"] == b["lote_id"] == e["lote"]
    assert R.conflitos_balanco(P, res["independente"], buffer_km=0)["n_conflitos"] <= c["n_conflitos"]


# =========================================================================== router
@pytest.fixture(scope="module")
def cliente(real):
    P, res = real
    app = FastAPI()
    cache = {}

    def resultado(c):
        if c not in ("linha_base", "construtora", "independente", "simulado"):
            from fastapi import HTTPException
            raise HTTPException(404, "cenário desconhecido")
        if c not in cache:
            cache[c] = res.get(c) or executar(P, c)
        return cache[c]

    app.dependency_overrides[rotas_recursos.obter_projeto] = lambda: P
    app.dependency_overrides[rotas_recursos.obter_resultado] = lambda: resultado
    app.include_router(rotas_recursos.router)
    return TestClient(app)


def test_router_sem_configuracao_responde_503():
    app = FastAPI()
    app.include_router(rotas_recursos.router)
    assert TestClient(app).get("/api/recursos/histograma").status_code == 503


def test_router_endpoints(cliente, real):
    P, res = real
    h = cliente.get("/api/recursos/histograma", params={"cenario": "independente", "lote": "L3", "agrupar": "semana"})
    assert h.status_code == 200 and h.json()["agrupar"] == "semana"
    assert all(s["lote"] == "L3" for s in h.json()["series"])
    assert cliente.get("/api/recursos/histograma", params={"lote": "L9"}).status_code == 404
    assert cliente.get("/api/recursos/histograma", params={"agrupar": "mes"}).status_code == 422
    n = cliente.get("/api/recursos/nivelamento", params={"cenario": "independente"})
    assert n.status_code == 200 and "_resultado" not in n.json()
    assert n.json()["termino_cpm"] == res["independente"]["termino"]
    assert n.json()["prova_relacoes"]["ok"] and n.json()["prova_capacidade"]["ok"]
    c = cliente.get("/api/recursos/conflitos-balanco", params={"cenario": "independente", "buffer_km": 1,
                                                               "buffer_dias": 0})
    assert c.status_code == 200
    assert c.json()["n_conflitos"] == R.conflitos_balanco(P, res["independente"], 1.0, 0.0)["n_conflitos"]
    assert cliente.get("/api/recursos/conflitos-balanco", params={"buffer_km": -1}).status_code == 422
    assert cliente.get("/api/recursos/nivelamento", params={"cenario": "xpto"}).status_code == 404


def test_router_ligar_por_obra(real):
    """Contrato de api.registrar_rotas: ligar(app, obter_estado) com ?obra=."""
    P, res = real

    class Est:
        projeto = P

        @staticmethod
        def resultado(c):
            return res[c]

    pedidos = []

    def obter_estado(obra):
        pedidos.append(obra)
        if obra not in (None, "ferrovia"):
            from fastapi import HTTPException
            raise HTTPException(404, "obra desconhecida")
        return Est

    app = FastAPI()
    rotas_recursos.ligar(app, obter_estado)
    cl = TestClient(app)
    r = cl.get("/api/recursos/conflitos-balanco", params={"cenario": "independente", "obra": "ferrovia"})
    assert r.status_code == 200 and "ferrovia" in pedidos
    assert cl.get("/api/recursos/histograma", params={"cenario": "linha_base"}).status_code == 200
    assert cl.get("/api/recursos/histograma", params={"obra": "marte"}).status_code == 404


def test_router_nivelamento_com_capacidades(cliente):
    """*/TER:2 na linha de base da ferrovia: término nivelado medido antes pela função = 18/07/2029."""
    r = cliente.get("/api/recursos/nivelamento", params=[("cenario", "linha_base"), ("capacidade", "*/TER:2")])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["capacidades_informadas"] == {"*/TER": 2} and j["capacidades"]["*/TER"] == 2
    assert j["termino_cpm"] == "2027-05-27" and j["termino_nivelado"] == "2029-07-18"
    assert j["prova_capacidade"]["ok"] and j["prova_relacoes"]["ok"]
    # a chave de cache inclui as capacidades: sem elas, o término volta ao do CPM
    assert cliente.get("/api/recursos/nivelamento",
                       params={"cenario": "linha_base"}).json()["termino_nivelado"] == "2027-05-27"
    # ordem dos parâmetros não muda o resultado (normalizado)
    a = cliente.get("/api/recursos/nivelamento", params=[("cenario", "independente"), ("capacidade", "*/SUB:1"),
                                                         ("capacidade", "L1/TER:3")]).json()
    b = cliente.get("/api/recursos/nivelamento", params=[("cenario", "independente"), ("capacidade", "L1/TER:3"),
                                                         ("capacidade", "*/SUB:1")]).json()
    assert a == b and a["capacidades_informadas"] == {"*/SUB": 1, "L1/TER": 3}
    for ruim in ("TER:2", "*/TER", "*/TER:0", "*/TER:-1", "*/XYZ:2", "L9/TER:1", "*/TER:x"):
        resp = cliente.get("/api/recursos/nivelamento", params=[("capacidade", ruim)])
        assert resp.status_code == 422, ruim
        assert "capacidade" in resp.json()["detail"]
    dup = cliente.get("/api/recursos/nivelamento", params=[("capacidade", "*/TER:2"), ("capacidade", "*/TER:3")])
    assert dup.status_code == 422


# =========================================================================== E1: cruzamento analítico
def _par_cruzamento():
    # Calendário corrido, início qui 01/01/2026 (t = 0). A: km 0→6,4 em 21 dias (ES 0, EF 21), 6,4/21 km/dia.
    # B: SS+2, km 0→6,4 em 17 dias (ES 2, EF 19), 6,4/17 km/dia. Cruzam onde 6,4t/21 = 6,4(t−2)/17
    # => 17t = 21t − 42 => t* = 10,5 d, km* = 6,4 × 10,5/21 = 3,2.
    return _projeto([_ativ("A", "TER", 21, km=(0.0, 6.4)), _ativ("B", "SUB", 17, km=(0.0, 6.4))],
                    [("A", "B", "SS", 2)], dias=TODOS, inicio="2026-01-01", status="2026-01-01")


def test_cruzamento_analitico_exato(limite):
    P = _par_cruzamento()
    c = R.conflitos_balanco(P, executar(P, "linha_base"), buffer_km=0.5)
    assert c["n_conflitos"] == 1
    cz = c["conflitos"][0]["cruzamento"]
    tol = limite("tolerancia_cruzamento_dias")
    assert abs(cz["t_dias"] - 10.5) <= tol
    assert abs(cz["km"] - 3.2) <= tol * (6.4 / 17)  # erro em km equivalente à tolerância em dias
    assert cz["data"] == "2026-01-11"  # dia 10 (0-based) desde 01/01 => 11/01, meio do dia
    an = c["conflitos"][0]["analitico"]
    # distância < 0,5 km de forma exata: d(t) = 6,4t/21 − 6,4(t−2)/17 = 0,5 => t = (12,8/17 − 0,5)/(6,4/17 − 6,4/21)
    t_buf = (12.8 / 17 - 0.5) / (6.4 / 17 - 6.4 / 21)
    assert abs(an["inicio_t_dias"] - t_buf) <= tol
    assert abs(an["distancia_km_min"] - (6.4 * 19 / 21 - 6.4)) <= 1e-6  # no fim da janela (t = 19)


def test_par_paralelo_acima_do_buffer_nao_alerta():
    # mesma velocidade, B 3 dias atrás => 3 km de distância constante; buffer 2 km => 0 alertas
    P = _projeto([_ativ("A", "TER", 10, km=(0.0, 10.0)), _ativ("B", "SUB", 10, km=(0.0, 10.0))],
                 [("A", "B", "SS", 3)], dias=TODOS, inicio="2026-01-01", status="2026-01-01")
    c = R.conflitos_balanco(P, executar(P, "linha_base"), buffer_km=2.0)
    assert c["n_conflitos"] == 0


def test_cruzamento_entre_amostras_diarias_e_detectado():
    # A: km 0→20 em 20 d (1 km/d). B: SS+3, km 0→10,4 em 7 d (ES 3, EF 10; 10,4/7 km/d).
    # Amostras diárias (início dos dias 3..9): d(9) = 9 − 10,4×6/7 = +0,086 — nenhuma negativa.
    # Mas d(10) = 10 − 10,4 = −0,4: B ultrapassa A dentro do último dia. t* = 3v/(v − 1), v = 10,4/7.
    P = _projeto([_ativ("A", "TER", 20, km=(0.0, 20.0)), _ativ("B", "SUB", 7, km=(0.0, 10.4))],
                 [("A", "B", "SS", 3)], dias=TODOS, inicio="2026-01-01", status="2026-01-01")
    v = 10.4 / 7
    t_est = 3 * v / (v - 1)
    c = R.conflitos_balanco(P, executar(P, "linha_base"), buffer_km=0.0)
    assert c["n_conflitos"] == 1
    e = c["conflitos"][0]
    assert e["fonte"] == "analitico" and e["dias"] == 0 and e["ultrapassagem"]
    assert e["cruzamento"]["t_dias"] == pytest.approx(t_est, abs=1e-9)
    assert e["cruzamento"]["km"] == pytest.approx(t_est, abs=1e-9)


def test_linha_real_conflito_ja_ocorrido():
    # Índice de dia desde 01/01 (t). Real A: (0, 0) → (5, 5) → parada até (10, 5). Real B: (2, 0) → (8, 6).
    # Data de status 10/01 (t = 9). Em [5, 8]: d = 5 − (t − 2) => zero em t = 7 (08/01), km 5; < 0,5 a partir de
    # t = 6,5 (07/01). Depois de t = 8, B parada em 6: d = −1 até a data de status.
    P = _projeto([_ativ("A", "TER", 20, km=(0.0, 10.0), status="em_andamento", inicio_real="2026-01-01",
                        percentual_executado=50),
                  _ativ("B", "SUB", 20, km=(0.0, 10.0), status="em_andamento", inicio_real="2026-01-03",
                        percentual_executado=50)],
                 [("A", "B", "SS", 2)], dias=TODOS, inicio="2026-01-01", status="2026-01-10")

    def pts(*xs):
        return [{"data": iso(_d("2026-01-01") + t), "km": k} for t, k in xs]

    real = {"frentes": [{"atividade_id": "A", "pontos": pts((0, 0), (5, 5), (10, 5))},
                        {"atividade_id": "B", "pontos": pts((2, 0), (8, 6))}]}
    c = R.conflitos_balanco(P, executar(P, "construtora"), buffer_km=0.5, linha_real=real)
    assert c["n_conflitos_reais"] == 1
    e = c["conflitos_reais"][0]
    assert e["fonte"] == "real" and e["ocorrido"] and e["ultrapassagem"]
    assert e["inicio_t_dias"] == pytest.approx(6.5) and e["data"] == "2026-01-07"
    assert e["cruzamento"]["t_dias"] == pytest.approx(7.0) and e["cruzamento"]["km"] == pytest.approx(5.0)
    assert e["distancia_km_min"] == pytest.approx(-1.0) and e["data_fim"] == "2026-01-09"
    # sem linha real, nada de conflitos reais
    assert R.conflitos_balanco(P, executar(P, "construtora"), buffer_km=0.5)["n_conflitos_reais"] == 0


def test_dataset_real_cruzamentos_analiticos_coerentes(real, limite):
    P, res = real
    c = R.conflitos_balanco(P, res["independente"], buffer_km=1.0)
    tol = limite("tolerancia_cruzamento_dias")
    for e in c["conflitos"]:
        cz = e["cruzamento"]
        if cz:
            a, b = (P.atividades[x] for x in e["atividades"])
            ra, rb = (res["independente"]["atividades"][x] for x in e["atividades"])

            def km(at, r, t):
                es, ef = _d(r["es"]), _d(r["ef"])
                return at["km_ini"] + (at["km_fim"] - at["km_ini"]) * (t - es) / (ef - es)

            t = cz["t_ordinal"]
            # no cruzamento as duas retas estão no mesmo km (erro em dias convertido pelo ritmo, folgado)
            assert abs(km(a, ra, t) - km(b, rb, t)) <= tol
            assert e["ultrapassagem"]


def test_router_conflitos_com_linha_real(cliente):
    r = cliente.get("/api/recursos/conflitos-balanco", params={"cenario": "independente", "com_linha_real": True})
    assert r.status_code == 200
    j = r.json()
    assert j["n_conflitos_reais"] == len(j["conflitos_reais"]) and j["n_conflitos_reais"] > 0
    assert all(e["fonte"] == "real" and e["data"] < j["data_status"] for e in j["conflitos_reais"])
    sem = cliente.get("/api/recursos/conflitos-balanco", params={"cenario": "independente"}).json()
    assert sem["n_conflitos_reais"] == 0 and sem["n_conflitos"] == j["n_conflitos"]


def test_linha_real_antecessora_concluida_libera_o_trecho():
    # A concluída: real (0, 0) → (5, 10). B: (2, 0) → (9, 12), passa do km 10 em t ≈ 7,8 — DEPOIS de A acabar.
    # Até t = 5 a distância mínima é 10 − 3·12/7 ≈ 4,86 km: nenhum conflito real.
    P = _projeto([_ativ("A", "TER", 5, km=(0.0, 10.0), status="concluida", inicio_real="2026-01-01",
                        termino_real="2026-01-05"),
                  _ativ("B", "SUB", 20, km=(0.0, 12.0), status="em_andamento", inicio_real="2026-01-03",
                        percentual_executado=50)],
                 [("A", "B", "SS", 2)], dias=TODOS, inicio="2026-01-01", status="2026-01-12")

    def pts(*xs):
        return [{"data": iso(_d("2026-01-01") + t), "km": k} for t, k in xs]

    real = {"frentes": [{"atividade_id": "A", "pontos": pts((0, 0), (5, 10))},
                        {"atividade_id": "B", "pontos": pts((2, 0), (9, 12))}]}
    c = R.conflitos_balanco(P, executar(P, "construtora"), buffer_km=0.5, linha_real=real)
    assert c["n_conflitos_reais"] == 0
