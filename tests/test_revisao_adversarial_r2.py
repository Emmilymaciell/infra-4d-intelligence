"""Revisão adversarial — rodada 2: tentativa de quebrar as CORREÇÕES da rodada 1.

Mesmo protocolo: resultado esperado calculado à mão no docstring. Os 18 casos que
nasceram como ``xfail(strict=True)`` (14 defeitos) foram corrigidos e viraram
REGRESSÃO normal; "O motor devolve ..." nos docstrings descreve o defeito anterior.

Calendários: c5 = seg–sex; c6 = seg–sáb; cF = seg–sex com feriados em
07, 08, 19, 20 e 21/01/2026. 2026-01-05 é segunda. Status de teste: qua 14/01.
"""

import random
from datetime import date

import pytest

from infra4d import montecarlo, painel
from infra4d.calendario import Calendario, ErroCalendario, ordinal
from infra4d.cenarios import Ajuste, Projeto, comparar, executar, montar_entrada, progresso_em
from infra4d.motor import AtividadeCPM as A
from infra4d.motor import Relacao as R, calcular

SEG = date(2026, 1, 5).toordinal()
DS = date(2026, 1, 14).toordinal()


def o(s):
    return date.fromisoformat(s).toordinal()


def cals():
    return {
        "c5": Calendario("c5", "5 dias"),
        "c6": Calendario("c6", "6 dias", (0, 1, 2, 3, 4, 5)),
        "cF": Calendario("cF", "5 dias com feriados", (0, 1, 2, 3, 4), frozenset(
            {date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 19), date(2026, 1, 20), date(2026, 1, 21)})),
    }


CALS = cals()


def rodar(ativs, rels, **kw):
    res = calcular(ativs, rels, CALS, SEG, **kw)
    by = {a.id: a for a in ativs}
    return res, {k: v.como_dict(CALS[by[k].calendario], by[k]) for k, v in res.atividades.items()}


def termino_iso(res):
    return date.fromordinal(res.termino_projeto_data).isoformat()


def MT(i, **k):
    return A(i, 0, "c5", tipo="marco_termino", **k)


def MI(i, **k):
    return A(i, 0, "c5", tipo="marco_inicio", **k)


def _clone(b, **kw):
    d = dict(id=b.id, duracao=b.duracao, calendario=b.calendario, tipo=b.tipo, status=b.status,
             inicio_real=b.inicio_real, termino_real=b.termino_real, restricao_inicio=b.restricao_inicio)
    d.update(kw)
    return A(**d)


# =============================================================================
# 1. Propriedades com calendários mistos e progresso (SEM marcos) — passam
# =============================================================================
def _rede_aleatoria(rng, com_progresso):
    n = rng.randint(2, 5)
    ativs = []
    for i in range(n):
        c = rng.choice(["c5", "c6", "cF"])
        x = rng.random() if com_progresso else 1.0
        if x < 0.2:
            ativs.append(A(f"N{i}", 0, c, status="concluida", inicio_real=SEG, termino_real=SEG + rng.randint(0, 8)))
        elif x < 0.45:
            ativs.append(A(f"N{i}", rng.randint(1, 6), c, status="em_andamento", inicio_real=SEG + rng.randint(0, 8)))
        else:
            ativs.append(A(f"N{i}", rng.randint(1, 6), c))
    rels, vistos = [], set()
    for j in range(1, n):
        for i in rng.sample(range(j), min(j, rng.randint(1, 2))):
            t = rng.choice(["FS", "SS", "FF", "SF"])
            if (i, j, t) not in vistos:
                vistos.add((i, j, t))
                rels.append(R(f"N{i}", f"N{j}", t, rng.randint(-3, 4)))
    return ativs, rels


