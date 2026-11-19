"""Cobertura da previsão: em que evidência se apoia o término previsto de cada marco.

Motivação (diagnóstico da rodovia L2, docs/research/R12 §5 e BACKLOG P1): a previsão independente projeta a
produtividade observada; onde não há medição ela cai para a analogia da obra ou para a planejada e fica
otimista sem avisar. Este módulo NÃO muda a previsão — declara em que ela se apoia, em três partes.

1. RELATÓRIO POR ORIGEM (informativo). Cadeia determinante do marco: a partir do marco, para trás pelas
   predecessoras que o motor marcou como ``determinantes`` (todas as que empatam), recursivamente. Trabalho
   remanescente de cada tarefa da cadeia em EQUIPE·DIA = remanescente ÷ produtividade usada pelo cenário (sem
   ceil); duração fixa = dias úteis × 1. Origem lida da memória do motor (``fonte_produtividade``, a mesma
   hierarquia de ``cenarios.Projeto.produtividade_efetiva``):

   ===========================  =================================================  ==========
   origem                       texto da memória                                   medida?
   ===========================  =================================================  ==========
   ``atividade_medida``         "medida na própria atividade …"                    sim
   ``lote_servico_medido``      "média medida do serviço no L…"                    sim
   ``analogia_obra``            "média medida do serviço na obra …"                NÃO
   ``planejada``                "sem medição utilizável…" ou "planejada"           NÃO
   ``ajuste_usuario``           "AJUSTE DO USUÁRIO (simulação)"                    NÃO
   ``duracao_fixa``             tarefa sem quantidade (prazo declarado)            neutra
   ``desconhecida``             qualquer outro texto (mudança no motor)            NÃO
   ===========================  =================================================  ==========

   Limite declarado: a cadeia da previsão só mostra o que determina o marco NA previsão. Uma frente sem
   medição com pouca folga fica fora dela — e é exatamente a que pode virar determinante se render menos
   (caso da rodovia L2 em 2026-03-30). Por isso as partes 2 e 3.

2. CONFIANÇA POR ESTRESSE NO MOTOR. Fator ``f`` = PIOR índice (produtividade medida ÷ planejada) por
   (lote, serviço) já observado na obra ATÉ a data de status (só os boletins do dataset/fotografia), limitado
   a 1 e com PISO ``F_MIN`` = 0,25 (abaixo de um quarto do planejado o índice é tratado como erro de cadastro,
   não como ritmo — revisão r17: um boletim de 0,001 un em 500 equipe·dias dava f ≈ 1e-5 e estourava o
   calendário). A resposta traz o índice bruto (``fator_estresse_observado``) e se o piso foi aplicado. Nunca
   um valor externo ou o "gabarito" do gerador. Duas execuções extras do motor:
   - ``sem_medicao``: toda tarefa por quantidade cuja origem NÃO é medida rende × f;
   - ``medida``: toda tarefa por quantidade cuja origem é medida rende × f.
   Δ = término do marco estressado − término previsto (dias corridos). Nível:
   - ``concluido``: marco já concluído; ``sem_historico``: nenhum boletim utilizável (f indefinido);
   - ``indeterminada`` (com ``motivo``), CONFIANÇA EXIGE EVIDÊNCIA (revisão r17):
     (a) f ≥ 1 — nenhuma frente medida rendeu abaixo do planejado, o estresse não testa nada — E a fração sem
         medição do remanescente da cadeia determinante > 0,5; com f ≥ 1 e cobertura medida majoritária vale
         a regra do Δ (que dá ``alta``);
     (b) a execução estressada do motor falhou (``ErroCalendario``: durações além do horizonte do calendário);
   - ``alta`` se Δ_sem_medicao < DELTA_MINIMO_DIAS (7) — a parte sem medição não move o marco de forma relevante;
   - senão, participação p = Δ_sem_medicao ÷ (Δ_sem_medicao + Δ_medida): ``baixa`` se p > 0,50 (a exposição
     ao que não foi medido domina), ``media`` se p > 0,20, ``alta`` caso contrário.
   Também: ``entram_na_cadeia_sob_estresse`` = tarefas com trabalho que passam a determinar o marco quando a
   parte sem medição rende × f.

3. ALERTA DE QUASE-CRÍTICAS SEM MEDIÇÃO. Tarefas com trabalho e origem não medida que são ANTECESSORAS do
   marco (por qualquer relação) com folga RELATIVA AO MARCO ≤ ``folga_alerta_du`` dias úteis. A folga relativa é
   a folga total do próprio motor rodado na SUB-REDE do marco (o marco, suas antecessoras e as relações entre
   elas; mesma data de status), em que o marco é o fim — a folga total da rede inteira mede contra o fim da OBRA
   e daria valores sem sentido para marcos de lote. ``folga_alerta_du`` é parâmetro; o valor do projeto está no manifesto
   (``verificacao.limites.folga_alerta_sem_medicao_du``) e a rota recebe por query.

No cenário ``construtora`` tudo é ``planejada`` por definição: o estresse só tem a parte "sem medição".
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import replace

from .calendario import ErroCalendario, iso
from .cenarios import Ajuste, Projeto, montar_entrada
from .motor import calcular

CENARIOS_COBERTURA = ("construtora", "independente", "simulado")
LIMIAR_BAIXA = 0.50
LIMIAR_ALTA = 0.20
DELTA_MINIMO_DIAS = 7
F_MIN = 0.25                 # piso declarado do fator de estresse (ver docstring, parte 2)
FRACAO_SEM_MEDICAO_INDETERMINADA = 0.50
FOLGA_ALERTA_PADRAO_DU = 10
MEDIDAS = ("atividade_medida", "lote_servico_medido")
NAO_MEDIDAS = ("analogia_obra", "planejada", "ajuste_usuario", "desconhecida")
ORIGENS = MEDIDAS + NAO_MEDIDAS + ("duracao_fixa",)
TOP_FRENTES = 10


class ErroCobertura(ValueError):
    """Parâmetro inválido para a cobertura."""


def origem_da_fonte(memoria: dict) -> str:
    """Classifica a origem da produtividade a partir da memória de cálculo de ``cenarios.montar_entrada``."""
    if memoria.get("regra") == "duração fixa":
        return "duracao_fixa"
    fonte = str(memoria.get("fonte_produtividade") or "")
    if fonte.startswith("medida na própria atividade"):
        return "atividade_medida"
    if fonte.startswith("média medida do serviço na obra"):
        return "analogia_obra"
    if fonte.startswith("média medida do serviço no "):
        return "lote_servico_medido"
    if fonte.startswith("sem medição utilizável") or fonte == "planejada":
        return "planejada"
    if fonte.startswith("AJUSTE DO USUÁRIO"):
        return "ajuste_usuario"
    return "desconhecida"


def fator_estresse(dados: dict) -> tuple[float | None, dict | None]:
    """Pior índice medida/planejada por (lote, serviço) nos boletins do dataset, limitado a 1.

    Índice = (Σ quantidade ÷ Σ equipes·dia) ÷ produtividade planejada média das atividades medidas do par.
    Devolve (f, {lote_id, servico_id, indice, boletins}) ou (None, None) sem boletim utilizável."""
    ativ = {a["id"]: a for a in dados["atividades"]}
    soma = defaultdict(lambda: [0.0, 0.0, 0, set()])
    for m in dados.get("medicoes", []):
        a = ativ.get(m.get("atividade_id"))
        if not a or not m.get("equipes_dias") or m["equipes_dias"] <= 0 or not a.get("produtividade_planejada"):
            continue
        s = soma[(a.get("lote_id"), a.get("servico_id"))]
        s[0] += m["quantidade"]
        s[1] += m["equipes_dias"]
        s[2] += 1
        s[3].add(a["id"])
    pior = None
    for (lote, serv), (q, eqd, n, ids) in soma.items():
        plan = sum(ativ[i]["produtividade_planejada"] for i in ids) / len(ids)
        if eqd <= 0 or plan <= 0:
            continue
        indice = (q / eqd) / plan
        if indice > 0 and (pior is None or indice < pior["indice"]):
            pior = {"lote_id": lote, "servico_id": serv, "indice": round(indice, 4), "boletins": n}
    if pior is None:
        return None, None
    return min(1.0, pior["indice"]), pior


def _equipe_dia(mem: dict) -> float:
    if mem.get("regra") == "quantidade":
        prod = mem["produtividade"]
        return mem["quantidade_remanescente"] / prod if prod > 0 else 0.0
    return float(mem.get("duracao_calculada", 0))  # duração fixa: dias úteis × 1 equipe


def _cadeia(res, marco: str) -> set[str]:
    vistos, pilha = set(), [marco]
    while pilha:
        x = pilha.pop()
        if x not in vistos:
            vistos.add(x)
            pilha.extend(res.atividades[x].determinantes)
    return vistos


def _antecessoras(rels, marco: str) -> set[str]:
    preds = defaultdict(list)
    for r in rels:
        preds[r.sucessora].append(r.predecessora)
    vistos, pilha = set(), [marco]
    while pilha:
        x = pilha.pop()
        for p in preds[x]:
            if p not in vistos:
                vistos.add(p)
                pilha.append(p)
    return vistos


def _estressar(ativs, mem, origem: dict, grupo: tuple, f: float):
    """Cópia das atividades com a produtividade das tarefas por quantidade do ``grupo`` de origens × f."""
    out = []
    for a in ativs:
        m = mem[a.id]
        if (a.tipo == "tarefa" and a.status != "concluida" and m.get("regra") == "quantidade"
                and origem[a.id] in grupo and m["quantidade_remanescente"] > 0):
            taxa = m["produtividade"] * f * m["equipes"]
            dur = math.ceil(m["quantidade_remanescente"] / taxa - 1e-9)
            if a.status == "em_andamento":
                dur = max(1, dur)
            a = replace(a, duracao=dur)
        out.append(a)
    return out


def aplicar_piso(indice: float | None) -> tuple[float | None, bool]:
    """Fator usado = índice limitado a [F_MIN, 1]. Devolve (f, piso_aplicado)."""
    if indice is None:
        return None, False
    return max(F_MIN, min(1.0, indice)), indice < F_MIN


def nivel_confianca(delta_sem: int, delta_med: int) -> tuple[str, float | None]:
    """Nível pelo Δ do estresse (dias corridos). Devolve (nível, participação da parte sem medição)."""
    if delta_sem < DELTA_MINIMO_DIAS:
        tot = delta_sem + delta_med
        return "alta", (round(delta_sem / tot, 4) if tot > 0 else None)
    p = delta_sem / (delta_sem + max(0, delta_med))
    if p > LIMIAR_BAIXA:
        return "baixa", round(p, 4)
    if p > LIMIAR_ALTA:
        return "media", round(p, 4)
    return "alta", round(p, 4)


def cobertura(projeto: Projeto, cenario: str = "independente", ajustes: list[Ajuste] | None = None,
              folga_alerta_du: int = FOLGA_ALERTA_PADRAO_DU) -> dict:
    if cenario not in CENARIOS_COBERTURA:
        raise ErroCobertura(f"cenário inválido: {cenario!r}; use um de {', '.join(CENARIOS_COBERTURA)}")
    if isinstance(folga_alerta_du, bool) or not isinstance(folga_alerta_du, int) or folga_alerta_du < 0:
        raise ErroCobertura("folga_alerta_du deve ser inteiro >= 0")
    ativs, rels, mem = montar_entrada(projeto, cenario, ajustes if cenario == "simulado" else None)

    def rodar(lista):  # mesmos parâmetros de cenarios.executar (data de status, lógica "sobrepor")
        return calcular(lista, rels, projeto.calendarios, projeto.inicio_projeto, data_status=projeto.data_status)

    try:
        res = rodar(ativs)
    except ErroCalendario as e:  # a PRÓPRIA previsão não cabe no calendário (ex.: boletim ínfimo → duração absurda)
        raise ErroCobertura(f"o cenário {cenario} não pode ser calculado pelo motor: {e}. Verifique boletins com "
                            "produtividade implausível") from None
    por_id = {a.id: a for a in ativs}
    origem = {a.id: origem_da_fonte(mem[a.id]) for a in ativs}
    _, pior = fator_estresse(projeto.dados)
    f, piso = aplicar_piso(pior["indice"] if pior else None)
    est, falha_estresse = None, None
    if f is not None:
        try:
            est = {"sem_medicao": rodar(_estressar(ativs, mem, origem, NAO_MEDIDAS, f)),
                   "medida": rodar(_estressar(ativs, mem, origem, MEDIDAS, f))}
        except ErroCalendario as e:
            falha_estresse = f"a execução estressada (× {f:g}) falhou no calendário: {e}"

    def com_trabalho(aid: str) -> bool:
        a = por_id[aid]
        return a.tipo == "tarefa" and a.status != "concluida" and a.duracao > 0 and _equipe_dia(mem[aid]) > 0

    def termino(r, mid: str) -> int:
        a = por_id[mid]
        return r.atividades[mid].data_termino(projeto.calendarios[a.calendario], a)

    marcos = [a for a in projeto.dados["atividades"] if a.get("tipo") == "marco_termino"]
    saida = []
    for m in marcos:
        mid = m["id"]
        cadeia = {i for i in _cadeia(res, mid) if com_trabalho(i)}
        # ---- 1. relatório por origem (informativo)
        por_origem = defaultdict(float)
        frentes: dict[tuple, dict] = {}
        for aid in res.ordem:
            if aid not in cadeia:
                continue
            mm, dad = mem[aid], projeto.atividades[aid]
            ed, org = _equipe_dia(mm), origem[aid]
            por_origem[org] += ed
            chave = (dad.get("lote_id"), dad.get("servico_id"), org)
            fr = frentes.setdefault(chave, {"lote_id": chave[0], "servico_id": chave[1], "origem": org,
                                           "equipe_dia": 0.0, "quantidade_remanescente": 0.0,
                                           "unidade": mm.get("unidade"), "atividades": []})
            fr["equipe_dia"] += ed
            fr["quantidade_remanescente"] += mm.get("quantidade_remanescente", 0.0)
            fr["atividades"].append(aid)
        total = sum(por_origem.values())
        lista = sorted(frentes.values(), key=lambda x: -x["equipe_dia"])
        for fr in lista:
            fr["equipe_dia"] = round(fr["equipe_dia"], 2)
            fr["quantidade_remanescente"] = round(fr["quantidade_remanescente"], 3)
            fr["pct"] = round(100 * fr["equipe_dia"] / total, 1) if total else 0.0
        med = sum(por_origem[o] for o in MEDIDAS)
        nao = sum(por_origem[o] for o in NAO_MEDIDAS)
        # ---- 2. estresse
        base = termino(res, mid)
        concluido = por_id[mid].status == "concluida"
        estresse, motivo = None, None
        frac = nao / (med + nao) if med + nao > 0 else None
        if concluido:
            nivel, part = "concluido", None
        elif f is None:
            nivel, part = "sem_historico", None
            motivo = "nenhum boletim utilizável: não há índice medido para o estresse"
        elif falha_estresse:
            nivel, part, motivo = "indeterminada", None, falha_estresse
        else:
            d_sem = termino(est["sem_medicao"], mid) - base
            d_med = termino(est["medida"], mid) - base
            nivel, part = nivel_confianca(d_sem, d_med)
            if f >= 1.0 and frac is not None and frac > FRACAO_SEM_MEDICAO_INDETERMINADA:
                nivel = "indeterminada"
                motivo = (f"nenhuma frente medida rendeu abaixo do planejado (f = 1): o estresse não testa nada, e "
                          f"{100 * frac:.0f}% do remanescente que determina o marco não tem medição")
            entram = sorted(i for i in _cadeia(est["sem_medicao"], mid) - _cadeia(res, mid) if com_trabalho(i))
            estresse = {"delta_sem_medicao_dias": d_sem, "delta_medida_dias": d_med,
                        "termino_estressado_sem_medicao": iso(base + d_sem),
                        "termino_estressado_medida": iso(base + d_med),
                        "participacao_sem_medicao": part,
                        "entram_na_cadeia_sob_estresse": entram}
        # ---- 3. alerta de quase-críticas sem medição
        alerta = []
        ants = _antecessoras(rels, mid)
        cands = [aid for aid in sorted(ants) if com_trabalho(aid) and origem[aid] in NAO_MEDIDAS]
        if not concluido and cands:
            keep = ants | {mid}
            sub = calcular([a for a in ativs if a.id in keep],
                           [r for r in rels if r.predecessora in keep and r.sucessora in keep],
                           projeto.calendarios, projeto.inicio_projeto, data_status=projeto.data_status)
            for aid in cands:
                rel = sub.atividades[aid].folga_total
                if rel is not None and rel <= folga_alerta_du:
                    dad = projeto.atividades[aid]
                    alerta.append({"atividade_id": aid, "lote_id": dad.get("lote_id"),
                                   "servico_id": dad.get("servico_id"), "origem": origem[aid],
                                   "folga_relativa_du": rel, "na_cadeia": aid in cadeia})
        alerta.sort(key=lambda x: (x["folga_relativa_du"], x["atividade_id"]))
        saida.append({
            "id": mid, "nome": m.get("nome"), "lote_id": m.get("lote_id"), "termino": iso(base),
            "confianca": nivel,
            "motivo": motivo,
            "estresse": estresse,
            "alerta_sem_medicao": alerta,
            "relatorio_origem": {
                "fracao_sem_medicao": round(nao / (med + nao), 4) if med + nao > 0 else None,
                "equipe_dia_remanescente": round(total, 2),
                "por_origem": {o: {"equipe_dia": round(por_origem[o], 2),
                                   "pct": round(100 * por_origem[o] / total, 1) if total else 0.0} for o in ORIGENS},
                "tarefas_determinantes_com_trabalho": len(cadeia),
                "frentes": lista[:TOP_FRENTES],
                "frentes_omitidas": max(0, len(lista) - TOP_FRENTES),
            },
        })
    return {
        "cenario": cenario,
        "data_status": projeto.dados["meta"]["data_status"],
        "fator_estresse": f,
        "fator_estresse_observado": pior["indice"] if pior else None,
        "fator_estresse_limitado_pelo_piso": piso,
        "fator_estresse_origem": pior,
        "parametros": {"limiar_baixa": LIMIAR_BAIXA, "limiar_alta": LIMIAR_ALTA, "f_min": F_MIN,
                       "fracao_sem_medicao_indeterminada": FRACAO_SEM_MEDICAO_INDETERMINADA,
                       "delta_minimo_dias": DELTA_MINIMO_DIAS, "folga_alerta_du": folga_alerta_du},
        "regras": {
            "confianca": "estresse no motor: produtividade sem medição × f e medida × f, f = pior índice "
                         "medida/planejada por (lote, serviço) já observado na obra (≤ 1); nível pelo Δ do marco",
            "alerta": "antecessoras do marco com origem sem medição e folga ≤ folga_alerta_du dias úteis, folga do "
                      "motor rodado na sub-rede do marco (o marco é o fim)",
            "relatorio_origem": "informativo: cadeia determinante do motor, equipe·dia = remanescente ÷ produtividade "
                                "usada; o peso favorece o que já foi medido e não decide a confiança",
            "limite": "nenhum sinal nos dados antecipa uma frente sem medição que renderá muito abaixo do pior índice "
                      "já observado (ver docs/research/R12, limitações)",
        },
        "marcos": saida,
    }
