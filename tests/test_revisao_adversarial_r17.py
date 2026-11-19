"""Revisão adversarial — rodada 17: ``orcamento.py`` (BDI pela fórmula do TCU, reajuste com anualidade, tipo
da composição pela chave), ``cobertura.py`` (/api/cobertura) e ``ifc/cronograma.py`` (cronograma nativo no
IFC: ida e volta, Psets de lag negativo, calendário com exceções, simulado, arquivo de terceiro).

Cada teste traz no docstring o resultado esperado calculado à mão ou por conferência independente.
Defeito confirmado fica ``xfail(strict=True, reason="DEFEITO: ...")``.

A parte de IFC é pulada (SKIP, não verde) se ``ifcopenshell`` não estiver no .venv.
"""

import copy
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import cobertura as C
from infra4d import orcamento as O
from infra4d.cenarios import Ajuste, Projeto, executar, montar_entrada
from infra4d.motor import calcular

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")


def _defeito(motivo):
    return pytest.mark.xfail(strict=True, reason="DEFEITO: " + motivo)


@pytest.fixture(scope="module")
def bases():
    return {o: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json") for o in OBRAS}


def _app(fontes):
    from infra4d.api import criar_app
    return TestClient(criar_app(fontes=fontes), raise_server_exceptions=False)


def _mini(rels_extra=(), lb=("2026-03-02", "2026-03-13"), **meta) -> Projeto:
    """M0 → A → B → MF. A e B: 1000 m³ de TER a 100 m³/equipe·dia, 1 equipe = 10 dias úteis cada.
    Calendário seg–sex com 10/03, 11/03 e 20/03/2026 não úteis. Início = data de status = seg 02/03/2026.
    À mão: A = 02–06, 09, 12, 13, 16, 17/03 (termina 17/03); B = 18, 19, 23–27, 30, 31/03 e 01/04."""
    def q(aid):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": "L1", "segmento_id": "L1-S01",
                "servico_id": "TER", "quantidade_total": 1000.0, "produtividade_planejada": 100.0, "equipes": 1,
                "calendario": "C", "status": "nao_iniciada", "unidade": "m³", "km_ini": 0.0, "km_fim": 1.0,
                "inicio_lb": lb[0], "termino_lb": lb[1]}

    def marco(aid, tipo, dia):
        return {"id": aid, "nome": aid, "tipo": tipo, "calendario": "C", "status": "nao_iniciada",
                "inicio_lb": dia, "termino_lb": dia}

    return Projeto({
        "meta": {"aviso": "DADOS FICTÍCIOS de teste", "ficticio": True, "tipo_obra": "ferrovia",
                 "inicio_projeto": "2026-03-02", "data_status": "2026-03-02", "calendario_obra": "C", **meta},
        "ferrovia": {"id": "TESTE", "nome": "mini"},
        "lotes": [{"id": "L1", "nome": "L1", "km_ini": 0.0, "km_fim": 1.0}],
        "segmentos": [{"id": "L1-S01", "lote_id": "L1", "km_ini": 0.0, "km_fim": 1.0}],
        "servicos": [{"id": "TER", "unidade": "m³"}], "oaes": [], "medicoes": [], "restricoes": [],
        "calendarios": [{"id": "C", "nome": "seg-sex", "dias_semana": [0, 1, 2, 3, 4],
                         "nao_uteis": ["2026-03-10", "2026-03-11", "2026-03-20"]}],
        "atividades": [marco("M0", "marco_inicio", "2026-03-02"), q("A"), q("B"),
                       marco("MF", "marco_termino", "2026-03-30")],
        "relacoes": [{"predecessora": p, "sucessora": s, "tipo": "FS", "lag": 0}
                     for p, s in (("M0", "A"), ("A", "B"), ("B", "MF"))] + list(rels_extra),
        "alinhamento": {"pontos": [[0.0, 0.0, 0.0, 0.0], [0.5, 500.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0]]}})


