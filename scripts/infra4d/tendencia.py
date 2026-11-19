"""Análise de tendência de marcos (MTA — Milestone Trend Analysis), sem vazar dado futuro.

Para cada data de status semanal ``d`` (passo configurável, contada para TRÁS a partir da data de status
atual, de modo que a última data é exatamente a atual), monta a FOTOGRAFIA da obra em ``d`` e recalcula
os cenários construtora e independente e o término de cada marco de término.

Fotografia em ``d`` — regras declaradas, usando só o que se sabia em ``d``:
- BOLETIM conhecido em ``d`` se a semana dele já TERMINOU: fim = min(semana_inicio + 7, término real + 1 se a
  atividade concluiu, data de status atual) <= d. Boletim de semana em curso não entra;
- atividade INICIADA se ``inicio_real < d``; CONCLUÍDA se ``termino_real < d`` (senão em andamento, sem
  término real); NÃO INICIADA se ``inicio_real >= d`` (perde as datas reais);
- quantidade executada = soma dos boletins conhecidos (o mesmo vínculo boletim -> executado do gerador);
- duração fixa em andamento: % = dias úteis decorridos ÷ duração planejada (no máximo 99%), porque o % da
  data de status atual seria dado futuro; na data atual vale o % do próprio dataset;
- restrições (R12): liberada em ``d`` se a liberação REAL (``data_liberacao``) <= d, e aí vale a data real (fato
  passado). Se ainda não liberou em ``d``, a data real é informação FUTURA: vale a data PREVISTA
  (``data_liberacao_planejada``; na falta dela, o início da atividade na linha de base, também conhecido desde o
  começo), nunca antes de ``d``. O mesmo vale para ``restricao_inicio`` da atividade restringida.
Na data de status ATUAL a fotografia é o próprio dataset — por isso a última linha da série bate com o painel.

Saída por marco: série [{data_status, termino_construtora, termino_independente}], inclinação (regressão
linear do término contra a data de status, em dias de deslize por semana) e a primeira data em que a
independente passa a divergir da construtora em mais de ``limiar_divergencia_dias`` dias corridos.
"""

from __future__ import annotations

import time

from .calendario import iso, ordinal
from .cenarios import Projeto, executar

CENARIOS_MTA = ("construtora", "independente")
LIMIAR_DIVERGENCIA_DIAS = 15     # o mesmo do alerta do painel (independente − construtora > 15 dias)


class ErroTendencia(ValueError):
    """Parâmetro inválido para a tendência."""


def fotografia(dados: dict, d: int) -> dict:
    """Dados da obra como eram conhecidos na data ``d`` (ordinal). Não altera ``dados``."""
    ds_atual = ordinal(dados["meta"]["data_status"])
    if d > ds_atual:
        raise ErroTendencia("a fotografia não pode ser posterior à data de status atual")
    if d == ds_atual:
        return dados
    ativ = {a["id"]: a for a in dados["atividades"]}
    calendarios = {c["id"]: c for c in dados["calendarios"]}

    def fim_boletim(m: dict) -> int:
        a = ativ.get(m["atividade_id"], {})
        fim = min(ordinal(m["semana_inicio"]) + 7, ds_atual)
        if a.get("termino_real"):
            fim = min(fim, ordinal(a["termino_real"]) + 1)
        return fim

    medicoes = [m for m in dados.get("medicoes", []) if fim_boletim(m) <= d]
    soma: dict[str, float] = {}
    for m in medicoes:
        soma[m["atividade_id"]] = soma.get(m["atividade_id"], 0.0) + m["quantidade"]

    from .calendario import Calendario
    cals = {}
    novas = []
    for a in dados["atividades"]:
        b = dict(a)
        for k in ("inicio_real", "termino_real", "quantidade_executada", "percentual_executado"):
            b.pop(k, None)
        ini = ordinal(a.get("inicio_real")) if a.get("inicio_real") else None
        fim = ordinal(a.get("termino_real")) if a.get("termino_real") else None
        if ini is None or ini >= d:
            b["status"] = "nao_iniciada"
            if "quantidade_total" in a:
                b["quantidade_executada"] = 0.0
        else:
            b["inicio_real"] = a["inicio_real"]
            if fim is not None and fim < d:
                b["status"] = "concluida"
                b["termino_real"] = a["termino_real"]
            else:
                b["status"] = "em_andamento"
            if a.get("tipo", "tarefa") == "tarefa":
                if "quantidade_total" in a:
                    b["quantidade_executada"] = round(soma.get(a["id"], 0.0), 3)
                elif b["status"] == "concluida":
                    b["percentual_executado"] = 100.0
                else:
                    cid = a["calendario"]
                    if cid not in cals:
                        cals[cid] = Calendario.de_dict(calendarios[cid])
                    dias = cals[cid].dias_uteis_entre(ini, d)
                    b["percentual_executado"] = min(99.0, round(100 * dias / max(1, a.get("duracao_fixa", 1)), 1))
        novas.append(b)
    restricoes = []
    por_ativ = {b["id"]: b for b in novas}
    for r in dados.get("restricoes", []):
        if not r.get("data_liberacao"):                 # sem data informada: fica como está (pendente)
            restricoes.append(dict(r))
            continue
        if ordinal(r["data_liberacao"]) <= d:
            restricoes.append({**r, "situacao": "liberada"})
            continue
        b = por_ativ.get(r["atividade_id"], {})
        prevista = r.get("data_liberacao_planejada") or b.get("inicio_lb") or r["data_liberacao"]
        prevista = iso(max(ordinal(prevista), d))
        restricoes.append({**r, "situacao": "pendente", "data_liberacao": prevista,
                           "data_liberacao_fonte": "prevista em d" if r.get("data_liberacao_planejada")
                           else "início na linha de base (sem data prevista no dataset)"})
        if b and b.get("restricao_inicio"):
            b["restricao_inicio"] = prevista
    return {**dados, "meta": {**dados["meta"], "data_status": iso(d), "fotografia_de": dados["meta"]["data_status"]},
            "atividades": novas, "medicoes": medicoes, "restricoes": restricoes}


