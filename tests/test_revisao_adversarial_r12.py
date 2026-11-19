"""Revisão adversarial — rodada 12: dcma.py (DCMA 14 pontos) e produtividade_terraplenagem.py (+ rotas).

Mesmo protocolo: esperado calculado à mão no docstring; defeito confirmado fica
``xfail(strict=True, reason="DEFEITO: ...")``.

O que foi conferido no DCMA é se cada métrica segue a DEFINIÇÃO QUE O PRÓPRIO CÓDIGO DECLARA (população,
divisor, comparação). Não consultei a página da Deltek nem as diretrizes do DCMA nesta rodada: não afirmo
que os limites citados no módulo estão certos, só que o cálculo bate com o que ele diz fazer.
"""

import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import dcma
from infra4d import produtividade_terraplenagem as PT
from infra4d.calendario import Calendario
from infra4d.cenarios import Projeto
from infra4d.massas import Secao, calcular_massas, massas_da_obra
from infra4d.motor import AtividadeCPM as A
from infra4d.motor import Relacao as R

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")
CALS = {"c5": Calendario("c5", "5 dias"), "c6": Calendario("c6", "6 dias", (0, 1, 2, 3, 4, 5))}


def o(s):
    return date.fromisoformat(s).toordinal()


SEG = o("2026-01-05")


def ponto(r, n):
    return next(p for p in r["pontos"] if p["numero"] == n)


