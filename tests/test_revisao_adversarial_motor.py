"""Revisão adversarial do motor CPM e de cenarios.py.

Cada teste traz, no docstring, o resultado esperado CALCULADO À MÃO.
Os 26 casos que nasceram como ``xfail(strict=True)`` (22 defeitos confirmados na
revisão de 2026-11-12) foram corrigidos no motor/cenários e viraram testes de
REGRESSÃO normais. O texto "O motor devolve ..." nos docstrings descreve o
comportamento DEFEITUOSO anterior, mantido como registro.

Calendários: c5 = segunda a sexta; c6 = segunda a sábado. 2026-01-05 é segunda.
Convenção de fronteiras semiabertas: EF = dia seguinte ao último trabalhado.
"""

import random
from datetime import date

import pytest

from infra4d.calendario import Calendario, ErroCalendario
from infra4d.cenarios import Ajuste, Projeto, comparar, executar, montar_entrada
from infra4d.motor import AtividadeCPM as A
from infra4d.motor import CicloNaRede, ErroRede, Relacao as R, calcular

SEG = date(2026, 1, 5).toordinal()
DS = date(2026, 1, 14).toordinal()  # quarta-feira, usada como data de status


def o(s):
    return date.fromisoformat(s).toordinal()


def cals():
    return {"c5": Calendario("c5", "5 dias"), "c6": Calendario("c6", "6 dias", (0, 1, 2, 3, 4, 5))}


def rodar(ativs, rels, inicio=SEG, **kw):
    cs = cals()
    res = calcular(ativs, rels, cs, inicio, **kw)
    by = {a.id: a for a in ativs}
    return res, {k: v.como_dict(cs[by[k].calendario], by[k]) for k, v in res.atividades.items()}


def termino_iso(res):
    return date.fromordinal(res.termino_projeto_data).isoformat()


# =============================================================================
# 1. Passadas com FS/SS/FF/SF, lags e calendários — comportamento CORRETO
# =============================================================================
def test_fs_lag_negativo():
    """A(5) seg5–sex9, EF=sáb10. FS-2: recua 2 úteis de sáb10 -> qui8.
    B(3) = qui8, sex9, seg12. Término seg12. Ida e volta exatas: folga 0 nas duas."""
    res, r = rodar([A("A", 5, "c5"), A("B", 3, "c5")], [R("A", "B", "FS", -2)])
    assert (r["B"]["inicio"], r["B"]["termino"]) == ("2026-01-08", "2026-01-12")
    assert r["A"]["folga_total"] == 0 and r["B"]["folga_total"] == 0
    assert res.caminho_critico == ["A", "B"]


def test_fs_lag_negativo_maior_que_a_rede_para_no_inicio_do_projeto():
    """FS-20 pediria B antes do início do projeto: B fica em seg5–qua7 (EF qui8).
    Término = EF de A = sáb10. Folga de B = qui8, sex9 = 2. A crítica (folga 0)."""
    res, r = rodar([A("A", 5, "c5"), A("B", 3, "c5")], [R("A", "B", "FS", -20)])
    assert (r["B"]["inicio"], r["B"]["termino"]) == ("2026-01-05", "2026-01-07")
    assert r["B"]["folga_total"] == 2 and r["A"]["folga_total"] == 0
    assert termino_iso(res) == "2026-01-09"


def test_ff_que_pede_inicio_antes_do_projeto_e_limitada_pelo_piso():
    """A(2) EF qua7. B(5) FF+0 pediria início em 31/12; piso = seg5.
    B seg5–sex9 (EF sáb10) = término. A pode terminar até sáb10: folga qua7,qui8,sex9 = 3."""
    res, r = rodar([A("A", 2, "c5"), A("B", 5, "c5")], [R("A", "B", "FF")])
    assert (r["B"]["inicio"], r["B"]["termino"]) == ("2026-01-05", "2026-01-09")
    assert r["A"]["folga_total"] == 3 and r["B"]["folga_total"] == 0
    assert res.caminho_critico == ["B"]


def test_sf_que_pede_inicio_antes_da_data_de_status_e_limitada_pelo_piso():
    """Status qua14. A(3) qua14–sex16. SF+1: B termina >= qui15 -> início ter13 < status.
    B(2) não pode começar antes de qua14: qua14–qui15."""
    _, r = rodar([A("A", 3, "c5"), A("B", 2, "c5")], [R("A", "B", "SF", 1)], data_status=DS)
    assert (r["B"]["inicio"], r["B"]["termino"]) == ("2026-01-14", "2026-01-15")


