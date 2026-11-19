"""Registro CONSOLIDADO de riscos ao prazo: junta os sinais que o sistema já calcula.

Cada risco traz título, nível, Δ potencial no término (dias CORRIDOS, quando calculável),
probabilidade (quando houver: índice de criticidade do Monte Carlo), atividades e frentes afetadas,
EVIDÊNCIAS — a rota GET exata, os parâmetros e o caminho no JSON que reproduzem cada número — e uma
explicação montada só a partir desses números.

Fontes (importação tolerante: módulo ausente ou com erro = fonte OMITIDA e declarada em
``fontes_omitidas``; ``rapido=True`` pula as fontes caras, também declaradas):

==============  ==========================================================  ======================
fonte           sinal                                                       Δ / probabilidade
==============  ==========================================================  ======================
produtividade   frente (lote, serviço) com tarefa crítica no independente   —
                e índice medida/planejada < 1 (painel)
restricao       restrição pendente do dataset                               — (folga da atividade)
clima           cenário chuvoso (+30 % da chuva do mês, ``clima.py``)        Δ do cenário
tornado         grupos com amplitude > 0 (p = 10 %, ``sensibilidade.py``)    Δ de −10 % de produção
criticidade     índice de criticidade do grupo >= 0,5 (MC 200 it., sem. 7)  probabilidade (caro)
es_cpm          Earned Schedule × CPM independente, |diferença| > 5 dias    Δ = diferença, se > 0
recuperacao     prazo contratual (término da LB) inviável sem mudança       Δ = atraso projetado (caro)
balanco         conflitos projetados de linha de balanço (buffer 1 km)       —
dcma            pontos DCMA reprovados no independente                      — (confiança)
nao_conformidade  NC da fiscalização VENCIDA (``nao_conformidade.py``)       — (dias vencida)
==============  ==========================================================  ======================

DEDUPLICAÇÃO: sinais da MESMA frente (lote, serviço) — produtividade, restrição, tornado e
criticidade — viram UM risco, com as fontes DISTINTAS citadas, Δ = maior Δ das fontes e probabilidade =
a da criticidade. Atividade SEM serviço (marco, liberação) tem chave própria (a atividade), nunca a
frente (lote, None). Os demais sinais são de obra (clima, ES×CPM, recuperação, DCMA) ou de par de
frentes (balanço) e ficam separados. "Confirmado por N fontes" conta fontes distintas (duas restrições
na mesma frente são UMA fonte).

ORDENAÇÃO (declarada; decisão do orquestrador, revisão r15): pelo Δ (impacto em dias, decrescente);
riscos sem Δ depois; desempate por nível (alto > médio > baixo) e pela chave (lote, serviço…). A
probabilidade e a exposição Δ × p são ATRIBUTOS exibidos e NÃO entram na ordem — assim o modo rápido
(sem Monte Carlo) e o completo dão a mesma ordem relativa.

RESTRIÇÃO pendente em atividade já CONCLUÍDA (folga indefinida) não é tratada como folga 0: vira risco
de nível BAIXO com o aviso "cadastro provavelmente desatualizado".

EVIDÊNCIA: parâmetro ausente não é gravado (nunca ``obra: null``); a rota grava a obra resolvida.
"""

from __future__ import annotations

import time

from .cenarios import Projeto, executar

NIVEIS = ("alto", "medio", "baixo")
P_TORNADO = 0.1
EQ_TORNADO = 1
INTENS_CLIMA = 0.3
MC_IT, MC_SEM = 200, 7
LIMIAR_CRITICIDADE = 0.5
LIMIAR_ES_CPM = 5
BUFFER_BALANCO = 1.0
FONTES_CARAS = ("criticidade", "recuperacao")


def _ev(rota: str, params: dict, caminho: list, valor) -> dict:
    return {"rota": rota, "params": {k: v for k, v in params.items() if v is not None}, "caminho": caminho,
            "valor": valor}


def extrair(dado, caminho: list):
    """Segue ``caminho`` no JSON: chave (str), índice (int) ou filtro (dict: 1º item da lista com esses campos)."""
    for passo in caminho:
        if isinstance(passo, dict):
            dado = next(x for x in dado if all(x.get(k) == v for k, v in passo.items()))
        else:
            dado = dado[passo]
    return dado


def _nivel_max(*ns):
    return min((n for n in ns if n), key=NIVEIS.index, default="baixo")