@pytest.fixture(scope="module")
def obras():
    return {x: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{x}_ficticia.json") for x in OBRAS}


@pytest.fixture(scope="module")
def cliente(obras):
    from infra4d.api import criar_app
    return TestClient(criar_app(fontes=dict(obras)), raise_server_exceptions=False)


# =============================================================================
# 1. DCMA — as 14 métricas numa rede calculada à mão
# =============================================================================
def _rede_dcma():
    """Status seg 19/01/2026; calendário de 5 dias; início 05/01.
    C  concluída 05–09/01            E  em andamento desde 12/01, remanescente 5
    N1 50 dias                       N2 10 dias, FNLT 06/02       N3 3 dias, SNET 02/02
    M  marco de término              Z  tarefa de duração 0
    Relações: C→E FS; E→N1 FS; E→N2 SS+2; N2→M FS−1; N1→M FS; C→Z FS; N3→M FF.
    Linha de base (término): C 09/01, E 16/01, N1 27/03, N2 27/01, N3 07/01. Prazo contratual 27/03."""
    ats = [A("C", 0, "c5", status="concluida", inicio_real=SEG, termino_real=o("2026-01-09")),
           A("E", 5, "c5", status="em_andamento", inicio_real=o("2026-01-12")),
           A("N1", 50, "c5"), A("N2", 10, "c5", restricao_termino=o("2026-02-06")),
           A("N3", 3, "c5", restricao_inicio=o("2026-02-02")), A("M", 0, "c5", tipo="marco_termino"), A("Z", 0, "c5")]
    rels = [R("C", "E"), R("E", "N1"), R("E", "N2", "SS", 2), R("N2", "M", "FS", -1), R("N1", "M"), R("C", "Z"),
            R("N3", "M", "FF", 0)]
    lb = {"C": (SEG, o("2026-01-09")), "E": (o("2026-01-12"), o("2026-01-16")),
          "N1": (o("2026-01-19"), o("2026-03-27")), "N2": (o("2026-01-14"), o("2026-01-27")),
          "N3": (SEG, o("2026-01-07")), "M": (None, o("2026-03-27")), "Z": (None, None)}
    return ats, rels, lb


def test_dcma_cada_metrica_segue_a_definicao_declarada():
    """População = tarefas não concluídas com duração > 0 = {E, N1, N2, N3} (4); relações vivas = 7.
     1 Lógica: N3 não tem predecessora -> 1/4 = 25 %  (limite 5 % -> reprovado)
     2 Leads: N2→M FS−1 -> 1/7 = 14,2857 %            3 Lags: E→N2 SS+2 -> 1/7 = 14,2857 %
     4 FS: 5 de 7 = 71,4286 % (< 90 % -> reprovado); violadoras = as 2 que não são FS
     5 Restrições rígidas: só o FNLT de N2 -> 25 % (o SNET de N3 é brando e não conta)
     8 Duração alta: N1 = 50 > 44 -> 25 %             9 Datas inválidas: 0 -> aprovado
    10 Recursos (informativo, nunca aprovado/reprovado): N1 e N3 sem equipes -> 50 %
    11 Tarefas perdidas: devidas (LB < 19/01) = C, E, N3; perdidas = E e N3 -> 66,6667 %
    13 CPLI: término calculado 03/04; CPL = dias úteis de 19/01 a 03/04 = 10 + 20 + 22 + 3 = 55;
       folga do projeto até 27/03 = −5 -> (55 − 5)/55 = 0,9091 (< 0,95 -> reprovado)
    14 BEI: concluídas (1) ÷ devidas (3) = 0,3333; violadoras = E e N3
    12 Teste do caminho crítico: +10 dias úteis em E -> término anda 10 dias úteis -> aprovado."""
    ats, rels, lb = _rede_dcma()
    r = dcma.avaliar(ats, rels, CALS, SEG, o("2026-01-19"), linha_base=lb,
                     recursos={"E": 1, "N1": None, "N2": 2, "N3": 0}, termino_contratual=o("2026-03-27"),
                     calendario_projeto="c5")
    assert (r["populacao"], r["n_relacoes_vivas"], r["termino_calculado"]) == (4, 7, "2026-04-03")
    esperado = {1: (25.0, False, ["N3"]), 2: (14.2857, False, ["N2->M FS-1"]), 3: (14.2857, False, ["E->N2 SS+2"]),
                4: (71.4286, False, ["E->N2 SS", "N3->M FF"]), 5: (25.0, False, ["N2"]), 8: (25.0, False, ["N1"]),
                9: (0.0, True, []), 10: (50.0, None, ["N1", "N3"]), 11: (66.6667, False, ["E", "N3"]),
                12: (10.0, True, []), 13: (0.9091, False, []), 14: (0.3333, False, ["E", "N3"])}
    for n, (valor, aprovado, violadoras) in esperado.items():
        p = ponto(r, n)
        assert (p["valor"], p["aprovado"], p["violadoras"]) == (valor, aprovado, violadoras), n
    assert ponto(r, 13)["detalhe"] == {"cpl": 55, "folga_projeto": -5}
    assert ponto(r, 12)["detalhe"]["atividade_testada"] == "E"
    assert (ponto(r, 6)["aprovado"], ponto(r, 7)["aprovado"]) == (True, True)
    assert r["resumo"] == {"aprovados": 4, "reprovados": 9, "nao_avaliados": 1}


def test_dcma_folga_negativa_e_alta_contam_em_dias_uteis_do_motor():
    """População {A, B, X} = 3; o término é ditado por X(60).
    A(10) 05–16/01 com FNLT 12/01 (LF = 13/01; EF = 17/01): folga −4 dias úteis -> ponto 7 = 1/3 = 33,3333 %,
    reprovado, violadora A (e A, com folga negativa, não conta como folga alta).
    B(1): folga 59 > 44 -> ponto 6 = 1/3 = 33,3333 %, violadora B.
    No limite exato: Y(16) ao lado de X(60) tem folga 44 e NÃO conta (a regra é '> 44'); Y(15) tem 45 e conta."""
    r = dcma.avaliar([A("A", 10, "c5", restricao_termino=o("2026-01-12")), A("B", 1, "c5"), A("X", 60, "c5")], [],
                     CALS, SEG, calendario_projeto="c5")
    assert (ponto(r, 7)["valor"], ponto(r, 7)["aprovado"], ponto(r, 7)["violadoras"]) == (33.3333, False, ["A"])
    assert (ponto(r, 6)["valor"], ponto(r, 6)["violadoras"]) == (33.3333, ["B"])
    lim = dcma.avaliar([A("Y", 16, "c5"), A("X", 60, "c5")], [], CALS, SEG, calendario_projeto="c5")
    assert ponto(lim, 6)["violadoras"] == []          # folga de Y = 60 − 16 = 44: não é "alta"
    acima = dcma.avaliar([A("Y", 15, "c5"), A("X", 60, "c5")], [], CALS, SEG, calendario_projeto="c5")
    assert ponto(acima, 6)["violadoras"] == ["Y"]     # folga 45


def test_dcma_ponto_que_nao_se_aplica_nunca_sai_aprovado(obras):
    """(a) Linha de base (sem data de status): 9, 11 e 14 não se aplicam -> aprovado None; CPLI = 1,0.
    (b) Cronograma importado (sem linha de base, sem recursos, sem prazo): 10, 11, 13, 14 -> None.
    (c) Só atividades concluídas (população 0, sem relação viva): 1–8 e 12 -> None, nenhum 'aprovado'
        por percentual de 0/0.
    (d) Data real depois da data de status: o motor não roda; 6, 7, 12, 13 -> None e o ponto 9 REPROVA.
    Em todos: todo ponto cuja nota começa por 'não se aplica' ou 'não calculado' tem aprovado None, e
    aprovados + reprovados + não avaliados = 14."""
    ats, rels, _ = _rede_dcma()
    casos = [
        dcma.avaliar_cenario(obras["ferrovia"], "linha_base"),
        dcma.avaliar(ats, rels, CALS, SEG, o("2026-01-19")),
        dcma.avaliar([A("C", 0, "c5", status="concluida", inicio_real=SEG, termino_real=o("2026-01-09"))], [],
                     CALS, SEG, o("2026-01-19")),
        dcma.avaliar([A("E", 5, "c5", status="em_andamento", inicio_real=o("2026-02-02")), A("B", 3, "c5")],
                     [R("E", "B")], CALS, SEG, o("2026-01-19")),
    ]
    nulos = [{9, 11, 14}, {10, 11, 13, 14}, {1, 2, 3, 4, 5, 6, 7, 8, 12}, {6, 7, 12, 13}]
    for r, esperados in zip(casos, nulos):
        assert sum(r["resumo"].values()) == 14
        for p in r["pontos"]:
            if p["numero"] in esperados or p["nota"].startswith(("não se aplica", "não calculado")):
                assert p["aprovado"] is None and p["valor"] is None, (p["numero"], p["nota"])
    assert ponto(casos[0], 13)["valor"] == 1.0
    assert (ponto(casos[3], 9)["valor"], ponto(casos[3], 9)["aprovado"]) == (1.0, False)


@pytest.mark.parametrize("obra", OBRAS)
def test_dcma_nas_obras_teste_do_caminho_critico_e_cpli(cliente, obra):
    """Pela API, nos 3 cenários: o ponto 12 foi EXECUTADO (a atividade testada está na cadeia determinante,
    o término depois é 10 dias úteis mais tarde no calendário da obra) e aprova; CPLI = (CPL + folga)/CPL
    com os números do detalhe, < 1 quando o término calculado passa do contratual e = 1 na linha de base."""
    for cenario in ("linha_base", "construtora", "independente"):
        r = cliente.get("/api/dcma", params={"obra": obra, "cenario": cenario}).json()
        res = cliente.get(f"/api/cenarios/{cenario}", params={"obra": obra}).json()
        p12, p13 = ponto(r, 12), ponto(r, 13)
        assert (p12["valor"], p12["aprovado"]) == (10.0, True)
        assert p12["detalhe"]["atividade_testada"] in res["cadeia_determinante"]
        assert p12["detalhe"]["termino_antes"] == res["termino"] == r["termino_calculado"]
        d = p13["detalhe"]
        assert p13["valor"] == round((d["cpl"] + d["folga_projeto"]) / d["cpl"], 4)
        assert (d["folga_projeto"] < 0) == (res["termino"] > r["termino_referencia_cpli"])
        if cenario == "linha_base":
            assert p13["valor"] == 1.0
    assert cliente.get("/api/dcma", params={"obra": obra, "cenario": "x"}).status_code == 422


def test_dcma_importado_malformado_nunca_responde_500(cliente):
    """POST /api/dcma/importado: fixtures válidas -> 200 com 14 pontos; corpo vazio -> 400; formato não
    reconhecido -> 415; XML truncado, 'inf', duração de 400 dígitos, encoding desconhecido, XER com 'nan',
    clndr_data com 3000 níveis e XER só com cabeçalho -> 422. XER com ciclo (A→B e B→A) -> 200 com
    ``erro_motor`` preenchido e os pontos que dependem do motor não avaliados."""
    xml = (RAIZ / "examples" / "fixtures" / "mspdi_minimo.xml").read_text(encoding="utf-8")
    xer = (RAIZ / "examples" / "fixtures" / "p6_minimo.xer").read_bytes().decode("utf-8").replace("\r\n", "\n")

    def post(corpo):
        return cliente.post("/api/dcma/importado", content=corpo if isinstance(corpo, bytes) else corpo.encode(),
                            headers={"Content-Type": "application/octet-stream"})

    for bom in (xml, xer):
        r = post(bom)
        assert r.status_code == 200 and len(r.json()["pontos"]) == 14
    assert post(b"").status_code == 400 and post("abc").status_code == 415
    ruins = [xml[:len(xml) // 2], xml.replace("<StartDate>", "<MinutesPerDay>inf</MinutesPerDay><StartDate>", 1),
             re.sub(r"<Duration>PT\d+H", "<Duration>PT" + "9" * 400 + "H", xml, count=1),
             re.sub(r'encoding="[^"]+"', 'encoding="utf-99"', xml), xer.replace("\t48\t48\t", "\tnan\tnan\t", 1),
             re.sub(r"\(0\|\|CalendarData.*", "(0||a()(" * 3000, xer, count=1), "ERMHDR\t1\n"]
    for ruim in ruins:
        assert post(ruim).status_code == 422, ruim[:60]
    ls = xer.split("\n")
    i = next(k for k, ln in enumerate(ls) if ln.startswith("%T\tTASKPRED"))
    campos, linha = ls[i + 1].split("\t")[1:], ls[i + 2].split("\t")
    inv = list(linha)
    a, b = 1 + campos.index("task_id"), 1 + campos.index("pred_task_id")
    inv[a], inv[b], inv[1 + campos.index("task_pred_id")] = linha[b], linha[a], "9999"
    r = post("\n".join(ls[:i + 3] + ["\t".join(inv)] + ls[i + 3:]))
    assert r.status_code == 200 and "ciclo" in r.json()["erro_motor"]
    assert all(ponto(r.json(), n)["aprovado"] is None for n in (6, 7, 12, 13))


# Regressão: defeito da rodada 12, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: o teste do caminho crítico (ponto 12) aumenta N dias úteis no calendário da ATIVIDADE "
#   "mas mede o atraso no calendário do PROJETO e exige igualdade. Com calendários diferentes uma rede "
#   "perfeita reprova: tarefa de 5 dias/semana em projeto de 6 dias dá 12 (≠ 10); o inverso dá 8. "
#   "No cronograma importado, sem calendário de projeto, vale o da última atividade da cadeia")
@pytest.mark.parametrize("cal_atividade,cal_projeto", [("c5", "c6"), ("c6", "c5")])
def test_dcma_teste_do_caminho_critico_com_calendarios_diferentes(cal_atividade, cal_projeto):
    """Rede de UMA atividade de 20 dias (ela é o caminho crítico). +10 dias úteis nela empurram o término em
    exatamente 10 dias úteis DELA: o teste tem de aprovar, qualquer que seja o calendário do projeto."""
    r = dcma.avaliar([A("X", 20, cal_atividade)], [], CALS, SEG, calendario_projeto=cal_projeto)
    assert ponto(r, 12)["aprovado"] is True


# Regressão: defeito da rodada 12, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: 'dirige pelo término' é decidido pelo TIPO de qualquer relação entre os dois elos da "
#   "cadeia; num par com SS (a que dirige) e FF (que não dirige) a predecessora é escolhida, o aumento de "
#   "duração não move nada (atraso 0) e o ponto 12 REPROVA uma rede sã. O motor informa a relação que "
#   "de fato fixou o início (motivo_inicio: 'SS+2 de A')")
def test_dcma_teste_do_caminho_critico_com_par_ss_e_ff():
    """A(10) e B(30) com A→B SS+2 e A→B FF+0. B começa em 07/01 (pela SS) e termina muito depois de A: quem
    dirige é a SS. Alongar A em 10 dias não muda o término (a FF pede fim de B >= fim de A, com folga).
    A tarefa que dirige pelo término é B (fecha a cadeia): +10 em B move o término 10 dias. Esperado: aprovado,
    testando B."""
    r = dcma.avaliar([A("A", 10, "c5"), A("B", 30, "c5")], [R("A", "B", "SS", 2), R("A", "B", "FF", 0)], CALS, SEG,
                     calendario_projeto="c5")
    p = ponto(r, 12)
    assert (p["detalhe"]["atividade_testada"], p["valor"], p["aprovado"]) == ("B", 10.0, True)


# =============================================================================
# 2. produtividade de terraplenagem pela DMT
# =============================================================================
def test_ciclo_de_frota_limites_e_dmt_de_equilibrio():
    """Parâmetros padrão. Escavadeira: 3600/22 × 2,0 × 0,85 = 278,18 m³ solto/h; × 0,70 × 8 h = 1.557,82 m³/dia.
    Caminhão: carga = 10 ÷ (278,18/60) = 2,157 min; fixo 3 min; ida a 15 km/h + volta a 25 km/h = 6,4 min/km.
      DMT 0: ciclo 5,157 min -> 8 × 10 × 60/5,157 × 0,7 × 8 = 5.212 m³/dia: limita a ESCAVADEIRA
             -> 1.557,82 solto = 1.246,25 m³ de corte (÷ 1,25 de empolamento).
      DMT 5 km: ciclo 5,157 + 32 = 37,157 min -> 723,42 m³ solto/dia: limitam os CAMINHÕES -> 578,74 de corte.
    Equilíbrio: ciclo máximo = 26.880 ÷ 1.557,82 = 17,255 min -> (17,255 − 5,157) ÷ 6,4 = 1,8903 km.
    Monotonia: de 0 a 20 km (passo 50 m) a produção nunca aumenta."""
    p0, p5 = PT.producao_frota(0), PT.producao_frota(5000)
    assert (p0["limitante"], p5["limitante"]) == ("escavadeira", "caminhões")
    assert p0["ciclo_caminhao_min"] == pytest.approx(5.1569, abs=1e-4)
    assert p0["escavadeira_m3_solto_dia"] == pytest.approx(1557.82, abs=0.01)
    assert p0["producao_m3_corte_dia"] == pytest.approx(1246.25, abs=0.01)
    assert p5["ciclo_caminhao_min"] == pytest.approx(37.1569, abs=1e-4)
    assert (p5["caminhoes_m3_solto_dia"], p5["producao_m3_corte_dia"]) == pytest.approx((723.42, 578.74), abs=0.01)
    eq = PT.dmt_de_equilibrio_m()
    assert eq == pytest.approx(1890.3, abs=0.1)
    no_eq = PT.producao_frota(eq)
    assert no_eq["escavadeira_m3_solto_dia"] == pytest.approx(no_eq["caminhoes_m3_solto_dia"])
    assert (PT.producao_frota(eq - 1)["limitante"], PT.producao_frota(eq + 1)["limitante"]) == ("escavadeira", "caminhões")
    prod = [PT.producao_frota(d)["producao_m3_corte_dia"] for d in range(0, 20001, 50)]
    assert all(b <= a + 1e-9 for a, b in zip(prod, prod[1:]))
    for dmt in (-1, float("nan")):
        with pytest.raises(PT.ErroProdutividade):
            PT.producao_frota(dmt)


def test_conversao_de_unidade_corte_mais_aterro():
    """m³ de TER (corte + aterro) por m³ de corte escavado = (Vc + Va) ÷ max(Vc, Fh·Va), Fh = 1,25:
    só corte (100, 0) -> 1,0; só aterro (0, 100) -> 100/125 = 0,8; (100, 80): Fh·Va = 100 -> 180/100 = 1,8;
    (100, 50): 150/100 = 1,5; sem volume -> 1,0."""
    f = PT.fator_quantidade
    assert [f(100, 0, 1.25), f(0, 100, 1.25), f(100, 80, 1.25), f(100, 50, 1.25), f(0, 0, 1.25)] == \
           pytest.approx([1.0, 0.8, 1.8, 1.5, 1.0])


@pytest.mark.parametrize("obra", OBRAS)
def test_rateio_por_segmento_ajustes_e_efeito_no_termino(cliente, obras, obra):
    """Rateio das ondas pelos segmentos: Σ volume compensado e Σ momento dos segmentos = totais do diagrama
    de massas (diferença relativa < 0,1 %: o rateio é pela fração do comprimento da onda dentro do segmento).
    Ajustes recomendados: só atividades '-TER' NÃO concluídas, uma por segmento em aberto, com produtividade
    = geométrica arredondada a 3 casas. Efeito no término: aplicando os mesmos ajustes por
    POST /api/simulacao, o término simulado é o `termino_pela_geometria` e o delta bate."""
    p = obras[obra]
    m = massas_da_obra(p.dados, 20.0)
    d = PT.dmt_por_segmento(p.dados, m)
    t = m["total"]
    assert sum(x["volume_compensado_m3"] for x in d.values()) == pytest.approx(t["volume_compensado_m3"], rel=1e-3)
    proprio = sum(x["momento_m3m"] - x["volume_externo_m3"] * PT.ParametrosFrota().dmt_externa_m for x in d.values())
    assert proprio == pytest.approx(t["momento_transporte_m3km"] * 1000, rel=1e-3)

    q = {"obra": obra}
    r = cliente.get("/api/produtividade/terraplenagem", params=q).json()
    seg = {x["atividade_id"]: x for x in r["segmentos"]}
    abertas = {i for i, x in seg.items() if x["status"] != "concluida"}
    assert {a["atividade_id"] for a in r["ajustes_recomendados"]} == abertas
    assert all(i.endswith("-TER") and p.atividades[i]["status"] != "concluida" for i in abertas)
    for a in r["ajustes_recomendados"]:
        assert a["produtividade"] == round(seg[a["atividade_id"]]["produtividade_geometrica"], 3)
    for x in r["segmentos"]:
        assert x["produtividade_geometrica"] == pytest.approx(x["producao_m3_corte_dia"] * x["fator_quantidade"])
        assert x["producao_m3_corte_dia"] == pytest.approx(PT.producao_frota(x["dmt_m"])["producao_m3_corte_dia"])
    try:
        s = cliente.post("/api/simulacao", params=q, json={"ajustes": r["ajustes_recomendados"]})
        assert s.status_code == 200, s.text[:200]
        c = s.json()["comparacao"]
        e = r["efeito_no_termino"]
        assert (c["termino_ref"], c["termino_alvo"], c["delta_dias_corridos"]) == \
               (e["termino_independente"], e["termino_pela_geometria"], e["delta_dias_corridos"])
    finally:
        cliente.delete("/api/simulacao", params=q)


# Regressão: defeito da rodada 12, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: o bota-fora/empréstimo nunca entra na DMT do segmento. O rateio externo depende de uma "
#   "onda marcada `aberta`, e o diagrama de massas (corrigido na rodada 9) não marca mais nenhuma: na "
#   "ferrovia 15.215 m³ e na rodovia 4.891 m³ de empréstimo não são atribuídos a segmento algum, e "
#   "`dmt_externa_m` só é usada quando não há NENHUMA onda. O trecho que manda material a 3 km aparece "
#   "com a DMT das ondas vizinhas e a produtividade geométrica sai otimista")
@pytest.mark.parametrize("caso", ["ferrovia", "rodovia", "onda seguida de cauda de corte"])
def test_volume_externo_e_atribuido_a_algum_segmento(obras, caso):
    """Σ volume externo dos segmentos = bota-fora + empréstimo do diagrama (±0,1 %).
    Caso à mão (Fh = 1, estacas de 20 m): h = 0, −2, −2, 0, +2, +2, 0, −2, −2, 0 -> uma onda fechada de
    1.200 m³ (km 0 a 0,12) e, depois, 1.200 m³ de corte sem aterro (km 0,12 a 0,18): bota-fora 1.200 m³.
    Segmentos S1 (0–0,10) e S2 (0,10–0,18): os 1.200 m³ externos pertencem a S2, cuja DMT tem de passar
    de 60 m (parte dele vai a 3.000 m). (Na rodada 12 o módulo dava externo 0 e DMT 60 m nos dois.)"""
    if caso in OBRAS:
        dados = obras[caso].dados
        m = massas_da_obra(dados, 20.0)
    else:
        hs = [0, -2, -2, 0, 2, 2, 0, -2, -2, 0]
        kms = [i * 0.02 for i in range(len(hs))]
        m = calcular_massas(kms, hs, [0.0] * len(hs), Secao(12.0), fh=1.0)
        dados = {"segmentos": [{"id": "S1", "km_ini": 0.0, "km_fim": 0.10}, {"id": "S2", "km_ini": 0.10, "km_fim": 0.18}]}
        assert m["total"]["bota_fora_m3"] == pytest.approx(1200.0)
    d = PT.dmt_por_segmento(dados, m)
    livre = m["total"]["bota_fora_m3"] + m["total"]["emprestimo_m3"]
    assert livre > 0
    assert sum(x["volume_externo_m3"] for x in d.values()) == pytest.approx(livre, rel=1e-3)
    if caso not in OBRAS:
        assert d["S2"]["volume_externo_m3"] == pytest.approx(1200.0) and d["S2"]["dmt_m"] > 60.0


# Regressão: defeito da rodada 12, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: ParametrosFrota aceita frota sem caminhão (n_caminhoes = 0 -> produção 0; `analisar` "
#   "estoura ErroAjuste 'produtividade × equipes deve ser positiva', não ErroProdutividade) e valores "
#   "infinitos (caçamba inf -> DMT de equilíbrio 0 e produção sem sentido); a validação só testa > 0 e NaN")
@pytest.mark.parametrize("parametro", [dict(n_caminhoes=0), dict(cacamba_m3=float("inf")),
                                        dict(v_carregado_kmh=float("inf"))])
def test_parametros_de_frota_sem_sentido_sao_recusados(parametro):
    """Frota com 0 caminhões não transporta nada e valor infinito não é parâmetro físico: ErroProdutividade
    já na construção."""
    with pytest.raises(PT.ErroProdutividade):
        PT.ParametrosFrota(**parametro)