def test_lag_e_contado_no_calendario_da_predecessora():
    """A(5, c6) seg5–sex9, EF sáb10. FS+1 no calendário de A (c6): o lag consome o
    SÁBADO 10 -> fronteira dom11 -> B(c5) começa seg12.
    (Se o lag fosse contado no c5 da sucessora, consumiria seg12 e B começaria ter13.)"""
    _, r = rodar([A("A", 5, "c6"), A("B", 1, "c5")], [R("A", "B", "FS", 1)])
    assert r["B"]["inicio"] == "2026-01-12"


def test_duas_relacoes_de_tipos_diferentes_entre_o_mesmo_par():
    """A(5) seg5–sex9. SS+1 -> B >= ter6. FF+1 -> B termina >= fim de seg12 -> início qui8.
    Vence a mais restritiva: B(3) = qui8, sex9, seg12."""
    _, r = rodar([A("A", 5, "c5"), A("B", 3, "c5")], [R("A", "B", "SS", 1), R("A", "B", "FF", 1)])
    assert (r["B"]["inicio"], r["B"]["termino"]) == ("2026-01-08", "2026-01-12")
    assert r["B"]["motivo_inicio"].startswith("FF")


def test_propriedades_da_rede_em_calendario_unico():
    """Propriedade (300 redes aleatórias, semente fixa, 1 calendário, FS/SS/FF/SF, lag -3..4,
    sem restrição nem progresso): (a) folga total >= 0; (b) toda relação é satisfeita em
    tempo de trabalho; (c) atrasar o início em exatamente a folga total NÃO move o término;
    (d) atrasar folga+1 MOVE o término. Vale por definição de folga total."""
    cs = cals()
    c = cs["c5"]
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(2, 5)
        ativs = [A(f"N{i}", rng.randint(1, 6), "c5") for i in range(n)]
        rels, vistos = [], set()
        for j in range(1, n):
            for i in rng.sample(range(j), min(j, rng.randint(1, 2))):
                t = rng.choice(["FS", "SS", "FF", "SF"])
                if (i, j, t) not in vistos:
                    vistos.add((i, j, t))
                    rels.append(R(f"N{i}", f"N{j}", t, rng.randint(-3, 4)))
        res = calcular(ativs, rels, cs, SEG)
        ra = res.atividades
        for rel in rels:
            p, s = ra[rel.predecessora], ra[rel.sucessora]
            alvo = c.somar(p.ef if rel.tipo in ("FS", "FF") else p.es, rel.lag)
            valor = s.es if rel.tipo in ("FS", "SS") else s.ef
            assert c.dias_uteis_entre(valor, alvo) <= 0, (rel, ativs, rels)
        for a in ativs:
            x = ra[a.id]
            assert x.folga_total >= 0, (a.id, ativs, rels)

            def termino_com_atraso(k, a=a, x=x):
                mod = [A(b.id, b.duracao, "c5",
                         restricao_inicio=c.proximo_util(c.somar(x.es, k)) if b.id == a.id and k else None)
                       for b in ativs]
                return calcular(mod, rels, cs, SEG).termino_projeto

            assert termino_com_atraso(x.folga_total) == res.termino_projeto, (a.id, ativs, rels)
            assert termino_com_atraso(x.folga_total + 1) > res.termino_projeto, (a.id, ativs, rels)


# =============================================================================
# 1b. DEFEITOS: calendários diferentes entre predecessora e sucessora
# =============================================================================
@pytest.mark.parametrize("ativs,rel", [
    ([A("A", 6, "c6"), A("B", 2, "c5")], R("A", "B", "FF", 0)),
    ([A("A", 1, "c6"), A("B", 2, "c5")], R("A", "B", "SF", 6)),
])
def test_ff_sf_com_calendarios_diferentes_respeitam_o_termino_da_predecessora(ativs, rel):
    """FF: A(6, c6) trabalha seg5..SÁB10 (EF dom11). B(2, c5) não pode terminar antes de A:
    o primeiro término possível no c5 é o fim de seg12 -> B = sex9 + seg12.
    SF+6: A.ES seg5 + 6 úteis do c6 (seg..sáb) -> alvo dom11; mesmo resultado para B.
    O motor entrega B = qui8–sex9 (termina um dia ANTES do alvo) e folga -1 em A."""
    _, r = rodar(ativs, [rel])
    assert r["B"]["termino"] == "2026-01-12"
    assert r["B"]["inicio"] == "2026-01-09"
    assert r["A"]["folga_total"] >= 0