@pytest.mark.parametrize("com_progresso", [False, True])
def test_propriedades_com_calendarios_mistos_feriados_e_progresso(com_progresso):
    """600 redes aleatórias (semente fixa) só com TAREFAS, calendários c5/c6/cF misturados,
    FS/SS/FF/SF com lag -3..4, com e sem progresso (status qua 14/01). Por definição:
    (a) folga total >= 0 e folga livre <= folga total (não há restrição);
    (b) relações de sucessora não iniciada satisfeitas em tempo real: FS/SS -> ES >= alvo;
        FF/SF -> último dia da sucessora >= último dia útil da predecessora antes do alvo;
    (c) atrasar o início (ou alongar o remanescente, se em andamento) em exatamente a folga
        total não move o término; (d) não iniciada: folga+1 move o término."""
    ds = DS if com_progresso else None
    rng = random.Random(11)
    for _ in range(600):
        ativs, rels = _rede_aleatoria(rng, com_progresso)
        res = calcular(ativs, rels, CALS, SEG, data_status=ds)
        ra, by = res.atividades, {a.id: a for a in ativs}
        ctx = (ativs, rels)
        for rel in rels:
            if by[rel.sucessora].status != "nao_iniciada":
                continue
            p, s = ra[rel.predecessora], ra[rel.sucessora]
            pc = CALS[by[rel.predecessora].calendario]
            alvo = pc.somar(p.ef if rel.tipo in ("FS", "FF") else p.es, rel.lag)
            if rel.tipo in ("FS", "SS"):
                assert s.es >= alvo, (rel, ctx)
            else:
                assert s.ef - 1 >= pc.ultimo_dia_util(alvo), (rel, ctx)
        for a in ativs:
            if a.status == "concluida":
                continue
            x, c = ra[a.id], CALS[a.calendario]
            assert x.folga_total >= 0, (a.id, ctx)
            assert 0 <= x.folga_livre <= x.folga_total, (a.id, ctx)

            def termino(k, a=a, x=x, c=c):
                if a.status == "nao_iniciada":
                    mod = [_clone(b, restricao_inicio=c.proximo_util(c.somar(x.es, k))) if b.id == a.id and k else b
                           for b in ativs]
                else:
                    mod = [_clone(b, duracao=b.duracao + k) if b.id == a.id else b for b in ativs]
                return calcular(mod, rels, CALS, SEG, data_status=ds).termino_projeto

            assert termino(x.folga_total) == res.termino_projeto, (a.id, ctx)
            if a.status == "nao_iniciada":
                assert termino(x.folga_total + 1) > res.termino_projeto, (a.id, ctx)


# =============================================================================
# 2. Marcos (duração 0): onde as correções quebram
# =============================================================================
def test_regra_nova_do_marco_de_termino_casos_basicos():
    """A(5) seg5–sex9 -> M: exibido sex 09/01 (fim do último dia de A).
    Marco solto: fim do 1º dia útil = seg 05/01. SNET sáb 10/01: fim de seg 12/01."""
    _, r = rodar([A("A", 5, "c5"), MT("M"), MT("S"), MT("K", restricao_inicio=o("2026-01-10"))], [R("A", "M")])
    assert (r["M"]["termino"], r["S"]["termino"], r["K"]["termino"]) == ("2026-01-09", "2026-01-05", "2026-01-12")


def test_folga_nao_negativa_com_marco_de_termino_e_lag_negativo():
    """N0(2) seg5–ter6 (EF qua7) --FS-2--> M (marco de término) --FS+3--> N2(2).
    M: qua7 − 2 úteis = seg5. N2: seg5 + 3 úteis -> qui8–sex9 (EF sáb10) = término.
    Caminho único: N0 é crítica com folga total 0 (atrasar N0 1 dia leva M a ter6 e N2 a seg12).
    O motor devolve folga -1 para N0."""
    _, r = rodar([A("N0", 2, "c5"), MT("M"), A("N2", 2, "c5")], [R("N0", "M", "FS", -2), R("M", "N2", "FS", 3)])
    assert (r["N2"]["inicio"], r["N2"]["termino"]) == ("2026-01-08", "2026-01-09")
    assert r["N0"]["folga_total"] == 0


def test_folga_exata_com_marco_de_inicio_e_lag_negativo():
    """N0(1) seg5 (EF ter6) --FS-3--> M (marco de início) --FS+2--> N2(2) qua7–qui8.
    M fica no piso (seg5) enquanto EF(N0) − 3 úteis <= seg5, isto é, EF(N0) <= qui8.
    N0 pode atrasar 2 dias úteis (EF ter6 -> qui8) sem mover nada: folga total = 2.
    O motor devolve 1 (e, com N0 atrasada 2 dias por SNET, devolve folga -1 sem o término mudar)."""
    _, r = rodar([A("N0", 1, "c5"), MI("M"), A("N2", 2, "c5")], [R("N0", "M", "FS", -3), R("M", "N2", "FS", 2)])
    assert r["N2"]["inicio"] == "2026-01-07"
    assert r["N0"]["folga_total"] == 2


