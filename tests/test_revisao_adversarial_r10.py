"""Revisão adversarial — rodada 10: PROPRIEDADES DO SISTEMA INTEIRO (integração entre módulos).

Gera variações FICTÍCIAS (``meta.ficticio = true``) das duas obras sintéticas e confere invariantes ENTRE
módulos, sempre pela API real (``criar_app(fontes=...)`` + TestClient).

Variações (semente fixa 20261112; ver ``_variantes``):
- ``<obra>-base``      : a obra como está;
- ``<obra>-s<k>``      : data de status recuada k semanas com ``persistencia.projeto_na_data`` (boletins,
                         status e executado truncados de forma coerente) E produtividade medida perturbada:
                         em ~1/3 dos pares (lote, serviço) os boletins perdem equipes·dia (fator 0,6 ou 0,8,
                         arredondado a múltiplo das equipes da frente) — a frente "rende mais" sem mudar as
                         quantidades, logo status e executado continuam coerentes;
- ``<obra>-plano``     : obra EXATAMENTE no plano numa quarta-feira: concluído/em andamento/executado
                         copiados da linha de base naquela data, sem boletins.

Tempo: 8 variações × ~20 chamadas de API ≈ 20 s nesta máquina (a coleta é feita uma vez por módulo).
Para encurtar, reduza ``SEMANAS``. Nada aqui é marcado ``slow``.

Mesmo protocolo: invariante que falha fica ``xfail(strict=True, reason="DEFEITO: ...")`` só nas variações
em que falha.
"""

import copy
import random
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d.calendario import iso, ordinal
from infra4d.cenarios import Projeto, executar
from infra4d.painel import peso
from infra4d.persistencia import projeto_na_data

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")
SEMANAS = (9, 23)          # recuos da data de status, em semanas
SEMENTE = 20261112
NOMES = [f"{o}-{s}" for o in OBRAS for s in ("base", *(f"s{k}" for k in SEMANAS), "plano")]


# ----------------------------------------------------------------------------- geração das variações
def _perturbar_boletins(projeto: Projeto, rng: random.Random) -> Projeto:
    d = copy.deepcopy(projeto.dados)
    ativ = {a["id"]: a for a in d["atividades"]}
    pares = sorted({(a.get("lote_id"), a.get("servico_id")) for a in d["atividades"] if a.get("quantidade_total")},
                   key=str)
    fator = {p: rng.choice([0.6, 0.8]) for p in pares if rng.random() < 1 / 3}
    for m in d["medicoes"]:
        a = ativ[m["atividade_id"]]
        f = fator.get((a.get("lote_id"), a.get("servico_id")))
        if f:
            eqs = max(1, int(a.get("equipes") or 1))
            m["equipes_dias"] = max(eqs, int(round(m["equipes_dias"] * f / eqs)) * eqs)
    assert d["meta"]["ficticio"] is True
    return Projeto(d)


def _no_plano(projeto: Projeto, t: int) -> Projeto:
    """Obra exatamente no plano na data ``t``: reais = linha de base, executado proporcional aos dias úteis."""
    lb = executar(projeto, "linha_base")["atividades"]
    d = copy.deepcopy(projeto.dados)
    d["meta"]["data_status"] = iso(t)
    d["medicoes"] = []
    for a in d["atividades"]:
        r = lb[a["id"]]
        ini, fim = ordinal(r["inicio"]), ordinal(r["termino"])
        for k in ("inicio_real", "termino_real"):
            a.pop(k, None)
        marco = a.get("tipo", "tarefa") != "tarefa"
        if fim < t and (not marco or ini < t):
            a.update(status="concluida", inicio_real=r["inicio"], termino_real=r["termino"])
            frac = 1.0
        elif ini < t and not marco:
            cal = projeto.calendarios[a["calendario"]]
            frac = cal.dias_uteis_entre(ini, t) / max(1, cal.dias_uteis_entre(ini, fim + 1))
            a.update(status="em_andamento", inicio_real=r["inicio"])
        else:
            a["status"], frac = "nao_iniciada", 0.0
        if a.get("quantidade_total"):
            a["quantidade_executada"] = a["quantidade_total"] * frac
        elif "duracao_fixa" in a:
            a["percentual_executado"] = 100.0 * frac
    return Projeto(d)