def _frente(projeto: Projeto, aid: str) -> tuple:
    a = projeto.atividades[aid]
    return a.get("lote_id"), a.get("servico_id")


# ============================================================================ fontes
def _f_produtividade(projeto, ind, obra):
    from .painel import produtividades
    crit = {}
    for aid, r in ind["atividades"].items():
        a = projeto.atividades[aid]
        if r["critica"] and r["status"] != "concluida" and a.get("quantidade_total"):
            crit.setdefault(_frente(projeto, aid), []).append(aid)
    out = []
    for lote in sorted({k[0] for k in crit}, key=str):
        for linha in produtividades(projeto, lote):
            k = (linha["lote_id"], linha["servico_id"])
            if k in crit and linha["indice"] is not None and linha["indice"] < 1:
                idx = linha["indice"]
                out.append({"chave": ("frente",) + k, "fonte": "produtividade", "atividades": crit[k],
                            "nivel": "alto" if idx < 0.85 else "medio", "delta": None, "prob": None,
                            "titulo": f"{k[1]} do {k[0]}: frente crítica abaixo da produtividade planejada",
                            "texto": f"{k[1]} do {k[0]} produz {idx:.0%} do planejado ({linha['boletins']} boletins) "
                                     f"e tem {len(crit[k])} tarefa(s) crítica(s) no independente.",
                            "evidencias": [_ev("/api/painel", {"obra": obra, "lote": k[0]},
                                               ["produtividades", {"lote_id": k[0], "servico_id": k[1]}, "indice"],
                                               idx)]})
    return out


def _f_restricao(projeto, ind, obra):
    out = []
    for rest in projeto.dados.get("restricoes", []):
        if rest.get("situacao") != "pendente" or rest.get("atividade_id") not in projeto.atividades:
            continue
        aid = rest["atividade_id"]
        r = ind["atividades"][aid]
        ft = r["folga_total"]
        lote, serv = _frente(projeto, aid)
        chave = ("frente", lote, serv) if serv else ("atividade", aid)
        if r["status"] == "concluida" or ft is None:
            nivel = "baixo"
            texto = (f"Restrição '{rest.get('descricao')}' consta como pendente, mas {aid} já está "
                     f"{'concluída' if r['status'] == 'concluida' else 'sem folga calculada'}: não atrasa o término; "
                     "cadastro provavelmente desatualizado.")
        else:
            nivel = "alto" if ft <= 10 else "medio"
            texto = (f"Restrição pendente '{rest.get('descricao')}' libera em {rest.get('data_liberacao')}; "
                     f"{aid} tem folga total de {ft} dias úteis no independente.")
        out.append({"chave": chave, "fonte": "restricao", "atividades": [aid],
                    "nivel": nivel, "delta": None, "prob": None,
                    "titulo": f"Restrição pendente: {rest.get('descricao')}",
                    "texto": texto,
                    "evidencias": [_ev("/api/cenarios/independente", {"obra": obra},
                                       ["atividades", aid, "folga_total"], ft)]})
    return out


def _f_clima(projeto, ind, obra):
    from .clima import cenarios_climaticos
    r = cenarios_climaticos(projeto, intensidade=INTENS_CLIMA)
    c = next(x for x in r["cenarios"] if x["tipo"] == "chuvoso")
    d = c["delta_dias_corridos"]
    if d <= 0:
        return []
    return [{"chave": ("obra", "clima"), "fonte": "clima", "atividades": c["criticas_em_calendario_sensivel"],
             "nivel": "alto" if d >= 10 else "medio", "delta": d, "prob": None,
             "titulo": f"Chuva acima da média (+{INTENS_CLIMA:.0%}) nos calendários {', '.join(r['calendarios_sensiveis'])}",
             "texto": c["explicacao"],
             "evidencias": [_ev("/api/clima", {"obra": obra, "intensidade": INTENS_CLIMA, "deslocamento_semanas": 0},
                                ["cenarios", {"tipo": "chuvoso"}, "delta_dias_corridos"], d)]}]


