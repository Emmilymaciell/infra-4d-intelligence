"""Cenários de recuperação: o mínimo de produtividade/equipes para cumprir um prazo.

Redes pequenas com valores calculados À MÃO. Calendário corrido (7 dias), início qui 01/01/2026, data de
status = início (tudo não iniciado) => dia útil k (0-based) = 01/01 + k.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infra4d import rotas_recuperacao
from infra4d.cenarios import DATASET_PADRAO, Ajuste, Projeto, executar
from infra4d.recuperacao import recuperar

RODOVIA = DATASET_PADRAO.parent / "rodovia_ficticia.json"
TODOS = [0, 1, 2, 3, 4, 5, 6]


def _q(aid, qtd, boletins, prod_plan=10.0, eq=1, serv=None):
    return ({"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": "L1", "servico_id": serv or aid,
             "quantidade_total": qtd, "produtividade_planejada": prod_plan, "equipes": eq, "calendario": "C",
             "status": "nao_iniciada"},
            [{"atividade_id": aid, "semana_inicio": f"2025-12-{1 + 7 * i:02d}", "quantidade": q, "equipes_dias": e}
             for i, (q, e) in enumerate(boletins)])


def _proj(itens, rels=(), extras=(), termino_lb="2026-12-31"):
    ativs = [a for a, _ in itens] + list(extras)
    meds = [m for _, ms in itens for m in ms]
    return Projeto({"meta": {"inicio_projeto": "2026-01-01", "data_status": "2026-01-01", "calendario_obra": "C",
                             "termino_linha_base": termino_lb},
                    "lotes": [{"id": "L1"}],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": TODOS, "nao_uteis": []}],
                    "servicos": [], "atividades": ativs, "medicoes": meds,
                    "relacoes": [{"predecessora": p, "sucessora": s, "tipo": t, "lag": 0} for p, s, t in rels]})


# A e B: 100 un, medida 5 un/eq·dia (boletins 40 un em 8 eq·dia). Melhor semana: A 6 (24/4), B 8 (32/4).
A = _q("A", 100.0, [(24.0, 4.0), (16.0, 4.0)])
B = _q("B", 100.0, [(32.0, 4.0), (8.0, 4.0)])


def test_cadeia_simples_escolhe_menor_esforco_e_desempata_pela_viabilidade():
    # A → B (FS): 20 + 20 dias => término 09/02 (dia 39). Prazo 03/02 (dia 33): 6 dias a recuperar.
    # Só A ou só B a 14 dias resolve: produtividade 100/14 = 7,1429 (+42,86 %) nas duas. Desempate pela
    # viabilidade: B (7,14 / melhor semana 8 = 0,89 ⇒ já atingida) vence A (7,14 / 6 = 1,19).
    P = _proj([A, B], [("A", "B", "FS")])
    r = recuperar(P, prazo="2026-02-03")
    assert r["termino_atual"] == "2026-02-09" and r["prazo"] == "2026-02-03"
    assert r["cumpre_prazo"] and r["viabilidade"] == "viavel"
    assert [p["id"] for p in r["plano"]] == ["B"]
    b = r["plano"][0]
    assert (b["duracao_atual"], b["duracao_necessaria"]) == (20, 14)
    assert b["produtividade_medida"] == pytest.approx(5.0)
    assert b["produtividade_necessaria"] == pytest.approx(100 / 14, rel=1e-6)
    assert b["aumento_pct"] == pytest.approx(42.857, abs=1e-3)
    assert b["melhor_semana"] == pytest.approx(8.0) and b["viabilidade"] == "viavel"
    # alternativa por equipes, mantendo a produtividade medida: ceil(100 / (5 × 14)) = 2
    assert b["equipes_necessarias"] == 2
    v = r["verificacao"]
    assert v["produtividade"]["termino"] == "2026-02-03" and v["produtividade"]["cumpre"]
    assert v["equipes"]["cumpre"]


def test_aplicar_o_plano_no_simulado_cumpre_o_prazo():
    P = _proj([A, B], [("A", "B", "FS")])
    r = recuperar(P, prazo="2026-02-03")
    ajustes = [Ajuste(**a) for a in r["ajustes_produtividade"]]
    assert executar(P, "simulado", ajustes)["termino"] <= "2026-02-03"


def test_troca_de_cadeia_caminhos_paralelos():
    # A (100 un, 20 d) e C (90 un, medida 5 => 18 d) em paralelo. Prazo 16/01 (dia 15) => 16 dias cada.
    # Só A não basta (C passa a determinar em 18). Mínimo de cada um: 16 dias.
    #   A: 100/16 = 6,25 (+25 %); C: 90/16 = 5,625 (+12,5 %). Ordem por esforço: C, A.
    C = _q("C", 90.0, [(20.0, 4.0), (20.0, 4.0)])
    P = _proj([A, C])
    r = recuperar(P, prazo="2026-01-16")
    assert r["cumpre_prazo"]
    assert [(p["id"], p["duracao_necessaria"]) for p in r["plano"]] == [("C", 16), ("A", 16)]
    assert r["plano"][0]["aumento_pct"] == pytest.approx(12.5, abs=1e-3)
    assert r["plano"][1]["aumento_pct"] == pytest.approx(25.0, abs=1e-3)
    assert r["verificacao"]["produtividade"]["termino"] == "2026-01-16"


def test_minimalidade_um_dia_a_menos_de_esforco_estoura():
    P = _proj([A, B], [("A", "B", "FS")])
    r = recuperar(P, prazo="2026-02-03")
    b = r["plano"][0]
    menos = Ajuste(produtividade=100 / (b["duracao_necessaria"] + 1), atividade_id="B")
    assert executar(P, "simulado", [menos])["termino"] > "2026-02-03"


def test_prazo_impossivel_declara_inviabilidade():
    # fator máximo 2 × medida: A e B a 10 dias cada => término mínimo 20/01 (dia 19). Prazo 10/01 é impossível.
    P = _proj([A, B], [("A", "B", "FS")])
    r = recuperar(P, prazo="2026-01-10")
    assert not r["cumpre_prazo"] and r["viabilidade"] == "inviavel"
    assert r["termino_alcancado"] == "2026-01-20" and r["plano_tipo"] == "melhor_esforco_sem_cumprir"
    assert {(p["id"], p["duracao_necessaria"]) for p in r["plano"]} == {("A", 10), ("B", 10)}
    assert "não alcança" in r["motivo"]


def test_exigir_mais_que_1_3_da_melhor_semana_e_inviavel_sem_mudanca_de_metodo():
    # Só A (melhor semana 6). Prazo 11/01 (dia 10) => 11 dias => 100/11 = 9,09 > 1,3 × 6 = 7,8.
    P = _proj([A])
    r = recuperar(P, prazo="2026-01-11")
    assert r["cumpre_prazo"]
    assert r["plano"][0]["viabilidade"] == "inviavel_sem_mudanca_de_metodo"
    assert r["viabilidade"] == "inviavel_sem_mudanca_de_metodo"
    # 7,14 (14 dias, prazo 14/01) / 6 = 1,19 => exige esforço acima da melhor semana
    assert recuperar(P, prazo="2026-01-14")["plano"][0]["viabilidade"] == "acima_da_melhor_semana"


def test_ja_no_prazo_plano_vazio():
    P = _proj([A, B], [("A", "B", "FS")])
    r = recuperar(P, prazo="2026-03-01")
    assert r["cumpre_prazo"] and r["plano"] == [] and r["viabilidade"] == "no_prazo" and r["plano_tipo"] == "nenhum"


def test_cadeia_so_de_duracao_fixa_e_inviavel():
    fixa = {"id": "F", "nome": "F", "tipo": "tarefa", "lote_id": "L1", "servico_id": "SIN", "duracao_fixa": 30,
            "calendario": "C", "status": "nao_iniciada"}
    P = _proj([A], extras=[fixa])
    r = recuperar(P, prazo="2026-01-25")
    assert not r["cumpre_prazo"] and r["viabilidade"] == "inviavel"
    assert "ajustável" in r["motivo"]


def test_marco_contratual_como_alvo():
    # A → M (marco de término). LB: produtividade planejada 10 => 10 dias => marco em 10/01 (prazo padrão).
    # Independente: 20 dias. Recuperar o marco exige A em 10 dias: 100/10 = 10 (+100 %).
    M = {"id": "M", "nome": "M", "tipo": "marco_termino", "lote_id": "L1", "calendario": "C", "status": "nao_iniciada"}
    P = _proj([A, B], [("A", "M", "FS")], extras=[M])
    r = recuperar(P, marco="M")
    assert r["alvo"] == "M" and r["prazo"] == "2026-01-10"
    assert [(p["id"], p["duracao_necessaria"]) for p in r["plano"]] == [("A", 10)]
    assert r["verificacao"]["produtividade"]["cumpre"]
    with pytest.raises(ValueError):
        recuperar(P, marco="XPTO")


@pytest.mark.parametrize("arquivo", [DATASET_PADRAO, RODOVIA])
def test_obras_reais_plano_cumpre_ou_declara_inviabilidade(arquivo):
    P = Projeto.carregar(arquivo)
    r = recuperar(P)  # prazo padrão: término da linha de base
    assert r["prazo"] == P.dados["meta"]["termino_linha_base"]
    if r["cumpre_prazo"]:
        ajustes = [Ajuste(**a) for a in r["ajustes_produtividade"]]
        assert executar(P, "simulado", ajustes)["termino"] <= r["prazo"]
        assert r["plano"] and all(p["aumento_pct"] > 0 for p in r["plano"])
        assert [p["aumento_pct"] for p in r["plano"]] == sorted(p["aumento_pct"] for p in r["plano"])
    else:
        assert r["viabilidade"] == "inviavel" and r["motivo"]
    assert r["viabilidade"] in ("no_prazo", "viavel", "acima_da_melhor_semana", "inviavel_sem_mudanca_de_metodo",
                                "inviavel")


def test_rota_recuperacao():
    P = _proj([A, B], [("A", "B", "FS")])

    class Est:
        projeto = P

    def obter_estado(obra):
        if obra not in (None, "x"):
            from fastapi import HTTPException
            raise HTTPException(404, "obra desconhecida")
        return Est

    vazio = FastAPI()
    vazio.include_router(rotas_recuperacao.router)
    assert TestClient(vazio).get("/api/recuperacao").status_code == 503
    app = FastAPI()
    rotas_recuperacao.ligar(app, obter_estado)
    c = TestClient(app)
    j = c.get("/api/recuperacao", params={"obra": "x", "prazo": "2026-02-03"}).json()
    assert j["cumpre_prazo"] and j["plano"][0]["id"] == "B"
    assert c.get("/api/recuperacao", params={"prazo": "03/02/2026"}).status_code == 422
    assert c.get("/api/recuperacao", params={"marco": "ZZ"}).status_code == 422
    assert c.get("/api/recuperacao", params={"folga_max": -1}).status_code == 422
    assert c.get("/api/recuperacao", params={"obra": "marte"}).status_code == 404


def test_escalonamento_equaliza_o_esforco_e_relaxa():
    # A → B (FS), ambos 20 dias. Prazo 30/01 (dia 29): 10 dias a recuperar. Uma frente sozinha precisaria de
    # 10 dias (100 %): o fator máximo 2 permite, mas exige 100/10 = 10. Com fator_max 1,5 (dmin 14) nenhuma
    # resolve sozinha; o escalonamento equaliza: A e B a 15 dias (+33,3 % cada) => 15 + 15 = 30 dias.
    P = _proj([A, B], [("A", "B", "FS")])
    r = recuperar(P, prazo="2026-01-30", fator_max=1.5)
    assert r["cumpre_prazo"] and r["plano_tipo"] == "minimo_que_cumpre"
    assert sorted((p["id"], p["duracao_necessaria"]) for p in r["plano"]) == [("A", 15), ("B", 15)]
    assert all(p["aumento_pct"] == pytest.approx(100 / 3, abs=1e-3) for p in r["plano"])
    assert r["verificacao"]["produtividade"] == {"termino": "2026-01-30", "cumpre": True}


def test_relaxacao_devolve_o_dia_desnecessario():
    # P (20 d) em paralelo com Q (10 d) → R (10 d): empate em 20. Prazo 19/01 (dia 18) = 19 dias.
    # Nenhuma frente sozinha resolve (o outro caminho segue em 20). O passo de empate encurta P, Q e R em 1
    # dia — mas o caminho Q→R só precisava de 1 dia no total. A relaxação devolve um deles: plano com 2
    # frentes, P a 19 dias e um só entre Q e R a 9.
    P_ = _q("P", 100.0, [(24.0, 4.0), (16.0, 4.0)])
    Q = _q("Q", 50.0, [(24.0, 4.0), (16.0, 4.0)])
    R_ = _q("R", 50.0, [(24.0, 4.0), (16.0, 4.0)])
    pj = _proj([P_, Q, R_], [("Q", "R", "FS")])
    r = recuperar(pj, prazo="2026-01-19")
    assert r["cumpre_prazo"] and r["verificacao"]["produtividade"]["termino"] == "2026-01-19"
    planos = {p["id"]: p["duracao_necessaria"] for p in r["plano"]}
    assert len(planos) == 2 and planos["P"] == 19 and sorted(planos.values()) == [9, 19]


def test_marco_ja_ocorrido_depois_do_prazo_diz_isso():
    M = {"id": "M", "nome": "M", "tipo": "marco_termino", "lote_id": "L1", "calendario": "C", "status": "concluida",
         "inicio_real": "2025-12-20", "termino_real": "2025-12-20"}
    P = _proj([A], extras=[M])
    r = recuperar(P, marco="M", prazo="2025-12-10")
    assert not r["cumpre_prazo"] and r["viabilidade"] == "inviavel" and r["plano"] == []
    assert "já ocorreu em 2025-12-20" in r["motivo"]


# ------------------------------------------------------------- atividade reversa no passo de empate (2026-11-13)
def test_empate_nao_encurta_atividade_reversa():
    # P (duração fixa 10, 01–10/01) --FF--> R (50 un, 5 d) --SS--> S (200 un, 20 d); Q (250 un, 25 d) em paralelo.
    # R termina com P (FF) e S começa com R (SS): R = 06–10/01, S = 06–25/01, Q = 01–25/01 (empate em 25/01).
    # R é "reversa": encurtá-la ADIA o seu início e o de S. Com fator 2: S >= 10 d, Q >= 13 d, R >= 3 d.
    # Prazo 15/01: S a 10 d (06–15/01, +100 %) e Q a 15 d (+66,7 %), R INTOCADA => cumpre.
    # Encurtar R para 3 d (como fazia o passo de empate antigo) leva S a 08–17/01: falso "inviável".
    fixa = {"id": "P", "nome": "P", "tipo": "tarefa", "lote_id": "L1", "servico_id": "P", "duracao_fixa": 10,
            "calendario": "C", "status": "nao_iniciada"}
    R = _q("R", 50.0, [])
    S = _q("S", 200.0, [])
    Q = _q("Q", 250.0, [])
    P = _proj([R, S, Q], [("P", "R", "FF"), ("R", "S", "SS")], extras=[fixa])
    assert executar(P, "independente")["termino"] == "2026-01-25"
    r = recuperar(P, prazo="2026-01-15")
    assert r["cumpre_prazo"] and r["termino_alcancado"] == "2026-01-15"
    assert sorted((p["id"], p["duracao_necessaria"]) for p in r["plano"]) == [("Q", 15), ("S", 10)]
    assert any("R" in x.get("rejeitadas_por_piorar", []) for x in r["passos"])
    assert r["verificacao"]["produtividade"] == {"termino": "2026-01-15", "cumpre": True}


def test_ferrovia_cumpre_o_prazo_contratual_com_fator_ate_2():
    # regressão: antes da correção, o passo de empate encurtava frentes reversas e declarava "inviável" (28/05)
    P = Projeto.carregar(DATASET_PADRAO)
    r = recuperar(P)
    assert r["prazo"] == "2027-05-27" and r["cumpre_prazo"] and r["plano_tipo"] == "minimo_que_cumpre"
    assert r["termino_alcancado"] <= "2027-05-27" and r["verificacao"]["produtividade"]["cumpre"]
    assert all(p["aumento_pct"] <= 100 + 1e-6 for p in r["plano"])


def test_certificado_pela_aceleracao_antes_de_declarar_inviavel():
    # mesma rede do paradoxo: a aceleração (equipes inteiras, só aceita passo que antecipa) cumpre 15/01 com
    # S e Q a 2 equipes (fator 2 <= fator_max): S = ⌈200/20⌉ = 10 d, Q = ⌈250/20⌉ = 13 d; R não é tocada.
    from infra4d.recuperacao import _Rede, _certificado_aceleracao
    import math
    fixa = {"id": "P", "nome": "P", "tipo": "tarefa", "lote_id": "L1", "servico_id": "P", "duracao_fixa": 10,
            "calendario": "C", "status": "nao_iniciada"}
    P = _proj([_q("R", 50.0, []), _q("S", 200.0, []), _q("Q", 250.0, [])],
              [("P", "R", "FF"), ("R", "S", "SS")], extras=[fixa])
    R = _Rede(P, None)
    aj = {i: {"rem": q, "eq": 1, "prod": 10.0, "dmin": math.ceil(q / 20)} for i, q in (("R", 50.0), ("S", 200.0),
                                                                                       ("Q", 250.0))}
    cert = _certificado_aceleracao(P, None, date_ord("2026-01-15"), 2.0, aj, R)
    assert cert == {"S": 10, "Q": 13}
    assert _certificado_aceleracao(P, None, date_ord("2026-01-12"), 2.0, aj, R) is None  # Q >= 13 d: impossível
    assert _certificado_aceleracao(P, None, date_ord("2026-01-15"), 1.5, aj, R) is None  # 2 equipes > 1,5×


def date_ord(txt):
    from infra4d.calendario import ordinal
    return ordinal(txt)


def test_certificado_segura_a_ferrovia_mesmo_sem_a_defesa_do_empate(monkeypatch):
    # desligando a defesa (a), o escalonamento volta a parar em 28/05; a contraprova (b) pela aceleração
    # tem de transformar a resposta em "cumpre", com ajustes que a verificação confirma
    import infra4d.recuperacao as rec
    monkeypatch.setattr(rec, "_EMPATE_SO_SE_NAO_PIORA", False)
    r = recuperar(Projeto.carregar(DATASET_PADRAO))
    assert r["cumpre_prazo"] and r["verificacao"]["produtividade"]["cumpre"]
    assert any("certificado" in x["tipo"] for x in r["passos"])
    assert all(p["aumento_pct"] <= 100 + 1e-6 for p in r["plano"])
