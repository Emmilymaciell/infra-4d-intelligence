"""Registro consolidado de riscos ao prazo: cada fonte isolada, deduplicação, ordenação e EVIDÊNCIA que
reproduz o número pela API. Redes pequenas: calendário corrido, início = data de status = 01/01/2026."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infra4d import riscos_prazo as RP
from infra4d import rotas_riscos
from infra4d.api import criar_app
from infra4d.cenarios import Projeto, executar

TODOS = [0, 1, 2, 3, 4, 5, 6]


def _q(aid, qtd, boletins, lote="L1", serv=None, prod_plan=10.0, **extra):
    a = {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": lote, "servico_id": serv or aid, "quantidade_total": qtd,
         "produtividade_planejada": prod_plan, "equipes": 1, "calendario": "C", "status": "nao_iniciada",
         "unidade": "m3", **extra}
    meds = [{"atividade_id": aid, "semana_inicio": f"2025-12-{1 + 7 * i:02d}", "quantidade": q, "equipes_dias": e}
            for i, (q, e) in enumerate(boletins)]
    return a, meds


def _proj(itens, rels=(), restricoes=(), termino_lb="2026-12-31", lotes=("L1", "L2"), extras=()):
    return Projeto({"meta": {"inicio_projeto": "2026-01-01", "data_status": "2026-01-01", "calendario_obra": "C",
                             "termino_linha_base": termino_lb},
                    "lotes": [{"id": x} for x in lotes], "servicos": [],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": TODOS, "nao_uteis": []}],
                    "atividades": [a for a, _ in itens] + list(extras), "medicoes": [m for _, ms in itens for m in ms],
                    "relacoes": [{"predecessora": p, "sucessora": s, "tipo": t, "lag": l} for p, s, t, l in rels],
                    "restricoes": list(restricoes)})


# A: 100 un, medida 5 (40 un em 8 eq·dia), planejada 10 => índice 0,5; 20 dias; crítica.
A = _q("A", 100.0, [(24.0, 4.0), (16.0, 4.0)], serv="TER")


def _fonte(nome, P):
    f = dict(RP.FONTES)[nome]
    return RP.registro(P, obra="x", fontes=[(nome, f)])


def test_fonte_produtividade():
    r = _fonte("produtividade", _proj([A]))
    assert r["n_riscos"] == 1
    x = r["riscos"][0]
    assert x["fontes"] == ["produtividade"] and x["nivel"] == "alto" and x["atividades"] == ["A"]
    assert x["frentes"] == [{"lote_id": "L1", "servico_id": "TER"}]
    assert x["evidencias"][0]["valor"] == 0.5 and "50%" in x["explicacao"]


def test_fonte_restricao_pendente():
    rest = {"id": "R1", "descricao": "licença", "atividade_id": "A", "data_liberacao": "2026-01-01",
            "situacao": "pendente"}
    r = _fonte("restricao", _proj([A], restricoes=[rest]))
    x = r["riscos"][0]
    assert x["fontes"] == ["restricao"] and x["nivel"] == "alto" and x["evidencias"][0]["valor"] == 0
    rest["situacao"] = "liberada"
    assert _fonte("restricao", _proj([A], restricoes=[rest]))["n_riscos"] == 0


def test_fonte_tornado():
    # −10 %: 100 ÷ 4,5 = 22,2 => 23 dias contra 20 => +3 dias corridos (calendário corrido) => nível médio
    r = _fonte("tornado", _proj([A]))
    x = r["riscos"][0]
    assert x["delta_potencial_dias"] == 3 and x["nivel"] == "medio" and x["fontes"] == ["tornado"]


def test_fonte_criticidade():
    # X (L1/S) crítica com p = 1/4 (excluída, < 0,5); Y (L2/S) com 3/4; Z e W (L1/F) — Z sempre crítica.
    from test_montecarlo import _rede_criticidade
    r = _fonte("criticidade", _rede_criticidade())
    probs = {(x["frentes"][0]["lote_id"], x["frentes"][0]["servico_id"]): x["probabilidade"] for x in r["riscos"]}
    assert set(probs) == {("L1", "F"), ("L2", "S")}
    assert probs[("L1", "F")] == 1.0 and abs(probs[("L2", "S")] - 0.75) <= 0.05


def test_fonte_es_cpm():
    # obra de previsao_es "atraso constante": ES(SPI) 14/05 contra CPM 20/04 => +24 dias
    from test_previsao_es import _obra
    r = _fonte("es_cpm", _obra(30))
    obra = next(x for x in r["riscos"] if "(obra)" in x["titulo"])
    assert obra["delta_potencial_dias"] == 24 and obra["evidencias"][0]["valor"] == 24


def test_fonte_recuperacao_inviavel():
    # A → B (20 + 20 dias, término 09/02). Prazo contratual 10/01 inalcançável (mínimo 20/01): Δ = 30 dias.
    B = _q("B", 100.0, [(32.0, 4.0), (8.0, 4.0)], serv="SUB")
    r = _fonte("recuperacao", _proj([A, B], [("A", "B", "FS", 0)], termino_lb="2026-01-10"))
    x = r["riscos"][0]
    assert x["delta_potencial_dias"] == 30 and x["nivel"] == "alto"
    assert x["evidencias"][0]["valor"] == "inviavel"


def test_fonte_balanco_com_ultrapassagem():
    from test_recursos import _par_cruzamento
    r = _fonte("balanco", _par_cruzamento())
    x = r["riscos"][0]
    assert x["fontes"] == ["balanco"] and x["nivel"] == "alto" and "ULTRAPASSAGEM" in x["explicacao"]
    assert {f["servico_id"] for f in x["frentes"]} == {"TER", "SUB"}


def test_fonte_clima_e_dcma_coerentes_com_os_modulos():
    from infra4d.clima import cenarios_climaticos
    from infra4d.dcma import avaliar_cenario
    P = Projeto.carregar()
    x = _fonte("clima", P)["riscos"][0]
    c = next(c for c in cenarios_climaticos(P, 0.3)["cenarios"] if c["tipo"] == "chuvoso")
    assert x["delta_potencial_dias"] == c["delta_dias_corridos"] > 0
    d = _fonte("dcma", P)["riscos"][0]
    assert d["evidencias"][0]["valor"] == avaliar_cenario(P, "independente")["resumo"]["reprovados"] > 0


def _sinal(chave, fonte, delta=None, prob=None, nivel="medio"):
    return {"chave": chave, "fonte": fonte, "atividades": [fonte], "nivel": nivel, "delta": delta, "prob": prob,
            "titulo": f"t-{fonte}", "texto": f"x-{fonte}.", "evidencias": [RP._ev("/r", {}, [], 1)]}


def test_deduplicacao_por_frente_cita_todas_as_fontes():
    f = ("frente", "L1", "TER")
    rs = RP.consolidar([_sinal(f, "produtividade", nivel="alto"), _sinal(f, "tornado", delta=7),
                        _sinal(f, "criticidade", prob=0.6), _sinal(("obra", "clima"), "clima", delta=3)])
    assert len(rs) == 2
    t = next(r for r in rs if r["frentes"])
    assert t["fontes"] == ["produtividade", "tornado", "criticidade"]
    assert (t["delta_potencial_dias"], t["probabilidade"], t["exposicao"], t["nivel"]) == (7, 0.6, 4.2, "alto")
    assert len(t["evidencias"]) == 3 and {e["fonte"] for e in t["evidencias"]} == set(t["fontes"])


def test_ordenacao_segue_a_regra():
    # regra (r15): pelo Δ; a probabilidade NÃO entra na ordem. a = Δ 10 (p 0,3); c = Δ 8 (p 1); b = Δ 5;
    # depois os sem Δ por nível: d (alto), e (baixo). A exposição continua exibida: a = 3, c = 8, b = 5.
    rs = RP.consolidar([_sinal(("o", "a"), "a", 10, 0.3), _sinal(("o", "b"), "b", 5),
                        _sinal(("o", "c"), "c", 8, 1.0), _sinal(("o", "e"), "e", nivel="baixo"),
                        _sinal(("o", "d"), "d", nivel="alto")])
    assert [r["fontes"][0] for r in rs] == ["a", "c", "b", "d", "e"]
    assert [r["exposicao"] for r in rs] == [3.0, 8.0, 5.0, None, None]
    assert [r["id"] for r in rs] == ["RP-01", "RP-02", "RP-03", "RP-04", "RP-05"]


def test_fonte_quebrada_e_omitida_e_declarada():
    def quebra(*_):
        raise ImportError("sem módulo")
    r = RP.registro(_proj([A]), fontes=[("produtividade", dict(RP.FONTES)["produtividade"]), ("x", quebra)])
    assert "x" in r["fontes_omitidas"] and r["fontes_usadas"] == ["produtividade"] and r["n_riscos"] == 1
    r = RP.registro(_proj([A]), rapido=True)
    assert set(r["fontes_omitidas"]) >= {"criticidade", "recuperacao"}


@pytest.fixture(scope="module")
def cliente():
    return TestClient(criar_app())


@pytest.mark.parametrize("obra,rapido", [("ferrovia", False), ("rodovia", True)])
def test_evidencia_reproduz_o_numero_pela_api(cliente, obra, rapido):
    r = cliente.get("/api/riscos", params={"obra": obra, "rapido": rapido})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["n_riscos"] == len(j["riscos"]) > 3 and j["fontes_omitidas"] == (
        {"criticidade": "pulada no modo rápido (cálculo caro)", "recuperacao": "pulada no modo rápido (cálculo caro)"}
        if rapido else {})
    deltas = [x["delta_potencial_dias"] for x in j["riscos"] if x["delta_potencial_dias"] is not None]
    assert deltas == sorted(deltas, reverse=True)
    vistos = {}
    for x in j["riscos"]:
        assert x["evidencias"] and x["explicacao"]
        for ev in x["evidencias"]:
            chave = (ev["rota"], tuple(sorted((k, str(v)) for k, v in ev["params"].items())))
            if chave not in vistos:
                resp = cliente.get(ev["rota"], params=ev["params"])
                assert resp.status_code == 200, (ev, resp.text[:200])
                vistos[chave] = resp.json()
            assert RP.extrair(vistos[chave], ev["caminho"]) == ev["valor"], (x["id"], ev)
    assert cliente.get("/api/riscos", params={"obra": obra, "rapido": rapido}).json()["cache"] is True


def test_rota_isolada():
    P = _proj([A])

    class Est:
        projeto = P

    vazio = FastAPI()
    vazio.include_router(rotas_riscos.router)
    assert TestClient(vazio).get("/api/riscos").status_code == 503
    app = FastAPI()
    rotas_riscos.ligar(app, lambda obra: Est)
    j = TestClient(app).get("/api/riscos", params={"rapido": True}).json()
    assert j["n_riscos"] >= 1 and j["tempo_total_s"] >= 0
    assert executar(P, "independente")["termino"] == j["termino_independente"]


def test_es_mais_otimista_que_o_cpm_nao_vira_delta():
    # ferrovia: ES(SPI) 11/08/2027 × CPM 09/09/2027 = −29 dias: risco de confiança (baixo), sem Δ de atraso
    r = _fonte("es_cpm", Projeto.carregar())
    obra = next(x for x in r["riscos"] if "(obra)" in x["titulo"])
    assert obra["evidencias"][0]["valor"] == -29
    assert obra["delta_potencial_dias"] is None and obra["nivel"] == "baixo"


# ------------------------------------------------------------------ r15
def test_restricao_em_concluida_e_baixa_e_sem_none():
    rest = {"id": "R1", "descricao": "esquecida", "atividade_id": "A", "data_liberacao": "2025-12-01",
            "situacao": "pendente"}
    a = dict(A[0], status="concluida", inicio_real="2025-12-01", termino_real="2025-12-20",
             quantidade_executada=100.0)
    x = _fonte("restricao", _proj([(a, A[1])], restricoes=[rest]))["riscos"][0]
    assert x["nivel"] == "baixo" and "None" not in x["explicacao"] and "desatualizado" in x["explicacao"]


def test_fontes_distintas_e_chave_por_atividade_sem_servico():
    f = ("frente", "L1", "GRA")
    rs = RP.consolidar([_sinal(f, "restricao"), _sinal(f, "restricao")])
    assert len(rs) == 1 and rs[0]["fontes"] == ["restricao"] and "confirmado" not in rs[0]["titulo"]
    marcos = [{"id": m, "nome": m, "tipo": "marco_termino", "lote_id": "L1", "calendario": "C",
               "status": "nao_iniciada"} for m in ("M1", "M2")]
    rests = [{"id": f"R{i}", "descricao": f"p{i}", "atividade_id": m, "data_liberacao": "2026-02-01",
              "situacao": "pendente"} for i, m in enumerate(("M1", "M2"))]
    P = _proj([A], [("A", "M1", "FS", 0), ("A", "M2", "FS", 0)], restricoes=rests, extras=marcos)
    r = _fonte("restricao", P)["riscos"]
    assert sorted(x["atividades"] for x in r) == [["M1"], ["M2"]] and all(x["frentes"] == [] for x in r)


def test_evidencia_nao_grava_parametro_nulo():
    r = RP.registro(_proj([A]), obra=None, fontes=[("tornado", dict(RP.FONTES)["tornado"])])
    assert r["riscos"] and all("obra" not in e["params"] for x in r["riscos"] for e in x["evidencias"])


# ------------------------------------------------------------------ não conformidade (fonte nova)
def _com_nc(base_dados, ncs):
    import copy
    d = copy.deepcopy(base_dados)
    d["nao_conformidades"] = ncs
    return Projeto(d)


def test_nc_vencida_vira_risco_com_evidencia_reconsultavel():
    # NC aberta em L3-S03-TER (crítica), prazo 20 dias antes da data de status (09/11/2026) => 20 dias vencida
    P0 = Projeto.carregar()
    nc = {"id": "NC-T1", "atividade_id": "L3-S03-TER", "data_abertura": "2026-10-01", "descricao": "teste",
          "gravidade": "media", "prazo": "2026-10-20", "situacao": "aberta"}
    P = _com_nc(P0.dados, [nc])
    r = RP.registro(P, obra="x", fontes=[("nao_conformidade", dict(RP.FONTES)["nao_conformidade"])])
    assert r["fontes_usadas"] == ["nao_conformidade"] and r["n_riscos"] == 1
    x = r["riscos"][0]
    assert x["fontes"] == ["nao_conformidade"] and x["atividades"] == ["L3-S03-TER"] and x["nivel"] == "alto"
    assert x["frentes"] == [{"lote_id": "L3", "servico_id": "TER"}] and x["delta_potencial_dias"] is None
    (ev,) = x["evidencias"]
    assert ev["valor"] == 20
    c = TestClient(criar_app(P))
    j = c.get("/api/riscos", params={"rapido": True}).json()
    assert "nao_conformidade" in j["fontes_usadas"]
    risco = next(y for y in j["riscos"] if "nao_conformidade" in y["fontes"])
    assert "produtividade" in risco["fontes"] or "tornado" in risco["fontes"]  # deduplicada na frente L3/TER
    ev = next(e for e in risco["evidencias"] if e["fonte"] == "nao_conformidade")
    resp = c.get(ev["rota"], params=ev["params"])
    assert resp.status_code == 200 and RP.extrair(resp.json(), ev["caminho"]) == ev["valor"] == 20


@pytest.mark.parametrize("obra", ["ferrovia", "rodovia"])
def test_sem_ncs_o_ranking_nao_muda(obra):
    from infra4d.cenarios import DATASET_PADRAO
    P = Projeto.carregar(DATASET_PADRAO.parent / f"{obra}_ficticia.json")
    com = RP.registro(P, obra=obra, rapido=True)
    sem = RP.registro(P, obra=obra, rapido=True, fontes=[f for f in RP.FONTES if f[0] != "nao_conformidade"])
    assert "nao_conformidade" in com["fontes_usadas"] and not com["fontes_omitidas"].get("nao_conformidade")
    assert com["riscos"] == sem["riscos"]


def test_modulo_de_nc_ausente_fica_omitido(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "infra4d.nao_conformidade", None)  # import passa a falhar (ImportError)
    r = RP.registro(_proj([A]), rapido=True)
    assert "nao_conformidade" in r["fontes_omitidas"] and "indisponível" in r["fontes_omitidas"]["nao_conformidade"]
