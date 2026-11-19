"""Cobertura da previsão (P1): confiança por estresse, alerta de quase-críticas sem medição e relatório por origem.

Esperados conferidos à mão contra o motor em 2026-11-13, cenário independente, rodovia fictícia:
- fotografia da MTA em 2026-03-30 (lida de tendencia.py): o pior índice medido/planejado até ali é o da
  terraplenagem do L3 (≈ 0,85) — NÃO o 0,60 do CBUQ do L2, que só aparece em boletim em outubro. Os CBUQ
  S01–S03 do L2 não têm medição, ficam a 5 dias úteis de folga do M-L2-FIM e fora da cadeia determinante.
  O alerta os lista. A confiança do M-L2-FIM sai "alta": a cadeia é a terraplenagem medida, e estressar o que
  não foi medido em × 0,85 move o marco pouco. LIMITE DOCUMENTADO (R12): nenhum sinal justo nos dados de
  03-30 marca "baixa" ali — o fator real do CBUQ do L2 (0,60) está abaixo de tudo que já tinha sido observado.
- data de status atual (2026-11-09): o CBUQ do L2 já é medido no lote (sai do alerta do M-L2-FIM); o M-L3-FIM
  depende do CBUQ do L3 por analogia da obra e sai "baixa".
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from infra4d import cobertura as C
from infra4d import rotas_cobertura
from infra4d.calendario import ordinal
from infra4d.cenarios import DATASET_PADRAO, Ajuste, Projeto, executar, montar_entrada
from infra4d.motor import calcular
from infra4d.tendencia import fotografia

RODOVIA = DATASET_PADRAO.parent / "rodovia_ficticia.json"


@pytest.fixture(scope="module")
def rodovia():
    return Projeto.carregar(RODOVIA)


@pytest.fixture(scope="module")
def ferrovia():
    return Projeto.carregar(DATASET_PADRAO)


@pytest.fixture(scope="module")
def rodovia_0330(rodovia):
    return Projeto(fotografia(rodovia.dados, ordinal("2026-03-30")))


@pytest.fixture
def folga_alerta(limite):
    return int(limite("folga_alerta_sem_medicao_du"))


def _marco(r, mid):
    return next(m for m in r["marcos"] if m["id"] == mid)


# ---------------------------------------------------------------- origem (hierarquia do motor)
@pytest.mark.parametrize("fonte, origem", [
    ({"regra": "quantidade", "fonte_produtividade": "medida na própria atividade (3 boletins)"}, "atividade_medida"),
    ({"regra": "quantidade", "fonte_produtividade": "média medida do serviço no L2 (4 boletins)"}, "lote_servico_medido"),
    ({"regra": "quantidade", "fonte_produtividade": "média medida do serviço na obra (7 boletins)"}, "analogia_obra"),
    ({"regra": "quantidade", "fonte_produtividade": "sem medição utilizável: produtividade planejada"}, "planejada"),
    ({"regra": "quantidade", "fonte_produtividade": "planejada"}, "planejada"),
    ({"regra": "quantidade", "fonte_produtividade": "AJUSTE DO USUÁRIO (simulação)"}, "ajuste_usuario"),
    ({"regra": "duração fixa"}, "duracao_fixa"),
    ({"regra": "quantidade", "fonte_produtividade": "outra coisa"}, "desconhecida"),
])
def test_origem_segue_a_hierarquia_de_produtividade_efetiva(fonte, origem):
    assert C.origem_da_fonte(fonte) == origem


@pytest.mark.parametrize("obra", ["rodovia", "ferrovia"])
def test_nenhuma_fonte_desconhecida_nos_datasets(obra, request):
    """Se o texto da memória do motor mudar, a classificação cai em 'desconhecida' — e este teste acusa."""
    P = request.getfixturevalue(obra)
    for cen in ("construtora", "independente"):
        for m in C.cobertura(P, cen)["marcos"]:
            assert m["relatorio_origem"]["por_origem"]["desconhecida"]["equipe_dia"] == 0


# ---------------------------------------------------------------- fator de estresse
def test_fator_e_o_pior_indice_observado_ate_a_data(rodovia, rodovia_0330):
    """03-30: pior índice é da terraplenagem do L3 (só dado até 03-30); hoje é o CBUQ do L2 (6 boletins).
    Em 03-30 o fator NÃO pode ser o 0,60 do gerador: esse dado ainda não existia."""
    f0, o0 = C.fator_estresse(rodovia_0330.dados)
    assert (o0["lote_id"], o0["servico_id"]) == ("L3", "TER") and f0 == pytest.approx(0.8517, abs=1e-4)
    f1, o1 = C.fator_estresse(rodovia.dados)
    assert (o1["lote_id"], o1["servico_id"], o1["boletins"]) == ("L2", "CBU", 6) and f1 < 0.60 + 0.05
    assert f0 > 0.80


def test_fator_e_o_minimo_e_reage_a_um_boletim_ruim(rodovia):
    """Boletins de TESTE com índice 0,4 em toda a supressão do L1: f vira 0,4 e aponta a frente; f nunca passa de 1."""
    d = copy.deepcopy(rodovia.dados)
    ativ = {x["id"]: x for x in d["atividades"]}
    for m in d["medicoes"]:
        a = ativ[m["atividade_id"]]
        if (a["lote_id"], a["servico_id"]) == ("L1", "SUP"):
            m["quantidade"] = 0.4 * a["produtividade_planejada"] * m["equipes_dias"]
    f, o = C.fator_estresse(d)
    assert (o["lote_id"], o["servico_id"]) == ("L1", "SUP") and f == pytest.approx(0.4)
    for m in d["medicoes"]:
        m["quantidade"] *= 10
    assert C.fator_estresse(d)[0] == 1.0


def test_sem_boletim_e_sem_historico(rodovia):
    d = copy.deepcopy(rodovia.dados)
    d["medicoes"] = []
    assert C.fator_estresse(d) == (None, None)
    assert {m["confianca"] for m in C.cobertura(Projeto(d))["marcos"]} <= {"sem_historico", "concluido"}


# ---------------------------------------------------------------- estresse conferido por outro caminho
def test_delta_do_estresse_bate_com_o_cenario_simulado(rodovia_0330):
    """Δ_sem_medicao recalculado pelo cenário SIMULADO (ajuste de produtividade por atividade = usada × f nas
    tarefas sem medição): mesmo término. Caminho independente do módulo (cenarios.executar)."""
    P = rodovia_0330
    r = C.cobertura(P)
    f = r["fator_estresse"]
    _, _, mem = montar_entrada(P, "independente")
    aj = [Ajuste(produtividade=mm["produtividade"] * f, atividade_id=aid) for aid, mm in mem.items()
          if mm.get("regra") == "quantidade" and mm["quantidade_remanescente"] > 0
          and C.origem_da_fonte(mm) in C.NAO_MEDIDAS and P.atividades[aid].get("status") != "concluida"]
    sim = executar(P, "simulado", aj)
    base = executar(P, "independente")
    for m in r["marcos"]:
        esperado = ordinal(sim["atividades"][m["id"]]["termino"]) - ordinal(base["atividades"][m["id"]]["termino"])
        assert m["estresse"]["delta_sem_medicao_dias"] == esperado


@pytest.mark.parametrize("d_sem, d_med, nivel", [
    (6, 0, "alta"), (6, 100, "alta"),          # abaixo do Δ mínimo (7 dias): não move o marco de forma relevante
    (7, 28, "alta"), (7, 27, "media"),         # p = 0,20 → alta; p > 0,20 → media
    (7, 7, "media"), (8, 7, "baixa"),          # p = 0,50 → media; p > 0,50 → baixa
    (30, 0, "baixa"), (30, -5, "baixa"),
])
def test_niveis_de_confianca_nos_limiares(d_sem, d_med, nivel):
    assert C.nivel_confianca(d_sem, d_med)[0] == nivel


# ---------------------------------------------------------------- teste-chave (honesto) e alerta
def test_rodovia_0330_alerta_lista_o_cbuq_do_l2_fora_da_cadeia(rodovia_0330, folga_alerta):
    """O alerta é o que o P1 consegue dizer em 03-30: o M-L2-FIM depende de CBUQ sem nenhuma medição a 5 dias
    úteis de virar determinante. A confiança sai 'alta' — limite documentado no R12: sem sinal justo de 'baixa'."""
    m = _marco(C.cobertura(rodovia_0330, folga_alerta_du=folga_alerta), "M-L2-FIM")
    al = {a["atividade_id"]: a for a in m["alerta_sem_medicao"]}
    for s in ("L2-S01-CBU", "L2-S02-CBU", "L2-S03-CBU"):
        assert al[s]["folga_relativa_du"] == 5 and al[s]["na_cadeia"] is False and al[s]["origem"] == "planejada"
    assert al["L2-S04-CBU"]["folga_relativa_du"] == 0 and al["L2-S04-CBU"]["na_cadeia"] is True
    assert m["confianca"] == "alta"
    assert m["estresse"]["delta_sem_medicao_dias"] < m["estresse"]["delta_medida_dias"]


def test_alerta_respeita_o_limiar_de_folga(rodovia_0330):
    """Com limiar 4 os CBUQ S01–S03 (folga 5) saem do alerta; com 5 entram."""
    def ids(x):
        return {a["atividade_id"] for a in _marco(C.cobertura(rodovia_0330, folga_alerta_du=x), "M-L2-FIM")
                ["alerta_sem_medicao"]}
    assert "L2-S01-CBU" not in ids(4) and "L2-S01-CBU" in ids(5)


@pytest.mark.parametrize("mid", ["M-L1-FIM", "M-L2-FIM", "M-L3-FIM"])
def test_folga_do_alerta_e_relativa_ao_marco_nao_ao_fim_da_obra(rodovia_0330, mid):
    """A folga do alerta vem da sub-rede do marco (o marco é o fim), conferida aqui recalculando a sub-rede.
    O M-L1-FIM termina meses antes da obra: na rede inteira o CBUQ do L1 teria folga enorme e sairia do alerta;
    relativo ao marco ele tem folga 0 e entra."""
    P = rodovia_0330
    at, rl, _ = montar_entrada(P, "independente")
    keep = C._antecessoras(rl, mid) | {mid}
    sub = calcular([a for a in at if a.id in keep], [r for r in rl if r.predecessora in keep and r.sucessora in keep],
                   P.calendarios, P.inicio_projeto, data_status=P.data_status)
    assert sub.atividades[mid].folga_total == 0
    al = _marco(C.cobertura(P), mid)["alerta_sem_medicao"]
    assert al
    for a in al:
        assert a["folga_relativa_du"] == sub.atividades[a["atividade_id"]].folga_total
    if mid == "M-L1-FIM":
        assert {a["atividade_id"]: a["folga_relativa_du"] for a in al}["L1-S04-CBU"] == 0


def test_rodovia_hoje_l2_medido_e_l3_baixa(rodovia, folga_alerta):
    r = C.cobertura(rodovia, folga_alerta_du=folga_alerta)
    l2, l3 = _marco(r, "M-L2-FIM"), _marco(r, "M-L3-FIM")
    assert not any(a["servico_id"] == "CBU" for a in l2["alerta_sem_medicao"])
    assert l2["confianca"] == "alta"
    assert l3["confianca"] == "baixa"
    assert {a["atividade_id"] for a in l3["alerta_sem_medicao"]} >= {f"L3-S0{i}-CBU" for i in range(1, 5)}
    assert l3["relatorio_origem"]["frentes"][0][("servico_id")] == "CBU"
    assert l3["relatorio_origem"]["frentes"][0]["origem"] == "analogia_obra"


def test_l3_melhora_quando_a_analogia_vira_medicao(rodovia):
    """1 boletim de CBUQ de TESTE no L3-S01: a fração sem medição do M-L3-FIM cai e o S01 sai do alerta."""
    antes = _marco(C.cobertura(rodovia), "M-L3-FIM")
    d = copy.deepcopy(rodovia.dados)
    a = next(x for x in d["atividades"] if x["id"] == "L3-S01-CBU")
    a.update(status="em_andamento", inicio_real="2026-11-03", quantidade_executada=400.0)
    d["medicoes"].append({"atividade_id": "L3-S01-CBU", "semana_inicio": "2026-11-02", "quantidade": 400.0,
                          "equipes_dias": 1.0, "origem": "DADO DE TESTE (test_cobertura)"})
    depois = _marco(C.cobertura(Projeto(d)), "M-L3-FIM")
    assert depois["relatorio_origem"]["fracao_sem_medicao"] < antes["relatorio_origem"]["fracao_sem_medicao"]
    assert "L3-S01-CBU" not in {x["atividade_id"] for x in depois["alerta_sem_medicao"]}


# ---------------------------------------------------------------- relatório por origem (informativo)
def _cadeia_motor(P, cenario, marco):
    at, rl, mem = montar_entrada(P, cenario)
    res = calcular(at, rl, P.calendarios, P.inicio_projeto, data_status=P.data_status)
    vistos, pilha = set(), [marco]
    while pilha:
        x = pilha.pop()
        if x not in vistos:
            vistos.add(x)
            pilha.extend(res.atividades[x].determinantes)
    por_id = {a.id: a for a in at}
    return {i for i in vistos if por_id[i].tipo == "tarefa" and por_id[i].status != "concluida"
            and por_id[i].duracao > 0}, mem


def test_relatorio_equipe_dia_conferido_contra_o_motor(rodovia):
    for m in C.cobertura(rodovia)["marcos"]:
        ro = m["relatorio_origem"]
        cadeia, mem = _cadeia_motor(rodovia, "independente", m["id"])
        esperado = sum(mem[i]["quantidade_remanescente"] / mem[i]["produtividade"] if mem[i]["regra"] == "quantidade"
                       else mem[i]["duracao_calculada"] for i in cadeia)
        assert ro["equipe_dia_remanescente"] == pytest.approx(esperado, abs=0.02)
        assert ro["tarefas_determinantes_com_trabalho"] == len(cadeia)
        assert sum(v["pct"] for v in ro["por_origem"].values()) == pytest.approx(100, abs=0.5)
        assert {a for f in ro["frentes"] for a in f["atividades"]} <= cadeia


def test_cadeia_segue_todas_as_determinantes_que_empatam():
    ra = lambda dets: SimpleNamespace(determinantes=dets)  # noqa: E731
    res = SimpleNamespace(atividades={"M": ra(["A", "B"]), "A": ra([]), "B": ra(["C"]), "C": ra([]), "D": ra([])})
    assert C._cadeia(res, "M") == {"M", "A", "B", "C"}


def test_relatorio_do_m_l1_so_tem_o_l1(rodovia):
    """Cadeia determinante, não a lista de críticas da obra: o M-L1-FIM não carrega frentes de outros lotes."""
    assert {f["lote_id"] for f in _marco(C.cobertura(rodovia), "M-L1-FIM")["relatorio_origem"]["frentes"]} == {"L1"}


def test_construtora_e_toda_planejada(ferrovia, rodovia):
    """Construtora usa a planejada por definição: relatório 100 % sem medição e Δ da parte medida = 0."""
    for P in (ferrovia, rodovia):
        for m in C.cobertura(P, "construtora")["marcos"]:
            ro = m["relatorio_origem"]
            if ro["fracao_sem_medicao"] is not None:
                assert ro["fracao_sem_medicao"] == 1.0
            assert m["estresse"]["delta_medida_dias"] == 0


def test_parametros_invalidos():
    P = Projeto.carregar(DATASET_PADRAO)
    with pytest.raises(C.ErroCobertura):
        C.cobertura(P, "linha_base")
    with pytest.raises(C.ErroCobertura):
        C.cobertura(P, folga_alerta_du=-1)


# ---------------------------------------------------------------- rota
@pytest.fixture(scope="module")
def cliente(rodovia, ferrovia):
    obras = {"rodovia": rodovia, "ferrovia": ferrovia}

    def obter(obra):
        if obra is None:
            return SimpleNamespace(projeto=ferrovia, ajustes=[])
        if obra not in obras:
            raise HTTPException(404, f"obra desconhecida: {obra}")
        return SimpleNamespace(projeto=obras[obra], ajustes=[])

    app = FastAPI()
    rotas_cobertura.ligar(app, obter)
    return app, TestClient(app)


def test_rota_responde_e_bate_com_o_modulo(cliente, rodovia):
    app, c = cliente
    r = c.get("/api/cobertura", params={"obra": "rodovia", "folga_alerta_du": 4})
    assert r.status_code == 200
    assert r.json()["marcos"] == C.cobertura(rodovia, folga_alerta_du=4)["marcos"]


def test_rota_404_422_documentados(cliente):
    app, c = cliente
    assert c.get("/api/cobertura", params={"obra": "nao-existe"}).status_code == 404
    assert c.get("/api/cobertura", params={"cenario": "linha_base"}).status_code == 422
    assert c.get("/api/cobertura", params={"folga_alerta_du": -1}).status_code == 422
    op = app.openapi()["paths"]["/api/cobertura"]["get"]
    assert (op.get("description") or "").strip()
    assert {"404", "422"} <= set(op["responses"])


def test_rota_sem_ligar_e_503():
    app = FastAPI()
    app.include_router(rotas_cobertura.router)
    assert TestClient(app).get("/api/cobertura").status_code == 503


# ---------------------------------------------------------------- revisão r17: confiança exige evidência; piso de f
def _rodovia_um_boletim_no_plano(rodovia, ritmo=1.0):
    """Rodovia com UM boletim de TESTE, no ritmo ``ritmo`` × planejado, numa atividade já concluída: toda tarefa
    em aberto fica sem medição própria (planejada) e f = min(1, ritmo)."""
    d = copy.deepcopy(rodovia.dados)
    a = next(x for x in d["atividades"] if x.get("status") == "concluida" and x.get("quantidade_total"))
    d["medicoes"] = [{"atividade_id": a["id"], "semana_inicio": a["inicio_real"], "equipes_dias": 5,
                      "quantidade": ritmo * 5 * a["produtividade_planejada"], "origem": "DADO DE TESTE"}]
    return Projeto(d)


def test_f_igual_a_1_e_cadeia_sem_medicao_e_indeterminada(rodovia):
    """f = 1 (nenhum índice < 1) e a cadeia do M-FIM quase toda sem medição: 'indeterminada', com motivo.
    Antes da r17 saía 'alta' (Δ do estresse × 1 = 0)."""
    r = C.cobertura(_rodovia_um_boletim_no_plano(rodovia))
    assert r["fator_estresse"] == 1.0 and r["fator_estresse_limitado_pelo_piso"] is False
    m = _marco(r, "M-FIM")
    assert m["relatorio_origem"]["fracao_sem_medicao"] > C.FRACAO_SEM_MEDICAO_INDETERMINADA
    assert m["confianca"] == "indeterminada" and "f = 1" in m["motivo"]


def test_f_igual_a_1_com_cobertura_medida_majoritaria_segue_o_delta(rodovia):
    """Dataset real da rodovia com todos os boletins multiplicados por 2 (índices ≥ 1 → f = 1): a cadeia do M-L2-FIM
    é majoritariamente medida (fração sem medição ≤ 0,5), então NÃO é 'indeterminada'; vale a regra do Δ ('alta')."""
    d = copy.deepcopy(rodovia.dados)
    for m in d["medicoes"]:
        m["quantidade"] *= 2
    r = C.cobertura(Projeto(d))
    assert r["fator_estresse"] == 1.0
    m = _marco(r, "M-L2-FIM")
    assert m["relatorio_origem"]["fracao_sem_medicao"] <= C.FRACAO_SEM_MEDICAO_INDETERMINADA
    assert m["confianca"] == "alta" and m["motivo"] is None


def _rodovia_boletim_infimo(rodovia):
    d = copy.deepcopy(rodovia.dados)
    a = next(x for x in d["atividades"] if x.get("status") == "nao_iniciada" and x.get("quantidade_total"))
    d["medicoes"].append({"atividade_id": a["id"], "semana_inicio": "2026-10-05", "quantidade": 0.001,
                          "equipes_dias": 500, "origem": "DADO DE TESTE"})
    return Projeto(d)


def test_piso_de_f_declarado_e_aplicado(rodovia):
    """Boletim ínfimo (0,001 un em 500 equipe·dias) numa atividade não iniciada: índice ~1e-5. Na CONSTRUTORA
    (que não usa o medido) o fator usado é o piso F_MIN, o bruto é exposto e o piso é declarado; nenhum erro."""
    r = C.cobertura(_rodovia_boletim_infimo(rodovia), "construtora")
    assert r["fator_estresse"] == C.F_MIN and r["fator_estresse_limitado_pelo_piso"] is True
    assert r["fator_estresse_observado"] < C.F_MIN  # o par (lote, serviço) agrega o boletim ínfimo com os demais
    assert all(m["confianca"] in ("alta", "media", "baixa", "indeterminada") for m in r["marcos"])


def test_boletim_infimo_na_independente_e_erro_declarado(rodovia):
    """Na INDEPENDENTE a própria previsão usa a produtividade ínfima e a duração estoura o calendário no motor
    (antes de qualquer estresse): ErroCobertura com o motivo (a rota responde 422), nunca exceção crua."""
    with pytest.raises(C.ErroCobertura, match="não pode ser calculado"):
        C.cobertura(_rodovia_boletim_infimo(rodovia), "independente")


@pytest.mark.parametrize("indice, f, piso", [(None, None, False), (0.1, C.F_MIN, True), (0.25, 0.25, False),
                                             (0.6, 0.6, False), (1.3, 1.0, False)])
def test_aplicar_piso(indice, f, piso):
    assert C.aplicar_piso(indice) == (f, piso)


def test_erro_de_calendario_no_estresse_vira_indeterminada(rodovia, monkeypatch):
    """Se a execução estressada estourar o calendário (ErroCalendario), o marco sai 'indeterminada' com o motivo —
    nunca exceção (a rota daria 500). Simulado trocando _estressar por uma versão que gera duração absurda."""
    from infra4d.calendario import ErroCalendario

    original = C._estressar

    def explode(*a, **k):
        raise ErroCalendario("horizonte excedido (teste)")

    monkeypatch.setattr(C, "_estressar", explode)
    r = C.cobertura(rodovia)
    monkeypatch.setattr(C, "_estressar", original)
    assert {m["confianca"] for m in r["marcos"]} == {"indeterminada"}
    assert all("calendário" in m["motivo"] for m in r["marcos"])
