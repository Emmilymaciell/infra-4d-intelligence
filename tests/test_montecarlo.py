"""Monte Carlo da previsão independente: reprodutível, ordenado e coerente."""

import pytest

from infra4d.cenarios import Projeto
from infra4d.montecarlo import simular


@pytest.fixture(scope="module")
def resultado():
    return simular(Projeto.carregar(), iteracoes=60, semente=11)


def test_percentis_ordenados(resultado):
    r = resultado
    assert r["min"] <= r["p10"] <= r["p50"] <= r["p80"] <= r["p90"] <= r["max"]


def test_reprodutivel_pela_semente(resultado):
    assert simular(Projeto.carregar(), iteracoes=60, semente=11)["p80"] == resultado["p80"]


def test_deterministico_dentro_da_faixa(resultado):
    """A previsão determinística usa a média medida: deve cair entre min e max."""
    assert resultado["min"] <= resultado["deterministico"] <= resultado["max"]


def test_histograma_soma_iteracoes(resultado):
    assert sum(c["n"] for c in resultado["histograma"]) == resultado["iteracoes"]


def test_endpoint_da_api():
    from fastapi.testclient import TestClient
    from infra4d.api import criar_app
    c = TestClient(criar_app(Projeto.carregar()))
    r = c.get("/api/previsao-probabilistica", params={"iteracoes": 30})
    assert r.status_code == 200 and r.json()["p50"] <= r.json()["p80"]
    assert c.get("/api/previsao-probabilistica", params={"iteracoes": 3}).status_code == 422


def test_iteracoes_fora_do_limite_recusadas():
    with pytest.raises(ValueError):
        simular(Projeto.carregar(), iteracoes=5)


# =========================================================================== v2
import random  # noqa: E402
from datetime import date  # noqa: E402

from infra4d.calendario import ordinal  # noqa: E402
from infra4d.cenarios import DATASET_PADRAO, Ajuste, executar  # noqa: E402
from infra4d.montecarlo import _boletins, _fonte, _histograma  # noqa: E402

RODOVIA = DATASET_PADRAO.parent / "rodovia_ficticia.json"


def _oraculo_v1(projeto, iteracoes, semente):
    """Cópia CONGELADA do laço de amostragem da v1 (antes da v2), para comparar bit a bit. O substituto sem
    boletim mudou depois (r10: U(0,85; 1,15)); nas duas obras ele não é usado (ver
    test_obras_sinteticas_nao_usam_o_substituto_sem_boletim), por isso a comparação continua exata."""
    rng = random.Random(semente)
    por = _boletins(projeto)
    alvo = [a for a in projeto.dados["atividades"] if a.get("quantidade_total") and a.get("status") != "concluida"]
    fontes = {a["id"]: _fonte(por, a) for a in alvo}
    terminos = []
    for _ in range(iteracoes):
        sorteio_frente, ajustes = {}, []
        for a in alvo:
            chave, bs = fontes[a["id"]]
            frente = (a.get("lote_id"), a.get("servico_id"))
            if frente not in sorteio_frente:
                sorteio_frente[frente] = rng.random()
            sub = random.Random(f"{sorteio_frente[frente]!r}|{chave!r}")
            prod = 0.0
            if bs:
                amostra = [sub.choice(bs) for _ in bs]
                q = sum(x for x, _ in amostra)
                e = sum(y for _, y in amostra)
                prod = q / e if e > 0 else 0.0
            if prod <= 0:
                prod = a["produtividade_planejada"] * sub.uniform(0.80, 1.05)
            ajustes.append(Ajuste(produtividade=prod, atividade_id=a["id"]))
        terminos.append(ordinal(executar(projeto, "simulado", ajustes)["termino"]))
    terminos.sort()
    return terminos


# valores da v1 gravados ANTES da mudança (ferrovia, 60 iterações, semente 11)
V1_FERROVIA_60_11 = {"deterministico": "2027-09-09", "p10": "2027-09-04", "p50": "2027-09-10", "p80": "2027-09-13",
                     "p90": "2027-09-14", "min": "2027-09-02", "max": "2027-09-16"}
V1_FERROVIA_60_11_HIST = [2, 5, 3, 18, 19, 3, 6, 4]


def test_v2_com_padroes_reproduz_v1_gravada(resultado):
    r = resultado
    assert {k: r[k] for k in V1_FERROVIA_60_11} == V1_FERROVIA_60_11
    assert [h["n"] for h in r["histograma"]] == V1_FERROVIA_60_11_HIST
    assert r["versao"] == "v1" and "v2" not in r


