"""Motor CPM: redes pequenas com resultado esperado calculado À MÃO.

Calendário-base: segunda a sexta. 2026-01-05 é segunda-feira.
Datas exibidas: 'inicio' = primeiro dia trabalhado, 'termino' = último dia trabalhado.
"""

from datetime import date

import pytest

from infra4d.calendario import Calendario, ErroCalendario
from infra4d.motor import AtividadeCPM as A
from infra4d.motor import CicloNaRede, ErroRede, Relacao as R, calcular

SEG = date(2026, 1, 5).toordinal()


def cal5(nao_uteis=()):
    return {"c5": Calendario("c5", "5 dias", (0, 1, 2, 3, 4), frozenset(nao_uteis))}


def rodar(ativs, rels, cals=None, **kw):
    cals = cals or cal5()
    res = calcular(ativs, rels, cals, SEG, **kw)
    by = {a.id: a for a in ativs}
    return res, {k: v.como_dict(cals[by[k].calendario], by[k]) for k, v in res.atividades.items()}


def d(s):
    return date.fromisoformat(s).isoformat()


# ------------------------------------------------------------------ calendário
def test_calendario_aritmetica_de_fronteiras():
    c = cal5()["c5"]
    # seg..sex trabalhados -> fronteira = dia seguinte ao último trabalhado (sábado 10)
    assert date.fromordinal(c.somar(SEG, 5)) == date(2026, 1, 10)
    assert date.fromordinal(c.ultimo_dia_util(c.somar(SEG, 5))) == date(2026, 1, 9)
    # inversa: de qualquer fronteira equivalente (sáb 10 ou seg 12) recua até seg 5
    assert date.fromordinal(c.subtrair(date(2026, 1, 10).toordinal(), 5)) == date(2026, 1, 5)
    assert date.fromordinal(c.subtrair(date(2026, 1, 12).toordinal(), 5)) == date(2026, 1, 5)
    assert c.dias_uteis_entre(SEG, date(2026, 1, 19).toordinal()) == 10
    # sábado não é útil: próximo útil é segunda
    assert date.fromordinal(c.proximo_util(date(2026, 1, 10).toordinal())) == date(2026, 1, 12)


def test_calendario_sem_dias_uteis_e_invalido():
    with pytest.raises(ErroCalendario):
        Calendario("x", "x", ())


# ------------------------------------------------------------------- FS série
def test_cadeia_fs_simples():
    res, r = rodar([A("A", 5, "c5"), A("B", 3, "c5")], [R("A", "B")])
    assert r["A"]["inicio"] == d("2026-01-05") and r["A"]["termino"] == d("2026-01-09")
    assert r["B"]["inicio"] == d("2026-01-12") and r["B"]["termino"] == d("2026-01-14")
    assert date.fromordinal(res.termino_projeto_data) == date(2026, 1, 14)
    assert res.caminho_critico == ["A", "B"]
    assert r["A"]["folga_total"] == 0 and r["B"]["folga_total"] == 0


def test_atividades_paralelas_e_folga():
    # A(5) -> C(2); B(2) -> C. B tem folga total 3 e livre 3.
    res, r = rodar([A("A", 5, "c5"), A("B", 2, "c5"), A("C", 2, "c5")],
                   [R("A", "C"), R("B", "C")])
    assert r["C"]["inicio"] == d("2026-01-12")
    assert r["B"]["folga_total"] == 3 and r["B"]["folga_livre"] == 3
    assert not r["B"]["critica"]
    assert set(res.caminho_critico) == {"A", "C"}
    assert res.cadeia_determinante == ["A", "C"]


def test_lag_fs_positivo():
    _, r = rodar([A("A", 2, "c5"), A("B", 1, "c5")], [R("A", "B", "FS", 3)])
    # A: seg-ter (5-6). fronteira qua 7; +3 úteis -> seg 12
    assert r["B"]["inicio"] == d("2026-01-12")


def test_relacao_ss_com_lag():
    _, r = rodar([A("A", 5, "c5"), A("B", 3, "c5")], [R("A", "B", "SS", 2)])
    assert r["B"]["inicio"] == d("2026-01-07") and r["B"]["termino"] == d("2026-01-09")


def test_relacao_ff():
    _, r = rodar([A("A", 5, "c5"), A("B", 2, "c5")], [R("A", "B", "FF", 0)])
    assert r["B"]["inicio"] == d("2026-01-08") and r["B"]["termino"] == d("2026-01-09")