# =============================================================================
# 1. orçamento — BDI, composição pela chave, reajuste
# =============================================================================
def test_bdi_pela_formula_do_tcu_a_mao():
    """BDI = ((1 + AC + S+G + R)(1 + DF)(1 + L)) / (1 − I) − 1, com os componentes declarados.
    Ferrovia: (1,073 × 1,010 × 1,075) / 0,9435 − 1 = 1,16500975 / 0,9435 − 1 = 0,234775 (23,48 %).
    Rodovia: (1,067 × 1,010 × 1,070) / 0,9435 − 1 = 1,1531069 / 0,9435 − 1 = 0,222159 (22,22 %).
    Os dois dentro da faixa declarada (19,60 % a 24,23 %)."""
    assert O.bdi_da_obra("ferrovia") == pytest.approx(1.16500975 / 0.9435 - 1, abs=1e-12)
    assert O.bdi_da_obra("rodovia") == pytest.approx(1.1531069 / 0.9435 - 1, abs=1e-12)
    assert round(O.bdi_da_obra("ferrovia"), 6) == 0.234775 and round(O.bdi_da_obra("rodovia"), 6) == 0.222159
    for t in OBRAS:
        assert O.FAIXA_BDI_TCU["q1"] <= O.bdi_da_obra(t) <= O.FAIXA_BDI_TCU["q3"]
    with pytest.raises(O.ErroOrcamento):
        O.bdi_da_obra("metro")


def test_tipo_da_composicao_vem_da_chave_e_decide_o_bdi(bases):
    """Toda composição carrega o tipo de obra da CHAVE em que está; ``preco_venda`` sem BDI explícito usa o BDI
    desse tipo. TER existe nas duas obras: o preço de cada uma é o custo direto dela × (1 + BDI da obra dela).
    Ferrovia TER: 1,48 + 11,47 + 0 + 5,55 = 18,50 → 18,50 × 1,234775 = 22,8433. Composição sem tipo é erro.
    Pela API, o BDI de /composicoes e o de /resumo são o da obra."""
    for tipo, comps in O.COMPOSICOES.items():
        for serv, comp in comps.items():
            assert comp["tipo_obra"] == tipo, (tipo, serv)
            cd = sum(comp["custo_direto"].values())
            assert O.preco_venda(comp) == pytest.approx(cd * (1 + O.bdi_da_obra(tipo)), abs=1e-6)
    assert O.preco_venda(O.COMPOSICOES["ferrovia"]["TER"]) == pytest.approx(22.8433, abs=5e-5)
    sem_tipo = {k: v for k, v in O.COMPOSICOES["ferrovia"]["TER"].items() if k != "tipo_obra"}
    with pytest.raises(O.ErroOrcamento):
        O.preco_venda(sem_tipo)
    c = _app(bases)
    for obra in OBRAS:
        esperado = round(O.bdi_da_obra(obra), 6)
        assert c.get("/api/orcamento/composicoes", params={"obra": obra}).json()["bdi"] == esperado
        assert c.get("/api/orcamento/resumo", params={"obra": obra}).json()["bdi"] == esperado


def test_anualidade_com_data_base_no_dia_1():
    """Data-base 01/11/2025, TER (terraplenagem, taxa fictícia 0,45 % ao mês). À mão:
    31/10/2026 (ainda no 1º ano) → 1,0; 01/11/2026 (1º aniversário) → 1,0045¹² = 1,055357; 31/10/2027 → o
    mesmo; 01/11/2027 → 1,0045²⁴ = 1,113778; dia anterior à data-base → 1,0."""
    b = date(2025, 11, 1)
    f = lambda d: O.fator_reajuste("ferrovia", "TER", b, d)  # noqa: E731
    assert f(date(2026, 10, 31)) == 1.0 and f(date(2025, 10, 1)) == 1.0
    assert f(date(2026, 11, 1)) == pytest.approx(1.0045 ** 12) == pytest.approx(1.055357, abs=1e-6)
    assert f(date(2027, 10, 31)) == pytest.approx(1.0045 ** 12)
    assert f(date(2027, 11, 1)) == pytest.approx(1.0045 ** 24) == pytest.approx(1.113778, abs=1e-6)


