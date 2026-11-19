"""Curva S FÍSICA e FINANCEIRA por obra e lote: planejado (LB), previsto construtora, previsto independente
e realizado (boletins), em % do total, numa grade semanal.

Pesos (declarados):
- **física**: esforço planejado = quantidade ÷ produtividade planejada (equipe·dia); duração fixa = dias
  (o mesmo ``painel.peso`` do avanço físico do painel);
- **financeira**: BAC = quantidade × preço de venda FICTÍCIO do ``orcamento.py`` (verba = 1 × preço).

Curvas (fração de cada atividade × peso, somadas, ÷ peso total × 100):
- **planejado**: progresso pela LINHA DE BASE (linear em dias úteis entre início e término da LB);
- **realizado** (só até a data de status): BOLETINS, com a regra de "semana terminada" da MTA (``tendencia``):
  o boletim entra na fronteira min(semana_inicio + 7, término real + 1, data de status). Duração fixa (verba):
  linear em dias úteis do início real até o término real + 1 (ou a data de status), chegando a 100 % (ou ao
  % executado). Na data de status o realizado = Σ executado × peso — na financeira é o EV do ``orcamento``;
- **previsto construtora / independente**: até a data de status = realizado; depois, a previsão do cenário
  (``cenarios.progresso_em``: executado na data de status + remanescente interpolado em dias úteis até o
  término previsto). Fecha em 100 % na fronteira seguinte ao término do cenário e é monotônica.

Convenção de data: fronteira (início do dia), como ``orcamento.curva_s``. Valores financeiros FICTÍCIOS.
"""

from __future__ import annotations

import time
from bisect import bisect_right
from collections import defaultdict

from .calendario import iso, ordinal
from .cenarios import Projeto, preparar_progresso, progresso_preparado
from .painel import peso as peso_fisico

BASES = ("fisica", "financeira")
CURVAS = ("planejado", "previsto_construtora", "previsto_independente", "realizado")


class ErroCurvaS(ValueError):
    """Parâmetro inválido para a curva S."""


def pesos(projeto: Projeto, base: str, lote: str | None = None) -> dict[str, float]:
    """atividade_id -> peso (só tarefas com peso > 0, do lote pedido)."""
    if base not in BASES:
        raise ErroCurvaS(f"base desconhecida: {base} (use fisica ou financeira)")
    if base == "fisica":
        w = {a["id"]: peso_fisico(a) for a in projeto.dados["atividades"]}
    else:
        from .orcamento import exigir_obra_ficticia, orcar_atividades
        exigir_obra_ficticia(projeto)
        w = {ln["atividade_id"]: ln["bac"] for ln in orcar_atividades(projeto)}
    return {aid: v for aid, v in w.items()
            if v > 0 and (not lote or projeto.atividades[aid].get("lote_id") == lote)}


def _fim_boletim(m: dict, a: dict, ds: int) -> int:
    fim = min(ordinal(m["semana_inicio"]) + 7, ds)
    if a.get("termino_real"):
        fim = min(fim, ordinal(a["termino_real"]) + 1)
    return fim


def eventos_realizado(projeto: Projeto, w: dict[str, float]) -> list[tuple[int, float]]:
    """(fronteira, peso realizado) — realizado até a data de status, regra da semana terminada."""
    ds = projeto.data_status
    bol = defaultdict(list)
    for m in projeto.dados.get("medicoes", []):
        bol[m["atividade_id"]].append(m)
    out = []
    for aid, peso in w.items():
        a = projeto.atividades[aid]
        if a.get("status", "nao_iniciada") == "nao_iniciada":
            continue
        total = a.get("quantidade_total")
        if total:
            for m in bol.get(aid, []):
                q = float(m["quantidade"])
                if q:
                    out.append((_fim_boletim(m, a, ds), peso * q / total))
            continue
        alvo = 1.0 if a.get("status") == "concluida" else float(a.get("percentual_executado", 0.0)) / 100
        if alvo <= 0 or not a.get("inicio_real"):
            continue
        cal = projeto.calendarios[a["calendario"]]
        fim = ordinal(a["termino_real"]) + 1 if a.get("termino_real") else ds
        dias = [d for d in range(ordinal(a["inicio_real"]), min(fim, ds)) if cal.eh_util(d)]
        if dias:
            out += [(d + 1, peso * alvo / len(dias)) for d in dias]
        else:
            out.append((min(fim, ds), peso * alvo))
    return out