def _f_tornado(projeto, ind, obra):
    from .sensibilidade import tornado
    r = tornado(projeto, P_TORNADO, EQ_TORNADO)
    out = []
    for g in r["grupos"]:
        if g["amplitude_dias_uteis"] <= 0 or g["piorar"]["delta_dias_corridos"] <= 0:
            continue
        d = g["piorar"]["delta_dias_corridos"]
        k = (g["lote_id"], g["servico_id"])
        out.append({"chave": ("frente",) + k, "fonte": "tornado", "atividades": g["atividades"],
                    "nivel": "alto" if d >= 10 else "medio" if d >= 3 else "baixo", "delta": d, "prob": None,
                    "titulo": f"{k[1]} do {k[0]}: término sensível à produtividade",
                    "texto": f"−{P_TORNADO:.0%} de produção em {k[1]} do {k[0]} atrasa o término em {d} dias corridos "
                             f"(amplitude {g['amplitude_dias_uteis']} dias úteis).",
                    "evidencias": [_ev("/api/sensibilidade", {"obra": obra, "p": P_TORNADO, "equipes": EQ_TORNADO},
                                       ["grupos", {"lote_id": k[0], "servico_id": k[1]}, "piorar",
                                        "delta_dias_corridos"], d)]})
    return out


def _f_criticidade(projeto, ind, obra):
    from .montecarlo import simular
    r = simular(projeto, MC_IT, MC_SEM, com_criticidade=True)
    out = []
    for g in r["criticidade"]["grupos"]:
        if g["indice"] < LIMIAR_CRITICIDADE or g["servico_id"] is None:
            continue
        k = (g["lote_id"], g["servico_id"])
        ids = [x["id"] for x in r["criticidade"]["atividades"]
               if (x["lote_id"], x["servico_id"]) == k and x["indice"] > 0]
        out.append({"chave": ("frente",) + k, "fonte": "criticidade", "atividades": ids,
                    "nivel": "alto" if g["indice"] >= 0.8 else "medio", "delta": None, "prob": g["indice"],
                    "titulo": f"{k[1]} do {k[0]}: frequentemente crítica na simulação",
                    "texto": f"{k[1]} do {k[0]} foi crítica em {g['indice']:.0%} das {MC_IT} iterações do Monte Carlo.",
                    "evidencias": [_ev("/api/previsao-probabilistica",
                                       {"obra": obra, "iteracoes": MC_IT, "semente": MC_SEM, "com_criticidade": True},
                                       ["criticidade", "grupos", {"lote_id": k[0], "servico_id": k[1]}, "indice"],
                                       g["indice"])]})
    return out


def _f_es_cpm(projeto, ind, obra):
    from .previsao_es import previsao
    out = []
    for x in previsao(projeto)["resultados"]:
        dif = x["diferenca_es_spi_vs_cpm_independente_dias"]
        if dif is None or abs(dif) <= LIMIAR_ES_CPM:
            continue
        nome = f"lote {x['lote']}" if x["lote"] else "obra"
        params = {"obra": obra, **({"lote": x["lote"]} if x["lote"] else {})}
        out.append({"chave": ("obra", "es_cpm", x["lote"]), "fonte": "es_cpm", "atividades": [],
                    "nivel": "medio" if dif > 0 else "baixo", "delta": dif if dif > 0 else None, "prob": None,
                    "titulo": f"Earned Schedule × CPM divergem ({nome})",
                    "texto": f"No {nome}, o Earned Schedule (SPI {x['SPI']}) projeta {x['IEAC_spi_termino']} e o CPM "
                             f"independente {x['cpm_independente_termino']}: diferença de {dif:+d} dias corridos. "
                             + ("O ES é mais pessimista: atraso fora da cadeia crítica pode virar crítico."
                                if dif > 0 else "O CPM é mais pessimista: o atraso está concentrado na cadeia crítica."),
                    "evidencias": [_ev("/api/previsao/earned-schedule", params,
                                       ["resultados", {"lote": x["lote"]}, "diferenca_es_spi_vs_cpm_independente_dias"],
                                       dif)]})
    return out


def _f_recuperacao(projeto, ind, obra):
    from .recuperacao import recuperar
    from .calendario import ordinal
    r = recuperar(projeto)
    if r["viabilidade"] not in ("inviavel", "inviavel_sem_mudanca_de_metodo"):
        return []
    d = ordinal(r["termino_atual"]) - ordinal(r["prazo"])
    texto = (f"O independente termina em {r['termino_atual']}, {d} dias corridos depois do prazo {r['prazo']}. "
             + (f"Nem com {r['parametros']['fator_max']:g} × a produtividade medida o prazo é alcançado "
                f"(melhor: {r['termino_alcancado']})." if r["viabilidade"] == "inviavel"
                else f"O plano mínimo exige {len(r['plano'])} frente(s), com aumentos até "
                     f"{max(p['aumento_pct'] for p in r['plano']):.0f} % — acima de 1,3 × a melhor semana medida."))
    return [{"chave": ("obra", "recuperacao"), "fonte": "recuperacao",
             "atividades": [p["id"] for p in r["plano"]], "nivel": "alto", "delta": d, "prob": None,
             "titulo": "Prazo contratual sem recuperação viável" if r["viabilidade"] == "inviavel"
             else "Prazo contratual só com mudança de método",
             "texto": texto,
             "evidencias": [_ev("/api/recuperacao", {"obra": obra}, ["viabilidade"], r["viabilidade"]),
                            _ev("/api/recuperacao", {"obra": obra}, ["termino_atual"], r["termino_atual"])]}]