def test_folga_total_ss_com_sucessora_em_calendario_de_6_dias():
    """X(8, c6): seg5..sáb10, seg12, ter13 -> término (EF) qua14.
    P(1, c5) --SS+0--> S(1, c6) --FS--> Y(2, c6).
    Para trás: Y.LS = seg12; S.LF = dom11 (trabalha sáb10) -> S.LS = SÁB10.
    P (c5) precisa COMEÇAR até sáb10 -> último início útil = sex9 -> LF sáb10.
    P.EF = ter6. Folga total = ter6, qua7, qui8, sex9 = 4.
    O motor devolve 5 (soma a duração a partir de sáb10 e cai em seg12).
    Prova: atrasar P em 5 dias úteis (início seg12) empurra S, Y e o término para 14/01."""
    ativs = [A("X", 8, "c6"), A("P", 1, "c5"), A("S", 1, "c6"), A("Y", 2, "c6")]
    rels = [R("P", "S", "SS"), R("S", "Y")]
    res, r = rodar(ativs, rels)
    assert termino_iso(res) == "2026-01-13"
    ft = r["P"]["folga_total"]
    cs = cals()
    atrasado = [A("X", 8, "c6"), A("P", 1, "c5", restricao_inicio=cs["c5"].somar(SEG, ft)),
                A("S", 1, "c6"), A("Y", 2, "c6")]
    res2, _ = rodar(atrasado, rels)
    assert res2.termino_projeto == res.termino_projeto, "consumir a folga total informada atrasou a obra"
    assert ft == 4


def test_caminho_critico_continuo_com_calendarios_mistos():
    """A(5, c6) seg5–sex9 --FS--> B(1, c5) seg12. A é a única predecessora de B e é quem fixa
    o término (cadeia determinante = A, B). Um caminho crítico contínuo do início ao fim
    tem de conter A. Pelo critério folga<=0, A tem folga 1 (pode usar o sábado) e sai.
    (O P6 tem o mesmo fenômeno com 'Total Float' e o resolve com 'Longest Path'.)"""
    res, _ = rodar([A("A", 5, "c6"), A("B", 1, "c5")], [R("A", "B")])
    assert res.cadeia_determinante == ["A", "B"]
    assert res.caminho_critico == ["A", "B"]


# =============================================================================
# 2. Marcos
# =============================================================================
def test_marco_de_termino_em_dia_nao_util_do_seu_calendario():
    """A(6, c6) termina SÁBADO 10/01. Marco de término M (c5) FS de A.
    M não pode ser exibido antes de 10/01 (aceitável: 10/01 ou 12/01), e o término do
    projeto é 10/01 (último dia trabalhado). O motor exibe M e o projeto em sex 09/01."""
    res, r = rodar([A("A", 6, "c6"), A("M", 0, "c5", tipo="marco_termino")], [R("A", "M")])
    assert r["A"]["termino"] == "2026-01-10"
    assert r["M"]["termino"] >= "2026-01-10"
    assert termino_iso(res) == "2026-01-10"


def test_marco_de_termino_com_restricao_nao_e_exibido_antes_dela():
    """Marco de término com 'não antes de' seg 12/01: a data exibida tem de ser >= 12/01.
    O motor exibe sex 09/01."""
    _, r = rodar([A("M", 0, "c5", tipo="marco_termino", restricao_inicio=o("2026-01-12"))], [])
    assert r["M"]["termino"] >= "2026-01-12"


def test_marco_de_termino_solto_nao_fica_antes_do_inicio_do_projeto():
    """Projeto começa seg 05/01. Um marco de término sem predecessora não pode ter data
    exibida anterior a 05/01. O motor devolve sex 02/01 para o marco e para o projeto."""
    res, r = rodar([A("M", 0, "c5", tipo="marco_termino")], [])
    assert r["M"]["termino"] >= "2026-01-05"
    assert termino_iso(res) >= "2026-01-05"


