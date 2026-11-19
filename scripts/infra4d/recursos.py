"""Recursos e produtividade: histograma, sobrealocação, nivelamento e conflitos de linha de balanço.

CAMADA SEPARADA do CPM (ADR-0003): nada aqui altera ``motor.py``. O nivelamento
só acrescenta restrições "início não antes de" (SNET) e pede ao motor que
recalcule; a prova de que as relações continuam satisfeitas é feita por um
verificador próprio (``verificar_relacoes``) sobre o resultado final.

Convenções (as mesmas do motor, ver ``calendario.py``):

- datas são ordinais; uma tarefa ocupa os dias ÚTEIS do SEU calendário em ``[ES, EF)``;
- o histograma é da PROJEÇÃO do cenário: concluídas não consomem; em andamento consomem de
  ``inicio_restante`` (recomeço do remanescente: a data de status ou, com lógica retida, depois das
  predecessoras abertas) até ``EF``; não iniciadas de ``ES`` a ``EF``;
- recurso = (lote, serviço). Equipes da atividade: ``memoria.equipes`` do cenário
  (respeita ajustes do simulado) → ``equipes`` declaradas na atividade → 1;
- equipamentos: ``servicos[].equipamentos`` × equipes. Um texto que começa por
  número ("8 caminhões basculantes") vale aquela quantidade por equipe, com o tipo
  "caminhões basculantes"; sem número vale 1. Serviço sem cadastro (OAE, SIN) não
  declara equipamento e não entra nessa contagem (declarado, não inventado).

Nivelamento: heurística SGS SERIAL clássica (Kelley, 1963). NÃO é ótimo — é a
regra de prioridade "menor folga total primeiro (do CPM sem recursos), desempate
por ES e depois por id". Só atrasa atividades NÃO INICIADAS; concluídas e em
andamento são fatos e ficam onde estão (a sobrecarga que elas sozinhas causam é
reportada como irredutível).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import replace
from datetime import date

from .calendario import Calendario, iso, ordinal
from .cenarios import Ajuste, Projeto, montar_entrada
from .motor import AtividadeCPM, Relacao, ResultadoCPM, _ef_minimo_por_alvo, calcular

HEURISTICA = ("SGS serial (Kelley): agenda uma atividade por vez, na ordem de prioridade entre as "
              "elegíveis (todas as predecessoras não iniciadas já agendadas), no 1º dia útil >= ES de "
              "precedência em que a capacidade comporta a duração inteira. Heurística: NÃO garante o "
              "término mínimo.")
PRIORIDADE = "menor folga total do CPM sem recursos; desempate por ES; depois por id"

_EPS = 1e-9  # tolerância de ponto flutuante na comparação com os buffers (limite exato não alerta)
_RE_QTD = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")


# =========================================================================== básicos
def chave_recurso(lote: str | None, servico: str | None) -> str:
    return f"{lote or '-'}/{servico}"


def _equipes(projeto: Projeto, aid: str, r: dict) -> int:
    mem = r.get("memoria") or {}
    if mem.get("equipes") is not None:
        return int(mem["equipes"])
    a = projeto.atividades.get(aid, {})
    return int(a.get("equipes") or 1)


def _equipamentos_por_equipe(projeto: Projeto, servico: str | None) -> dict[str, int]:
    for s in projeto.dados.get("servicos", []):
        if s["id"] == servico:
            out: dict[str, int] = defaultdict(int)
            for texto in s.get("equipamentos", []):
                m = _RE_QTD.match(texto)
                if m:
                    out[m.group(2)] += int(m.group(1))
                else:
                    out[texto.strip()] += 1
            return dict(out)
    return {}


def _cal(projeto: Projeto, aid: str) -> Calendario:
    return projeto.calendarios[projeto.atividades[aid]["calendario"]]


def _ds(resultado: dict) -> int | None:
    return ordinal(resultado["data_status"]) if resultado.get("data_status") else None


def intervalos(projeto: Projeto, resultado: dict) -> list[dict]:
    """Consumo de cada atividade que usa recurso na projeção do cenário.

    Cada item: id, lote, servico, recurso, equipes, inicio_consumo, ef (ordinais),
    dias (lista de dias úteis do calendário da atividade em [inicio_consumo, ef))."""
    ds = _ds(resultado)
    saida = []
    for aid, r in resultado["atividades"].items():
        a = projeto.atividades.get(aid, {})
        if a.get("tipo", "tarefa") != "tarefa" or not a.get("servico_id"):
            continue
        if r["status"] == "concluida" or not r.get("duracao"):
            continue
        es, ef = ordinal(r["es"]), ordinal(r["ef"])
        if r["status"] == "em_andamento":
            # o remanescente recomeça em inicio_restante (data de status; com lógica retida, depois das
            # predecessoras abertas — rodada 5). Sem o campo (resultado antigo): max(ES, data de status).
            ini = ordinal(r["inicio_restante"]) if r.get("inicio_restante") else (max(es, ds) if ds is not None else es)
        else:
            ini = es
        cal = _cal(projeto, aid)
        dias = [d for d in range(ini, ef) if cal.eh_util(d)]
        if not dias:
            continue
        saida.append({
            "id": aid, "lote": a.get("lote_id"), "servico": a["servico_id"],
            "recurso": chave_recurso(a.get("lote_id"), a["servico_id"]),
            "equipes": _equipes(projeto, aid, r), "status": r["status"],
            "inicio_consumo": ini, "ef": ef, "dias": dias,
        })
    return saida


def _mapear(itens: list[dict], cap: dict[str, int]) -> list[dict]:
    """Aplica os POOLS declarados: capacidade com chave ``*/SERV`` vale para o serviço na obra
    inteira (frota compartilhada entre lotes) e substitui as chaves por lote desse serviço."""
    pools = {k.split("/", 1)[1] for k in cap if k.startswith("*/")}
    if not pools:
        return itens
    return [dict(it, recurso=chave_recurso("*", it["servico"])) if it["servico"] in pools else it for it in itens]


def uso_diario(itens: list[dict]) -> dict[str, dict[int, int]]:
    """recurso -> dia -> equipes em uso."""
    uso: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for it in itens:
        for d in it["dias"]:
            uso[it["recurso"]][d] += it["equipes"]
    return {k: dict(v) for k, v in uso.items()}


def capacidades_padrao(projeto: Projeto, resultado: dict) -> dict[str, int]:
    """Capacidade padrão por (lote, serviço) = máximo de equipes declaradas: maior ``equipes``
    entre as atividades do par no cenário e ``servicos[].equipes_padrao``."""
    padrao_serv = {s["id"]: int(s.get("equipes_padrao") or 0) for s in projeto.dados.get("servicos", [])}
    cap: dict[str, int] = {}
    for aid, r in resultado["atividades"].items():
        a = projeto.atividades.get(aid, {})
        if a.get("tipo", "tarefa") != "tarefa" or not a.get("servico_id"):
            continue
        k = chave_recurso(a.get("lote_id"), a["servico_id"])
        cap[k] = max(cap.get(k, 0), _equipes(projeto, aid, r), padrao_serv.get(a["servico_id"], 0))
    return cap


def _normalizar_capacidades(projeto: Projeto, resultado: dict, capacidades: dict | None) -> dict[str, int]:
    cap = capacidades_padrao(projeto, resultado)
    for k, v in (capacidades or {}).items():
        chave = chave_recurso(*k) if isinstance(k, tuple) else str(k)
        if int(v) < 0:
            raise ValueError(f"capacidade negativa para {chave}")
        cap[chave] = int(v)
    return cap


def _semana(d: int) -> int:
    """Segunda-feira da semana ISO do dia ``d`` (ordinal)."""
    return d - date.fromordinal(d).weekday()


def _agrupar(serie: dict[int, int], agrupar: str, nome: str = "equipes") -> list[dict]:
    if agrupar == "dia":
        return [{"periodo": iso(d), nome: v, f"{nome}_dia": v} for d, v in sorted(serie.items())]
    sem: dict[int, list[int]] = defaultdict(list)
    for d, v in serie.items():
        sem[_semana(d)].append(v)
    # "equipes" = pico diário da semana; "equipes_dia" = soma de equipe·dia na semana
    return [{"periodo": iso(s), nome: max(vs), f"{nome}_dia": sum(vs)} for s, vs in sorted(sem.items())]


# =========================================================================== 1. histograma
def histograma(projeto: Projeto, resultado: dict, lote: str | None = None, agrupar: str = "dia",
               capacidades: dict | None = None) -> dict:
    """Uso de equipes por (lote, serviço) e total, e de equipamentos por tipo."""
    if agrupar not in ("dia", "semana"):
        raise ValueError("agrupar deve ser 'dia' ou 'semana'")
    cap = _normalizar_capacidades(projeto, resultado, capacidades)
    itens = _mapear([it for it in intervalos(projeto, resultado) if not lote or it["lote"] == lote], cap)
    uso = uso_diario(itens)
    total: dict[int, int] = defaultdict(int)
    equip: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for it in itens:
        por_eq = _equipamentos_por_equipe(projeto, it["servico"])
        for d in it["dias"]:
            total[d] += it["equipes"]
            for tipo, q in por_eq.items():
                equip[tipo][d] += q * it["equipes"]
    series = []
    for k in sorted(uso):
        lt, sv = k.split("/", 1)
        serie = uso[k]
        series.append({"recurso": k, "lote": None if lt in ("-", "*") else lt, "servico": sv,
                       "capacidade": cap.get(k), "pico": max(serie.values()),
                       "dias_sobrealocados": sum(1 for v in serie.values() if v > cap.get(k, 0)),
                       "periodos": _agrupar(serie, agrupar)})
    return {
        "cenario": resultado["cenario"], "data_status": resultado.get("data_status"), "lote": lote,
        "agrupar": agrupar,
        "regra": "dias úteis do calendário de cada atividade; em andamento consome de max(ES, data de status) "
                 "a EF; concluídas não consomem; 'equipes' = pico diário do período, 'equipes_dia' = soma",
        "series": series,
        "total": {"pico": max(total.values()) if total else 0, "periodos": _agrupar(dict(total), agrupar)},
        "equipamentos": [{"tipo": t, "pico": max(s.values()), "periodos": _agrupar(dict(s), agrupar, "quantidade")}
                         for t, s in sorted(equip.items())],
    }


# =========================================================================== 2. sobrealocação
def sobrealocacao(projeto: Projeto, resultado: dict, capacidades: dict | None = None,
                  lote: str | None = None) -> dict:
    """Picos e dias sobrealocados por (lote, serviço), com as atividades envolvidas."""
    cap = _normalizar_capacidades(projeto, resultado, capacidades)
    itens = _mapear([it for it in intervalos(projeto, resultado) if not lote or it["lote"] == lote], cap)
    uso = uso_diario(itens)
    quem: dict[tuple[str, int], list[str]] = defaultdict(list)
    for it in itens:
        for d in it["dias"]:
            quem[(it["recurso"], d)].append(it["id"])
    recursos = []
    for k in sorted(uso):
        serie, c = uso[k], cap.get(k, 0)
        dias = [{"data": iso(d), "uso": v, "capacidade": c, "atividades": sorted(quem[(k, d)])}
                for d, v in sorted(serie.items()) if v > c]
        pico = max(serie.values())
        recursos.append({"recurso": k, "capacidade": c, "pico": pico,
                         "data_pico": iso(min(d for d, v in serie.items() if v == pico)),
                         "dias_sobrealocados": len(dias), "sobrealocacao": dias})
    return {"cenario": resultado["cenario"], "capacidades": cap, "recursos": recursos,
            "total_dias_sobrealocados": sum(r["dias_sobrealocados"] for r in recursos)}


# =========================================================================== 3. nivelamento
def _entrada(projeto: Projeto, resultado: dict):
    ajustes = [Ajuste(**d) for d in resultado.get("ajustes", [])]
    ativs, rels, mem = montar_entrada(projeto, resultado["cenario"], ajustes)
    ds = None if resultado["cenario"] == "linha_base" else projeto.data_status
    return ativs, rels, mem, ds


def _como_resultado(projeto: Projeto, base: dict, ativs: list[AtividadeCPM], res: ResultadoCPM,
                    mem: dict) -> dict:
    """Mesmo formato de ``cenarios.executar`` (para o histograma e o frontend)."""
    por_id = {a.id: a for a in ativs}
    saida = {}
    for aid in res.ordem:
        a = por_id[aid]
        d = res.atividades[aid].como_dict(projeto.calendarios[a.calendario], a)
        d.update(duracao=a.duracao, status=a.status, memoria=mem[aid])
        saida[aid] = d
    return {"cenario": base["cenario"], "data_status": base.get("data_status"),
            "termino": iso(res.termino_projeto_data), "_termino_fronteira": res.termino_projeto,
            "caminho_critico": res.caminho_critico, "cadeia_determinante": res.cadeia_determinante,
            "atividades": saida, "ajustes": base.get("ajustes", []),
            **({"logica_progresso": base["logica_progresso"]} if "logica_progresso" in base else {})}


def verificar_relacoes(ativs: list[AtividadeCPM], rels: list[Relacao], cals: dict[str, Calendario],
                       res: ResultadoCPM) -> dict:
    """Confere cada relação no resultado (regras de ``motor.py``, recalculadas aqui de forma independente).

    FS/SS: ES_s >= 1º dia útil da sucessora a partir de somar_pred(EF_p | ES_p, lag).
    FF/SF (tarefa): EF_s >= _ef_minimo_por_alvo(...) — não termina antes do último dia
    efetivamente trabalhado pela predecessora até o alvo. Relações cuja sucessora já começou
    não se aplicam (progress override do motor), e são contadas à parte."""
    A = {a.id: a for a in ativs}
    violacoes, ok, ignoradas = [], 0, 0
    for r in rels:
        s, p = A[r.sucessora], A[r.predecessora]
        if s.status != "nao_iniciada":
            ignoradas += 1
            continue
        rs, rp = res.atividades[s.id], res.atividades[p.id]
        cs, cp = cals[s.calendario], cals[p.calendario]
        fonte = rp.ef if r.tipo in ("FS", "FF") else rp.es
        alvo = cp.somar(fonte, r.lag)
        ajusta = s.duracao > 0 or s.tipo != "marco_termino"
        if r.tipo in ("FS", "SS") or s.duracao == 0:
            minimo = cs.proximo_util(alvo) if ajusta else alvo
            obtido, campo = rs.es, "ES"
        else:
            minimo, obtido, campo = _ef_minimo_por_alvo(cs, cp, alvo), rs.ef, "EF"
        if obtido >= minimo:
            ok += 1
        else:
            violacoes.append({"predecessora": p.id, "sucessora": s.id, "tipo": r.tipo, "lag": r.lag,
                              "campo": campo, "minimo": iso(minimo), "obtido": iso(obtido)})
    return {"ok": not violacoes, "relacoes_verificadas": ok + len(violacoes),
            "relacoes_ignoradas_progresso": ignoradas, "violacoes": violacoes}


def nivelar(projeto: Projeto, resultado: dict, capacidades: dict | None = None) -> dict:
    """Nivelamento por SGS serial. Ver docstring do módulo (heurística, não ótimo)."""
    ativs, rels, mem, ds = _entrada(projeto, resultado)
    cals = projeto.calendarios
    cap = _normalizar_capacidades(projeto, resultado, capacidades)
    A = {a.id: a for a in ativs}
    # mesma lógica de progresso do cenário (se o motor/cenário a declararem)
    kw = {"logica_progresso": resultado["logica_progresso"]} if "logica_progresso" in resultado else {}
    cpm0 = calcular(ativs, rels, cals, projeto.inicio_projeto, data_status=ds, **kw)

    pools = {k.split("/", 1)[1] for k in cap if k.startswith("*/")}

    def recurso_de(aid):
        a = projeto.atividades.get(aid, {})
        if a.get("tipo", "tarefa") != "tarefa" or not a.get("servico_id"):
            return None
        return chave_recurso("*" if a["servico_id"] in pools else a.get("lote_id"), a["servico_id"])

    equipes = {aid: (int(mem[aid]["equipes"]) if mem[aid].get("equipes") is not None
                     else int(projeto.atividades[aid].get("equipes") or 1)) for aid in A}

    # carga fixa: em andamento (fatos) — do max(ES, ds) ao EF
    uso: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    fixa: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for a in ativs:
        k = recurso_de(a.id)
        if k is None or a.status != "em_andamento" or a.duracao == 0:
            continue
        r0 = cpm0.atividades[a.id]
        ini = (r0.inicio_restante if getattr(r0, "inicio_restante", None) is not None
               else (max(r0.es, ds) if ds is not None else r0.es))
        for d in range(ini, r0.ef):
            if cals[a.calendario].eh_util(d):
                uso[k][d] += equipes[a.id]
                fixa[k][d] += equipes[a.id]

    preds = defaultdict(list)
    for r in rels:
        preds[r.sucessora].append(r.predecessora)
    pendentes = {a.id for a in ativs if a.status == "nao_iniciada"}
    agendadas: dict[str, int] = {}
    motivo: dict[str, str] = {}
    snet_base = {a.id: a.restricao_inicio for a in ativs}
    trabalho = [replace(a) for a in ativs]
    T = {a.id: a for a in trabalho}
    acima_da_capacidade = []
    res = cpm0
    while pendentes:
        elegiveis = [i for i in pendentes if all(p not in pendentes for p in preds[i])]
        j = min(elegiveis, key=lambda i: (cpm0.atividades[i].folga_total, res.atividades[i].es, i))
        a = T[j]
        es_prec = res.atividades[j].es  # ES de precedência com as já agendadas fixadas
        k = recurso_de(j)
        t = es_prec
        if k is not None and a.duracao > 0:
            cal = cals[a.calendario]
            c, q = cap.get(k, 0), equipes[j]
            if q > c:
                acima_da_capacidade.append({"id": j, "recurso": k, "equipes": q, "capacidade": c})
                c = q  # atividade maior que a capacidade: exige o recurso sozinho
            while True:
                ef = cal.somar(t, a.duracao)
                conflito = next((d for d in range(t, ef) if cal.eh_util(d) and uso[k].get(d, 0) + q > c), None)
                if conflito is None:
                    break
                t = cal.proximo_util(conflito + 1)
            for d in range(t, ef):
                if cal.eh_util(d):
                    uso[k][d] += q
        motivo[j] = "recurso" if t > es_prec else ("precedência (predecessora nivelada)"
                                                   if t > cpm0.atividades[j].es else "")
        a.restricao_inicio = t if snet_base[j] is None else max(t, snet_base[j])
        agendadas[j] = t
        pendentes.discard(j)
        res = calcular(trabalho, rels, cals, projeto.inicio_projeto, data_status=ds, **kw)

    # ---------------------------------------------------------------- provas
    deriva = [i for i, t in agendadas.items() if res.atividades[i].es != t]
    nivelado = _como_resultado(projeto, resultado, trabalho, res, mem)
    uso_final = uso_diario(_mapear(intervalos(projeto, nivelado), cap))
    picos, violacoes, irredutivel = {}, [], []
    for k, serie in sorted(uso_final.items()):
        c = cap.get(k, 0)
        picos[k] = {"pico": max(serie.values()), "capacidade": c}
        for d, v in sorted(serie.items()):
            if v > c:
                if fixa.get(k, {}).get(d, 0) > c or v == fixa.get(k, {}).get(d, 0):
                    irredutivel.append({"recurso": k, "data": iso(d), "uso": v, "capacidade": c})
                elif any(x["recurso"] == k for x in acima_da_capacidade):
                    irredutivel.append({"recurso": k, "data": iso(d), "uso": v, "capacidade": c,
                                        "nota": "atividade com mais equipes que a capacidade"})
                else:
                    violacoes.append({"recurso": k, "data": iso(d), "uso": v, "capacidade": c})
    prova_rel = verificar_relacoes(trabalho, rels, cals, res)

    cal_obra = cals.get(projeto.dados.get("meta", {}).get("calendario_obra", ""))
    atrasadas = []
    for i in res.ordem:
        e0, e1 = cpm0.atividades[i].es, res.atividades[i].es
        if e1 != e0:
            cal = cals[A[i].calendario]
            atrasadas.append({"id": i, "recurso": recurso_de(i), "es_cpm": iso(e0), "es_nivelado": iso(e1),
                              "termino_cpm": nivelado_termino(projeto, cpm0, A[i]),
                              "termino_nivelado": nivelado_termino(projeto, res, T[i]),
                              "atraso_dias_uteis": cal.dias_uteis_entre(e0, e1),
                              "atraso_dias_corridos": e1 - e0,
                              "motivo": motivo.get(i) or "precedência (predecessora nivelada)"})
    return {
        "cenario": resultado["cenario"],
        "heuristica": HEURISTICA, "prioridade": PRIORIDADE,
        "capacidades": cap,
        "termino_cpm": iso(cpm0.termino_projeto_data),
        "termino_nivelado": iso(res.termino_projeto_data),
        "delta_dias_corridos": res.termino_projeto_data - cpm0.termino_projeto_data,
        "delta_dias_uteis_obra": (cal_obra.dias_uteis_entre(cpm0.termino_projeto_data + 1,
                                                            res.termino_projeto_data + 1) if cal_obra else None),
        "atividades_atrasadas": atrasadas,
        "n_atrasadas": len(atrasadas),
        "n_atrasadas_por_recurso": sum(1 for x in atrasadas if x["motivo"] == "recurso"),
        "prova_capacidade": {"ok": not violacoes, "picos": picos, "violacoes": violacoes,
                             "sobrecarga_irredutivel": irredutivel,
                             "atividades_acima_da_capacidade": acima_da_capacidade},
        "prova_relacoes": prova_rel,
        "prova_snet": {"ok": not deriva, "deriva": deriva,
                       "regra": "o motor, recalculado com as restrições SNET do nivelamento, reproduz "
                                "exatamente o início escolhido para cada atividade agendada"},
        "_resultado": nivelado,
    }


def nivelado_termino(projeto: Projeto, res: ResultadoCPM, a: AtividadeCPM) -> str | None:
    return iso(res.atividades[a.id].data_termino(projeto.calendarios[a.calendario], a))


# =========================================================================== 4. linha de balanço
def pares_sucessivos(projeto: Projeto) -> set[tuple[str, str]]:
    """Pares (serviço antecessor, serviço sucessor) que têm relação direta dentro do MESMO segmento
    (ou do mesmo lote, se a atividade não tem segmento). Derivado das relações, não inventado."""
    P = projeto.atividades
    pares = set()
    for r in projeto.dados["relacoes"]:
        a, b = P.get(r["predecessora"], {}), P.get(r["sucessora"], {})
        if (a.get("servico_id") and b.get("servico_id") and a["servico_id"] != b["servico_id"]
                and a.get("lote_id") == b.get("lote_id") and a.get("segmento_id") == b.get("segmento_id")):
            pares.add((a["servico_id"], b["servico_id"]))
    return pares


def _fracao_executada(a: dict) -> float:
    if a.get("quantidade_total"):
        return max(0.0, min(1.0, float(a.get("quantidade_executada", 0.0)) / float(a["quantidade_total"])))
    return max(0.0, min(1.0, float(a.get("percentual_executado", 0.0)) / 100.0))


def _linha(projeto: Projeto, aid: str, r: dict, ds: int | None = None):
    """Reta de produção projetada: (início do movimento, EF, km de partida, km_fim, ativa desde).

    Não iniciada: (ES, km_ini) → (EF, km_fim). EM ANDAMENTO (rodada 5): parte do EXECUTADO na data de
    status, km_ini + fração executada × extensão, e anda de ``inicio_restante`` (recomeço do
    remanescente) até EF; entre a data de status e o recomeço fica parada no km executado. Antes do
    início do movimento a frente está parada no km de partida (``_pos`` satura)."""
    a = projeto.atividades[aid]
    if a.get("km_ini") is None or a.get("km_fim") is None or a["km_fim"] == a["km_ini"]:
        return None
    if r["status"] == "concluida" or a.get("tipo", "tarefa") != "tarefa":
        return None
    es, ef = ordinal(r["es"]), ordinal(r["ef"])
    k0, k1 = float(a["km_ini"]), float(a["km_fim"])
    if r["status"] == "em_andamento" and ds is not None:
        mov = ordinal(r["inicio_restante"]) if r.get("inicio_restante") else max(es, ds)
        kx = k0 + _fracao_executada(a) * (k1 - k0)
        if ef <= mov or kx == k1:
            return None
        return mov, ef, kx, k1, min(ds, mov)
    if ef <= es:
        return None
    return es, ef, k0, k1, es


def _pos(l, t: float) -> float:
    es, ef, k0, k1 = l[:4]
    f = min(1.0, max(0.0, (t - es) / (ef - es)))
    return k0 + f * (k1 - k0)


# ------------------------------------------------------------------ geometria analítica (E1)
def _intervalo_abaixo(t0: float, t1: float, f0: float, f1: float, lim: float) -> tuple[float, float] | None:
    """Subintervalo de [t0, t1] em que a função LINEAR f (f(t0)=f0, f(t1)=f1) fica < lim (o limite exato
    não conta, tolerância _EPS)."""
    a0, a1 = f0 < lim - _EPS, f1 < lim - _EPS
    if a0 and a1:
        return t0, t1
    if not a0 and not a1:
        return None
    tc = t0 + (lim - f0) * (t1 - t0) / (f1 - f0)  # aqui f0 != f1
    return (t0, tc) if a0 else (tc, t1)


def _raiz(t0: float, t1: float, f0: float, f1: float) -> float | None:
    """Zero da função linear em [t0, t1] quando ela passa de positiva a negativa (alcance + ultrapassagem)
    ou de negativa a positiva. Tocar zero sem trocar de sinal não é cruzamento."""
    if f0 > 0 > f1 or f0 < 0 < f1:
        return t0 + f0 * (t1 - t0) / (f0 - f1)
    if f0 == 0 and f1 < 0:
        return t0
    return None


def _analitico_par(la, lb, sentido: float, t0: float, t1: float, buffer_km: float, buffer_dias: float,
                   inicio: int) -> dict | None:
    """Linhas de produção (RSM) LINEARES POR TRECHO: cada frente é parada no km de partida até começar a
    andar e reta depois. Entre os pontos de quebra (inícios de movimento) distância e folga de tempo são
    lineares em t — extremos, instantes de entrada no buffer e o cruzamento saem em forma fechada."""
    if t1 <= t0:
        return None

    def dist(t):
        return (_pos(la, t) - _pos(lb, t)) * sentido

    kA0, kA1 = la[2], la[3]
    lo, hi = sorted((kA0, kA1))

    def folga(t):
        return t - (la[0] + (_pos(lb, t) - kA0) / (kA1 - kA0) * (la[1] - la[0]))

    cortes = sorted({t0, t1} | {x for x in (la[0], lb[0]) if t0 < x < t1})
    esps, tmps, tz, dmin, t_min = [], [], None, None, None
    for u0, u1 in zip(cortes, cortes[1:]):
        d0, d1 = dist(u0), dist(u1)
        for t_, d_ in ((u0, d0), (u1, d1)):
            if dmin is None or d_ < dmin:
                dmin, t_min = d_, t_
        iv = _intervalo_abaixo(u0, u1, d0, d1, buffer_km)
        if iv:
            esps.append(iv)
        if tz is None:
            tz = _raiz(u0, u1, d0, d1)
        if buffer_dias > 0:
            kb0, kb1 = _pos(lb, u0), _pos(lb, u1)
            if kb1 != kb0:
                # subtrecho em que o km da sucessora está dentro do trecho (a percorrer) da antecessora
                ta = u0 + (min(max(lo, kb0), hi) - kb0) * (u1 - u0) / (kb1 - kb0)
                tb = u0 + (min(max(lo, kb1), hi) - kb0) * (u1 - u0) / (kb1 - kb0)
                v0, v1 = max(min(ta, tb), u0), min(max(ta, tb), u1)
                if v1 > v0:
                    iv = _intervalo_abaixo(v0, v1, folga(v0), folga(v1), buffer_dias)
                    if iv:
                        tmps.append(iv)
    if not esps and not tmps and tz is None:
        return None
    esp = (min(x[0] for x in esps), max(x[1] for x in esps)) if esps else None
    tmp = (min(x[0] for x in tmps), max(x[1] for x in tmps)) if tmps else None
    ivs = [x for x in (esp, tmp) if x]
    ini = min(x[0] for x in ivs) if ivs else None
    fim = max(x[1] for x in ivs) if ivs else None
    return {
        "janela_t_dias": [t0 - inicio, t1 - inicio],
        "espacial_t_dias": None if not esp else [esp[0] - inicio, esp[1] - inicio],
        "temporal_t_dias": None if not tmp else [tmp[0] - inicio, tmp[1] - inicio],
        "inicio_t_dias": None if ini is None else ini - inicio,
        "inicio_data": None if ini is None else iso(math.floor(ini)),
        "distancia_km_min": dmin, "t_dias_distancia_min": t_min - inicio,
        "cruzamento": None if tz is None else {"t_dias": tz - inicio, "t_ordinal": tz,
                                               "data": iso(math.floor(tz)), "km": _pos(lb, tz)},
        "_ini": ini, "_fim": fim, "_t_min": t_min,
    }


def _poli(pontos: list[dict]) -> list[tuple[int, float]]:
    return [(ordinal(p["data"]), float(p["km"])) for p in pontos]


def _pos_poli(pl: list[tuple[int, float]], t: float) -> float:
    if t <= pl[0][0]:
        return pl[0][1]
    for (ta, ka), (tb, kb) in zip(pl, pl[1:]):
        if t <= tb:
            return ka if tb == ta else ka + (kb - ka) * (t - ta) / (tb - ta)
    return pl[-1][1]  # depois do último ponto: parada no km atual


def _conflitos_reais(projeto: Projeto, linha_real: dict, pares, buffer_km: float, ds: int | None,
                     lote: str | None) -> list[dict]:
    """Conflitos JÁ OCORRIDOS entre as linhas REAIS (poligonais tempo-km dos diários), até a data de status.
    Depois do último ponto a frente fica parada no km atual; antecessora CONCLUÍDA libera o trecho depois
    do seu último ponto. Só o buffer espacial (a folga de tempo exigiria inverter a poligonal)."""
    frentes = {f["atividade_id"]: f for f in linha_real.get("frentes", []) if f.get("pontos")}
    grupos: dict[tuple, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for aid in frentes:
        a = projeto.atividades.get(aid, {})
        if a.get("servico_id") and (not lote or a.get("lote_id") == lote):
            grupos[(a.get("lote_id"), a.get("segmento_id"))][a["servico_id"]].append(aid)
    saida = []
    for (lt, seg), por_serv in sorted(grupos.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        for s_ant, s_suc in sorted(pares):
            for ia in por_serv.get(s_ant, []):
                for ib in por_serv.get(s_suc, []):
                    A = frentes[ia]
                    pa, pb = _poli(A["pontos"]), _poli(frentes[ib]["pontos"])
                    a_ = projeto.atividades[ia]
                    sentido = 1.0 if (a_.get("km_fim", 1) or 0) >= (a_.get("km_ini", 0) or 0) else -1.0
                    t0 = max(pa[0][0], pb[0][0])
                    t1 = ds if ds is not None else max(pa[-1][0], pb[-1][0])
                    if a_.get("status") == "concluida":
                        t1 = min(t1, pa[-1][0])
                    if t1 <= t0:
                        continue
                    cortes = sorted({t0, t1} | {t for t, _ in pa + pb if t0 < t < t1})
                    ep = None
                    for u0, u1 in zip(cortes, cortes[1:]):
                        f0 = (_pos_poli(pa, u0) - _pos_poli(pb, u0)) * sentido
                        f1 = (_pos_poli(pa, u1) - _pos_poli(pb, u1)) * sentido
                        iv = _intervalo_abaixo(u0, u1, f0, f1, buffer_km)
                        if iv is None:
                            ep = None
                            continue
                        if ep is None or abs(ep["_fim"] - iv[0]) > 1e-9:
                            ep = {"fonte": "real", "ocorrido": True, "lote": lt, "segmento": seg,
                                  "servicos": [s_ant, s_suc], "atividades": [ia, ib],
                                  "data": iso(math.floor(iv[0])), "inicio_t_dias": iv[0] - projeto.inicio_projeto,
                                  "distancia_km_min": f0 if f0 < f1 else f1, "ultrapassagem": False,
                                  "cruzamento": None}
                            saida.append(ep)
                        ep["_fim"] = iv[1]
                        ep["data_fim"] = iso(math.ceil(iv[1]) - 1)
                        ep["distancia_km_min"] = min(ep["distancia_km_min"], f0, f1)
                        ep["ultrapassagem"] |= min(f0, f1) < 0
                        tz = _raiz(u0, u1, f0, f1)
                        if tz is not None and ep["cruzamento"] is None:
                            ep["cruzamento"] = {"t_dias": tz - projeto.inicio_projeto, "data": iso(math.floor(tz)),
                                                "km": _pos_poli(pb, tz)}
    for e in saida:
        e.pop("_fim", None)
        e["distancia_km_min"] = round(e["distancia_km_min"], 6)
    return saida


def conflitos_balanco(projeto: Projeto, resultado: dict, buffer_km: float = 1.0, buffer_dias: float = 0.0,
                      pares: set[tuple[str, str]] | None = None, lote: str | None = None,
                      linha_real: dict | None = None) -> dict:
    """Frente sucessora perto demais da antecessora no mesmo segmento, na projeção do cenário.

    Cada atividade é uma reta km × tempo de (ES, km_ini) a (EF, km_fim), em dias CORRIDOS — a linha de
    produção do RSM (Harris & Ioannou, 1998) e do LBMS (Kenley & Seppänen). Na janela em que as duas
    estão ativas (e a partir da data de status), dois cálculos:

    - AMOSTRAGEM no início de cada dia (episódios de dias seguidos, com o pior momento):
        distância  = (km_ant(t) − km_suc(t)) × sentido      (negativa = ultrapassagem)
        folga_dias = t − instante em que a antecessora passou no km atual da sucessora;
    - ANALÍTICO (experimento E1 da R05): as duas são retas na janela, então distância e folga são
      LINEARES em t. Saem em forma fechada o instante em que a distância cai abaixo do buffer, a
      distância mínima (num extremo da janela) e o CRUZAMENTO (t*, km*) em que a sucessora alcança a
      antecessora — inclusive dentro de um dia, entre duas amostras: aí o alerta tem
      fonte "analitico" e dias = 0.

    Alerta quando distância < buffer_km OU folga_dias < buffer_dias (o limite exato não alerta).
    ``linha_real`` (opcional, saída de ``fiscalizacao.linha_real``): acrescenta os conflitos JÁ
    OCORRIDOS entre as poligonais reais (``conflitos_reais``, fonte "real")."""
    if buffer_km < 0 or buffer_dias < 0:
        raise ValueError("buffers devem ser >= 0")
    pares = pares_sucessivos(projeto) if pares is None else set(pares)
    ds = _ds(resultado)
    inicio = projeto.inicio_projeto
    grupos: dict[tuple, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for aid in resultado["atividades"]:
        a = projeto.atividades.get(aid, {})
        if a.get("servico_id") and (not lote or a.get("lote_id") == lote):
            grupos[(a.get("lote_id"), a.get("segmento_id"))][a["servico_id"]].append(aid)
    alertas = []
    for (lt, seg), por_serv in sorted(grupos.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        for s_ant, s_suc in sorted(pares):
            for ia in por_serv.get(s_ant, []):
                for ib in por_serv.get(s_suc, []):
                    la = _linha(projeto, ia, resultado["atividades"][ia], ds)
                    lb = _linha(projeto, ib, resultado["atividades"][ib], ds)
                    if not la or not lb:
                        continue
                    a_ = projeto.atividades[ia]
                    sentido = 1.0 if float(a_["km_fim"]) > float(a_["km_ini"]) else -1.0
                    # janela: enquanto a SUCESSORA está ativa e a antecessora não terminou (rodada 5:
                    # antecessora ainda não iniciada conta parada no km de partida — uma sucessora que
                    # percorre o trecho antes dela é ultrapassagem, não "sem dia comum")
                    t0 = max(lb[4], ds if ds is not None else lb[4])
                    t1 = min(la[1], lb[1])
                    an = _analitico_par(la, lb, sentido, t0, t1, buffer_km, buffer_dias, inicio)
                    do_par = []
                    episodio = None
                    for t in range(t0, t1):
                        ka, kb = _pos(la, t), _pos(lb, t)
                        dist = (ka - kb) * sentido
                        folga = None
                        lo, hi = sorted((la[2], la[3]))
                        if lo <= kb <= hi:
                            t_pass = la[0] + (kb - la[2]) / (la[3] - la[2]) * (la[1] - la[0])
                            folga = t - t_pass
                        esp = dist < buffer_km - _EPS
                        tmp = folga is not None and folga < buffer_dias - _EPS
                        if esp or tmp:
                            if episodio is None:
                                episodio = {"fonte": "amostragem", "lote": lt, "segmento": seg,
                                            "servicos": [s_ant, s_suc],
                                            "atividades": [ia, ib], "data": iso(t), "data_fim": iso(t),
                                            "km": round(kb, 3), "km_antecessora": round(ka, 3),
                                            "distancia_km": round(dist, 3), "distancia_km_min": round(dist, 3),
                                            "data_pior": iso(t),
                                            "folga_dias_min": None if folga is None else round(folga, 2),
                                            "dias": 0, "espacial": False, "temporal": False,
                                            "ultrapassagem": False}
                                do_par.append(episodio)
                            e = episodio
                            e["data_fim"] = iso(t)
                            e["dias"] += 1
                            e["espacial"] |= esp
                            e["temporal"] |= tmp
                            e["ultrapassagem"] |= dist < 0
                            if dist < e["distancia_km_min"]:
                                e.update(distancia_km_min=round(dist, 3), data_pior=iso(t), km=round(kb, 3),
                                         km_antecessora=round(ka, 3))
                            if folga is not None and (e["folga_dias_min"] is None or folga < e["folga_dias_min"]):
                                e["folga_dias_min"] = round(folga, 2)
                        else:
                            episodio = None
                    if an is not None and an["_ini"] is not None and not do_par:
                        # conflito só entre amostras (dentro de um dia): só o analítico o vê
                        ini, tm = an["_ini"], an["_t_min"]
                        do_par.append({"fonte": "analitico", "lote": lt, "segmento": seg,
                                       "servicos": [s_ant, s_suc], "atividades": [ia, ib],
                                       "data": iso(math.floor(ini)), "data_fim": iso(math.ceil(an["_fim"]) - 1),
                                       "km": round(_pos(lb, tm), 3), "km_antecessora": round(_pos(la, tm), 3),
                                       "distancia_km": round(an["distancia_km_min"], 3),
                                       "distancia_km_min": round(an["distancia_km_min"], 3),
                                       "data_pior": iso(math.ceil(tm) - 1), "folga_dias_min": None, "dias": 0,
                                       "espacial": an["espacial_t_dias"] is not None,
                                       "temporal": an["temporal_t_dias"] is not None,
                                       "ultrapassagem": an["distancia_km_min"] < 0})
                    an_pub = None if an is None else {k: v for k, v in an.items()
                                                      if not k.startswith("_") and k != "cruzamento"}
                    for e in do_par:
                        if an is not None and e["fonte"] == "amostragem":
                            e["fonte"] = "amostragem+analitico"
                        e["analitico"] = an_pub
                        e["cruzamento"] = None if an is None else an["cruzamento"]
                        if an is not None:
                            e["ultrapassagem"] |= an["distancia_km_min"] < 0
                    alertas.extend(do_par)
    reais = _conflitos_reais(projeto, linha_real, pares, buffer_km, ds, lote) if linha_real else []
    return {"cenario": resultado["cenario"], "data_status": resultado.get("data_status"),
            "buffer_km": buffer_km, "buffer_dias": buffer_dias, "pares": [list(p) for p in sorted(pares)],
            "regra": "retas km×tempo por atividade (ES→km_ini, EF→km_fim), dias corridos, a partir da data de "
                     "status; amostragem diária + cálculo analítico exato (cruzamento t*, km*)",
            "referencias": "RSM: Harris & Ioannou (1998), JCEM 124(4):269–278; LBMS: Kenley & Seppänen. "
                           "Citados pela R05; textos pagos, não lidos na íntegra.",
            "n_conflitos": len(alertas), "conflitos": alertas,
            "n_conflitos_reais": len(reais), "conflitos_reais": reais}