@pytest.mark.parametrize("arquivo", [DATASET_PADRAO, RODOVIA])
def test_rho_zero_sem_riscos_igual_ao_oraculo_v1(arquivo):
    P = Projeto.carregar(arquivo)
    t = _oraculo_v1(P, 30, 5)
    r = simular(P, 30, 5, rho=0.0, com_riscos=False, com_chuva=False)

    def iso(o):
        return date.fromordinal(o).isoformat()

    assert (r["min"], r["max"], r["p50"], r["p90"]) == (iso(t[0]), iso(t[-1]), iso(t[15]), iso(t[27]))
    assert r["histograma"] == _histograma(t)


def _rede_serie(n=4):
    """n frentes do MESMO serviço (lotes diferentes) em série, 100 un cada; boletins variáveis."""
    ativs, rels, meds = [], [], []
    for i in range(n):
        aid = f"F{i}"
        ativs.append({"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": f"L{i}", "servico_id": "S",
                      "quantidade_total": 100.0, "produtividade_planejada": 10.0, "equipes": 1,
                      "calendario": "C", "status": "nao_iniciada"})
        meds += [{"atividade_id": aid, "quantidade": q, "equipes_dias": 1.0} for q in (4.0, 8.0, 12.0, 20.0)]
        if i:
            rels.append({"predecessora": f"F{i - 1}", "sucessora": aid, "tipo": "FS", "lag": 0})
    return Projeto({"meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "C"},
                    "lotes": [{"id": f"L{i}"} for i in range(n)],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                    "servicos": [], "atividades": ativs, "relacoes": rels, "medicoes": meds})


def test_rho_maior_alarga_a_faixa():
    P = _rede_serie()
    baixo = simular(P, 400, 3, rho=0.01, comparar_v1=False)["largura_p10_p90_dias"]
    alto = simular(P, 400, 3, rho=0.95, comparar_v1=False)["largura_p10_p90_dias"]
    v1 = simular(P, 400, 3)["largura_p10_p90_dias"]
    assert alto > baixo and alto > v1


def _rede_risco():
    # seg–sex. A (5) → B (5) FS; C (1) paralela. Determinístico: A 05..09/01, B 12..16/01.
    def t(aid, d):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": "L1", "servico_id": "S", "duracao_fixa": d,
                "calendario": "C", "status": "nao_iniciada"}
    return Projeto({"meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "C"},
                    "lotes": [{"id": "L1"}],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []}],
                    "servicos": [], "atividades": [t("A", 5), t("B", 5), t("C", 1)],
                    "relacoes": [{"predecessora": "A", "sucessora": "B", "tipo": "FS", "lag": 0}]})


def _risco(aid, p, imp, rid="R1"):
    return [{"id": rid, "descricao": "teste", "probabilidade": p, "atividade_id": aid, "impacto_dias_uteis": imp}]


def test_risco_certo_em_atividade_critica_desloca_exatamente_o_impacto():
    P = _rede_risco()
    r = simular(P, 20, 1, com_riscos=True, riscos=_risco("B", 1.0, 3))
    assert r["deterministico"] == "2026-01-16"
    # +3 dias úteis depois de sex 16/01: seg 19, ter 20, qua 21
    assert r["p10"] == r["p90"] == r["min"] == r["max"] == "2026-01-21"
    assert r["v2"]["riscos"]["frequencia_observada"] == {"R1": 1.0}
    assert r["faixa_v1"]["p50"] == "2026-01-16"
    # risco certo em atividade NÃO crítica (C, folga 9) não move o término
    assert simular(P, 20, 1, com_riscos=True, riscos=_risco("C", 1.0, 2))["max"] == "2026-01-16"
    # probabilidade 0: nada
    assert simular(P, 20, 1, com_riscos=True, riscos=_risco("B", 0.0, 9))["max"] == "2026-01-16"
    with pytest.raises(ValueError):
        simular(P, 20, 1, com_riscos=True, riscos=_risco("B", 1.5, 1))


def test_lista_de_riscos_sintetica_quando_a_obra_nao_tem():
    P = Projeto.carregar()
    r = simular(P, 20, 2, com_riscos=True)
    lista = r["v2"]["riscos"]["lista"]
    assert lista and all(x["sintetico"] for x in lista) and "SINTÉTICA" in r["v2"]["riscos"]["origem"]
    det = executar(P, "independente")
    assert all(x["atividade_id"] in det["caminho_critico"] for x in lista)
    assert r["faixa_v1"]["p50"] <= r["p90"]