def test_marco_de_inicio_com_ff_cai_no_proximo_dia_util():
    """A(5) EF sáb10. Marco de início M com FF+0: fronteira sáb10 -> próximo útil seg12."""
    _, r = rodar([A("A", 5, "c5"), A("M", 0, "c5", tipo="marco_inicio")], [R("A", "M", "FF")])
    assert r["M"]["inicio"] == "2026-01-12"


def test_cadeia_determinante_inclui_marco_inicial():
    """M0 (marco de início) -> A(5) -> M1 (marco de término). Só existe um caminho:
    a cadeia determinante é M0, A, M1. O motor devolve A, M1 (M0 empata com o piso)."""
    res, _ = rodar([A("M0", 0, "c5", tipo="marco_inicio"), A("A", 5, "c5"),
                    A("M1", 0, "c5", tipo="marco_termino")], [R("M0", "A"), R("A", "M1")])
    assert res.cadeia_determinante == ["M0", "A", "M1"]


# =============================================================================
# 3. Progresso (em andamento / concluídas) e folga livre
# =============================================================================
def test_sucessora_em_andamento_fora_de_sequencia_nao_restringe_predecessora_fs():
    """Status qua14. P(5) não iniciada --FS--> S em andamento (remanescente 1: qua14, EF qui15).
    Progress override: S ignora P. P = qua14..ter20 (EF qua21) = término. Folga de P = 0."""
    res, r = rodar([A("P", 5, "c5"), A("S", 1, "c5", status="em_andamento", inicio_real=SEG)],
                   [R("P", "S")], data_status=DS)
    assert (r["P"]["inicio"], r["P"]["termino"]) == ("2026-01-14", "2026-01-20")
    assert r["S"]["termino"] == "2026-01-14"
    assert r["P"]["folga_total"] == 0 and termino_iso(res) == "2026-01-20"


def test_sucessora_concluida_nao_restringe_predecessora():
    """Status qua14. P(2) não iniciada --FS--> C concluída (05–09/01). Z(5) solta.
    P = qua14–qui15 (EF sex16); Z = qua14..ter20 (EF qua21) = término.
    Folga de P = sex16, seg19, ter20 = 3. Concluída não tem folga (None)."""
    _, r = rodar([A("P", 2, "c5"), A("C", 0, "c5", status="concluida", inicio_real=SEG, termino_real=o("2026-01-09")),
                  A("Z", 5, "c5")], [R("P", "C")], data_status=DS)
    assert r["P"]["folga_total"] == 3 and r["P"]["folga_livre"] == 3
    assert r["C"]["folga_total"] is None


@pytest.mark.parametrize("tipo,termino,folga", [("SS", "2026-02-02", 4), ("SF", "2026-01-30", 3)])
def test_predecessora_em_andamento_com_ss_ou_sf_nao_gera_folga_negativa(tipo, termino, folga):
    """Status qua14. A em andamento desde 05/01, remanescente 10: qua14..ter27 (EF qua28).
    SS+20: 20 úteis a partir de 05/01 -> B(1) em seg 02/02; término 02/02.
      Folga de A = qua28, qui29, sex30, seg02 = 4.
    SF+20: B termina >= fronteira 31/01 -> B em sex 30/01; término 30/01.
      Folga de A = qua28, qui29, sex30 = 3.
    O início de A já aconteceu: SS/SF não limitam mais o TÉRMINO de A. O motor devolve -7."""
    res, r = rodar([A("A", 10, "c5", status="em_andamento", inicio_real=SEG), A("B", 1, "c5")],
                   [R("A", "B", tipo, 20)], data_status=DS)
    assert r["A"]["termino"] == "2026-01-27" and termino_iso(res) == termino
    assert r["A"]["folga_total"] == folga


def test_ff_para_sucessora_em_andamento_e_consistente_entre_ida_e_volta():
    """Status qua14. S em andamento (remanescente 1 -> EF qui15) -> T(10) qui15..qua28 (EF qui29).
    P(5) não iniciada qua14..ter20 (EF qua21) --FF--> S.
    Ida: S ignora a FF (termina 14/01 embora P termine 20/01). Volta: P.LF = S.LF = qui15.
    Folga de P = -4 sem restrição alguma. Qualquer política coerente dá folga >= 0
    (progress override puro: 6 = qua21..qua28; FF retida: S é empurrada e P fica crítica)."""
    _, r = rodar([A("P", 5, "c5"), A("S", 1, "c5", status="em_andamento", inicio_real=SEG), A("T", 10, "c5")],
                 [R("P", "S", "FF"), R("S", "T")], data_status=DS)
    assert r["P"]["folga_total"] >= 0


