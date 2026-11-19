"""Análise de sensibilidade do TÉRMINO (gráfico tornado), sobre o cenário independente.

Para cada GRUPO (lote, serviço) com atividades por quantidade NÃO concluídas:

- produtividade efetiva (a do cenário independente, com a fonte dos boletins) × (1 − p) e × (1 + p), só nas
  atividades pendentes do grupo; recalcula com ``executar(..., "simulado", ajustes)``;
- variante de EQUIPES: + ``equipes`` em cada atividade pendente do grupo (produtividade inalterada);
- Δ término em dias ÚTEIS do calendário da obra (mesma régua de ``cenarios.comparar``) e em dias corridos.

Classificação (regras declaradas, derivadas só dos números):
- **amplitude** = Δ(piorar) − Δ(melhorar), em dias úteis; o tornado é ordenado por ela (decrescente);
- **efeito zero**: Δ = 0 nos dois sentidos (a folga absorve ±p);
- **assimétrico**: piorar atrasa e melhorar antecipa MENOS DA METADE disso (|Δ melhorar| < 0,5 × Δ piorar).
  Só a forma 1/(1 ± p) já dá uma assimetria pequena (com p = 10%, a melhora rende ~82% da piora); abaixo
  de 50% a causa é estrutural: outro caminho com folga próxima passa a determinar o término;
- **reverso**: piorar ANTECIPA (paradoxo de rede, atividade reversa — ver ``cenarios.comparar``);
- **fora do horizonte**: a variação leva o término além do horizonte do calendário (2040) — com p alto a
  produtividade cai a quase zero. O grupo fica marcado, com Δ None, amplitude None, e vai para o TOPO do
  tornado (impacto maior do que o motor representa); os demais grupos seguem normalmente (revisão r11).
  Se nem o cenário independente de referência calcula, a análise inteira é ``ErroSensibilidade`` (422 na rota).
"""

from __future__ import annotations

import time
from collections import OrderedDict

from .calendario import ErroCalendario, ordinal
from .cenarios import Ajuste, Projeto, executar

LIMIAR_ASSIMETRIA = 0.5
EQUIPES_MAX = 20


class ErroSensibilidade(ValueError):
    """Parâmetro de sensibilidade inválido."""


def _delta(projeto: Projeto, ref: str, novo: str) -> tuple[int, int]:
    cal = projeto.calendarios[projeto.dados["meta"]["calendario_obra"]]
    return cal.dias_uteis_entre(ordinal(ref) + 1, ordinal(novo) + 1), ordinal(novo) - ordinal(ref)


def grupos_pendentes(projeto: Projeto, ind: dict) -> "OrderedDict[tuple, list[str]]":
    """(lote, serviço) -> ids das atividades por quantidade não concluídas, na ordem do dataset."""
    g: OrderedDict = OrderedDict()
    for a in projeto.dados["atividades"]:
        r = ind["atividades"][a["id"]]
        if a.get("tipo", "tarefa") != "tarefa" or not a.get("quantidade_total") or r["status"] == "concluida":
            continue
        g.setdefault((a.get("lote_id"), a.get("servico_id")), []).append(a["id"])
    return g


def _simular(projeto: Projeto, ajustes: list) -> dict | None:
    """Cenário simulado, ou None se a variação passa do horizonte do calendário."""
    try:
        return executar(projeto, "simulado", ajustes)
    except ErroCalendario:
        return None


def _variante(projeto: Projeto, ref: str, sim: dict | None, **extra) -> dict:
    if sim is None:
        return {**extra, "termino": None, "delta_dias_uteis": None, "delta_dias_corridos": None,
                "fora_do_horizonte": True}
    du, dc = _delta(projeto, ref, sim["termino"])
    return {**extra, "termino": sim["termino"], "delta_dias_uteis": du, "delta_dias_corridos": dc,
            "fora_do_horizonte": False}


def _dias(n: int) -> str:
    return f"{abs(n)} dia útil" if abs(n) == 1 else f"{abs(n)} dias úteis"


def _explicar(nome: str, p: float, linha: dict, posicao: str, equipes: int) -> str:
    dm, dp = linha["melhorar"]["delta_dias_uteis"], linha["piorar"]["delta_dias_uteis"]
    pct = f"{p:.0%}"
    partes = [f"{nome} {posicao}."]
    if linha["fora_do_horizonte"]:
        fora = [k for k in ("melhorar", "piorar", "equipes") if linha.get(k, {}).get("fora_do_horizonte")]
        rot = {"melhorar": f"+{pct} de produtividade", "piorar": f"−{pct} de produtividade",
               "equipes": f"+{equipes} equipe(s)"}
        partes.append("Com " + " e ".join(rot[k] for k in fora) + " o término passa do horizonte do calendário "
                      "(2040): impacto além do que o motor representa.")
        return " ".join(partes)
    if linha["efeito_zero"]:
        partes.append(f"A folga absorve ±{pct} de produtividade: o término não muda.")
    else:
        partes.append(("+" + pct + " de produtividade " + (f"antecipa {_dias(dm)}" if dm < 0 else
                       ("não antecipa" if dm == 0 else f"ATRASA {_dias(dm)}")) + "; "))
        partes[-1] += "−" + pct + " " + (f"atrasa {_dias(dp)}" if dp > 0 else
                                          ("não atrasa" if dp == 0 else f"ANTECIPA {_dias(dp)}")) + "."
        if linha["reverso"]:
            partes.append("Efeito reverso: piorar antecipa (paradoxo de rede).")
        elif linha["assimetrico"]:
            partes.append("Assimétrico: melhorar rende menos da metade do que piorar custa "
                          "(outro caminho com folga próxima passa a determinar o término).")
    if linha.get("equipes"):
        de = linha["equipes"]["delta_dias_uteis"]
        partes.append(f"+{equipes} equipe{'s' if equipes > 1 else ''}: " +
                      (f"antecipa {_dias(de)}." if de < 0 else ("não muda o término." if de == 0 else
                                                               f"atrasa {_dias(de)}.")))
    return " ".join(partes)