def test_pv_reajustado_de_linha_de_base_que_cruza_o_aniversario():
    """Mini obra com data-base 01/03/2025 e A e B com linha de base 23/02 a 06/03/2026 (10 dias úteis:
    23–27/02 antes do 1º aniversário, 02–06/03 depois). BAC = 2 × 1000 × 18,50 × (1 + BDI ferrovia).
    PV reajustado total = BAC × (5 × 1,0 + 5 × 1,0045¹²) / 10."""
    P = _mini(lb=("2026-02-23", "2026-03-06"), data_base_orcamento="2025-03-01")
    r = O.curva_s(P)
    bac = 2 * 1000 * 18.5 * (1 + O.bdi_da_obra("ferrovia"))
    assert r["bac"] == pytest.approx(bac, abs=0.01)
    assert r["bac_reajustado"] == pytest.approx(bac * (5 + 5 * 1.0045 ** 12) / 10, abs=0.01)


@pytest.mark.parametrize("dia", [date(2026, 11, 1), date(2026, 11, 14)])
# Regressão: defeito da rodada 17, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("anualidade contada por MÊS, não por data: `_meses` ignora o dia e `fator_reajuste` aplica o índice do 1º "
#   "aniversário a partir do dia 1 do mês do aniversário. Com data-base 15/11/2025 (aceita em "
#   "`meta.data_base_orcamento`), serviço executado de 01 a 14/11/2026 — ANTES de completar 12 meses — "
#   "já sai reajustado (1,055357). A anualidade é contada da data-base (12 meses completos). Correção: "
#   "comparar a data inteira (aniversário = mesmo dia e mês) ou recusar data-base fora do dia 1")
def test_reajuste_nao_comeca_antes_de_completar_12_meses(dia):
    """Data-base 15/11/2025. O 1º aniversário é 15/11/2026: em 01/11 e 14/11/2026 o fator ainda é 1,0;
    em 15/11/2026 passa a 1,0045¹²."""
    b = date(2025, 11, 15)
    assert O.fator_reajuste("ferrovia", "TER", b, date(2026, 11, 15)) == pytest.approx(1.0045 ** 12)
    assert O.fator_reajuste("ferrovia", "TER", b, dia) == 1.0


# Regressão: defeito da rodada 17, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("`resumo(bdi=0.25)` devolve bdi 0,25 mas `bdi_nota` continua dizendo 'BDI fictício da obra (ferrovia) = "
#   "23.48% pela fórmula do TCU' e `bdi_declarado` os componentes da obra: a nota descreve um BDI que NÃO "
#   "foi o usado no BAC/EV/AC da mesma resposta. Correção: com bdi explícito, a nota tem de dizer que o BDI "
#   "foi informado (e qual)")
def test_nota_do_bdi_descreve_o_bdi_usado(bases):
    """Com BDI explícito de 25 %, a nota tem de citar 25,00 % (o BDI usado), não só os 23,48 % declarados."""
    r = O.resumo(bases["ferrovia"], bdi=0.25)
    assert r["bdi"] == 0.25
    assert "25.00%" in r["bdi_nota"] or "25,00" in r["bdi_nota"], r["bdi_nota"]


@pytest.mark.parametrize("valor", ["2025-13-01", "abc", 20251101, "2025-11-01T00:00:00"])
# Regressão: defeito da rodada 17, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("`meta.data_base_orcamento` inválida (mês 13, texto, número, data com hora): `date.fromisoformat` estoura "
#   "ValueError/TypeError fora de ErroOrcamento e /api/orcamento/resumo e /curva-s-financeira respondem 500. "
#   "Correção: validar em `data_base` e levantar ErroOrcamento (422 com o motivo)")
def test_data_base_invalida_e_422_nao_500(bases, valor):
    """Dataset com data-base do orçamento malformada: as duas rotas respondem 422 com o motivo."""
    d = copy.deepcopy(bases["ferrovia"].dados)
    d["meta"]["data_base_orcamento"] = valor
    c = _app({"x": Projeto(d)})
    assert c.get("/api/orcamento/resumo", params={"obra": "x"}).status_code == 422
    assert c.get("/api/orcamento/curva-s-financeira", params={"obra": "x"}).status_code == 422


