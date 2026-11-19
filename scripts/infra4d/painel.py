"""Indicadores do painel gerencial e estado 4D, calculados a partir dos cenários.

Avanço físico ponderado por ESFORÇO PLANEJADO (equipe·dia):
    peso = quantidade_total ÷ produtividade_planejada   (atividade por quantidade)
    peso = duracao_fixa                                (atividade de duração fixa)
Não há custo no beta (5D é evolução futura), por isso o peso não é financeiro.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .calendario import iso, ordinal
from .cenarios import Projeto, preparar_progresso, progresso_em, progresso_preparado


def peso(a: dict) -> float:
    if a.get("tipo", "tarefa") != "tarefa":
        return 0.0
    if a.get("quantidade_total"):
        return a["quantidade_total"] / a["produtividade_planejada"]
    return float(a.get("duracao_fixa", 0))


def _filtrar(projeto: Projeto, lote: str | None):
    return [a for a in projeto.dados["atividades"] if not lote or a.get("lote_id") == lote]


def _ds(resultado: dict) -> int | None:
    return ordinal(resultado["data_status"]) if resultado.get("data_status") else None


def _preparar_avanco(projeto: Projeto, resultado: dict, lote: str | None) -> list[tuple[float, tuple]]:
    """[(peso, progresso preparado)] na ordem das atividades — a mesma ordem de soma de ``avanco``."""
    ds = _ds(resultado)
    out = []
    for a in _filtrar(projeto, lote):
        w = peso(a)
        if w:
            out.append((w, preparar_progresso(projeto, a, resultado["atividades"][a["id"]], ds)))
    return out


def _avanco_preparado(itens: list[tuple[float, tuple]], t: int) -> float:
    num = den = 0.0
    for w, prep in itens:
        num += w * progresso_preparado(prep, t)
        den += w
    return num / den if den else 0.0


def avanco(projeto: Projeto, resultado: dict, t: int, lote: str | None = None) -> float:
    return _avanco_preparado(_preparar_avanco(projeto, resultado, lote), t)


def estado_4d(projeto: Projeto, res: dict, res_lb: dict, t: int) -> dict:
    """Estado de cada atividade na data ``t`` (fração executada vs. linha de base)."""
    saida = {}
    for a in projeto.dados["atividades"]:
        r = res["atividades"][a["id"]]
        f = progresso_em(projeto, a, r, t, _ds(res))
        flb = progresso_em(projeto, a, res_lb["atividades"][a["id"]], t, None)
        # "concluído" só quando a fração é exatamente 1 (concluída ou t >= EF); 99,95 % em
        # andamento continua em execução (revisão adversarial, rodada 2)
        if f >= 1.0:
            estado = "concluido"
        elif f > 0:
            estado = "em_execucao"
        else:
            estado = "nao_iniciado"
        saida[a["id"]] = {"fracao": round(f, 4), "fracao_lb": round(flb, 4), "estado": estado,
                          "desvio": round(f - flb, 4), "critica": r["critica"]}
    return saida


def curva_s(projeto: Projeto, resultados: dict[str, dict], lote: str | None = None, passo_dias: int = 14) -> dict:
    ini = projeto.inicio_projeto
    fim = max(ordinal(r["termino"]) for r in resultados.values()) + passo_dias
    datas, series = [], defaultdict(list)
    # otimização: datas convertidas e pesos calculados UMA vez por cenário (antes, a cada data)
    preparados = {nome: _preparar_avanco(projeto, r, lote) for nome, r in resultados.items()}
    t = ini
    while t <= fim:
        datas.append(iso(t))
        for nome in resultados:
            series[nome].append(round(100 * _avanco_preparado(preparados[nome], t), 2))
        t += passo_dias
    return {"datas": datas, "series": dict(series)}


def produtividades(projeto: Projeto, lote: str | None = None) -> list[dict]:
    """Planejada x efetiva por (lote, serviço), com a fonte declarada."""
    vistos, linhas = set(), []
    for a in _filtrar(projeto, lote):
        if not a.get("quantidade_total"):
            continue
        k = (a.get("lote_id"), a.get("servico_id"))
        if k in vistos:
            continue
        vistos.add(k)
        ef = projeto._prod_ef["lote_servico"].get(k)
        linhas.append({
            "lote_id": k[0], "servico_id": k[1], "unidade": a["unidade"],
            "planejada": a["produtividade_planejada"],
            "efetiva": None if not ef else round(ef[0], 3),
            "boletins": 0 if not ef else ef[1],
            "indice": None if not ef else round(ef[0] / a["produtividade_planejada"], 3),
        })
    return linhas


def producao_semanal(projeto: Projeto, lote: str | None = None, semanas: int = 16) -> dict:
    ativ = projeto.atividades
    ds = projeto.data_status
    corte = ds - 7 * semanas
    por = defaultdict(lambda: defaultdict(float))
    for m in projeto.dados.get("medicoes", []):
        a = ativ.get(m.get("atividade_id"))
        if a is None or not a.get("quantidade_total") or not m.get("semana_inicio"):
            continue  # boletim órfão ou de atividade sem quantidade: ignorado, como em cenarios.py
        if lote and a.get("lote_id") != lote:
            continue
        t = ordinal(m["semana_inicio"])
        if t < corte:
            continue
        semana = date.fromordinal(t - date.fromordinal(t).weekday()).isoformat()
        por[a.get("servico_id")][semana] += m["quantidade"] / a["quantidade_total"] * 100
    todas = sorted({s for d in por.values() for s in d})
    return {"semanas": todas,
            "servicos": {s: [round(d.get(w, 0.0), 2) for w in todas] for s, d in sorted(por.items())},
            "unidade": "% da quantidade da atividade executada na semana (somado no serviço)"}


def alertas(projeto: Projeto, res_ind: dict, res_con: dict, lote: str | None = None) -> list[dict]:
    out = []
    ds = projeto.data_status
    for a in _filtrar(projeto, lote):
        r = res_ind["atividades"][a["id"]]
        if r["status"] == "concluida" or a.get("tipo") != "tarefa":
            continue
        mem = r["memoria"]
        if mem.get("regra") == "quantidade" and r["critica"]:
            idx = mem["produtividade"] / mem["produtividade_planejada"]
            if idx < 0.85:
                out.append({"nivel": "alto", "atividade_id": a["id"],
                            "texto": f"{a['id']} é CRÍTICA e produz {idx:.0%} do planejado "
                                     f"({mem['fonte_produtividade']})."})
        if r["status"] == "em_andamento" and r["folga_total"] is not None and 0 < r["folga_total"] <= 10:
            out.append({"nivel": "medio", "atividade_id": a["id"],
                        "texto": f"{a['id']} em andamento com folga total de apenas {r['folga_total']} dias úteis."})
    for rest in projeto.dados.get("restricoes", []):
        if rest["situacao"] != "pendente":
            continue
        a = projeto.atividades.get(rest.get("atividade_id"))
        if a is None:
            # restrição sem atividade conhecida: dado inconsistente, avisado em vez de derrubar o painel (r15)
            if not lote:
                out.append({"nivel": "medio", "atividade_id": None,
                            "texto": f"Restrição pendente '{rest.get('descricao', '?')}' sem atividade conhecida "
                                     f"({rest.get('atividade_id')!r}): não entra na análise."})
            continue
        if lote and a.get("lote_id") != lote:
            continue
        r = res_ind["atividades"][a["id"]]
        if r["folga_total"] is None:
            continue  # atividade já concluída: a restrição pendente não ameaça mais o prazo (r15)
        out.append({"nivel": "alto" if r["folga_total"] <= 10 else "medio", "atividade_id": a["id"],
                    "texto": f"Restrição pendente '{rest.get('descricao', '?')}' libera "
                             f"{rest.get('data_liberacao') or 'em data não informada'}; "
                             f"{a['id']} tem folga total {r['folga_total']} no cenário independente."})
    d = ordinal(res_ind["termino"]) - ordinal(res_con["termino"])
    if d > 15 and not lote:
        out.append({"nivel": "alto", "atividade_id": None,
                    "texto": f"A previsão independente termina {d} dias corridos depois da previsão da construtora "
                             f"({res_ind['termino']} vs {res_con['termino']})."})
    ordem = {"alto": 0, "medio": 1}
    return sorted(out, key=lambda x: ordem[x["nivel"]])


def marcos_contratuais(projeto: Projeto, resultados: dict[str, dict], lote: str | None = None) -> list[dict]:
    """Marcos de término com prazo = data da LINHA DE BASE (contratual, fictícia) e o desvio
    de cada previsão em dias corridos (positivo = atraso)."""
    saida = []
    for a in projeto.dados["atividades"]:
        if a.get("tipo") != "marco_termino" or (lote and a.get("lote_id") != lote):
            continue
        prazo = resultados["linha_base"]["atividades"][a["id"]]["termino"]
        linha = {"id": a["id"], "nome": a["nome"], "lote_id": a.get("lote_id"), "prazo": prazo}
        for c in ("construtora", "independente", "simulado"):
            if c in resultados:
                t = resultados[c]["atividades"][a["id"]]["termino"]
                linha[c] = t
                linha[f"desvio_{c}"] = ordinal(t) - ordinal(prazo)
        saida.append(linha)
    return saida


def termino_lote(res: dict, lote: str) -> str | None:
    m = res["atividades"].get(f"M-{lote}-FIM")
    return m["termino"] if m else None


def datas_semanais(projeto: Projeto, fim: str) -> list[str]:
    t = date.fromordinal(projeto.inicio_projeto)
    f = date.fromisoformat(fim) + timedelta(days=14)
    out = []
    while t <= f:
        out.append(t.isoformat())
        t += timedelta(days=7)
    return out