def test_relacao_sf():
    _, r = rodar([A("A", 3, "c5"), A("B", 2, "c5")], [R("A", "B", "SF", 5)])
    # A.es seg 5 + 5 úteis -> fronteira seg 12; B termina ali: qui 8 - sex 9
    assert r["B"]["inicio"] == d("2026-01-08") and r["B"]["termino"] == d("2026-01-09")


def test_feriado_estende_duracao():
    _, r = rodar([A("A", 5, "c5")], [], cals=cal5({date(2026, 1, 7)}))
    assert r["A"]["termino"] == d("2026-01-12")


def test_calendarios_diferentes_por_atividade():
    cals = cal5()
    cals["c6"] = Calendario("c6", "6 dias", (0, 1, 2, 3, 4, 5))
    _, r = rodar([A("A", 6, "c6"), A("B", 1, "c5")], [R("A", "B")], cals=cals)
    # A: seg 5 .. sab 10 ; B: próximo útil do c5 = seg 12
    assert r["A"]["termino"] == d("2026-01-10")
    assert r["B"]["inicio"] == d("2026-01-12")


def test_restricao_inicio_nao_antes_de():
    _, r = rodar([A("A", 2, "c5", restricao_inicio=date(2026, 1, 14).toordinal())], [])
    assert r["A"]["inicio"] == d("2026-01-14")
    assert "restrição" in r["A"]["motivo_inicio"]


def test_marcos():
    _, r = rodar([A("M0", 0, "c5", tipo="marco_inicio"), A("A", 5, "c5"),
                  A("M1", 0, "c5", tipo="marco_termino")],
                 [R("M0", "A"), R("A", "M1")])
    assert r["M0"]["inicio"] == d("2026-01-05")
    assert r["M1"]["termino"] == d("2026-01-09")


# ------------------------------------------------------------- data de status
def test_data_de_status_concluida_em_andamento_e_nao_iniciada():
    ds = date(2026, 1, 14).toordinal()  # quarta
    ativs = [
        A("A", 0, "c5", status="concluida", inicio_real=SEG, termino_real=date(2026, 1, 9).toordinal()),
        A("B", 2, "c5", status="em_andamento", inicio_real=date(2026, 1, 12).toordinal()),
        A("C", 1, "c5"),
        A("D", 1, "c5"),  # sem predecessora: não pode começar antes da data de status
    ]
    _, r = rodar(ativs, [R("A", "B"), R("B", "C")], data_status=ds)
    assert r["A"]["termino"] == d("2026-01-09") and r["A"]["folga_total"] is None
    assert r["B"]["inicio"] == d("2026-01-12") and r["B"]["termino"] == d("2026-01-15")
    assert r["C"]["inicio"] == d("2026-01-16")
    assert r["D"]["inicio"] == d("2026-01-14")


# ------------------------------------------------------------------ inválidos
def test_ciclo_e_detectado_e_nomeado():
    with pytest.raises(CicloNaRede) as e:
        rodar([A("A", 1, "c5"), A("B", 1, "c5"), A("C", 1, "c5")],
              [R("A", "B"), R("B", "C"), R("C", "A")])
    assert set(e.value.ciclo) == {"A", "B", "C"}


def test_autorrelacao_e_ciclo():
    with pytest.raises(CicloNaRede):
        rodar([A("A", 1, "c5")], [R("A", "A")])


@pytest.mark.parametrize("ativs,rels,trecho", [
    ([A("A", -1, "c5")], [], "negativa"),
    ([A("A", 1, "c5")], [R("A", "X")], "inexistente"),
    ([A("A", 1, "zz")], [], "calendário"),
    ([A("A", 1, "c5"), A("B", 1, "c5")], [R("A", "B", "XX")], "inválido"),
    ([A("M", 2, "c5", tipo="marco_inicio")], [], "marco"),
    ([A("A", 1, "c5", status="concluida")], [], "início real"),
])
def test_entradas_invalidas_sao_recusadas(ativs, rels, trecho):
    with pytest.raises(ErroRede) as e:
        rodar(ativs, rels)
    assert trecho in str(e.value)