def test_chuva_certa_no_mes_empurra_o_inicio():
    # atividade por quantidade sem boletins: 50 un ÷ (10 × U(0,85; 1,15)) => 5 ou 6 dias, a partir de seg 05/01.
    # Com chuva p=1 em janeiro, todo janeiro é perdido: começa em 01/02 (calendário corrido) => tudo depois.
    P = Projeto({"meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "C"},
                 "lotes": [{"id": "L1"}],
                 "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                 "servicos": [], "relacoes": [],
                 "atividades": [{"id": "A", "nome": "A", "tipo": "tarefa", "lote_id": "L1", "servico_id": "S",
                                 "quantidade_total": 50.0, "produtividade_planejada": 10.0, "equipes": 1,
                                 "calendario": "C", "status": "nao_iniciada"}]})
    seco = simular(P, 30, 4)
    chuva = simular(P, 30, 4, com_chuva=True, meses_chuvosos=(1,), p_chuva=1.0)
    assert seco["max"] <= "2026-01-11"
    assert chuva["min"] >= "2026-02-05" and chuva["min"] > seco["max"]
    assert chuva["v2"]["chuva"]["calendarios"] == ["C"]


def test_v2_reprodutivel_pela_semente():
    P = Projeto.carregar(RODOVIA)
    a = simular(P, 20, 9, rho=0.5, com_riscos=True, com_chuva=True)
    b = simular(P, 20, 9, rho=0.5, com_riscos=True, com_chuva=True)
    assert a == b
    assert a["versao"] == "v2" and a["faixa_v1"]["largura_p10_p90_dias"] >= 0
    with pytest.raises(ValueError):
        simular(P, 20, 9, rho=1.5)


# =========================================================================== índice de criticidade
def _rede_criticidade():
    """Calendário corrido, início 01/01/2026 = data de status, tudo não iniciado.

    X (lote L1, 120 un, 1 equipe): 2 boletins de 1 eq·dia, 10 e 15 un. Bootstrap de 2 com reposição:
      {10,10} p=1/4 -> 10 un/dia -> 12 d;  {10,15} p=1/2 -> 12,5 -> ⌈9,6⌉ = 10 d;  {15,15} p=1/4 -> 15 -> 8 d.
    Y (lote L2, 110 un): 1 boletim de 10 un/eq·dia -> sempre 11 d.
    Z (duração fixa 5) depois de X e Y (FS); W (duração fixa 1) solta, em paralelo.
    Analítico: X crítica <=> X = 12 d: P = 1/4. Y crítica <=> X <= 10: P = 3/4. Z sempre (1,0); W nunca (0,0).
    Término = max(X, 11) + 5: sobe com X => correlação duração×término de X positiva; Y constante => None."""
    def q(aid, lote, qtd):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": lote, "servico_id": "S", "quantidade_total": qtd,
                "produtividade_planejada": 10.0, "equipes": 1, "calendario": "C", "status": "nao_iniciada"}

    def f(aid, d):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": "L1", "servico_id": "F", "duracao_fixa": d,
                "calendario": "C", "status": "nao_iniciada"}

    meds = [{"atividade_id": "X", "semana_inicio": "2025-12-01", "quantidade": 10.0, "equipes_dias": 1.0},
            {"atividade_id": "X", "semana_inicio": "2025-12-08", "quantidade": 15.0, "equipes_dias": 1.0},
            {"atividade_id": "Y", "semana_inicio": "2025-12-01", "quantidade": 10.0, "equipes_dias": 1.0}]
    return Projeto({"meta": {"inicio_projeto": "2026-01-01", "data_status": "2026-01-01", "calendario_obra": "C"},
                    "lotes": [{"id": "L1"}, {"id": "L2"}],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                    "servicos": [], "medicoes": meds,
                    "atividades": [q("X", "L1", 120.0), q("Y", "L2", 110.0), f("Z", 5), f("W", 1)],
                    "relacoes": [{"predecessora": "X", "sucessora": "Z", "tipo": "FS", "lag": 0},
                                 {"predecessora": "Y", "sucessora": "Z", "tipo": "FS", "lag": 0}]})


@pytest.fixture(scope="module")
def criticidade():
    # 2000 iterações: desvio-padrão de p = 1/4 é √(p(1−p)/N) ≈ 0,0097
    return simular(_rede_criticidade(), 2000, 13, com_criticidade=True)