def test_afrouxar_o_lag_de_um_marco_nao_atrasa_a_sucessora():
    """A(1) seg5 (EF ter6) --FS lag--> M (marco de término) --FS--> B(1).
    lag -1: alvo = seg5 = piso -> M no início de seg5 -> B em seg 05/01.
    lag -2: alvo = sex 02/01 < piso -> M 'no fim de seg5' -> B em ter 06/01.
    Uma relação MAIS frouxa não pode atrasar B: início de B com lag -2 <= início com lag -1."""
    inicio = {}
    for lag in (-1, -2):
        _, r = rodar([A("A", 1, "c5"), MT("M"), A("B", 1, "c5")], [R("A", "M", "FS", lag), R("M", "B")])
        inicio[lag] = r["B"]["inicio"]
    assert inicio[-2] <= inicio[-1]


def test_marco_de_termino_apos_concluida_nao_atrasa_a_sucessora():
    """Status qua14. C concluída (05–09/01) -> M (marco de término, não iniciado) -> B(1).
    Sem o marco, B começaria na data de status, qua 14/01. Um marco tem duração 0:
    B continua em qua 14/01. O motor põe M no fim de qua14 e B em qui 15/01."""
    _, r = rodar([A("C", 0, "c5", status="concluida", inicio_real=SEG, termino_real=o("2026-01-09")),
                  MT("M"), A("B", 1, "c5")], [R("C", "M"), R("M", "B")], data_status=DS)
    assert r["B"]["inicio"] == "2026-01-14"


@pytest.mark.parametrize("ativs,rels,minimo", [
    ([A("X", 5, "c5"), A("A", 3, "c5"), MT("M")], [R("X", "A"), R("A", "M", "SS")], "2026-01-12"),
    ([MI("M0"), MT("M")], [R("M0", "M")], "2026-01-05"),
])
def test_marco_de_termino_nao_e_exibido_antes_do_evento_que_o_dispara(ativs, rels, minimo):
    """(1) X(5) -> A(3) começa seg 12/01; M com SS+0 de A acontece quando A começa: data >= 12/01.
        O motor exibe DOMINGO 11/01.
    (2) Marco de início M0 em seg 05/01 -> M: data >= 05/01 (início do projeto).
        O motor exibe domingo 04/01, antes do início do projeto."""
    _, r = rodar(ativs, rels)
    assert r["M"]["termino"] >= minimo


def test_tarefa_de_duracao_zero_nao_termina_antes_de_comecar():
    """Z: 50 de 50 m3 executados mas status 'nao_iniciada' -> duração 0. B(2) depois.
    Z ocupa o instante seg 05/01: início e término exibidos têm de ser coerentes (término >= início).
    O motor exibe início 05/01 e término 04/01."""
    p = proj([qtd("Z", 50, quantidade_executada=50), qtd("B", 20)], [{"predecessora": "Z", "sucessora": "B"}])
    z = executar(p, "construtora")["atividades"]["Z"]
    assert z["termino"] >= z["inicio"]


def test_consumir_folga_nao_move_termino_quando_o_final_e_marco_de_inicio():
    """N0(5) seg5–sex9 define o término (09/01). N1(2) seg5–ter6 --FF--> M (marco de início).
    O motor informa folga total 3 para N1. Atrasando N1 3 dias úteis (qui8–sex9), M (FF) vai para
    o próximo início útil, seg 12/01, e o término exibido do projeto passa de 09/01 para 12/01.
    Folga total consumida não pode mover o término."""
    rels = [R("N0", "N1", "SF", 0), R("N0", "M", "SS", 2), R("N1", "M", "FF", 0)]
    res, r = rodar([A("N0", 5, "c5"), A("N1", 2, "c5"), MI("M")], rels)
    ft = r["N1"]["folga_total"]
    assert termino_iso(res) == "2026-01-09" and ft > 0
    res2, _ = rodar([A("N0", 5, "c5"), A("N1", 2, "c5", restricao_inicio=CALS["c5"].somar(SEG, ft)), MI("M")], rels)
    assert termino_iso(res2) == termino_iso(res)


# =============================================================================
# 3. progresso_em / estado 4D / avanço / curva S
# =============================================================================
@pytest.fixture(scope="module")
def projeto():
    return Projeto.carregar()