def test_folga_livre_nunca_excede_folga_total():
    """A(5) seg5–sex9 --FS-20--> B(3) seg5–qua7. A define o término (folga total 0):
    qualquer atraso em A atrasa a obra, logo folga livre = 0. O motor devolve 15."""
    _, r = rodar([A("A", 5, "c5"), A("B", 3, "c5")], [R("A", "B", "FS", -20)])
    assert r["A"]["folga_total"] == 0
    assert r["A"]["folga_livre"] <= r["A"]["folga_total"]


@pytest.mark.parametrize("ativ", [
    A("A", 0, "c5", status="concluida", inicio_real=o("2026-01-09"), termino_real=SEG),
    A("A", 0, "c5", status="concluida", inicio_real=SEG, termino_real=o("2026-03-02")),
    A("A", 2, "c5", status="em_andamento", inicio_real=o("2026-02-02")),
])
def test_datas_reais_incoerentes_sao_recusadas(ativ):
    """Status 14/01. (1) término real 05/01 < início real 09/01; (2) concluída em 02/03, no
    futuro; (3) em andamento com início real 02/02, no futuro. Esperado: ErroRede.
    O motor calcula normalmente (no caso 1 exibe início 09/01 e término 05/01)."""
    with pytest.raises(ErroRede):
        rodar([ativ], [], data_status=DS)


# =============================================================================
# 4. Restrição SNET
# =============================================================================
def test_snet_empurra_e_folga_e_medida_ate_o_termino():
    """B(10) seg5..sex16 (EF sáb17) define o término. A(2) com SNET qua14: qua14–qui15 (EF sex16).
    Folga total de A = sex16 = 1. SNET num sábado (10/01) cai em seg12."""
    _, r = rodar([A("A", 2, "c5", restricao_inicio=o("2026-01-14")), A("B", 10, "c5"),
                  A("C", 1, "c5", restricao_inicio=o("2026-01-10"))], [])
    assert (r["A"]["inicio"], r["A"]["folga_total"], r["A"]["critica"]) == ("2026-01-14", 1, False)
    assert r["C"]["inicio"] == "2026-01-12"


def test_snet_anterior_a_predecessora_nao_antecipa():
    """A(5) -> B(1) com SNET 06/01: a lógica vence, B em seg12; motivo aponta a relação."""
    _, r = rodar([A("A", 5, "c5"), A("B", 1, "c5", restricao_inicio=o("2026-01-06"))], [R("A", "B")])
    assert r["B"]["inicio"] == "2026-01-12" and r["B"]["motivo_inicio"].startswith("FS")


# =============================================================================
# 5. Robustez
# =============================================================================
def test_atividades_desconectadas():
    """A(5) e B(2) sem relação: término = fim de A (09/01). B: folga total e livre 3."""
    res, r = rodar([A("A", 5, "c5"), A("B", 2, "c5")], [])
    assert res.caminho_critico == ["A"]
    assert (r["B"]["folga_total"], r["B"]["folga_livre"]) == (3, 3)


def test_ciclo_de_dois_nos():
    with pytest.raises(CicloNaRede) as e:
        rodar([A("A", 1, "c5"), A("B", 1, "c5")], [R("A", "B"), R("B", "A", "SS")])
    assert set(e.value.ciclo) == {"A", "B"}


def test_ciclo_com_atividade_a_jusante_e_reportado_como_ciclo():
    """X <-> Y formam ciclo; Y -> A. 'A' não está no ciclo, mas fica com grau > 0 e é o
    primeiro em ordem alfabética. Esperado: CicloNaRede com ciclo {X, Y}."""
    with pytest.raises(CicloNaRede) as e:
        rodar([A("X", 1, "c5"), A("Y", 1, "c5"), A("A", 1, "c5")],
              [R("X", "Y"), R("Y", "X"), R("Y", "A")])
    assert set(e.value.ciclo) == {"X", "Y"}