def datas_de_status(dados: dict, passo_dias: int) -> list[int]:
    ds = ordinal(dados["meta"]["data_status"])
    ini = ordinal(dados["meta"]["inicio_projeto"])
    out, d = [], ds
    while d > ini:
        out.append(d)
        d -= passo_dias
    return out[::-1]


def _inclinacao(xs: list[int], ys: list[int]) -> float | None:
    """Mínimos quadrados de y (término) contra x (data de status), em dias de término por SEMANA."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    return 7 * sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


def tendencia(projeto: Projeto, passo_dias: int = 7, limiar_divergencia_dias: int = LIMIAR_DIVERGENCIA_DIAS) -> dict:
    if isinstance(passo_dias, bool) or not isinstance(passo_dias, int) or not 1 <= passo_dias <= 91:
        raise ErroTendencia("passo_dias deve ser inteiro entre 1 e 91")
    if isinstance(limiar_divergencia_dias, bool) or not isinstance(limiar_divergencia_dias, int) \
            or limiar_divergencia_dias < 0:
        raise ErroTendencia("limiar_divergencia_dias deve ser inteiro >= 0")
    t0 = time.perf_counter()
    dados = projeto.dados
    marcos = [a for a in dados["atividades"] if a.get("tipo") == "marco_termino"]
    series = {a["id"]: [] for a in marcos}
    datas = datas_de_status(dados, passo_dias)
    execucoes = 0
    for d in datas:
        P = projeto if d == ordinal(dados["meta"]["data_status"]) else Projeto(fotografia(dados, d))
        res = {c: executar(P, c) for c in CENARIOS_MTA}
        execucoes += len(CENARIOS_MTA)
        for a in marcos:
            series[a["id"]].append({"data_status": iso(d),
                                    **{f"termino_{c}": res[c]["atividades"][a["id"]]["termino"] for c in CENARIOS_MTA}})
    saida = []
    for a in marcos:
        s = series[a["id"]]
        xs = [ordinal(p["data_status"]) for p in s]
        incl = {c: _inclinacao(xs, [ordinal(p[f"termino_{c}"]) for p in s]) for c in CENARIOS_MTA}
        divergiu = next((p["data_status"] for p in s
                         if ordinal(p["termino_independente"]) - ordinal(p["termino_construtora"]) > limiar_divergencia_dias),
                        None)
        saida.append({"id": a["id"], "nome": a.get("nome"), "lote_id": a.get("lote_id"), "serie": s,
                      "inclinacao_dias_por_semana": {c: None if v is None else round(v, 3) for c, v in incl.items()},
                      "divergencia_desde": divergiu})
    return {
        "passo_dias": passo_dias, "limiar_divergencia_dias": limiar_divergencia_dias,
        "datas_de_status": [iso(d) for d in datas],
        "regras": {
            "boletim": "conhecido em d se a semana terminou: min(início + 7, término real + 1, data de status) <= d",
            "atividade": "iniciada se início real < d; concluída se término real < d",
            "duracao_fixa": "em andamento: dias úteis decorridos ÷ duração planejada (máx. 99%)",
            "inclinacao": "regressão linear do término contra a data de status, em dias por semana",
            "divergencia": f"1ª data em que independente − construtora > {limiar_divergencia_dias} dias corridos",
        },
        "marcos": saida,
        "execucoes_motor": execucoes,
        "tempo_s": round(time.perf_counter() - t0, 3),
    }