def _variantes() -> dict[str, Projeto]:
    rng = random.Random(SEMENTE)
    out = {}
    for obra in OBRAS:
        base = Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{obra}_ficticia.json")
        out[f"{obra}-base"] = base
        for k in SEMANAS:
            out[f"{obra}-s{k}"] = _perturbar_boletins(projeto_na_data(base, base.data_status - 7 * k), rng)
        t = base.data_status - 7 * 30
        t += (2 - date.fromordinal(t).weekday()) % 7          # quarta-feira
        out[f"{obra}-plano"] = _no_plano(base, t)
    return out


# ----------------------------------------------------------------------------- coleta pela API
def _coletar(nome: str, c: TestClient, projeto: Projeto) -> dict:
    q = {"obra": nome}

    def g(rota, **p):
        r = c.get(rota, params={**q, **p})
        assert r.status_code == 200, (nome, rota, p, r.status_code, r.text[:300])
        return r

    s = {"projeto": projeto}
    s["painel"] = g("/api/painel").json()
    s["ind"] = g("/api/cenarios/independente").json()
    s["relatorio"] = g("/api/relatorio").text
    fim = ordinal(s["ind"]["termino"])
    s["e4d_fim"] = g("/api/estado4d", data=iso(fim)).json()["atividades"]
    s["e4d_depois"] = g("/api/estado4d", data=iso(fim + 1)).json()["atividades"]
    s["es"] = g("/api/previsao/earned-schedule").json()["resultados"]
    s["mc"] = g("/api/previsao-probabilistica", iteracoes=20).json()
    hist = g("/api/recursos/histograma", cenario="independente", agrupar="dia").json()
    s["hist"] = hist
    caps = [f"{x['recurso']}:99" for x in hist["series"]]
    s["niv"] = g("/api/recursos/nivelamento", cenario="independente", capacidade=caps).json()
    xml = g("/api/cronograma/exportar/mspdi", cenario="independente").content
    r = c.post("/api/cronograma/importar", params=q, content=xml, headers={"Content-Type": "application/xml"})
    assert r.status_code == 200, (nome, r.text[:300])
    s["mspdi"] = r.json()
    s["conc"] = g("/api/fiscalizacao/conciliacao").json()

    # simulações: (a) atividade aberta por quantidade da cadeia determinante a 70 % da produtividade;
    #             (b) atividade não crítica com folga, com acréscimo de duração <= folga
    ats = s["ind"]["atividades"]

    def ajustavel(i):
        return ats[i]["status"] != "concluida" and ats[i]["memoria"].get("regra") == "quantidade"

    s["sim_cadeia"] = s["sim_folga"] = None
    crit = next((i for i in s["ind"]["cadeia_determinante"] if ajustavel(i)), None)
    if crit:
        prod = ats[crit]["memoria"]["produtividade"] * 0.7
        r = c.post("/api/simulacao", params=q, json={"ajustes": [{"atividade_id": crit, "produtividade": prod}]})
        assert r.status_code == 200, (nome, r.text[:300])
        s["sim_cadeia"] = (crit, r.json()["comparacao"], g("/api/cenarios/simulado").json()["termino"])
    folgada = next((i for i in sorted(ats, key=lambda k: -(ats[k]["folga_total"] or 0))
                    if ajustavel(i) and not ats[i]["critica"] and (ats[i]["folga_total"] or 0) >= 3
                    and ats[i]["duracao"] >= 5), None)
    if folgada:
        m, a = ats[folgada]["memoria"], ats[folgada]
        alvo = a["duracao"] + min(a["folga_total"], max(1, a["duracao"] // 5))
        prod = m["quantidade_remanescente"] / (m["equipes"] * (alvo - 0.5))
        r = c.post("/api/simulacao", params=q, json={"ajustes": [{"atividade_id": folgada, "produtividade": prod}]})
        assert r.status_code == 200, (nome, r.text[:300])
        s["sim_folga"] = (folgada, r.json()["comparacao"], a["folga_total"])
    assert c.delete("/api/simulacao", params=q).status_code == 200
    return s


@pytest.fixture(scope="module")
def sistema():
    from infra4d.api import criar_app
    variantes = _variantes()
    c = TestClient(criar_app(fontes=variantes), raise_server_exceptions=False)
    return {nome: _coletar(nome, c, p) for nome, p in variantes.items()}


def casos(falham: dict[str, str] | None = None):
    """Parametriza por variação; as listadas em ``falham`` (nome -> motivo) ficam xfail strict."""
    falham = falham or {}
    return [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason="DEFEITO: " + falham[n])) if n in falham
            else n for n in NOMES]


def _br(texto_iso):
    return date.fromisoformat(texto_iso).strftime("%d/%m/%Y")


