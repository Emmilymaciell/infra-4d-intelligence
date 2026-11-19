"""Backtest da previsão de término (construtora × independente) sobre a MTA, sem dado futuro.

Para cada data passada ``d`` (as datas de ``tendencia.datas_de_status``), a fotografia em ``d``
(``tendencia.fotografia``: só boletins de semana terminada, datas reais anteriores a ``d``) é recalculada
nos cenários construtora e independente. Para cada marco de término:

    erro(d) = término previsto em d − término de REFERÊNCIA        (dias corridos; + = previu tarde)

Duas referências, as duas DECLARADAS:
1. ``final_independente`` (pedida): o término independente na data de status ATUAL. É SINTÉTICA e
   PARCIALMENTE CIRCULAR: usa os mesmos boletins que as previsões das datas próximas (na última data o erro
   da independente é 0 por construção). A circularidade é MEDIDA: fração dos boletins da referência já
   conhecidos em cada ``d`` (``sobreposicao_boletins``) e diferença entre esta referência e a 2ª.
2. ``realidade_simulada`` (quando a obra é uma das sintéticas do beta): o término do "futuro" que o gerador
   simulou e NÃO exporta no dataset — vem do GABARITO, lido só pelo acessor ``sintetico_comum.gabarito`` (P9).
   Não é circular: o motor nunca o vê.
   Só é usada se a obra é reconhecida (gerador e semente do ``meta``) e se as datas reais do dataset batem
   com essa realidade; senão fica indisponível.

PREVISORES: construtora e independente (CPM, cenários) e, como REFERÊNCIA de literatura (R12), o Earned
Schedule de ``previsao_es.earned_schedule`` (só leitura) com PF = 1 (``es_pf1``) e PF = SPI(t) (``es_spi``),
calculado na mesma fotografia, com a linha de base original (o plano é conhecido desde o início).

Métricas por marco, previsor e referência (R12 §2; D = referência − início + 1, a duração "real"):
- erro em cada ``d``; MAE; MAPE = média de |e| / D; viés = média de e (com sinal);
- acerto em ±10 % = fração das datas com |e| <= 0,10·D (margem de Lipke);
- por fase de avanço físico 0–30 %, 30–70 %, 70–100 % (Hurtado): MAPE e acerto;
- erro na 1ª data em que o avanço físico (``painel.avanco`` da fotografia) atinge 10 %, 20 %, …, 90 %;
- ganho da independente sobre cada outro previsor = 1 − MAE_indep / MAE_outro;
- ``independente_melhor_desde``: a partir de quando |e_indep| <= |e_construtora| em todas as datas seguintes.
Datas em que o ES não tem previsão (SPI indefinido logo no início) ficam fora das métricas do ES (contadas).
"""

from __future__ import annotations

import time

from .calendario import iso, ordinal
from .cenarios import Projeto, executar
from .painel import avanco
from .tendencia import ErroTendencia, datas_de_status, fotografia

CENARIOS_BT = ("construtora", "independente")
PREVISORES = CENARIOS_BT + ("es_pf1", "es_spi")
FASES = ((0, 30), (30, 70), (70, 100.0001))
FAIXAS = tuple(range(10, 100, 10))


class ErroBacktest(ValueError):
    """Parâmetro inválido para o backtest."""


def realidade_da_obra(dados: dict) -> tuple[dict[str, str] | None, str]:
    """(término por atividade na realidade simulada, motivo). None se a obra não é reconhecida."""
    # P9: o gabarito NÃO está no dataset; vem do acessor único (marca fictícia, gerador reconhecido, semente;
    # arquivo publicado conferido contra o gerador)
    from .sintetico_comum import ErroGabarito, gabarito
    try:
        real = gabarito(dados)["termino_realidade_simulada"]
    except ErroGabarito as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001 — referência opcional; ausência é declarada, não erro
        return None, f"realidade simulada indisponível: {type(e).__name__}: {e}"
    # coerência (r16): (a) todo marco de término do dataset existe na realidade; (b) toda tarefa concluída terminou
    # quando a realidade diz; (c) toda tarefa iniciada com quantidade tem boletins que somam o executado
    # (dataset sem boletins — ou com boletins trocados — não é o mundo que o gerador simulou)
    for a in dados["atividades"]:
        if a.get("tipo") == "marco_termino" and a["id"] not in real:
            return None, f"marco {a['id']} ausente da realidade simulada do gerador: referência indisponível"
        if a.get("tipo", "tarefa") == "tarefa" and a.get("termino_real") and real.get(a["id"]) != a["termino_real"]:
            return None, f"dataset não corresponde à realidade simulada ({a['id']}): dados alterados?"
    soma: dict[str, float] = {}
    for m in dados.get("medicoes", []):
        soma[m.get("atividade_id")] = soma.get(m.get("atividade_id"), 0.0) + float(m.get("quantidade") or 0)
    for a in dados["atividades"]:
        if a.get("quantidade_total") and a.get("status", "nao_iniciada") != "nao_iniciada":
            if abs(soma.get(a["id"], 0.0) - float(a.get("quantidade_executada") or 0)) > 0.01:
                return None, (f"boletins de {a['id']} não fecham com o executado (soma {soma.get(a['id'], 0.0):g}): "
                              "dataset não é o mundo do gerador")
    return real, "realidade simulada do gerador (semente do meta), coerente com marcos, datas reais e boletins do dataset"