def test_rede_vazia():
    """Sem atividades: ou ErroRede com mensagem clara, ou término = início do projeto."""
    try:
        res, _ = rodar([], [])
    except ErroRede:
        return
    assert res.termino_projeto == SEG


def test_inicio_antes_do_horizonte_nao_e_deslocado_em_silencio():
    """Projeto inicia seg 01/07/2019. Esperado: A em 01/07/2019, ou ErroCalendario.
    O motor devolve A em 01/01/2020 sem aviso."""
    try:
        _, r = rodar([A("A", 1, "c5")], [], inicio=o("2019-07-01"))
    except ErroCalendario:
        return
    assert r["A"]["inicio"] == "2019-07-01"


def test_datas_fora_do_horizonte_dao_erro_de_calendario():
    """Início em 2018 (mais de 366 dias antes do horizonte) e duração de 4000 dias úteis
    (2026 + ~15,3 anos > 2040) têm de falhar com ErroCalendario, não devolver data errada."""
    with pytest.raises(ErroCalendario):
        rodar([A("A", 1, "c5")], [], inicio=o("2018-07-02"))
    with pytest.raises(ErroCalendario):
        rodar([A("A", 4000, "c5")], [])


def test_ff_com_sucessora_muito_longa_nao_estoura_o_horizonte():
    """A(1) seg5. B(1700) FF: pediria início ~1699 dias úteis antes de 06/01/2026 (meados de 2019).
    Como em test_ff_que_pede_inicio_antes_do_projeto..., B deve começar no piso, seg 05/01/2026
    (1700 dias úteis terminam em 2032, dentro do horizonte)."""
    _, r = rodar([A("A", 1, "c5"), A("B", 1700, "c5")], [R("A", "B", "FF")])
    assert r["B"]["inicio"] == "2026-01-05"