# Regressão: defeito da rodada 17, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("obra com `meta.tipo_obra` sem composições nem BDI ('metro'): /api/orcamento/resumo responde 422 com o "
#   "motivo, mas /api/orcamento/composicoes responde 500 — `O.mapa_ifc(tipo)` levanta ErroOrcamento fora do "
#   "`_executar` (só MapaIfcIndisponivel é tratado ali). Correção: passar a chamada por `_executar`")
def test_composicoes_de_tipo_de_obra_desconhecido_e_422(bases):
    """Mesma obra, mesmo defeito de dado: as duas rotas têm de recusar com 422."""
    d = copy.deepcopy(bases["rodovia"].dados)
    d["meta"]["tipo_obra"] = "metro"
    c = _app({"x": Projeto(d)})
    assert c.get("/api/orcamento/resumo", params={"obra": "x"}).status_code == 422
    assert c.get("/api/orcamento/composicoes", params={"obra": "x"}).status_code == 422


# =============================================================================
# 2. cobertura da previsão
# =============================================================================
@pytest.mark.parametrize("obra", OBRAS)
def test_fator_de_estresse_e_o_menor_indice_conferido_por_fora(bases, obra):
    """Conferência independente: por (lote, serviço), índice = (Σ quantidade ÷ Σ equipe·dia) ÷ média da
    produtividade planejada das atividades medidas do par; f = o MENOR deles, limitado a 1. Ferrovia: L2/LAS
    0,6171; rodovia: L2/CBU 0,5878."""
    dados = bases[obra].dados
    ativ = {a["id"]: a for a in dados["atividades"]}
    soma = {}
    for m in dados["medicoes"]:
        a = ativ[m["atividade_id"]]
        s = soma.setdefault((a["lote_id"], a["servico_id"]), [0.0, 0.0, set()])
        s[0] += m["quantidade"]
        s[1] += m["equipes_dias"]
        s[2].add(a["id"])
    indices = {k: (q / e) / (sum(ativ[i]["produtividade_planejada"] for i in ids) / len(ids))
               for k, (q, e, ids) in soma.items()}
    par, menor = min(indices.items(), key=lambda x: x[1])
    f, origem = C.fator_estresse(dados)
    assert f == pytest.approx(min(1.0, menor), abs=5e-5)
    assert (origem["lote_id"], origem["servico_id"]) == par
    assert (par, round(menor, 4)) == {"ferrovia": (("L2", "LAS"), 0.6171), "rodovia": (("L2", "CBU"), 0.5878)}[obra]


@pytest.mark.parametrize("obra", OBRAS)
def test_estresse_do_marco_final_conferido_pelo_cenario_simulado(bases, obra):
    """O Δ 'medida' do marco final tem de ser o que o PRÓPRIO motor dá, pela via pública, quando toda tarefa
    por quantidade de origem medida rende × f: cenário simulado com Ajuste(produtividade = usada × f).
    E a construtora (tudo planejado) não tem parte medida: Δ medida = 0."""
    P = bases[obra]
    r = C.cobertura(P, "independente")
    f = r["fator_estresse"]
    ativs, _, mem = montar_entrada(P, "independente")
    ajustes = [Ajuste(atividade_id=a.id, produtividade=mem[a.id]["produtividade"] * f) for a in ativs
               if a.tipo == "tarefa" and a.status != "concluida" and mem[a.id].get("regra") == "quantidade"
               and mem[a.id]["quantidade_remanescente"] > 0 and C.origem_da_fonte(mem[a.id]) in C.MEDIDAS]
    assert ajustes
    sim = executar(P, "simulado", ajustes)["termino"]
    final = next(m for m in r["marcos"] if m["id"] == "M-FIM")
    assert final["termino"] == executar(P, "independente")["termino"]
    assert final["estresse"]["termino_estressado_medida"] == sim
    for m in C.cobertura(P, "construtora")["marcos"]:
        assert m["estresse"]["delta_medida_dias"] == 0


def test_rota_cobertura_parametros(bases):
    """Cenário inválido e folga negativa: 422; obra desconhecida: 404; sem boletins: 200 com 'sem_historico'."""
    d = copy.deepcopy(bases["rodovia"].dados)
    d["medicoes"] = []
    c = _app({"rodovia": bases["rodovia"], "vazia": Projeto(d)})
    assert c.get("/api/cobertura", params={"cenario": "linha_base"}).status_code == 422
    assert c.get("/api/cobertura", params={"folga_alerta_du": -1}).status_code == 422
    assert c.get("/api/cobertura", params={"obra": "nao-existe"}).status_code == 404
    j = c.get("/api/cobertura", params={"obra": "vazia"}).json()
    assert j["fator_estresse"] is None and {m["confianca"] for m in j["marcos"]} == {"sem_historico"}