def _acumulador(eventos):
    ev = sorted(eventos)
    ts = [t for t, _ in ev]
    acc, s = [], 0.0
    for _, v in ev:
        s += v
        acc.append(s)

    def em(t: int) -> float:
        i = bisect_right(ts, t)
        return acc[i - 1] if i else 0.0
    return em


def curva_s(projeto: Projeto, resultados: dict[str, dict], base: str = "fisica", lote: str | None = None,
            passo_dias: int = 7) -> dict:
    """``resultados``: linha_base, construtora e independente (saída de ``cenarios.executar``)."""
    t0 = time.perf_counter()
    if isinstance(passo_dias, bool) or not isinstance(passo_dias, int) or not 1 <= passo_dias <= 91:
        raise ErroCurvaS("passo_dias deve ser inteiro entre 1 e 91")
    if lote and lote not in {l["id"] for l in projeto.dados.get("lotes", [])}:
        raise ErroCurvaS(f"lote desconhecido: {lote}")
    w = pesos(projeto, base, lote)
    total = sum(w.values())
    if total <= 0:
        raise ErroCurvaS("nenhuma atividade com peso na seleção")
    ds = projeto.data_status
    real = _acumulador(eventos_realizado(projeto, w))
    prep = {}
    for c, ds_c in (("linha_base", None), ("construtora", ds), ("independente", ds)):
        prep[c] = [(peso, preparar_progresso(projeto, projeto.atividades[aid], resultados[c]["atividades"][aid], ds_c))
                   for aid, peso in w.items()]

    def frac(c: str, t: int) -> float:
        return sum(peso * progresso_preparado(p, t) for peso, p in prep[c]) / total

    fechamento = {c: ordinal(resultados[c]["termino"]) + 1 for c in ("linha_base", "construtora", "independente")}
    ini = projeto.inicio_projeto
    fim = max(fechamento.values())
    ts = sorted(set(range(ini, fim + passo_dias, passo_dias)) | {ds} | set(fechamento.values()))
    pontos = []
    for t in ts:
        r = real(t) / total if t <= ds else None
        pontos.append({
            "data": iso(t),
            "planejado": round(100 * frac("linha_base", t), 4),
            "previsto_construtora": round(100 * (real(t) / total if t <= ds else frac("construtora", t)), 4),
            "previsto_independente": round(100 * (real(t) / total if t <= ds else frac("independente", t)), 4),
            "realizado": None if r is None else round(100 * r, 4),
        })
    real_ds = real(ds)
    return {
        "base": base, "lote": lote, "passo_dias": passo_dias, "data_status": iso(ds),
        "unidade": "% do total ponderado " + ("pelo esforço planejado (equipe·dia)" if base == "fisica"
                                              else "pelo BAC (R$ FICTÍCIOS, preço de venda)"),
        "total": total, "realizado_na_data_status": real_ds,
        "percentual_realizado_na_data_status": 100 * real_ds / total,
        "fechamento": {c: iso(t) for c, t in fechamento.items()},
        "convencao": "data = fronteira (início do dia); previstos = realizado até a data de status",
        "regras": {"realizado": "boletim na fronteira min(semana_inicio + 7, término real + 1, data de status)",
                   "previsto": "progresso_em do cenário após a data de status; 100 % na fronteira após o término"},
        "aviso": None if base == "fisica" else "Valores financeiros FICTÍCIOS (orcamento.py).",
        "pontos": pontos,
        "tempo_s": round(time.perf_counter() - t0, 3),
    }