def test_indice_de_criticidade_bate_com_a_probabilidade_analitica(criticidade, limite):
    tol = limite("tolerancia_criticidade")
    ic = {x["id"]: x for x in criticidade["criticidade"]["atividades"]}
    assert abs(ic["X"]["indice"] - 0.25) <= tol
    assert abs(ic["Y"]["indice"] - 0.75) <= tol
    assert ic["Z"]["indice"] == 1.0 and ic["W"]["indice"] == 0.0


def test_cruciality_correlacao_duracao_termino(criticidade):
    ic = {x["id"]: x for x in criticidade["criticidade"]["atividades"]}
    assert ic["X"]["correlacao_duracao_termino"] > 0.5
    assert ic["Y"]["correlacao_duracao_termino"] is None  # duração constante
    assert ic["Z"]["correlacao_duracao_termino"] is None
    # ordenação: índice decrescente
    idx = [x["indice"] for x in criticidade["criticidade"]["atividades"]]
    assert idx == sorted(idx, reverse=True)


def test_criticidade_por_grupo_lote_servico(criticidade, limite):
    g = {(x["lote_id"], x["servico_id"]): x["indice"] for x in criticidade["criticidade"]["grupos"]}
    assert g[("L1", "F")] == 1.0  # Z sempre
    assert abs(g[("L1", "S")] - 0.25) <= limite("tolerancia_criticidade")
    assert abs(g[("L2", "S")] - 0.75) <= limite("tolerancia_criticidade")


def test_criticidade_reprodutivel_e_nao_altera_a_faixa():
    P = _rede_criticidade()
    a = simular(P, 50, 3, com_criticidade=True)
    b = simular(P, 50, 3, com_criticidade=True)
    c = simular(P, 50, 3)
    assert a == b
    assert {k: a[k] for k in ("p10", "p50", "p90", "histograma")} == {k: c[k] for k in ("p10", "p50", "p90", "histograma")}
    assert "criticidade" not in c


def test_criticidade_na_ferrovia_com_padrao_identico_a_v1(resultado):
    P = Projeto.carregar()
    r = simular(P, iteracoes=60, semente=11, com_criticidade=True)
    assert {k: r[k] for k in V1_FERROVIA_60_11} == V1_FERROVIA_60_11
    top = r["criticidade"]["atividades"][0]
    assert top["indice"] == 1.0  # há atividade crítica em todas as iterações
    assert all(0.0 <= x["indice"] <= 1.0 for x in r["criticidade"]["atividades"])
    # também no caminho v2
    r2 = simular(P, 20, 5, com_riscos=True, com_criticidade=True, comparar_v1=False)
    assert r2["criticidade"]["iteracoes"] == 20


# =========================================================================== boletins por estado
def test_estados_padrao_identico_a_v1(resultado):
    r = simular(Projeto.carregar(), iteracoes=60, semente=11, estados=None)
    assert {k: r[k] for k in V1_FERROVIA_60_11} == V1_FERROVIA_60_11
    assert r["fonte_boletins"]["filtro"] is None


def test_estados_filtra_boletins_pela_fiscalizacao():
    from infra4d import fiscalizacao
    P = Projeto.carregar()
    est = fiscalizacao.boletins_estendidos(P, fiscalizacao.diarios_da_obra(P))
    aprovados = {(b["atividade_id"], b["periodo_ini"]) for b in est if b["estado"] == "aprovado"}
    r = simular(P, 20, 4, estados=("aprovado",))
    fb = r["fonte_boletins"]
    assert fb["filtro"] == ["aprovado"] and fb["origem_estado"].startswith("fiscalizacao")
    assert 0 < fb["usados"] < fb["total"] and fb["usados"] + fb["descartados"] == fb["total"]
    assert aprovados  # existem boletins aprovados
    todos = simular(P, 20, 4, estados=("aprovado", "conferido_fiscal", "lancado"))
    assert todos["fonte_boletins"]["usados"] == todos["fonte_boletins"]["total"] - todos["fonte_boletins"]["sem_estado"]
    with pytest.raises(ValueError):
        simular(P, 20, 4, estados=("xpto",))