# =============================================================================
# 1. Término: painel = cenário = relatório = marco final = 4D
# =============================================================================
@pytest.mark.parametrize("v", casos())
def test_termino_e_o_mesmo_em_todo_lugar(sistema, v):
    """Término do /api/painel (independente) = /api/cenarios/independente = "Término — independente" do
    relatório HTML = data do marco M-FIM = maior término entre as atividades."""
    s = sistema[v]
    t = s["ind"]["termino"]
    assert s["painel"]["terminos"]["independente"] == t
    assert dict(re.findall(r"Término — ([^<]+)</span><b>([^<]+)", s["relatorio"]))["independente"] == _br(t)
    assert s["ind"]["atividades"]["M-FIM"]["termino"] == t
    assert max(a["termino"] for a in s["ind"]["atividades"].values()) == t


@pytest.mark.parametrize("v", casos())
def test_marco_final_e_avanco_iguais_no_painel_e_no_relatorio(sistema, v):
    """Marcos contratuais do painel: M-FIM tem prazo = término da linha de base, independente = término do
    cenário e desvio = diferença em dias corridos. O "Avanço físico real" do relatório (1 casa decimal) é o do
    painel (2 casas), a menos do arredondamento."""
    s = sistema[v]
    p = s["painel"]
    m = next(x for x in p["marcos_contratuais"] if x["id"] == "M-FIM")
    assert m["prazo"] == p["terminos"]["linha_base"] and m["independente"] == s["ind"]["termino"]
    assert m["desvio_independente"] == ordinal(m["independente"]) - ordinal(m["prazo"])
    rel, = re.findall(r"Avanço físico real</span><b>([\d.,]+)%", s["relatorio"])
    # o relatório arredonda o avanço a 1 casa e o painel a 2: diferença máxima de 0,05 p.p. (+ folga de float)
    assert float(rel.replace(".", "").replace(",", ".")) == pytest.approx(p["avanco_real"], abs=0.0501)


@pytest.mark.parametrize("v", casos())
def test_estado_4d_fecha_exatamente_no_termino(sistema, v):
    """No início do dia SEGUINTE ao término todo elemento está com fração 1 e estado 'concluido'. No início
    do dia do término ainda há pelo menos uma tarefa com fração < 1 (o último dia ainda não foi trabalhado)."""
    s = sistema[v]
    assert all(x["fracao"] == 1 and x["estado"] == "concluido" for x in s["e4d_depois"].values())
    tarefas = {a["id"] for a in s["projeto"].dados["atividades"] if a.get("tipo", "tarefa") == "tarefa"}
    assert any(s["e4d_fim"][i]["fracao"] < 1 for i in tarefas)


# =============================================================================
# 2. Avanço e curva S
# =============================================================================
@pytest.mark.parametrize("v", casos())
def test_avanco_do_painel_e_a_media_ponderada_do_executado(sistema, v):
    """avanco_real do painel = Σ peso × fração executada ÷ Σ peso, com a fração tirada direto dos dados
    (concluída = 1; por quantidade = executado ÷ total; duração fixa = percentual ÷ 100) e
    peso = esforço planejado (``painel.peso``). Tolerância: 0,01 ponto percentual (arredondamento do painel)."""
    s = sistema[v]
    num = den = 0.0
    for a in s["projeto"].dados["atividades"]:
        w = peso(a)
        if not w:
            continue
        if a.get("status") == "concluida":
            f = 1.0
        elif a.get("status", "nao_iniciada") == "nao_iniciada":
            f = 0.0
        elif a.get("quantidade_total"):
            f = a.get("quantidade_executada", 0) / a["quantidade_total"]
        else:
            f = a.get("percentual_executado", 0) / 100
        num, den = num + w * f, den + w
    assert s["painel"]["avanco_real"] == pytest.approx(100 * num / den, abs=0.01)


@pytest.mark.parametrize("v", casos())
def test_curva_s_e_monotona_e_ancorada(sistema, v):
    """Cada série da curva S começa em 0, termina em 100 e nunca decresce. Até a data de status as séries
    construtora, independente e simulado são idênticas (o passado é o REAL, igual em todo cenário), e o
    último ponto <= data de status não passa do avanço real do painel."""
    s = sistema[v]
    cs, ds = s["painel"]["curva_s"], s["painel"]["data_status"]
    for nome, serie in cs["series"].items():
        assert serie[0] == 0.0 and serie[-1] == 100.0, nome
        assert all(b >= a for a, b in zip(serie, serie[1:])), nome
    passado = [i for i, d in enumerate(cs["datas"]) if d <= ds]
    for i in passado:
        assert cs["series"]["construtora"][i] == cs["series"]["independente"][i] == cs["series"]["simulado"][i]
    assert cs["series"]["independente"][passado[-1]] <= s["painel"]["avanco_real"] + 0.01


