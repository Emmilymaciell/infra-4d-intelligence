"""Earned Schedule (ES): segundo método de previsão, independente do CPM, para confrontá-lo.

Referência: W. Lipke, "Schedule is Different", The Measurable News, mar. 2003 (origem do
método). Fórmulas CONFERIDAS contra o registro da pesquisa R05 §4 (docs/research/R05-pesquisa-
aprofundada.md), que as confirmou nos PDFs públicos do site do autor
(https://www.earnedschedule.com/Docs/Forecasting%20Schedule%20Variance%20Using%20Earned%20Schedule.pdf):
SV(t) = ES − AT; SPI(t) = ES/AT; IEAC(t) = PD/SPI(t) (forma curta) ou AT + (PD − ES)/PF (longa);
IECD = início + IEAC(t). Aqui IEAC(PF=SPI) = AT + (PD − ES)·AT/ES = PD/SPI(t), idêntico à forma curta.
Convenção de data (nossa): a data exibida é o ÚLTIMO dia de trabalho, início + ⌈IEAC⌉ − 1, porque PD
conta o dia de início (PD = término da LB − início + 1).

Definições (unidade de tempo = dia CORRIDO desde o início do projeto; o beta não tem custo):

- PV(t) = avanço planejado da LINHA DE BASE em t (``painel.avanco`` sobre o cenário
  ``linha_base``), ponderado por esforço planejado em equipe·dia;
- EV    = avanço REAL na data de status (``painel.avanco`` sobre o cenário independente em
  t = data de status: até a data de status ele usa o executado medido);
- ES    = instante em que a LB atingiu o EV (Lipke: C + I, interpolado no dia). Em PATAMAR da PV igual
  ao EV (fim de semana, feriado, período sem serviço, lote que ainda não devia ter começado) vale
  min(fim do patamar, max(início do patamar, AT)): obra no plano (EV = PV(AT)) tem ES = AT e SPI = 1
  (revisão r8: o "fim do patamar" sem esse limite dava SPI 1,4 a 3,0 a obras no plano);
- AT    = data de status − início (para as fórmulas, max(0, AT): status antes do início projeta a
  LB e o SPI fica indefinido); SV(t) = ES − AT; SPI(t) = ES ÷ AT;
- PD    = duração planejada (término da LB − início + 1);
- IEAC(t) = AT + (PD − ES) ÷ PF, com PF = 1 (o restante sai como planejado) e PF = SPI(t)
  (o desempenho de prazo observado continua). Data = início + ⌈IEAC⌉ − 1.

O ES IGNORA a lógica da rede: olha o avanço agregado, ponderado, e não sabe QUAL trabalho
atrasou. O CPM independente respeita relações, calendários e a produtividade de cada frente.
A diferença entre os dois é a informação: grande quando o atraso está concentrado no caminho
crítico (o ES dilui) ou em frentes com folga (o ES exagera).
"""

from __future__ import annotations

import math

from .calendario import iso, ordinal
from .cenarios import Projeto, executar
from .painel import avanco


def _termino_lote(resultado: dict, projeto: Projeto, lote: str | None) -> int | None:
    """Último dia (ordinal) das tarefas do lote no resultado; obra inteira = término do cenário."""
    if not lote:
        return ordinal(resultado["termino"])
    ts = [ordinal(r["termino"]) for aid, r in resultado["atividades"].items()
          if projeto.atividades.get(aid, {}).get("lote_id") == lote and r.get("termino")]
    return max(ts) if ts else None