# Regressão: defeito da rodada 17, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("confiança 'alta' com a previsão 100 % apoiada em produtividade NÃO medida: quando o pior índice "
#   "observado é >= 1 (f = 1), o estresse × 1 não move nada, Δ_sem_medicao = 0 < 7 e todo marco sai 'alta' — "
#   "inclusive com `fracao_sem_medicao` = 1,0. Um único boletim no ritmo planejado basta. O nível afirma "
#   "confiança onde só há ausência de evidência. Correção: quando f = 1 (ou a cadeia é toda sem medição), "
#   "declarar 'sem_historico'/'indeterminada' em vez de 'alta'")
def test_um_boletim_no_ritmo_planejado_nao_da_confianca_alta_a_obra_sem_medicao(bases):
    """Rodovia com UM boletim só, exatamente no ritmo planejado (índice 1,0) numa atividade já concluída.
    Todas as tarefas em aberto ficam sem medição própria (planejada ou analogia): a fração sem medição da
    cadeia do marco final é > 0,9. Esperado: o marco final NÃO pode sair com confiança 'alta'."""
    d = copy.deepcopy(bases["rodovia"].dados)
    a = next(x for x in d["atividades"] if x.get("status") == "concluida" and x.get("quantidade_total"))
    d["medicoes"] = [{"atividade_id": a["id"], "semana_inicio": a["inicio_real"],
                      "quantidade": 5 * a["produtividade_planejada"], "equipes_dias": 5}]
    r = C.cobertura(Projeto(d), "independente")
    assert r["fator_estresse"] == 1.0
    final = next(m for m in r["marcos"] if m["id"] == "M-FIM")
    assert final["relatorio_origem"]["fracao_sem_medicao"] > 0.9
    assert final["confianca"] != "alta", final["estresse"]


# Regressão: defeito da rodada 17, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("um boletim com produção ínfima (0,001 un em 500 equipe·dias — erro de digitação plausível) leva o fator "
#   "de estresse a ~1e-5; as durações estressadas estouram o horizonte do calendário e `ErroCalendario` "
#   "escapa: /api/cobertura responde 500 nos dois cenários. Correção: piso declarado para f (ou tratar "
#   "ErroCalendario e devolver o marco como 'sem_historico'/422 com o motivo)")
@pytest.mark.parametrize("cenario", ["independente", "construtora"])
def test_boletim_infimo_nao_derruba_a_cobertura(bases, cenario):
    """Dataset da rodovia com um boletim a mais, de valor ínfimo, numa atividade ainda não iniciada.
    A rota responde 200 (com o fator declarado) ou 422 com o motivo — nunca 500."""
    d = copy.deepcopy(bases["rodovia"].dados)
    a = next(x for x in d["atividades"] if x.get("status") == "nao_iniciada" and x.get("quantidade_total"))
    d["medicoes"].append({"atividade_id": a["id"], "semana_inicio": "2026-10-05", "quantidade": 0.001,
                          "equipes_dias": 500})
    r = _app({"x": Projeto(d)}).get("/api/cobertura", params={"obra": "x", "cenario": cenario})
    assert r.status_code in (200, 422), r.status_code


# =============================================================================
# 3. cronograma nativo no IFC
# =============================================================================
ifcopenshell = pytest.importorskip("ifcopenshell")
from infra4d.calendario import iso  # noqa: E402
from infra4d.ifc import cronograma as cron  # noqa: E402
from infra4d.ifc import exportar as exp  # noqa: E402
from infra4d.tendencia import fotografia  # noqa: E402


def _arquivo(P: Projeto, cenarios=("independente",), ajustes=None):
    """Exporta o modelo + cronograma e REABRE do texto STEP (o que um terceiro receberia)."""
    f, _ = exp.construir(P.dados, incluir_4d=False, posicionamento="local")
    cron.adicionar(f, P, list(cenarios), {}, ajustes=ajustes)
    return ifcopenshell.file.from_string(f.to_string())