# =============================================================================
# 3. Simulação e explicação
# =============================================================================
@pytest.mark.parametrize("v", casos())
def test_piorar_a_produtividade_na_cadeia_determinante_nunca_antecipa(sistema, v):
    """Atividade aberta por quantidade da cadeia determinante com 70 % da produtividade: o término simulado
    é >= o independente — a não ser que a explicação declare 'atividade reversa' para ela.
    A explicação é coerente com o Δ real: delta_dias_corridos = término simulado − término independente;
    Δ != 0 -> há a linha 'Término da obra: …'; Δ = 0 -> 'inalterado'; só uma duração foi alterada (a dela)
    e o efeito isolado tem o mesmo sinal do Δ."""
    s = sistema[v]
    if not s["sim_cadeia"]:
        pytest.skip("variação sem atividade ajustável na cadeia determinante")
    aid, cmp, termino_sim = s["sim_cadeia"]
    delta = ordinal(termino_sim) - ordinal(s["ind"]["termino"])
    texto = " ".join(cmp["explicacao"])
    assert cmp["termino_alvo"] == termino_sim and cmp["delta_dias_corridos"] == delta
    assert [m["id"] for m in cmp["duracoes_alteradas"]] == [aid]
    assert cmp["duracoes_alteradas"][0]["delta_duracao"] > 0
    reversa = "atividade reversa" in next(x for x in cmp["explicacao"] if x.startswith(aid + " ("))
    assert delta >= 0 or reversa
    assert ("Término da obra:" in texto) == (delta != 0) and ("inalterado" in texto) == (delta == 0)
    e = cmp["duracoes_alteradas"][0]["efeito_isolado_dias_uteis"]
    assert (e > 0) == (delta > 0) and (e < 0) == (delta < 0)


@pytest.mark.parametrize("v", casos())
def test_atraso_que_cabe_na_folga_nao_move_o_termino(sistema, v):
    """Atividade não crítica com folga total F: produtividade escolhida para a duração crescer Δ <= F dias
    úteis. O término não muda (delta 0 dias corridos e úteis), a explicação diz 'inalterado' e a linha da
    atividade não fala em propagar."""
    s = sistema[v]
    if not s["sim_folga"]:
        pytest.skip("variação sem atividade ajustável com folga")
    aid, cmp, folga = s["sim_folga"]
    alt, = cmp["duracoes_alteradas"]
    assert alt["id"] == aid and 0 < alt["delta_duracao"] <= folga
    assert (cmp["delta_dias_corridos"], cmp["delta_dias_uteis"]) == (0, 0)
    assert any("inalterado" in x for x in cmp["explicacao"])
    assert "se propaga" not in next(x for x in cmp["explicacao"] if x.startswith(aid + " ("))


# =============================================================================
# 4. Earned Schedule
# =============================================================================
@pytest.mark.parametrize("v", casos())
def test_es_sinal_do_sv_coerente_com_a_projecao(sistema, v):
    """Para a obra e cada lote: SV < 0 (atrasado) -> a projeção PF=1 termina DEPOIS da linha de base;
    SV > 0 -> ANTES ou no mesmo dia; SV = 0 -> no mesmo dia. SPI < 1 ⇔ SV < 0."""
    for r in sistema[v]["es"]:
        lb, pf1, sv, spi = r["termino_linha_base"], r["IEAC_pf1_termino"], r["SV_dias"], r["SPI"]
        if sv < 0:
            assert pf1 > lb and spi < 1, r["lote"]
        elif sv > 0:
            assert pf1 <= lb and spi > 1, r["lote"]
        else:
            assert pf1 == lb and spi == 1, r["lote"]


@pytest.mark.parametrize("v", [n for n in NOMES if n.endswith("plano")])
def test_es_da_obra_no_plano_tem_spi_1(sistema, v):
    """Variação 'plano' (reais = linha de base numa quarta-feira): na obra inteira EV = PV(AT), SPI = 1,000
    (±0,001) e as duas projeções do ES dão o término da linha de base."""
    r = next(x for x in sistema[v]["es"] if x["lote"] is None)
    assert r["EV"] == pytest.approx(r["PV_em_AT"], abs=1e-6)
    assert r["SPI"] == pytest.approx(1.0, abs=1e-3)
    assert r["IEAC_pf1_termino"] == r["IEAC_spi_termino"] == r["termino_linha_base"]