def tornado(projeto: Projeto, p: float = 0.10, equipes: int = 1) -> dict:
    if not (isinstance(p, (int, float)) and 0 <= p < 1):
        raise ErroSensibilidade("p deve estar em [0, 1)")
    if isinstance(equipes, bool) or not isinstance(equipes, int) or not 0 <= equipes <= 10:
        raise ErroSensibilidade("equipes deve ser inteiro entre 0 e 10 (0 = sem a variante)")
    t0 = time.perf_counter()
    try:
        ind = executar(projeto, "independente")
    except ErroCalendario as e:
        raise ErroSensibilidade(f"o cenário independente de referência não calcula: {e}") from None
    execucoes = 1
    cadeia = set(ind["cadeia_determinante"])
    linhas = []
    for (lote, serv), ids in grupos_pendentes(projeto, ind).items():
        prods = {i: ind["atividades"][i]["memoria"]["produtividade"] for i in ids}
        linha = {"lote_id": lote, "servico_id": serv, "atividades": ids}
        for chave, fator in (("melhorar", 1 + p), ("piorar", 1 - p)):
            sim = _simular(projeto, [Ajuste(produtividade=prods[i] * fator, atividade_id=i) for i in ids])
            execucoes += 1
            linha[chave] = _variante(projeto, ind["termino"], sim, fator=fator)
        if equipes:
            aj = [Ajuste(equipes=min(EQUIPES_MAX, int(ind["atividades"][i]["memoria"]["equipes"]) + equipes),
                         atividade_id=i) for i in ids]
            execucoes += 1
            linha["equipes"] = _variante(projeto, ind["termino"], _simular(projeto, aj), acrescimo=equipes)
        dm, dp = linha["melhorar"]["delta_dias_uteis"], linha["piorar"]["delta_dias_uteis"]
        linha["fora_do_horizonte"] = dm is None or dp is None or bool(linha.get("equipes", {}).get("fora_do_horizonte"))
        if dm is None or dp is None:
            linha["amplitude_dias_uteis"] = None
            linha["efeito_zero"] = linha["reverso"] = linha["assimetrico"] = False
        else:
            linha["amplitude_dias_uteis"] = dp - dm
            linha["efeito_zero"] = dm == 0 and dp == 0 and linha["melhorar"]["delta_dias_corridos"] == 0 \
                and linha["piorar"]["delta_dias_corridos"] == 0
            linha["reverso"] = dp < 0 or dm > 0
            linha["assimetrico"] = (not linha["reverso"]) and dp > 0 and abs(dm) < LIMIAR_ASSIMETRIA * dp
        no_cadeia = [i for i in ids if i in cadeia]
        criticas = [i for i in ids if ind["atividades"][i]["critica"]]
        folgas = [ind["atividades"][i]["folga_total"] for i in ids if ind["atividades"][i]["folga_total"] is not None]
        linha["no_caminho_determinante"] = no_cadeia
        linha["menor_folga_total"] = min(folgas) if folgas else None
        if no_cadeia:
            posicao = f"está no caminho determinante ({', '.join(no_cadeia)})"
        elif criticas:
            posicao = f"tem atividade crítica fora da cadeia determinante ({', '.join(criticas)})"
        else:
            posicao = f"está fora do caminho crítico (menor folga total: {linha['menor_folga_total']} dias úteis)"
        linha["explicacao"] = _explicar(f"{serv} do {lote}", p, linha, posicao, equipes)
        linhas.append(linha)
    # fora do horizonte primeiro (impacto além do representável), depois amplitude decrescente
    linhas.sort(key=lambda x: (x["amplitude_dias_uteis"] is not None, -(x["amplitude_dias_uteis"] or 0),
                               -abs(x["piorar"]["delta_dias_corridos"] or 0), str(x["lote_id"]), str(x["servico_id"])))
    return {
        "cenario_referencia": "independente", "termino_referencia": ind["termino"],
        "p": p, "equipes": equipes,
        "regras": {"amplitude": "Δ(piorar) − Δ(melhorar) em dias úteis do calendário da obra",
                   "assimetrico": f"|Δ melhorar| < {LIMIAR_ASSIMETRIA} × Δ piorar",
                   "efeito_zero": "Δ = 0 nos dois sentidos", "reverso": "piorar antecipa ou melhorar atrasa",
                   "fora_do_horizonte": "a variação passa do horizonte do calendário; Δ None; topo do tornado"},
        "n_fora_do_horizonte": sum(x["fora_do_horizonte"] for x in linhas),
        "grupos": linhas,
        "execucoes_motor": execucoes,
        "tempo_s": round(time.perf_counter() - t0, 3),
    }