def earned_schedule(projeto: Projeto, res_lb: dict, res_real: dict, lote: str | None = None,
                    res_construtora: dict | None = None) -> dict:
    ini = projeto.inicio_projeto
    ds = ordinal(res_real["data_status"]) if res_real.get("data_status") else projeto.data_status
    fim_lb = _termino_lote(res_lb, projeto, lote)
    if fim_lb is None:
        raise ValueError(f"lote sem atividades: {lote}")
    PD = fim_lb - ini + 1
    AT = ds - ini
    EV = avanco(projeto, res_real, ds, lote)

    def pv(t):
        return avanco(projeto, res_lb, t, lote)

    PV_AT = pv(ds)
    # ES (Lipke) com a regra do PATAMAR limitada pela data de status (revisão r8):
    #   C0 = 1º dia com PV >= EV. Se PV(C0) == EV (patamar), C1 = último dia do patamar e
    #   ES = min(C1, max(C0, AT)): obra no plano (EV = PV(AT)) tem ES = AT e SPI = 1, mesmo com o status
    #   num fim de semana, num período sem serviço ou antes de o lote começar. Senão, interpola entre
    #   C0 − 1 e C0 (Lipke: C + I).
    TOL = 5e-7  # o EV/PV publicados têm 6 casas
    AT_ef = max(0, AT)  # status antes do início: nada pode ter sido ganho; projeta a LB
    fim = fim_lb + 1

    def primeiro(cond, lo, hi):
        while lo < hi:
            m = (lo + hi) // 2
            if cond(m):
                hi = m
            else:
                lo = m + 1
        return lo

    c0 = primeiro(lambda t: pv(t) >= EV - TOL, ini, fim)
    p_c0 = pv(c0)
    if p_c0 <= EV + TOL:
        c1 = primeiro(lambda t: pv(t) > EV + TOL, c0, fim + 1) - 1
        c1 = min(c1, fim)
        ES = float(min(c1, max(c0, ini + AT_ef)) - ini)
    else:
        p0 = pv(c0 - 1)
        ES = (c0 - 1 - ini) + (EV - p0) / (p_c0 - p0)
    SV = ES - AT_ef
    SPI = ES / AT_ef if AT_ef > 0 else None

    def data(ieac):
        return None if ieac is None or not math.isfinite(ieac) else iso(ini + math.ceil(ieac - 1e-9) - 1)

    ieac1 = AT_ef + (PD - ES)
    ieac_spi = AT_ef + (PD - ES) / SPI if SPI else None
    cpm_ind = _termino_lote(res_real, projeto, lote)
    cpm_con = _termino_lote(res_construtora, projeto, lote) if res_construtora else None
    d_spi = ini + math.ceil(ieac_spi - 1e-9) - 1 if ieac_spi else None
    explicacao = _explicar(d_spi, cpm_ind, SPI)
    return {
        "lote": lote,
        "inicio": iso(ini), "data_status": iso(ds), "termino_linha_base": iso(fim_lb),
        "PD_dias": PD, "AT_dias": AT,
        "PV_em_AT": round(PV_AT, 6), "EV": round(EV, 6),
        "ES_dias": round(ES, 3), "ES_data": iso(ini + int(ES)),
        "SV_dias": round(SV, 3), "SPI": None if SPI is None else round(SPI, 4),
        "IEAC_pf1_dias": round(ieac1, 3), "IEAC_pf1_termino": data(ieac1),
        "IEAC_spi_dias": None if ieac_spi is None else round(ieac_spi, 3), "IEAC_spi_termino": data(ieac_spi),
        "cpm_independente_termino": iso(cpm_ind) if cpm_ind else None,
        "cpm_construtora_termino": iso(cpm_con) if cpm_con else None,
        "diferenca_es_spi_vs_cpm_independente_dias": (d_spi - cpm_ind) if d_spi and cpm_ind else None,
        "explicacao": explicacao,
    }


def _explicar(d_spi: int | None, cpm: int | None, spi: float | None) -> str:
    base = ("O Earned Schedule projeta pelo avanço AGREGADO (SPI = {spi}) e ignora a lógica da rede; o CPM "
            "independente respeita relações, calendários e a produtividade medida de cada frente. ")
    s = base.format(spi="n/d" if spi is None else f"{spi:.3f}")
    if d_spi is None or cpm is None:
        return s + "Sem avanço medido suficiente para projetar pelo ES."
    dif = d_spi - cpm
    if abs(dif) <= 5:
        return s + f"Os dois métodos concordam (diferença de {dif:+d} dias corridos, tolerância de 5)."
    if dif < 0:
        return s + (f"O ES termina {-dif} dias corridos ANTES: o padrão típico de atraso concentrado no caminho "
                    f"crítico, que o avanço agregado dilui. O CPM localiza qual trabalho atrasou.")
    return s + (f"O ES termina {dif} dias corridos DEPOIS: o padrão típico de atraso em frentes com folga, "
                f"que o avanço agregado trata como críticas, ou de recuperação prevista na rede. Confira as frentes no CPM.")


def previsao(projeto: Projeto, lote: str | None = None, resultados: dict | None = None) -> dict:
    """ES da obra e de cada lote (ou só do ``lote``). ``resultados`` = {cenario: dict} já calculados."""
    res = dict(resultados or {})
    for c in ("linha_base", "construtora", "independente"):
        if c not in res:
            res[c] = executar(projeto, c)
    lotes = [l["id"] for l in projeto.dados.get("lotes", [])]
    if lote and lote not in lotes:
        raise ValueError(f"lote desconhecido: {lote}")
    alvo = [lote] if lote else [None] + lotes
    resultados, vazios = [], []
    for l in alvo:
        if l is not None and _termino_lote(res["linha_base"], projeto, l) is None:
            if lote:
                raise ValueError(f"lote sem atividades: {l}")
            vazios.append(l)  # lote cadastrado sem atividades: fica de fora, declarado (r8)
            continue
        resultados.append(earned_schedule(projeto, res["linha_base"], res["independente"], l, res["construtora"]))
    return {
        "metodo": "Earned Schedule (Lipke, 2003) sobre avanço ponderado por esforço planejado (equipe·dia)",
        "referencia_verificada": True,
        "nota": ("fórmulas conferidas contra a R05 §4 (docs/research/R05-pesquisa-aprofundada.md), que as "
                 "confirmou em https://www.earnedschedule.com/Docs/Forecasting%20Schedule%20Variance%20Using"
                 "%20Earned%20Schedule.pdf: SPI(t)=ES/AT, IEAC(t)=PD/SPI(t) ou AT+(PD−ES)/PF, IECD=início+IEAC. "
                 "Data exibida = último dia de trabalho (início + ⌈IEAC⌉ − 1)."),
        "unidade": "dias corridos desde o início do projeto",
        "resultados": resultados,
        "lotes_sem_atividades": vazios,
    }