# =============================================================================
# 6. cenarios.py
# =============================================================================
def proj(ativs, rels=(), medicoes=()):
    return Projeto({
        "meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "c5"},
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


def test_duracao_por_quantidade_resiste_a_ponto_flutuante():
    """0,3/0,1 = 2,9999999999999996 em float -> 3 (não 2,99 -> 3 por acaso: ceil dá 3).
    2,1/0,7 = 3,0000000000000004 em float -> tem de ser 3, não 4. 95/(10×2) = 4,75 -> 5.
    Remanescente 0 e não iniciada -> 0."""
    p = proj([qtd("A", 0.3, 0.1), qtd("B", 2.1, 0.7), qtd("C", 95, 10.0, equipes=2), qtd("D", 50, quantidade_executada=50)])
    mem = montar_entrada(p, "construtora")[2]
    assert {k: v["duracao_calculada"] for k, v in mem.items()} == {"A": 3, "B": 3, "C": 5, "D": 0}


def test_ajuste_por_servico_sem_lote_atinge_todos_os_lotes_e_so_o_servico():
    """TER em L1 e L2 (100 m3 a 10/dia = 10 d) e DRE em L1. Ajuste TER -> 5 m3/dia, sem lote:
    as duas TER vão a 20 dias; a DRE fica em 10."""
    p = proj([qtd("T1", 100), qtd("T2", 100, lote_id="L2"), qtd("D1", 100, servico_id="DRE")])
    sim = executar(p, "simulado", [Ajuste.de_dict({"servico_id": "TER", "produtividade": 5})])
    assert {k: v["duracao"] for k, v in sim["atividades"].items()} == {"T1": 20, "T2": 20, "D1": 10}


def test_duracao_fixa_remanescente_nao_sofre_erro_de_ponto_flutuante():
    """Duração fixa 10 dias, 70 % executado: remanescente = 10 × 0,30 = 3 dias. O motor dá 4."""
    p = proj([{"id": "F", "nome": "F", "tipo": "tarefa", "calendario": "c5", "duracao_fixa": 10,
               "percentual_executado": 70, "status": "em_andamento", "inicio_real": "2025-12-01"}])
    assert montar_entrada(p, "construtora")[2]["F"]["duracao_calculada"] == 3


def test_produtividade_efetiva_zero_nao_derruba_o_cenario():
    """Boletim com 5 equipes·dia e quantidade 0 (ex.: semana de chuva). Esperado: um término
    calculado com fonte alternativa declarada, ou erro de domínio claro — nunca ZeroDivisionError."""
    p = proj([qtd("A", 100, status="em_andamento", inicio_real="2025-12-01", quantidade_executada=0)],
             medicoes=[{"atividade_id": "A", "quantidade": 0, "equipes_dias": 5}])
    try:
        r = executar(p, "independente")
    except ValueError:
        return  # erro de domínio explícito é aceitável
    assert r["termino"] is not None


def test_medicao_de_atividade_sem_lote():
    """Atividade sem lote_id com 1 boletim (10 m3 em 1 equipe·dia): produtividade efetiva 10
    -> 100/10 = 10 dias: seg 05/01 a sex 16/01."""
    a = qtd("A", 100)
    del a["lote_id"]
    p = proj([a], medicoes=[{"atividade_id": "A", "quantidade": 10, "equipes_dias": 1}])
    assert executar(p, "independente")["termino"] == "2026-01-16"


def test_memoria_nao_afirma_ceil_de_zero_igual_a_um():
    """Em andamento, 100 de 100 executados: duração 1 por REGRA (não encerrada), não por conta.
    A fórmula auditável não pode dizer que ceil(0) = 1; a regra tem de aparecer na memória."""
    p = proj([qtd("A", 100, status="em_andamento", inicio_real="2025-12-01", quantidade_executada=100)])
    mem = montar_entrada(p, "construtora")[2]["A"]
    assert mem["duracao_calculada"] == 1
    assert "ceil(0.0" not in mem["formula"] or "= 0" in mem["formula"]


def test_explicacao_nao_diz_absorvido_quando_a_folga_e_compartilhada():
    """A(10 d) crítica; em paralelo B(3 d) -> C(4 d), ambas com folga total 3 (a MESMA folga).
    Ajuste DRE 10 -> 6 m3/dia: B 30/6 = 5 (+2), C ceil(40/6) = 7 (+3). Cadeia B+C = 12 > 10:
    término anda +2 dias úteis (16/01 -> 20/01) e a cadeia determinante passa a ser B -> C.
    Nenhuma linha pode dizer que o acréscimo de B ou de C 'não empurra o término'."""
    p = proj([qtd("A", 100), qtd("B", 30, servico_id="DRE"), qtd("C", 40, servico_id="DRE"),
              {"id": "M", "nome": "M", "tipo": "marco_termino", "calendario": "c5", "status": "nao_iniciada"}],
             [{"predecessora": "A", "sucessora": "M"}, {"predecessora": "B", "sucessora": "C"},
              {"predecessora": "C", "sucessora": "M"}])
    ind = executar(p, "independente")
    sim = executar(p, "simulado", [Ajuste.de_dict({"servico_id": "DRE", "produtividade": 6})])
    cmp = comparar(p, ind, sim)
    assert (ind["termino"], sim["termino"], cmp["delta_dias_uteis"]) == ("2026-01-16", "2026-01-20", 2)
    assert sim["cadeia_determinante"][:2] == ["B", "C"]
    assert not any("não empurra o término" in linha for linha in cmp["explicacao"])


def test_explicacao_nao_diz_inalterado_quando_a_data_de_termino_mudou():
    """A (c6): 50 m3 a 10/dia = 5 d (seg5–sex9). Ajuste para 50/6 m3/dia -> 6 d (até SÁB 10/01).
    Término 09/01 -> 10/01 (+1 dia corrido). No calendário da obra (c5) o delta é 0 dias úteis,
    e a explicação afirma 'Término da obra inalterado (2026-01-10)'."""
    p = proj([qtd("A", 50, calendario="c6")])
    ind = executar(p, "independente")
    sim = executar(p, "simulado", [Ajuste.de_dict({"atividade_id": "A", "produtividade": 50 / 6})])
    cmp = comparar(p, ind, sim)
    assert (cmp["termino_ref"], cmp["termino_alvo"], cmp["delta_dias_corridos"]) == ("2026-01-09", "2026-01-10", 1)
    assert not any("inalterado" in linha for linha in cmp["explicacao"])


def test_comparar_linha_de_base_com_cenario_com_progresso():
    """Dataset sintético do projeto: comparar linha_base -> independente tem de devolver uma
    explicação (lista não vazia), sem exceção."""
    p = Projeto.carregar()
    cmp = comparar(p, executar(p, "linha_base"), executar(p, "independente"))
    assert cmp["explicacao"]