# =========================================================================== r10: substituto sem boletim
@pytest.mark.parametrize("arquivo", [DATASET_PADRAO, RODOVIA])
def test_obras_sinteticas_nao_usam_o_substituto_sem_boletim(arquivo):
    """Garante a premissa da comparação bit a bit com a v1: toda frente em aberto tem fonte de boletins."""
    P = Projeto.carregar(arquivo)
    por = _boletins(P)
    alvo = [a for a in P.dados["atividades"] if a.get("quantidade_total") and a.get("status") != "concluida"]
    assert alvo and all(_fonte(por, a)[0] is not None for a in alvo)


def test_obra_sem_boletins_tem_o_deterministico_dentro_da_faixa():
    """Sem boletins, o independente usa a planejada (× 1) e o MC sorteia planejada × U(0,85; 1,15), centrado
    em 1. Cadeia A → B, 100 un cada, planejada 10: determinístico 10 + 10 dias. Faixa: cada uma entre
    ⌈100/11,5⌉ = 9 e ⌈100/8,5⌉ = 12 dias."""
    def q(aid):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": "L1", "servico_id": aid, "quantidade_total": 100.0,
                "produtividade_planejada": 10.0, "equipes": 1, "calendario": "C", "status": "nao_iniciada"}
    P = Projeto({"meta": {"inicio_projeto": "2026-01-01", "data_status": "2026-01-01", "calendario_obra": "C"},
                 "lotes": [{"id": "L1"}], "servicos": [], "medicoes": [],
                 "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                 "atividades": [q("A"), q("B")],
                 "relacoes": [{"predecessora": "A", "sucessora": "B", "tipo": "FS", "lag": 0}]})
    for kw in ({}, {"rho": 0.5, "comparar_v1": False}):
        r = simular(P, 200, 3, **kw)
        assert r["deterministico"] == "2026-01-20"
        assert r["min"] < r["deterministico"] < r["max"]
        assert "2026-01-18" <= r["min"] and r["max"] <= "2026-01-24"


# =========================================================================== P4: incerteza sem medição
def test_sem_medicao_desligado_e_identico(resultado):
    r = simular(Projeto.carregar(), iteracoes=60, semente=11, incerteza_sem_medicao=False)
    assert {k: r[k] for k in V1_FERROVIA_60_11} == V1_FERROVIA_60_11 and "incerteza_sem_medicao" not in r


def _rede_sem_medicao():
    """Frentes MEDIDAS: X (L1/TER, 5 contra 10 planejada => índice 0,5) e W (L1/DRE, 15 => índice 1,5).
    Sem medição própria: Y (L1/SUB, 100 un, sem boletim e sem analogia) e Z (L2/TER: analogia com X pelo
    serviço). Sem o modo, Y = planejada × U(0,85; 1,15) => ⌈100/11,5⌉ = 9 a ⌈100/8,5⌉ = 12 dias. Com o modo
    (alargamento 0,2), Y = 10 × {0,5 ou 1,5} × U(0,8; 1,2): 4–6 un/dia (17–25 dias) OU 12–18 un/dia (6–9 dias).
    Tudo em paralelo; as demais são curtas (<= 4 dias): o término é o de Y."""
    def q(aid, lote, serv, qtd):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": lote, "servico_id": serv, "quantidade_total": qtd,
                "produtividade_planejada": 10.0, "equipes": 1, "calendario": "C", "status": "nao_iniciada"}
    return Projeto({"meta": {"inicio_projeto": "2026-01-01", "data_status": "2026-01-01", "calendario_obra": "C"},
                    "lotes": [{"id": "L1"}, {"id": "L2"}], "servicos": [], "relacoes": [],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                    "atividades": [q("X", "L1", "TER", 10.0), q("W", "L1", "DRE", 10.0), q("Y", "L1", "SUB", 100.0),
                                   q("Z", "L2", "TER", 10.0)],
                    "medicoes": [{"atividade_id": "X", "semana_inicio": "2025-12-01", "quantidade": 5.0,
                                  "equipes_dias": 1.0},
                                 {"atividade_id": "W", "semana_inicio": "2025-12-01", "quantidade": 15.0,
                                  "equipes_dias": 1.0}]})