def _mae(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(abs(x) for x in xs) / len(xs), 2) if xs else None


def _metricas(erros: list, avancos: list[float], dur: int) -> dict:
    """MAPE, viés, acerto em ±10 % (geral e por fase de avanço), ignorando datas sem previsão (None)."""
    def bloco(idx):
        es = [erros[i] for i in idx if erros[i] is not None]
        if not es:
            return {"n": 0, "mape": None, "acerto_10pct": None}
        return {"n": len(es), "mape": round(sum(abs(e) for e in es) / len(es) / dur, 4),
                "acerto_10pct": round(sum(abs(e) <= 0.10 * dur for e in es) / len(es), 4)}
    todos = list(range(len(erros)))
    validos = [e for e in erros if e is not None]
    return {**bloco(todos), "vies_dias": round(sum(validos) / len(validos), 2) if validos else None,
            "sem_previsao": len(erros) - len(validos),
            "por_fase": {f"{int(a)}-{int(min(b, 100))}%": bloco([i for i in todos if a <= avancos[i] < b])
                         for a, b in FASES}}


def backtest(projeto: Projeto, passo_dias: int = 7) -> dict:
    if isinstance(passo_dias, bool) or not isinstance(passo_dias, int) or not 1 <= passo_dias <= 91:
        raise ErroBacktest("passo_dias deve ser inteiro entre 1 e 91")
    t0 = time.perf_counter()
    dados = projeto.dados
    ds = ordinal(dados["meta"]["data_status"])
    marcos = [a["id"] for a in dados["atividades"] if a.get("tipo") == "marco_termino"]
    n_bol = len(dados.get("medicoes", [])) or 1
    from .previsao_es import earned_schedule
    res_lb = executar(projeto, "linha_base")       # o plano: conhecido desde o início
    lote_de = {m: projeto.atividades[m].get("lote_id") for m in marcos}
    linhas = []
    for d in datas_de_status(dados, passo_dias):
        try:
            foto = dados if d == ds else fotografia(dados, d)
        except ErroTendencia as e:
            raise ErroBacktest(str(e)) from None
        P = projeto if d == ds else Projeto(foto)
        res = {c: executar(P, c) for c in CENARIOS_BT}
        termino = {c: {m: ordinal(res[c]["atividades"][m]["termino"]) for m in marcos} for c in CENARIOS_BT}
        termino["es_pf1"], termino["es_spi"] = {}, {}
        for m in marcos:
            es = earned_schedule(P, res_lb, res["independente"], lote_de[m])
            for k, campo in (("es_pf1", "IEAC_pf1_termino"), ("es_spi", "IEAC_spi_termino")):
                termino[k][m] = ordinal(es[campo]) if es.get(campo) else None
        linhas.append({"d": d, "avanco": 100 * avanco(P, res["independente"], d),
                       "sobreposicao": len(foto.get("medicoes", [])) / n_bol, "termino": termino})
    limitacoes = [
        "A chuva futura está no calendário desde o início (CAL-TERRA/CAL-PAV): no mundo sintético é previsão "
        "meteorológica perfeita, igual em todas as datas e igual à realidade — decisão declarada (BACKLOG).",
        "Os erros medem o método contra a realidade que o próprio gerador inventou (fatores por lote e serviço, "
        "ruído dos boletins); em obra real só existe a referência circular até o término efetivo."]
    if not linhas:                                    # data de status = início: não há data passada (r16)
        return {"passo_dias": passo_dias, "datas_de_status": [], "avanco_fisico": [], "marcos": [],
                "aviso": "sem data de status anterior à atual: nada a medir", "limitacoes": limitacoes,
                "referencias": {}, "circularidade": {}, "execucoes_motor": 1,
                "tempo_s": round(time.perf_counter() - t0, 3)}
    final = {m: linhas[-1]["termino"]["independente"][m] for m in marcos}
    real, motivo = realidade_da_obra(dados)
    referencias = {"final_independente": final}
    if real is not None:
        referencias["realidade_simulada"] = {m: ordinal(real[m]) for m in marcos}

    saida = []
    for m in marcos:
        por_ref = {}
        for nome_ref, ref in referencias.items():
            erros = {c: [None if ln["termino"][c][m] is None else ln["termino"][c][m] - ref[m] for ln in linhas]
                     for c in PREVISORES}
            dur = ref[m] - projeto.inicio_projeto + 1
            avancos = [ln["avanco"] for ln in linhas]
            faixas = {}
            for f in FAIXAS:
                k = next((i for i, ln in enumerate(linhas) if ln["avanco"] >= f), None)
                faixas[f"{f}%"] = None if k is None else {"data_status": iso(linhas[k]["d"]),
                                                          **{c: erros[c][k] for c in PREVISORES}}
            # a partir de quando a independente fica SEMPRE pelo menos tão acurada quanto a construtora
            desde = None
            for i in range(len(linhas) - 1, -1, -1):
                if abs(erros["independente"][i]) <= abs(erros["construtora"][i]):
                    desde = iso(linhas[i]["d"])
                else:
                    break
            n_melhor = sum(abs(a) < abs(b) for a, b in zip(erros["independente"], erros["construtora"]))
            mae = {c: _mae(erros[c]) for c in PREVISORES}
            por_ref[nome_ref] = {
                "referencia": iso(ref[m]), "duracao_referencia_dias": dur,
                "erro_dias": {c: erros[c] for c in PREVISORES},
                "mae_dias": mae,
                "metricas": {c: _metricas(erros[c], avancos, dur) for c in PREVISORES},
                "ganho_independente_sobre": {c: (None if not mae[c] else round(1 - mae["independente"] / mae[c], 4))
                                              for c in ("construtora", "es_pf1", "es_spi")},
                "por_fracao_concluida": faixas,
                "independente_melhor_desde": desde,
                "datas_independente_estritamente_melhor": n_melhor,
            }
        saida.append({"id": m, "nome": projeto.atividades[m].get("nome"), "por_referencia": por_ref})

    circ = {"sobreposicao_boletins": [round(ln["sobreposicao"], 4) for ln in linhas],
            "nota": "fração dos boletins da referência final já conhecidos em cada data: perto de 1 = previsão e "
                    "referência usam quase os mesmos dados (erro da independente tende a 0 por construção)"}
    if real is not None:
        circ["diferenca_referencias_dias"] = {m: final[m] - referencias["realidade_simulada"][m] for m in marcos}
    return {
        "passo_dias": passo_dias,
        "datas_de_status": [iso(ln["d"]) for ln in linhas],
        "avanco_fisico": [round(ln["avanco"], 3) for ln in linhas],
        "referencias": {"final_independente": "término independente na data de status atual (SINTÉTICA, "
                                              "parcialmente circular)",
                        "realidade_simulada": motivo if real is not None else f"indisponível: {motivo}"},
        "circularidade": circ,
        "limitacoes": limitacoes,
        "marcos": saida,
        "previsores": {"construtora": "CPM, produtividade planejada no remanescente",
                       "independente": "CPM, produtividade medida nos boletins",
                       "es_pf1": "Earned Schedule, IEAC com PF = 1 (previsao_es.py)",
                       "es_spi": "Earned Schedule, IEAC com PF = SPI(t) (previsao_es.py)"},
        "execucoes_motor": 2 * len(linhas) + 1,
        "tempo_s": round(time.perf_counter() - t0, 3),
    }