def _ida_e_volta(P: Projeto, cenario: str, ajustes=None):
    ativs, rels, cals, meta = cron.ler(_arquivo(P, (cenario,), ajustes), cenario)
    res = calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta["data_status"])
    ra, rr, _ = montar_entrada(P, cenario, ajustes)
    ref = calcular(ra, rr, P.calendarios, P.inicio_projeto,
                   data_status=None if cenario == "linha_base" else P.data_status)
    chave = lambda lista: sorted((x.predecessora, x.sucessora, x.tipo, x.lag) for x in lista)  # noqa: E731
    return res, ref, chave(rels) == chave(rr), cals


def test_mini_ida_e_volta_com_calendario_de_excecoes_a_mao():
    """Mini obra (ver ``_mini``): término à mão 01/04/2026 nos cenários linha de base, construtora e
    independente. O calendário volta do IFC com os mesmos dias da semana e as três exceções (10 e 11/03 em
    UMA faixa, 20/03 em outra). Simulado com 3 equipes em A: ⌈1000/300⌉ = 4 dias (02–05/03) e B termina
    10 dias úteis depois: 06, 09, 12, 13, 16–19, 23, 24/03 → 24/03/2026."""
    P = _mini()
    for cen in ("linha_base", "construtora", "independente"):
        res, ref, rels_ok, cals = _ida_e_volta(P, cen)
        assert iso(res.termino_projeto_data) == iso(ref.termino_projeto_data) == "2026-04-01" and rels_ok
        assert cals["C"].dias_semana == (0, 1, 2, 3, 4)
        assert cals["C"].nao_uteis == {date(2026, 3, 10), date(2026, 3, 11), date(2026, 3, 20)}
    f = _arquivo(P)
    faixas = sorted((w.StartDate, w.FinishDate) for w in f.by_type("IfcWorkCalendar")[0].ExceptionTimes)
    assert faixas == [("2026-03-10", "2026-03-11"), ("2026-03-20", "2026-03-20")]
    aj = [Ajuste(atividade_id="A", equipes=3)]
    res, ref, rels_ok, _ = _ida_e_volta(P, "simulado", aj)
    assert iso(res.termino_projeto_data) == iso(ref.termino_projeto_data) == "2026-03-24" and rels_ok
    assert "simulado" not in cron.cenarios_no_arquivo(_arquivo(P, ("independente", "simulado")))


@pytest.mark.parametrize("extra", [
    [("A", "B", "SS", -1), ("M0", "B", "FS", -2)],
    [("A", "B", "FF", -3)],
    [("M0", "B", "SS", -4), ("A", "MF", "FF", -1)]])
def test_lags_negativos_de_varios_tipos_e_predecessoras_voltam_iguais(extra):
    """Lags negativos em relações de tipos diferentes para a MESMA sucessora (e junto com a FS 0 do mesmo
    par): cada um volta do Pset INFRA4D_LagsNegativos para a relação certa, nenhum IfcLagTime é negativo e
    as datas de todas as atividades batem com as do motor."""
    P = _mini([{"predecessora": p, "sucessora": s, "tipo": t, "lag": lag} for p, s, t, lag in extra])
    res, ref, rels_ok, _ = _ida_e_volta(P, "independente")
    assert rels_ok
    assert {i: (v.es, v.ef) for i, v in res.atividades.items()} == {i: (v.es, v.ef) for i, v in ref.atividades.items()}
    for lt in _arquivo(P).by_type("IfcLagTime"):
        assert not str(lt.LagValue.wrappedValue).startswith("P-")


@pytest.mark.parametrize("obra", OBRAS)
def test_obra_em_data_passada_ida_e_volta(bases, obra):
    """A obra como era 143 dias atrás (outra mistura de concluídas, em andamento e não iniciadas): o
    cronograma independente lido do IFC dá as mesmas datas (es, ef) e folga total em TODAS as atividades."""
    B = bases[obra]
    res, ref, rels_ok, _ = _ida_e_volta(Projeto(fotografia(B.dados, B.data_status - 143)), "independente")
    assert rels_ok
    assert {i: (v.es, v.ef, v.folga_total) for i, v in res.atividades.items()} == \
           {i: (v.es, v.ef, v.folga_total) for i, v in ref.atividades.items()}