def _f_balanco(projeto, ind, obra):
    from .recursos import conflitos_balanco
    c = conflitos_balanco(projeto, ind, buffer_km=BUFFER_BALANCO)
    por = {}
    for e in c["conflitos"]:
        k = (e["lote"], tuple(e["servicos"]))
        por.setdefault(k, []).append(e)
    out = []
    for (lote, servs), es in sorted(por.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        ultr = any(e["ultrapassagem"] for e in es)
        pior = min(es, key=lambda e: (e["distancia_km_min"], e["data"]))
        dmin = pior["distancia_km_min"]
        ids = sorted({i for e in es for i in e["atividades"]})
        out.append({"chave": ("balanco", lote, servs), "fonte": "balanco", "atividades": ids,
                    "nivel": "alto" if ultr else "medio", "delta": None, "prob": None,
                    "titulo": f"Frentes {servs[0]}→{servs[1]} do {lote} próximas demais (linha de balanço)",
                    "texto": f"{len(es)} conflito(s) projetado(s) entre {servs[0]} e {servs[1]} no {lote}; distância "
                             f"mínima {dmin:.3f} km (buffer {BUFFER_BALANCO:g} km)"
                             + ("; há ULTRAPASSAGEM (sucessora à frente da antecessora)." if ultr else "."),
                    "evidencias": [_ev("/api/recursos/conflitos-balanco",
                                       {"obra": obra, "cenario": "independente", "buffer_km": BUFFER_BALANCO},
                                       ["conflitos", {"lote": lote, "servicos": list(servs),
                                                      "atividades": pior["atividades"], "data": pior["data"]},
                                        "distancia_km_min"], dmin)]})
    return out


def _f_dcma(projeto, ind, obra):
    from .dcma import avaliar_cenario
    d = avaliar_cenario(projeto, "independente")
    rep = [p for p in d["pontos"] if p["aprovado"] is False]
    if not rep:
        return []
    nomes = "; ".join(f"{p['numero']}. {p['nome']} = {p['valor']} (limite {p['criterio']} {p['limite']})" for p in rep)
    return [{"chave": ("obra", "dcma"), "fonte": "dcma", "atividades": [],
             "nivel": "medio" if any(p["numero"] in (13, 14) for p in rep) else "baixo", "delta": None, "prob": None,
             "titulo": f"Qualidade do cronograma: {len(rep)} ponto(s) DCMA reprovado(s)",
             "texto": f"Reprovados no independente: {nomes}. Afetam a CONFIANÇA na previsão, não o término em si.",
             "evidencias": [_ev("/api/dcma", {"obra": obra, "cenario": "independente"},
                                ["resumo", "reprovados"], d["resumo"]["reprovados"])]}]


def _f_nao_conformidade(projeto, ind, obra):
    """NCs VENCIDAS da fiscalização (``nao_conformidade.fonte_riscos``, módulo da pesquisa-r05, só leitura).
    Import tolerante: módulo ausente -> ImportError -> fonte em ``fontes_omitidas``. Sem NC declarada, nenhum
    sinal (os rankings atuais não mudam)."""
    from .nao_conformidade import fonte_riscos
    return fonte_riscos(projeto, ind, obra)


FONTES = (("produtividade", _f_produtividade), ("restricao", _f_restricao), ("clima", _f_clima),
          ("tornado", _f_tornado), ("criticidade", _f_criticidade), ("es_cpm", _f_es_cpm),
          ("recuperacao", _f_recuperacao), ("balanco", _f_balanco), ("dcma", _f_dcma),
          ("nao_conformidade", _f_nao_conformidade))


# ============================================================================ consolidação
def consolidar(sinais: list[dict]) -> list[dict]:
    """Deduplica por chave (mesma frente = mesma chave) e ordena pela regra declarada."""
    por: dict = {}
    for s in sinais:
        r = por.get(s["chave"])
        if r is None:
            por[s["chave"]] = r = {"chave": s["chave"], "fontes": [], "atividades": [], "titulos": [], "textos": [],
                                   "evidencias": [], "deltas": [], "probs": [], "niveis": []}
        if s["fonte"] not in r["fontes"]:
            r["fontes"].append(s["fonte"])
        r["atividades"] += [a for a in s["atividades"] if a not in r["atividades"]]
        r["titulos"].append(s["titulo"])
        r["textos"].append(s["texto"])
        r["evidencias"] += [dict(e, fonte=s["fonte"]) for e in s["evidencias"]]
        if s["delta"] is not None:
            r["deltas"].append(s["delta"])
        if s["prob"] is not None:
            r["probs"].append(s["prob"])
        r["niveis"].append(s["nivel"])
    riscos = []
    for r in por.values():
        delta = max(r["deltas"]) if r["deltas"] else None
        prob = max(r["probs"]) if r["probs"] else None
        expo = None if delta is None else (delta * prob if prob is not None else float(delta))
        ch = r["chave"]
        frentes = [{"lote_id": ch[1], "servico_id": ch[2]}] if ch[0] == "frente" else (
            [{"lote_id": ch[1], "servico_id": s} for s in ch[2]] if ch[0] == "balanco" else [])
        titulo = (f"{ch[2]} do {ch[1]}: risco ao prazo confirmado por {len(r['fontes'])} fontes"
                  if ch[0] == "frente" and len(r["fontes"]) > 1 else r["titulos"][0])
        riscos.append({
            "titulo": titulo, "nivel": _nivel_max(*r["niveis"]),
            "delta_potencial_dias": delta, "probabilidade": prob, "exposicao": None if expo is None else round(expo, 3),
            "atividades": r["atividades"], "frentes": frentes, "fontes": r["fontes"],
            "evidencias": r["evidencias"], "explicacao": " ".join(r["textos"]),
            "_chave": "|".join(str(x) for x in ch),
        })
    riscos.sort(key=lambda x: (x["delta_potencial_dias"] is None, -(x["delta_potencial_dias"] or 0),
                               NIVEIS.index(x["nivel"]), x["_chave"]))
    for n, x in enumerate(riscos, 1):
        x["id"] = f"RP-{n:02d}"
        x.pop("_chave")
    return riscos


def registro(projeto: Projeto, obra: str | None = None, rapido: bool = False, fontes=None) -> dict:
    t0 = time.perf_counter()
    ind = executar(projeto, "independente")
    sinais, omitidas, tempos = [], {}, {}
    for nome, f in (fontes or FONTES):
        if rapido and nome in FONTES_CARAS:
            omitidas[nome] = "pulada no modo rápido (cálculo caro)"
            continue
        t = time.perf_counter()
        try:
            sinais += f(projeto, ind, obra)
        except ImportError as e:
            omitidas[nome] = f"módulo indisponível: {e}"
        except Exception as e:  # noqa: BLE001 — uma fonte quebrada não derruba o registro; fica declarada
            omitidas[nome] = f"falhou: {type(e).__name__}: {e}"
        tempos[nome] = round(time.perf_counter() - t, 3)
    riscos = consolidar(sinais)
    return {
        "obra": obra, "data_status": ind["data_status"], "termino_independente": ind["termino"],
        "rapido": rapido, "n_riscos": len(riscos), "riscos": riscos,
        "fontes_usadas": [n for n, _ in (fontes or FONTES) if n not in omitidas],
        "fontes_omitidas": omitidas,
        "regras": {"ordenacao": "pelo Δ (dias, decrescente); sem Δ depois; desempate por nível (alto > médio > "
                                "baixo) e pela chave. Probabilidade e exposição (Δ × p) são exibidas, mas NÃO entram "
                                "na ordem: modo rápido e completo dão a mesma ordem relativa",
                   "deduplicacao": "sinais da mesma frente (lote, serviço) viram um risco: Δ = maior Δ, "
                                   "probabilidade = índice de criticidade, fontes DISTINTAS citadas; atividade sem "
                                   "serviço tem chave própria",
                   "restricao_em_concluida": "nível baixo, sem folga 0 presumida (cadastro desatualizado)",
                   "delta": "dias corridos no término do cenário independente"},
        "tempos_s": tempos, "tempo_total_s": round(time.perf_counter() - t0, 3),
    }