# =========================================================================== várias sementes (R12 item 3)
GERADORES = {"ferrovia": "dados_sinteticos", "rodovia": "dados_sinteticos_rodovia"}
GERADOR_DO_META = {"scripts/infra4d/dados_sinteticos.py": "ferrovia",
                   "scripts/infra4d/dados_sinteticos_rodovia.py": "rodovia"}
# orçamento de custo (r18): n mundos × nº de datas de status. Medido (2026-11-13): ~0,034 s por (mundo × data)
# (n = 10, passo 7: 530 → 13–18 s). 900 ≈ 30 s. Acima disso, 422 com o menor passo que cabe.
ORCAMENTO_MUNDOS_X_DATAS = 900


def tipo_sintetico(dados: dict) -> str:
    """Tipo de obra do gerador sintético, só se a obra É a sintética do beta (mesma condição de
    ``realidade_da_obra``: marca fictícia, gerador reconhecido e dataset coerente com a realidade simulada)."""
    real, motivo = realidade_da_obra(dados)
    if real is None:
        raise ErroBacktest(f"backtest por sementes só para as obras sintéticas do beta: {motivo}")
    return GERADOR_DO_META[dados["meta"]["gerador"]]


def passo_minimo(dados: dict, n: int) -> int | None:
    """Menor passo (dias) com n × nº de datas <= orçamento; None se nem 91 dias cabe."""
    for p in range(1, 92):
        if n * len(datas_de_status(dados, p)) <= ORCAMENTO_MUNDOS_X_DATAS:
            return p
    return None