@pytest.fixture(scope="module")
def resultados(projeto):
    return {c: executar(projeto, c) for c in ("linha_base", "construtora", "independente")}


def _executado(a):
    if a["status"] == "concluida":
        return 1.0
    if a["status"] == "nao_iniciada":
        return 0.0
    if a.get("quantidade_total"):
        return a.get("quantidade_executada", 0) / a["quantidade_total"]
    return a.get("percentual_executado", 0) / 100


def test_progresso_monotono_limitado_e_ancorado_no_real(projeto, resultados):
    """Dataset sintético, 3 cenários, toda atividade, dia a dia do início−3 ao término+5:
    fração em [0, 1], nunca decresce, termina em 1. Nos cenários com status: fração na data de
    status = executado medido (1 para concluída, 0 para não iniciada) e 0 no início real."""
    ds = projeto.data_status
    t1 = max(ordinal(r["termino"]) for r in resultados.values()) + 5
    for c, res in resultados.items():
        d = None if c == "linha_base" else ds
        for a in projeto.dados["atividades"]:
            ra, ant = res["atividades"][a["id"]], 0.0
            for t in range(projeto.inicio_projeto - 3, t1):
                f = progresso_em(projeto, a, ra, t, d)
                assert 0.0 <= f <= 1.0 and f >= ant - 1e-12, (c, a["id"], t)
                ant = f
            assert ant == 1.0, (c, a["id"])
            if d and a.get("tipo", "tarefa") == "tarefa":
                assert progresso_em(projeto, a, ra, ds, d) == pytest.approx(_executado(a), abs=1e-9), (c, a["id"])
                if a["status"] != "nao_iniciada":
                    assert progresso_em(projeto, a, ra, ordinal(a["inicio_real"]), d) == 0.0


def test_avanco_ate_a_data_de_status_independe_do_cenario_e_curva_s_e_monotona(projeto, resultados):
    """Até a data de status o avanço é o REAL: construtora e independente coincidem em qualquer
    data <= status. A curva S de cada cenário começa em 0, termina em 100 e nunca decresce."""
    ds = projeto.data_status
    for t in (projeto.inicio_projeto, ds - 200, ds - 30, ds - 1, ds):
        assert painel.avanco(projeto, resultados["construtora"], t) == pytest.approx(
            painel.avanco(projeto, resultados["independente"], t), abs=1e-12)
    cs = painel.curva_s(projeto, resultados)
    for nome, serie in cs["series"].items():
        assert serie[0] == 0.0 and serie[-1] == 100.0, nome
        assert all(b >= a for a, b in zip(serie, serie[1:])), nome


def test_estado_4d_na_data_de_status_bate_com_o_status_informado(projeto, resultados):
    """Na data de status: concluída -> 'concluido', em andamento -> 'em_execucao',
    não iniciada -> 'nao_iniciado', para todas as atividades do dataset."""
    e = painel.estado_4d(projeto, resultados["independente"], resultados["linha_base"], projeto.data_status)
    mapa = {"concluida": "concluido", "em_andamento": "em_execucao", "nao_iniciada": "nao_iniciado"}
    assert all(e[a["id"]]["estado"] == mapa[a["status"]] for a in projeto.dados["atividades"])


def proj(ativs, rels=(), medicoes=(), ds="2026-01-05"):
    return Projeto({
        "meta": {"inicio_projeto": "2026-01-05", "data_status": ds, "calendario_obra": "c5"},
        "calendarios": [{"id": "c5", "dias_semana": [0, 1, 2, 3, 4]},
                        {"id": "c6", "dias_semana": [0, 1, 2, 3, 4, 5]}],
        "atividades": list(ativs), "relacoes": list(rels), "medicoes": list(medicoes),
    })


def qtd(i, total, prod=10.0, **k):
    d = {"id": i, "nome": i, "tipo": "tarefa", "calendario": "c5", "lote_id": "L1", "servico_id": "TER",
         "unidade": "m3", "quantidade_total": total, "produtividade_planejada": prod, "equipes": 1,
         "status": "nao_iniciada"}
    d.update(k)
    return d


def em_andamento(**k):
    return qtd("A", 100, status="em_andamento", inicio_real="2025-12-01", quantidade_executada=40, **k)