def _tarefa(f, i):
    return next(t for t in f.by_type("IfcTask") if t.Identification == i)


def _post(c, f):
    return c.post("/api/ifc/cronograma", params={"obra": "x", "cenario": "independente"},
                  content=f.to_string().encode("latin-1", "replace"),
                  headers={"Content-Type": "application/octet-stream"})


RECUSAS = {
    "status de outro software": lambda f: setattr(_tarefa(f, "A"), "Status", "COMPLETED"),
    "duração negativa": lambda f: setattr(_tarefa(f, "A").TaskTime, "ScheduleDuration", "P-3D"),
    "duração com horas": lambda f: setattr(_tarefa(f, "A").TaskTime, "ScheduleDuration", "P5DT0H"),
    "duração gigante": lambda f: setattr(_tarefa(f, "A").TaskTime, "ScheduleDuration", "P9999999D"),
    "duas tarefas com o mesmo id": lambda f: setattr(_tarefa(f, "B"), "Identification", "A"),
    "data real ilegível": lambda f: setattr(_tarefa(f, "A").TaskTime, "ActualStart", "ontem"),
    "tipo de tarefa desconhecido": lambda f: setattr(_tarefa(f, "A"), "ObjectType", "ATIVIDADE"),
}


@pytest.mark.parametrize("nome", sorted(RECUSAS))
def test_arquivo_fora_da_convencao_e_recusado_com_422(nome):
    """Arquivo íntegro: 200 e término 01/04/2026. Cada desvio da convenção acima é recusado com 422 e motivo."""
    P = _mini()
    c = _app({"x": P})
    r = _post(c, _arquivo(P))
    assert r.status_code == 200 and r.json()["termino_calculado"] == "2026-04-01"
    f = _arquivo(P)
    RECUSAS[nome](f)
    r = _post(c, f)
    assert r.status_code == 422 and r.json()["detail"], nome


QUEBRAS = {
    "SequenceType NOTDEFINED": lambda f: setattr(f.by_type("IfcRelSequence")[0], "SequenceType", "NOTDEFINED"),
    "SequenceType ausente": lambda f: setattr(f.by_type("IfcRelSequence")[0], "SequenceType", None),
    "tarefa sem IfcTaskTime": lambda f: setattr(_tarefa(f, "A"), "TaskTime", None),
    "exceção de calendário sem StartDate": lambda f: setattr(f.by_type("IfcWorkCalendar")[0].ExceptionTimes[0],
                                                             "StartDate", None),
    "padrão semanal sem WeekdayComponent": lambda f: setattr(f.by_type("IfcRecurrencePattern")[0],
                                                             "WeekdayComponent", None),
    "tarefa sem Identification": lambda f: setattr(_tarefa(f, "A"), "Identification", None),
    "cronograma sem StartTime": lambda f: setattr(f.by_type("IfcWorkSchedule")[0], "StartTime", None),
}


@pytest.mark.parametrize("nome", sorted(QUEBRAS))
# Regressão: defeito da rodada 17, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("POST /api/ifc/cronograma responde 500 para IFC VÁLIDO no esquema mas fora do que `cronograma.ler` supõe "
#   "— todos atributos OPCIONAIS no IFC 4.3 e comuns em arquivo de terceiro: SequenceType NOTDEFINED ou "
#   "ausente (KeyError em SEQ_INV), IfcTask sem TaskTime (AttributeError), exceção de calendário só com "
#   "recorrência, sem StartDate (TypeError em fromisoformat), padrão WEEKLY sem WeekdayComponent "
#   "(TypeError), tarefa sem Identification, cronograma sem StartTime (início None no motor). A rota só "
#   "trata ErroCronograma/ErroRede/ValueError. Correção: validar cada um em `ler` e levantar ErroCronograma")
def test_ifc_de_terceiro_incompleto_e_422_nao_500(nome):
    """O mesmo arquivo íntegro do teste anterior, com UM atributo opcional do IFC retirado ou num valor
    que o esquema permite. Esperado: 422 com o motivo."""
    P = _mini()
    f = _arquivo(P)
    QUEBRAS[nome](f)
    assert _post(_app({"x": P}), f).status_code == 422