def _resumo(xs: list) -> dict | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None

    def q(p):                                    # quantil por interpolação linear (tipo 7)
        k = (len(xs) - 1) * p
        i = int(k)
        return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (k - i)
    return {"n": len(xs), "min": round(xs[0], 4), "p25": round(q(0.25), 4), "mediana": round(q(0.5), 4),
            "p75": round(q(0.75), 4), "max": round(xs[-1], 4), "media": round(sum(xs) / len(xs), 4)}


def backtest_sementes(tipo: str, n: int = 10, passo_dias: int = 7, marco: str = "M-FIM",
                      semente_base: int | None = None) -> dict:
    """Distribuição do erro sobre ``n`` mundos sintéticos (sementes base, base+1, …), gerados EM MEMÓRIA
    pelo gerador da obra (os JSON versionados não são tocados). Referência: ``realidade_simulada`` de cada
    mundo. A semente base (a do JSON publicado) é o 1º mundo."""
    import importlib
    if tipo not in GERADORES:
        raise ErroBacktest(f"obra sem gerador sintético: {tipo} (use {', '.join(GERADORES)})")
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 30:
        raise ErroBacktest("n deve ser inteiro entre 1 e 30")
    mod = importlib.import_module(f".{GERADORES[tipo]}", __package__)
    base = mod.SEMENTE if semente_base is None else semente_base
    if isinstance(passo_dias, bool) or not isinstance(passo_dias, int) or not 1 <= passo_dias <= 91:
        raise ErroBacktest("passo_dias deve ser inteiro entre 1 e 91")
    mundo0 = mod.gerar(base)
    custo = n * len(datas_de_status(mundo0, passo_dias))
    if custo > ORCAMENTO_MUNDOS_X_DATAS:
        sug = passo_minimo(mundo0, n)
        raise ErroBacktest(f"custo acima do orçamento: {n} mundos × {custo // n} datas = {custo} > "
                           f"{ORCAMENTO_MUNDOS_X_DATAS} (≈ 30 s); use passo_dias >= {sug}" if sug else
                           f"custo acima do orçamento com qualquer passo; reduza n")
    t0 = time.perf_counter()
    por_semente = []
    for k in range(n):
        s = base + k
        dados = mundo0 if k == 0 else mod.gerar(s)
        r = backtest(Projeto(dados), passo_dias)
        alvo = next((x for x in r["marcos"] if x["id"] == marco), None)
        if alvo is None:
            raise ErroBacktest(f"marco desconhecido: {marco}")
        ref = alvo["por_referencia"].get("realidade_simulada")
        if ref is None:
            raise ErroBacktest(f"semente {s}: realidade simulada indisponível")
        por_semente.append({"semente": s, "referencia": ref["referencia"],
                            "mae_dias": ref["mae_dias"],
                            "mape": {c: ref["metricas"][c]["mape"] for c in PREVISORES},
                            "acerto_10pct": {c: ref["metricas"][c]["acerto_10pct"] for c in PREVISORES},
                            "vies_dias": {c: ref["metricas"][c]["vies_dias"] for c in PREVISORES},
                            "independente_melhor_desde": ref["independente_melhor_desde"]})
    dist = {met: {c: _resumo([x[met][c] for x in por_semente]) for c in PREVISORES}
            for met in ("mae_dias", "mape", "acerto_10pct", "vies_dias")}
    venceu = {c: sum(x["mae_dias"]["independente"] < x["mae_dias"][c] for x in por_semente)
              for c in ("construtora", "es_pf1", "es_spi")}
    return {"obra": tipo, "marco": marco, "n": n, "passo_dias": passo_dias, "sementes": [x["semente"] for x in por_semente],
            "nota": "mundos sintéticos gerados em memória; fatores de desempenho fixos da narrativa (FATOR_DESEMPENHO) "
                    "são iguais em todas as sementes, mudam os sorteados, a chuva e o ruído dos boletins",
            "por_semente": por_semente, "distribuicao": dist,
            "independente_venceu_em": venceu,
            "custo_mundos_x_datas": custo, "orcamento_mundos_x_datas": ORCAMENTO_MUNDOS_X_DATAS,
            "tempo_s": round(time.perf_counter() - t0, 3)}