def test_estado_4d_nao_conclui_atividade_em_andamento():
    """10.000 m3, 9.995 executados (99,95 %), status em andamento, remanescente 5 m3 = 1 dia útil.
    Na data de status o estado é 'em_execucao'. O painel devolve 'concluido'."""
    p = proj([qtd("A", 10000, prod=100.0, status="em_andamento", inicio_real="2025-12-01",
                  quantidade_executada=9995)])
    r = executar(p, "independente")
    assert r["atividades"]["A"]["duracao"] == 1
    assert painel.estado_4d(p, r, executar(p, "linha_base"), p.data_status)["A"]["estado"] == "em_execucao"


def test_inicio_real_antes_do_horizonte_nao_derruba_o_estado_4d():
    """Em andamento desde 02/12/2019, 40 % executado. executar() calcula normalmente; logo o estado 4D
    de 02/06/2025 tem de existir (ou a entrada tem de ser recusada antes, com erro de validação)."""
    p = proj([qtd("A", 100, status="em_andamento", inicio_real="2019-12-02", quantidade_executada=40)])
    # Correção escolhida (permitida pelo docstring): recusar na VALIDAÇÃO, com ErroRede claro.
    from infra4d.motor import ErroRede
    try:
        r = executar(p, "independente")
    except ErroRede as e:
        assert "horizonte" in str(e)
        return
    e = painel.estado_4d(p, r, executar(p, "linha_base"), o("2025-06-02"))
    assert 0 < e["A"]["fracao"] < 0.4


# =============================================================================
# 4. Monte Carlo
# =============================================================================
def test_montecarlo_no_dataset_e_reprodutivel_e_ordenado(projeto):
    """Mesma semente -> mesmo resultado. min <= P10 <= P50 <= P80 <= P90 <= max (datas ISO).
    Histograma soma o número de iterações. Iterações fora de 10..2000 são recusadas."""
    m = montecarlo.simular(projeto, 60, 7)
    assert m == montecarlo.simular(projeto, 60, 7)
    seq = [m[k] for k in ("min", "p10", "p50", "p80", "p90", "max")]
    assert seq == sorted(seq)
    assert sum(h["n"] for h in m["histograma"]) == 60
    assert m["deterministico"] == executar(projeto, "independente")["termino"]
    with pytest.raises(ValueError):
        montecarlo.simular(projeto, 5)


def test_montecarlo_com_boletim_de_producao_zero():
    """Único boletim: 5 equipes·dia, quantidade 0. O cenário independente já cai na planejada
    (10 m3/dia, 60 m3 remanescentes -> 6 dias). O Monte Carlo tem de devolver uma faixa também."""
    p = proj([em_andamento()], medicoes=[{"atividade_id": "A", "quantidade": 0, "equipes_dias": 5}])
    assert executar(p, "independente")["atividades"]["A"]["duracao"] == 6
    assert montecarlo.simular(p, 10)["p50"] is not None


@pytest.mark.parametrize("funcao", [lambda p: montecarlo.simular(p, 10), lambda p: painel.producao_semanal(p)])
def test_boletim_orfao_e_tratado_igual_em_todos_os_modulos(funcao):
    """Boletim aponta para 'ZZ', que não existe. executar() funciona (ignora o boletim);
    Monte Carlo e produção semanal têm de funcionar também."""
    p = proj([em_andamento()], medicoes=[{"atividade_id": "ZZ", "quantidade": 5, "equipes_dias": 5,
                                          "semana_inicio": "2025-12-29"}])
    assert executar(p, "independente")["termino"]
    assert funcao(p) is not None


@pytest.mark.parametrize("funcao", [lambda p: montecarlo.simular(p, 10), painel.produtividades])
def test_atividade_sem_lote_e_tratada_igual_em_todos_os_modulos(funcao):
    """Atividade sem lote_id com 1 boletim. executar() funciona; os demais módulos também devem."""
    a = em_andamento()
    del a["lote_id"]
    p = proj([a], medicoes=[{"atividade_id": "A", "quantidade": 5, "equipes_dias": 1}])
    assert executar(p, "independente")["termino"]
    assert funcao(p) is not None