# =============================================================================
# 5. Monte Carlo
# =============================================================================
# (rodada 10: na obra sem boletins o determinístico ficava FORA da faixa — o MC sorteava planejada × U(0,80; 1,05)
# e o independente usava × 1,00. Corrigido: substituto centrado, U(0,85; 1,15). Hoje é regressão.)
@pytest.mark.parametrize("v", casos())
def test_monte_carlo_ordenado_e_contendo_o_deterministico(sistema, v):
    """min <= P10 <= P50 <= P80 <= P90 <= max; o determinístico do MC é o término independente e fica
    dentro de [min, max] das 20 iterações."""
    s = sistema[v]
    m = s["mc"]
    seq = [m[k] for k in ("min", "p10", "p50", "p80", "p90", "max")]
    assert seq == sorted(seq)
    assert m["deterministico"] == s["ind"]["termino"]
    assert m["min"] <= m["deterministico"] <= m["max"]


# =============================================================================
# 6. Recursos
# =============================================================================
@pytest.mark.parametrize("v", casos())
def test_nivelamento_sem_capacidade_restritiva_e_o_proprio_cpm(sistema, v):
    """Com capacidade 99 em todo recurso do histograma, nivelar não desloca ninguém: término nivelado =
    término CPM = término do cenário, 0 atividades atrasadas e as três provas ok."""
    s = sistema[v]
    n = s["niv"]
    assert n["termino_cpm"] == n["termino_nivelado"] == s["ind"]["termino"]
    assert (n["n_atrasadas"], n["delta_dias_corridos"]) == (0, 0)
    assert n["prova_capacidade"]["ok"] and n["prova_relacoes"]["ok"] and n["prova_snet"]["ok"]


@pytest.mark.parametrize("v", casos())
def test_histograma_soma_as_equipes_dia_das_atividades(sistema, v):
    """Σ equipes·dia do histograma diário (todas as séries) = Σ duração remanescente × equipes das tarefas
    abertas com serviço no cenário independente (cada dia útil de trabalho de cada atividade conta as suas
    equipes uma vez). O total diário é a soma das séries."""
    s = sistema[v]
    ativ = {a["id"]: a for a in s["projeto"].dados["atividades"]}
    esperado = 0
    for aid, r in s["ind"]["atividades"].items():
        a = ativ[aid]
        if a.get("tipo", "tarefa") != "tarefa" or not a.get("servico_id") or r["status"] == "concluida":
            continue
        esperado += r["duracao"] * int(r["memoria"].get("equipes") or a.get("equipes") or 1)
    soma = sum(p["equipes_dia"] for x in s["hist"]["series"] for p in x["periodos"])
    assert soma == esperado
    assert sum(p["equipes_dia"] for p in s["hist"]["total"]["periodos"]) == esperado


# =============================================================================
# 7. MSPDI e 8. fiscalização
# =============================================================================
@pytest.mark.parametrize("v", casos())
def test_exportar_e_reimportar_mspdi_reproduz_o_termino(sistema, v):
    """Exportar o cenário independente em MSPDI e reimportar pela API: mesmo término, mesma data de status,
    mesmo número de atividades e a mesma cadeia determinante."""
    s = sistema[v]
    m = s["mspdi"]
    assert m["termino_calculado"] == s["ind"]["termino"]
    assert m["data_status"] == s["ind"]["data_status"]
    assert m["n_atividades"] == len(s["ind"]["atividades"])
    assert m["cadeia_determinante"] == s["ind"]["cadeia_determinante"]


# (rodada 10: nas variações com a data de status recuada, projeto_na_data mantinha inteiro o boletim da semana
# cortada e a conciliação acusava 4 a 9 divergências. Corrigido: o boletim cortado é rateado pelos dias trabalhados
# antes da data, a mesma regra do gerador de diários. Hoje é regressão.)
@pytest.mark.parametrize("v", casos())
def test_fiscalizacao_concilia_sem_divergencia(sistema, v):
    """Diários sintéticos × boletins: 0 divergências e nenhum diário sem boletim, inclusive com a data de
    status recuada e com as equipes·dia dos boletins perturbadas (sempre em múltiplos das equipes)."""
    c = sistema[v]["conc"]
    assert c["sintetico"] is True
    assert (c["n_divergencias"], c["diarios_sem_boletim"]) == (0, [])
