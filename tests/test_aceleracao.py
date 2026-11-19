"""Aceleração com custo (crashing guloso): casos resolvidos à mão, curva monótona e verificação pela API.

Redes pequenas: calendário corrido (7 dias), início = data de status = qui 01/01/2026 (dia k = 01/01 + k),
sem boletins (o independente usa a produtividade planejada). Custo por equipe·dia passado à mão:
TER = 100, SUB = 300. Mobilização de cada equipe extra = 10 equipe·dias do serviço (MOBILIZACAO).
Custo de +1 equipe: custo_eq_dia × [(n'·D' − n·D) + MOBILIZACAO]  (equipe·dias ociosos do arredondamento + mobilização).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infra4d import rotas_aceleracao
from infra4d.aceleracao import MOBILIZACAO_EQUIPE_DIAS, acelerar, custo_equipe_dia
from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO, Ajuste, Projeto, executar

RODOVIA = DATASET_PADRAO.parent / "rodovia_ficticia.json"
CUSTOS = {"TER": 100.0, "SUB": 300.0}


def _q(aid, serv, qtd=100.0):
    return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": "L1", "servico_id": serv, "quantidade_total": qtd,
            "produtividade_planejada": 10.0, "equipes": 1, "calendario": "C", "status": "nao_iniciada",
            "unidade": "m³"}


def _proj(ativs, rels=(), termino_lb="2026-12-31"):
    return Projeto({"meta": {"inicio_projeto": "2026-01-01", "data_status": "2026-01-01", "calendario_obra": "C",
                             "termino_linha_base": termino_lb, "ficticio": True, "aviso": "FICTÍCIO",
                             "tipo_obra": "ferrovia"},
                    "lotes": [{"id": "L1"}], "servicos": [], "medicoes": [],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                    "atividades": list(ativs),
                    "relacoes": [{"predecessora": p, "sucessora": s, "tipo": "FS", "lag": 0} for p, s in rels]})


def test_mobilizacao_declarada():
    assert MOBILIZACAO_EQUIPE_DIAS == 10


def test_serie_um_passo():
    # A (TER) → B (SUB), 10 + 10 dias: término 20/01. Prazo 15/01 (15 dias).
    # +1 em A: 10 → 5 dias (ganho 5), custo 100 × ((2·5 − 1·10) + 10) = 1.000 => 200/dia.
    # +1 em B: ganho 5, custo 300 × 10 = 3.000 => 600/dia. Escolhe A: término 15/01, custo 1.000.
    P = _proj([_q("A", "TER"), _q("B", "SUB")], [("A", "B")])
    r = acelerar(P, prazo="2026-01-15", custos=CUSTOS)
    assert r["termino_inicial"] == "2026-01-20" and r["cumpre_prazo"]
    assert [(p["termino"], p["custo_acumulado"]) for p in r["curva"]] == [("2026-01-20", 0.0), ("2026-01-15", 1000.0)]
    assert r["ajustes_finais"] == [{"atividade_id": "A", "equipes": 2}]
    assert r["curva"][1]["ajustes"][0] | {} == {"id": "A", "equipes_de": 1, "equipes_para": 2, "duracao_de": 10,
                                                "duracao_para": 5, "custo": 1000.0}


def test_serie_dois_passos_custo_marginal():
    # Prazo 12/01. Depois de A a 2 equipes (15 dias): A +1 => ⌈100/30⌉ = 4 (ganho 1), custo 100 × ((3·4 − 2·5) + 10)
    # = 1.200/dia; B +1 => ganho 5, custo 3.000 => 600/dia. Escolhe B: término 10/01, custo total 4.000.
    P = _proj([_q("A", "TER"), _q("B", "SUB")], [("A", "B")])
    r = acelerar(P, prazo="2026-01-12", custos=CUSTOS)
    assert [(p["termino"], p["custo_acumulado"]) for p in r["curva"]] == [
        ("2026-01-20", 0.0), ("2026-01-15", 1000.0), ("2026-01-10", 4000.0)]
    assert sorted((a["atividade_id"], a["equipes"]) for a in r["ajustes_finais"]) == [("A", 2), ("B", 2)]


def test_caminhos_paralelos_exigem_encurtar_os_dois():
    # A (TER) ∥ C (SUB), 10 dias cada: término 10/01. Prazo 08/01. Sozinha nenhuma antecipa.
    # Passo composto: A +1 (1.000, a mais barata) e depois C +1 (3.000): término 05/01, custo 4.000.
    P = _proj([_q("A", "TER"), _q("C", "SUB")])
    r = acelerar(P, prazo="2026-01-08", custos=CUSTOS)
    assert r["cumpre_prazo"] and len(r["curva"]) == 2
    passo = r["curva"][1]
    assert (passo["termino"], passo["custo_acumulado"]) == ("2026-01-05", 4000.0)
    assert [x["id"] for x in passo["ajustes"]] == ["A", "C"] and passo["composto"]


def test_limite_de_equipes_declara_inviavel():
    # limite_extra 1: A e B no máximo 2 equipes => 5 + 5 = 10 dias. Prazo 05/01 inalcançável.
    P = _proj([_q("A", "TER"), _q("B", "SUB")], [("A", "B")])
    r = acelerar(P, prazo="2026-01-05", custos=CUSTOS, limite_extra=1)
    assert not r["cumpre_prazo"] and r["termino_alcancado"] == "2026-01-10"
    assert "limite" in r["motivo"]


def test_ja_no_prazo_e_parametros_invalidos():
    P = _proj([_q("A", "TER")])
    r = acelerar(P, prazo="2026-02-01", custos=CUSTOS)
    assert r["cumpre_prazo"] and len(r["curva"]) == 1 and r["ajustes_finais"] == []
    with pytest.raises(ValueError):
        acelerar(P, limite_extra=0)
    with pytest.raises(ValueError):
        acelerar(P, prazo="01/02/2026")


def test_custo_padrao_vem_do_orcamento():
    # sem 'custos': custo da equipe·dia = produtividade (un/equipe·dia) × (mão de obra + equipamento) × (1 + BDI)
    from infra4d.aceleracao import bdi
    from infra4d.orcamento import COMPOSICOES
    P = _proj([_q("A", "TER")])
    cd = COMPOSICOES["ferrovia"]["TER"]["custo_direto"]
    assert 0.15 < bdi(P) < 0.30  # BDI fictício da obra, lido do orçamento
    assert custo_equipe_dia(P, "TER", 10.0) == pytest.approx(10.0 * (cd["mao_de_obra"] + cd["equipamento"])
                                                               * (1 + bdi(P)))
    assert custo_equipe_dia(P, "XPTO", 10.0) is None


@pytest.mark.parametrize("arquivo", [DATASET_PADRAO, RODOVIA])
def test_obras_curva_monotona_e_ajustes_reproduzem(arquivo):
    P = Projeto.carregar(arquivo)
    r = acelerar(P)
    c = r["curva"]
    assert len(c) >= 2
    for a, b in zip(c, c[1:]):
        assert b["termino"] < a["termino"] and b["custo_acumulado"] > a["custo_acumulado"]
    assert r["tempo_s"] >= 0 and r["tempo_s"] == r["tempo_s"]
    sim = executar(P, "simulado", [Ajuste(**a) for a in r["ajustes_finais"]])
    assert sim["termino"] == r["termino_alcancado"] == c[-1]["termino"]
    assert r["verificacao"]["termino"] == r["termino_alcancado"]
    assert r["cumpre_prazo"] or r["motivo"]


def test_aplicar_pela_api_da_o_termino_prometido():
    P = _proj([_q("A", "TER"), _q("B", "SUB")], [("A", "B")])
    r = acelerar(P, prazo="2026-01-12", custos=CUSTOS)
    c = TestClient(criar_app(P))
    resp = c.post("/api/simulacao", json={"ajustes": r["ajustes_finais"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["comparacao"]["termino_alvo"] == r["termino_alcancado"] == "2026-01-10"


def test_rota_aceleracao():
    P = _proj([_q("A", "TER"), _q("B", "SUB")], [("A", "B")])

    class Est:
        projeto = P

    vazio = FastAPI()
    vazio.include_router(rotas_aceleracao.router)
    assert TestClient(vazio).get("/api/aceleracao").status_code == 503
    app = FastAPI()
    rotas_aceleracao.ligar(app, lambda obra: Est)
    cl = TestClient(app)
    j = cl.get("/api/aceleracao", params={"prazo": "2026-01-15", "limite_extra": 2}).json()
    assert j["termino_inicial"] == "2026-01-20" and j["cumpre_prazo"]
    assert cl.get("/api/aceleracao", params={"prazo": "xx"}).status_code == 422
    assert cl.get("/api/aceleracao", params={"limite_extra": 0}).status_code == 422


def test_escolhe_menor_custo_por_dia_e_nao_o_maior_ganho():
    # A (TER, 100 un) 10 d → B (SUB, 300 un) 30 d = 40 d (término 09/02). Prazo 05/02 (36 d): faltam 4.
    # +1 em A: ganho 5, custo 1.000 => 200/dia. +1 em B: ganho 15, custo 400 × ((2·15 − 30) + 10) = 4.000 => 267/dia.
    # Escolhe A (menor custo por dia), mesmo com ganho menor: término 04/02, custo 1.000.
    P = _proj([_q("A", "TER"), _q("B", "SUB", 300.0)], [("A", "B")])
    r = acelerar(P, prazo="2026-02-05", custos={"TER": 100.0, "SUB": 400.0})
    assert r["ajustes_finais"] == [{"atividade_id": "A", "equipes": 2}]
    assert (r["termino_alcancado"], r["custo_adicional_total"]) == ("2026-02-04", 1000.0)


def test_custo_inclui_equipe_dia_ocioso_do_arredondamento():
    # A com 90 un: 1 equipe = 9 dias; 2 equipes = ⌈4,5⌉ = 5 dias => 2·5 − 1·9 = 1 equipe·dia ocioso.
    # Custo = 100 × (1 + 10) = 1.100.
    P = _proj([_q("A", "TER", 90.0)])
    r = acelerar(P, prazo="2026-01-05", custos=CUSTOS)
    assert r["curva"][1]["ajustes"][0]["custo"] == 1100.0 and r["termino_alcancado"] == "2026-01-05"


def test_em_andamento_com_remanescente_zero_conta_um_dia():
    # A (TER) EM ANDAMENTO com 100 % executado e não encerrada: o motor usa 1 dia POR REGRA. B (SUB) depois (FS).
    # A aceleração tem de usar a mesma regra: término inicial = o do independente, e a verificação confere.
    A = _q("A", "TER") | {"status": "em_andamento", "inicio_real": "2025-12-20", "quantidade_executada": 100.0}
    P = _proj([A, _q("B", "SUB")], [("A", "B")])
    ind = executar(P, "independente")
    assert ind["atividades"]["A"]["duracao"] == 1
    r = acelerar(P, prazo="2026-01-06", custos=CUSTOS)
    assert r["termino_inicial"] == ind["termino"] == "2026-01-11"
    assert r["verificacao"]["confere"] and r["termino_alcancado"] == "2026-01-06"


def test_obra_sem_tipo_obra_e_erro_claro_e_422():
    from infra4d.orcamento import ErroOrcamento
    P = _proj([_q("A", "TER"), _q("B", "SUB")], [("A", "B")])
    del P.dados["meta"]["tipo_obra"]
    with pytest.raises(ErroOrcamento, match="aceleração sem custo.*tipo_obra"):
        acelerar(P, prazo="2026-01-15")
    assert acelerar(P, prazo="2026-01-15", custos=CUSTOS)["cumpre_prazo"]  # custos informados: não precisa do tipo

    class Est:
        projeto = P

    app = FastAPI()
    rotas_aceleracao.ligar(app, lambda obra: Est)
    r = TestClient(app).get("/api/aceleracao", params={"prazo": "2026-01-15"})
    assert r.status_code == 422 and "aceleração sem custo" in r.json()["detail"]