def test_sem_medicao_faixa_calculada_a_mao():
    P = _rede_sem_medicao()
    sem = simular(P, 300, 5)
    assert "2026-01-09" <= sem["min"] and sem["max"] <= "2026-01-12"
    com = simular(P, 300, 5, incerteza_sem_medicao=True, alargamento=0.2)
    # as DUAS caudas da distribuição empírica aparecem (a média 1,0 daria só 9–13 dias)
    assert "2026-01-06" <= com["min"] <= "2026-01-08" and "2026-01-17" <= com["max"] <= "2026-01-25"
    info = com["incerteza_sem_medicao"]
    assert info["ativo"] and info["grupos"] == ["L1/SUB", "L2/TER"] and info["atividades"] == ["Y", "Z"]
    assert info["indices"] == [1.5, 0.5] and info["indices_observados"] == 2
    assert simular(P, 300, 5, incerteza_sem_medicao=True, alargamento=0.2) == com  # reprodutível
    with pytest.raises(ValueError):
        simular(P, 20, 5, incerteza_sem_medicao=True, alargamento=1.0)


def test_sem_medicao_sem_nenhuma_frente_medida_declara_e_nao_muda():
    P = _rede_sem_medicao()
    P.dados["medicoes"] = []
    P = Projeto(P.dados)
    r = simular(P, 30, 5, incerteza_sem_medicao=True)
    assert not r["incerteza_sem_medicao"]["ativo"] and "nota" in r["incerteza_sem_medicao"]
    assert {k: r[k] for k in ("p10", "p90")} == {k: simular(P, 30, 5)[k] for k in ("p10", "p90")}


def test_rodovia_2026_03_30_p80_do_m_l2_fim_mais_tarde_com_o_modo():
    from infra4d.calendario import ordinal
    from infra4d.tendencia import fotografia
    P = Projeto.carregar(RODOVIA)
    foto = Projeto(fotografia(P.dados, ordinal("2026-03-30")))
    sem = simular(foto, 100, 7, por_marco=True)["marcos"]["M-L2-FIM"]
    com = simular(foto, 100, 7, por_marco=True, incerteza_sem_medicao=True)["marcos"]["M-L2-FIM"]
    assert com["p80"] > sem["p80"]
    assert com["largura_p10_p90_dias"] > sem["largura_p10_p90_dias"]


def test_realidade_simulada_cai_mais_vezes_na_faixa_com_o_modo():
    """Datas da MTA da rodovia (passo de 8 semanas), 40 iterações, todos os marcos de término: contagem de
    vezes em que o término da REALIDADE SIMULADA (backtest.realidade_da_obra) cai em [P10, P90]."""
    from infra4d.backtest import realidade_da_obra
    from infra4d.tendencia import datas_de_status, fotografia
    P = Projeto.carregar(RODOVIA)
    real, motivo = realidade_da_obra(P.dados)
    assert real, motivo
    marcos = [a["id"] for a in P.dados["atividades"] if a.get("tipo") == "marco_termino"]
    dentro = {False: 0, True: 0}
    for d in datas_de_status(P.dados, 56):
        foto = P if d == P.data_status else Projeto(fotografia(P.dados, d))
        for modo in (False, True):
            r = simular(foto, 40, 7, por_marco=True, incerteza_sem_medicao=modo)
            dentro[modo] += sum(r["marcos"][m]["p10"] <= real[m] <= r["marcos"][m]["p90"] for m in marcos)
    assert dentro[True] > dentro[False], dentro


TOL_P50_P4 = 1  # dias: ruído de amostragem com 100 iterações (declarado)


@pytest.mark.parametrize("arquivo", [DATASET_PADRAO, RODOVIA])
@pytest.mark.parametrize("semente", [7, 2])
def test_p4_nao_antecipa_o_p50_nem_o_p90(arquivo, semente):
    """r19: o modo acrescenta dúvida, não informação favorável. Com a analogia como centro, P50 e P90 com o modo
    não ficam ANTES dos de sem o modo. Tolerância DECLARADA no P50: 1 dia (ruído de 100 iterações: ferrovia,
    semente 7, dá −1; com 200 iterações, 4 sementes × 2 obras, ΔP50 vai de 0 a +8 e ΔP90 de +9 a +32 dias).
    O P90 tem de ficar estritamente mais tarde. A troca da analogia pela obra inteira (o defeito da r19) dá
    ΔP50 de −4 a −9 dias; normalizar pela média harmônica (centro otimista) dá −2."""
    from infra4d.calendario import ordinal
    P = Projeto.carregar(arquivo)
    sem = simular(P, 100, semente)
    com = simular(P, 100, semente, incerteza_sem_medicao=True)
    assert ordinal(com["p50"]) >= ordinal(sem["p50"]) - TOL_P50_P4 and ordinal(com["p90"]) > ordinal(sem["p90"])
    assert com["incerteza_sem_medicao"]["indices_por_servico"]