def test_logica_retida_x_sobrepor():
    """Status qua14. P(5) não iniciada qua14..ter20 (EF qua21) --FS--> S em andamento, remanescente 1.
    sobrepor: S termina qua14; término = ter20 (P); P folga 0.
    retida: o remanescente de S só recomeça depois de P: qua21 (EF qui22); término qua21; S e P críticas."""
    ds = date(2026, 1, 14).toordinal()
    ativs = [A("P", 5, "c5"), A("S", 1, "c5", status="em_andamento", inicio_real=SEG)]
    r1, d1 = rodar(ativs, [R("P", "S")], data_status=ds)
    assert d1["S"]["termino"] == d("2026-01-14") and date.fromordinal(r1.termino_projeto_data) == date(2026, 1, 20)
    r2, d2 = rodar(ativs, [R("P", "S")], data_status=ds, logica_progresso="retida")
    assert d2["S"]["termino"] == d("2026-01-21") and date.fromordinal(r2.termino_projeto_data) == date(2026, 1, 21)
    assert d2["P"]["folga_total"] == 0 and d2["S"]["folga_total"] == 0
    assert set(r2.caminho_mais_longo) == {"P", "S"}
    assert "lógica retida" in d2["S"]["motivo_inicio"]


def test_logica_retida_ignora_ss_ja_satisfeita():
    """SS de P para S em andamento: o início real de S já satisfez a SS -> retida = sobrepor."""
    ds = date(2026, 1, 14).toordinal()
    ativs = [A("P", 5, "c5"), A("S", 1, "c5", status="em_andamento", inicio_real=SEG)]
    _, d2 = rodar(ativs, [R("P", "S", "SS", 2)], data_status=ds, logica_progresso="retida")
    assert d2["S"]["termino"] == d("2026-01-14")


def test_restricao_de_termino_gera_folga_negativa_e_propaga():
    """A(5) seg5–sex9 -> B(3) seg12–qua14. B 'termina até' ter13 (FNLT): LF(B)=qua14 (fronteira) ->
    folga B = qua14 até qui15 = -1? Conta: EF(B)=qui15, LF(B)=fim de ter13=qua14 -> -1 dia útil.
    A: LS(B)=subtrair(qua14,3)=sex9 -> LF(A)=sex9 (fim de qui8) -> folga A = -1.
    As datas cedo NÃO mudam (FNLT só afeta datas tardias, como no P6)."""
    ativs = [A("A", 5, "c5"), A("B", 3, "c5", restricao_termino=date(2026, 1, 13).toordinal())]
    res, r = rodar(ativs, [R("A", "B")])
    assert r["B"]["termino"] == d("2026-01-14")
    assert r["B"]["folga_total"] == -1 and r["A"]["folga_total"] == -1
    assert r["A"]["critica"] and r["B"]["critica"]


def test_logica_desconhecida_e_recusada():
    with pytest.raises(ErroRede):
        rodar([A("A", 1, "c5")], [], logica_progresso="xyz")


def test_atividade_reversa_alongar_antecipa_o_termino():
    """Paradoxo clássico do CPM com relações de início/término (comportamento CORRETO).

    A(10) seg5..sex16 (EF sáb17). A --FF+2--> R --SS+2--> B(5).
    R(3): termina no máx. com A+2 úteis -> EF qua21 -> início sex16. B: sex16+2 úteis -> ter20..seg26.
    R(4): mesmo término -> início qui15. B: qui15+2 -> seg19..sex23.
    Alongar R em 1 dia ANTECIPA o término da obra em 1 dia útil (26/01 -> 23/01)."""
    rels = [R("A", "R", "FF", 2), R("R", "B", "SS", 2)]
    r3, d3 = rodar([A("A", 10, "c5"), A("R", 3, "c5"), A("B", 5, "c5")], rels)
    r4, d4 = rodar([A("A", 10, "c5"), A("R", 4, "c5"), A("B", 5, "c5")], rels)
    assert (d3["R"]["inicio"], d3["B"]["termino"]) == (d("2026-01-16"), d("2026-01-26"))
    assert (d4["R"]["inicio"], d4["B"]["termino"]) == (d("2026-01-15"), d("2026-01-23"))
    assert r4.termino_projeto < r3.termino_projeto


# --------------------------------------------- propagação da mudança de duração
def test_aumentar_duracao_critica_propaga_ate_o_fim_e_folga_absorve_nao_critica():
    base = [A("A", 5, "c5"), A("B", 2, "c5"), A("C", 2, "c5")]
    rels = [R("A", "C"), R("B", "C")]
    r0, _ = rodar(base, rels)
    # +2 dias em B (folga 3): término não muda
    r1, _ = rodar([A("A", 5, "c5"), A("B", 4, "c5"), A("C", 2, "c5")], rels)
    assert r1.termino_projeto == r0.termino_projeto
    # +2 dias em A (crítica): término anda 2 dias úteis
    r2, _ = rodar([A("A", 7, "c5"), A("B", 2, "c5"), A("C", 2, "c5")], rels)
    assert cal5()["c5"].dias_uteis_entre(r0.termino_projeto, r2.termino_projeto) == 2