# =============================================================================
# 5. Explicação de comparar()
# =============================================================================
def _contrafactual(projeto, ref_nome, cmp):
    """Para cada duração alterada: término da REFERÊNCIA trocando SÓ aquela duração."""
    ativs, rels, _ = montar_entrada(projeto, ref_nome)
    ds = None if ref_nome == "linha_base" else projeto.data_status
    base = calcular(ativs, rels, projeto.calendarios, projeto.inicio_projeto, data_status=ds).termino_projeto
    por_id = {a.id: a for a in ativs}
    saida = {}
    for m in cmp["duracoes_alteradas"]:
        a = por_id[m["id"]]
        if a.status == "concluida":
            continue
        antigo, a.duracao = a.duracao, m["duracao_depois"]
        try:
            t = calcular(ativs, rels, projeto.calendarios, projeto.inicio_projeto, data_status=ds).termino_projeto
        finally:
            a.duracao = antigo
        linha = next(x for x in cmp["explicacao"] if x.startswith(m["id"] + " ("))
        saida[m["id"]] = (linha, t - base)
    return saida


def test_no_dataset_toda_linha_absorvido_e_verdadeira_isoladamente(projeto, resultados):
    """construtora -> independente: para cada linha que diz 'absorvido e não empurra o término',
    refazer a referência trocando SÓ aquela duração tem de manter o término (contrafactual)."""
    cmp = comparar(projeto, resultados["construtora"], resultados["independente"])
    cf = _contrafactual(projeto, "construtora", cmp)
    absorvidas = {k: d for k, (linha, d) in cf.items() if "absorvido" in linha}
    assert absorvidas and all(d == 0 for d in absorvidas.values()), absorvidas


def test_no_dataset_toda_linha_excedem_e_verdadeira_isoladamente(projeto, resultados):
    """Mesmo contrafactual: se a linha diz que dias 'excedem a folga e se propagam', trocar SÓ aquela
    duração na referência tem de mover o término. Para L3-S04-SUB (+2) e L3-S04-SOL (+1) não move."""
    cmp = comparar(projeto, resultados["construtora"], resultados["independente"])
    cf = _contrafactual(projeto, "construtora", cmp)
    falsas = sorted(k for k, (linha, d) in cf.items() if "excedem a folga" in linha and d == 0)
    assert falsas == []


def test_explicacao_nao_diz_que_propaga_quando_a_ligacao_e_ss():
    """A: 100 m3 a 10/dia = 10 d (05–16/01). B: 200 m3 = 20 d, SS+2 de A -> 07/01 a 03/02 = término.
    Ajuste em A para 100/12 m3/dia -> 12 d (até 20/01). B só depende do INÍCIO de A: nada se
    propaga e o término continua 03/02. A explicação não pode dizer que 2 dias 'se propagam'."""
    p = proj([qtd("A", 100), qtd("B", 200, servico_id="DRE")],
             [{"predecessora": "A", "sucessora": "B", "tipo": "SS", "lag": 2}])
    ind = executar(p, "independente")
    sim = executar(p, "simulado", [Ajuste.de_dict({"atividade_id": "A", "produtividade": 100 / 12})])
    cmp = comparar(p, ind, sim)
    assert (ind["termino"], sim["termino"]) == ("2026-02-03", "2026-02-03")
    assert sim["atividades"]["A"]["duracao"] == 12
    assert not any("se propagam" in linha for linha in cmp["explicacao"])


def test_explicacao_nao_inventa_folga_compartilhada():
    """A(10 d) crítica e B(7 d) em paralelo, ambas -> marco M. Folga de B = 3.
    Ajuste só em B: 70 m3 a 7/dia = 10 d (+3). B consome exatamente a folga: término inalterado (16/01),
    B passa a crítica. Nenhuma outra duração mudou e nada excedeu a folga: a linha não pode dizer
    'COMPARTILHADA' nem 'excedem'."""
    m = {"id": "M", "nome": "M", "tipo": "marco_termino", "calendario": "c5", "status": "nao_iniciada"}
    p = proj([qtd("A", 100), qtd("B", 70, servico_id="DRE"), m],
             [{"predecessora": "A", "sucessora": "M"}, {"predecessora": "B", "sucessora": "M"}])
    ind = executar(p, "independente")
    sim = executar(p, "simulado", [Ajuste.de_dict({"atividade_id": "B", "produtividade": 7})])
    cmp = comparar(p, ind, sim)
    assert (ind["termino"], sim["termino"], len(cmp["duracoes_alteradas"])) == ("2026-01-16", "2026-01-16", 1)
    assert not any("COMPARTILHADA" in linha or "excedem" in linha for linha in cmp["explicacao"])
