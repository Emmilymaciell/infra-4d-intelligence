"""Fiscalização: diário de obra, boletim estendido, validação, conciliação e linha real tempo-km.

Esquema inspirado na IN 57/DNIT/2021 (ver docs/research/R05 §2): a medição no SIAC reúne ficha de
medição, informações do Diário de Obras, avanço físico e pluviometria; os horários de chuva são
anotados no diário (art. 11) e a medição só vale depois de aprovada pelo fiscal (arts. 16–17).
Este módulo NÃO substitui o SIAC nem afirma conformidade com ele.

Registros
---------
Diário (um por frente × dia)::

    {"tipo": "diario", "data": "AAAA-MM-DD", "atividade_id", "lote_id", "segmento_id",
     "km_ini_exec", "km_fim_exec", "quantidade", "equipes_dias", "horas_chuva",
     "ocorrencias": [str], "fotos": [{"ref": str, "sha256"?: hex64, "lat"?, "lon"?}],
     "estado": "lancado" | "conferido_fiscal" | "aprovado", "ref_memoria_calculo", "origem", "sintetico"}

Boletim estendido (um por frente × período): igual, com ``periodo_ini``/``periodo_fim`` no lugar de
``data`` e ``dias_chuva``.

Estados: ``lancado → conferido_fiscal → aprovado``; ``conferido_fiscal → lancado`` (devolução ao
lançador). ``aprovado`` é final e exige ``ref_memoria_calculo``. Pular etapa é erro.

Dados sintéticos
----------------
``gerar_diarios_sinteticos`` deriva diários FICTÍCIOS, em memória, dos boletins e calendários já
existentes. Só roda em obra com a marca booleana ``meta.ficticio is True`` — o texto de ``meta.aviso``
NÃO decide (revisão adversarial r6: avisos como "NÃO é fictício" passavam por substring). Regras:

- dias trabalhados de cada boletim = os ``equipes_dias ÷ equipes`` primeiros dias úteis (calendário
  da frente) a partir de ``semana_inicio`` — a mesma regra de ``sintetico_comum.boletins_semanais``;
- quantidade do boletim dividida em partes iguais (3 casas); o último dia fecha a soma;
- km executado = interpolação linear do avanço acumulado (quantidade acumulada ÷ quantidade total)
  entre ``km_ini`` e ``km_fim`` da atividade;
- dia de chuva = dia útil do calendário da obra que é não útil em TODOS os calendários cujo nome
  menciona chuva (descontados os não úteis do calendário da obra); ``horas_chuva`` desse dia é sorteada
  de forma determinística (semente da obra + data) entre 1 e 10 h, em meias horas;
- dia útil da obra em que a frente não trabalha (calendário da frente) vira registro de paralisação
  (quantidade 0, equipes·dia 0) com o motivo;
- não há foto fictícia: ``fotos`` fica vazio (nada que pareça evidência real).
"""

from __future__ import annotations

import math
import random
import re
import threading
from collections import defaultdict
from datetime import date

from .calendario import Calendario, iso, ordinal
from .cenarios import Projeto

ESTADOS = ("lancado", "conferido_fiscal", "aprovado")
TRANSICOES = {("lancado", "conferido_fiscal"), ("conferido_fiscal", "aprovado"), ("conferido_fiscal", "lancado")}
ORIGEM_SINTETICA = "SINTÉTICA — diário derivado dos boletins fictícios por fiscalizacao.py"
TOL_KM = 1e-6
_RE_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_FOTOS = 1000


class ErroFiscalizacao(ValueError):
    """Operação de fiscalização inválida (ex.: gerar diário sintético sobre obra não fictícia)."""


# =========================================================================== utilidades
def obra_ficticia(projeto: Projeto) -> bool:
    """Só a marca booleana explícita ``meta.ficticio is True`` conta; o texto do aviso é ignorado."""
    meta = projeto.dados.get("meta", {})
    return isinstance(meta, dict) and meta.get("ficticio") is True


def _cal_obra(projeto: Projeto) -> Calendario:
    cid = projeto.dados.get("meta", {}).get("calendario_obra")
    if cid in projeto.calendarios:
        return projeto.calendarios[cid]
    return next(iter(projeto.calendarios.values()))


def dias_de_chuva(projeto: Projeto) -> set[int]:
    """Dias úteis da obra não úteis em todos os calendários 'de chuva' (regra no docstring do módulo)."""
    obra = _cal_obra(projeto)
    base = set(obra.nao_uteis)
    conjuntos = [set(c.nao_uteis) - base for c in projeto.calendarios.values()
                 if "chuva" in (c.nome or "").lower() and c is not obra]
    if not conjuntos:
        return set()
    comum = set.intersection(*conjuntos)
    return {d.toordinal() for d in comum if obra.eh_util(d.toordinal())}


def horas_chuva_sintetica(semente, d: int) -> float:
    rng = random.Random(f"{semente}|chuva|{iso(d)}")
    return rng.randint(2, 20) / 2.0


def _sentido(a: dict) -> float:
    return -1.0 if a.get("km_fim", 0) < a.get("km_ini", 0) else 1.0


def _num(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _data(v) -> int | None:
    if not isinstance(v, str) or not _RE_DATA.match(v):
        return None  # só AAAA-MM-DD: fromisoformat (3.11+) aceitaria '20260331' e '2026-W14-2'
    try:
        return date.fromisoformat(v).toordinal()
    except ValueError:
        return None


# =========================================================================== validação
def transicao_valida(de: str | None, para: str) -> bool:
    if de is None or de == para:
        return para in ESTADOS
    return (de, para) in TRANSICOES


def validar(projeto: Projeto, reg: dict, estado_anterior: str | None = None) -> dict:
    """Valida um diário (``tipo`` ausente ou "diario") ou boletim estendido (``tipo`` = "boletim").

    Devolve ``{"valido", "erros": [{campo, regra, mensagem}], "avisos": [...]}``."""
    erros, avisos = [], []

    def erro(campo, regra, msg):
        erros.append({"campo": campo, "regra": regra, "mensagem": msg})

    if not isinstance(reg, dict):
        return {"valido": False, "erros": [{"campo": "", "regra": "formato",
                                            "mensagem": "o registro deve ser um objeto JSON"}], "avisos": []}
    tipo = reg.get("tipo", "diario")
    if tipo not in ("diario", "boletim"):
        erro("tipo", "tipo", f"tipo deve ser 'diario' ou 'boletim', não {tipo!r}")
        tipo = "diario"
    meta = projeto.dados.get("meta", {})
    ds, ini_proj = ordinal(meta.get("data_status")), ordinal(meta.get("inicio_projeto"))

    # --- frente
    aid = reg.get("atividade_id")
    a = projeto.atividades.get(aid) if isinstance(aid, str) else None
    if a is None:
        erro("atividade_id", "frente", f"atividade desconhecida nesta obra: {aid!r}")
    else:
        for campo in ("lote_id", "segmento_id"):
            if reg.get(campo) not in (None, "") and reg[campo] != a.get(campo):
                erro(campo, "frente", f"{campo} {reg[campo]!r} não é o da atividade {aid} ({a.get(campo)!r})")
        if a.get("tipo", "tarefa") != "tarefa":
            erro("atividade_id", "frente", f"{aid} é um marco: não recebe diário/boletim")

    # --- datas
    if tipo == "diario":
        campos_data = [("data", reg.get("data"))]
    else:
        campos_data = [("periodo_ini", reg.get("periodo_ini")), ("periodo_fim", reg.get("periodo_fim"))]
    datas = {}
    for campo, v in campos_data:
        d = _data(v)
        if d is None:
            erro(campo, "data", f"{campo} obrigatória no formato AAAA-MM-DD (recebido {v!r})")
            continue
        datas[campo] = d
        if ds is not None and d > ds:
            erro(campo, "data_status", f"{campo} {v} é posterior à data de status {meta.get('data_status')}: "
                                       "não se registra execução no futuro")
        if ini_proj is not None and d < ini_proj:
            erro(campo, "data", f"{campo} {v} é anterior ao início do projeto {meta.get('inicio_projeto')}")
    if tipo == "boletim" and len(datas) == 2 and datas["periodo_fim"] < datas["periodo_ini"]:
        erro("periodo_fim", "data", "periodo_fim anterior a periodo_ini")

    # --- quantidades
    q = _num(reg.get("quantidade"))
    if q is None:
        erro("quantidade", "numero", "quantidade obrigatória e numérica")
    elif q < 0:
        erro("quantidade", "nao_negativo", f"quantidade não pode ser negativa ({q})")
    eq = _num(reg.get("equipes_dias"))
    if eq is None:
        erro("equipes_dias", "numero", "equipes_dias obrigatório e numérico")
    elif eq < 0:
        erro("equipes_dias", "nao_negativo", f"equipes_dias não pode ser negativo ({eq})")
    if q is not None and eq is not None and q > 0 and eq == 0:
        erro("equipes_dias", "producao_sem_equipe", "quantidade > 0 com equipes_dias = 0: produção sem equipe")

    # --- chuva
    hc = _num(reg.get("horas_chuva", 0))
    if hc is None or hc < 0:
        erro("horas_chuva", "chuva", f"horas_chuva deve ser número >= 0 (recebido {reg.get('horas_chuva')!r})")
    elif tipo == "diario" and hc > 24:
        erro("horas_chuva", "chuva", f"horas_chuva {hc} > 24 h em um dia")
    elif tipo == "boletim" and len(datas) == 2 and hc > 24 * (datas["periodo_fim"] - datas["periodo_ini"] + 1):
        erro("horas_chuva", "chuva", "horas_chuva maior que as horas do período")

    if "dias_chuva" in reg:
        dc = reg["dias_chuva"]
        n_dias = 1
        if tipo == "boletim" and len(datas) == 2:
            n_dias = max(1, datas["periodo_fim"] - datas["periodo_ini"] + 1)
        if isinstance(dc, bool) or not isinstance(dc, int) or not (0 <= dc <= n_dias):
            erro("dias_chuva", "chuva", f"dias_chuva deve ser inteiro de 0 a {n_dias} (dias do período); "
                                        f"recebido {dc!r}")

    # --- km executado
    ki, kf = reg.get("km_ini_exec"), reg.get("km_fim_exec")
    if (ki is None) != (kf is None):
        erro("km_ini_exec" if ki is None else "km_fim_exec", "km",
             "km_ini_exec e km_fim_exec vêm juntos (ou nenhum dos dois)")
    elif ki is not None:
        ki_n, kf_n = _num(ki), _num(kf)
        if ki_n is None or kf_n is None:
            erro("km_ini_exec", "km", "km executado deve ser numérico")
        elif a is not None and "km_ini" in a and "km_fim" in a:
            lo, hi = sorted((a["km_ini"], a["km_fim"]))
            for campo, k in (("km_ini_exec", ki_n), ("km_fim_exec", kf_n)):
                if not (lo - TOL_KM <= k <= hi + TOL_KM):
                    erro(campo, "km_no_trecho", f"{campo} {k} fora do trecho da atividade {aid} "
                                                f"(km {lo} a {hi})")
            if (kf_n - ki_n) * _sentido(a) < -TOL_KM:
                erro("km_fim_exec", "km_sentido", "km executado anda contra o sentido da atividade")
            if q is not None and q == 0 and abs(kf_n - ki_n) > TOL_KM:
                erro("km_fim_exec", "km_sem_quantidade", "avanço de km com quantidade 0")
    elif a is not None and q and "km_ini" in a:
        avisos.append("produção sem km executado: o registro não entra na linha real tempo-km")

    # --- ocorrências e fotos (só referências)
    oc = reg.get("ocorrencias", [])
    if not isinstance(oc, list) or not all(isinstance(x, str) for x in oc):
        erro("ocorrencias", "formato", "ocorrencias deve ser lista de textos")
    fotos = reg.get("fotos", [])
    if not isinstance(fotos, list):
        erro("fotos", "formato", "fotos deve ser lista de referências")
    elif len(fotos) > MAX_FOTOS:
        erro("fotos", "foto_limite", f"no máximo {MAX_FOTOS} fotos por registro (recebidas {len(fotos)})")
    else:
        for i, f in enumerate(fotos):
            c = f"fotos[{i}]"
            if not isinstance(f, dict) or not isinstance(f.get("ref"), str) or not f["ref"].strip():
                erro(c, "foto_ref", "cada foto é uma referência {'ref': texto} (o arquivo não vem no registro)")
                continue
            if "sha256" in f and not (isinstance(f["sha256"], str) and _RE_SHA256.match(f["sha256"])):
                erro(c + ".sha256", "foto_hash", "sha256 deve ter 64 caracteres hexadecimais")
            for campo, lim in (("lat", 90), ("lon", 180)):
                if campo in f:
                    v = _num(f[campo])
                    if v is None or abs(v) > lim:
                        erro(f"{c}.{campo}", "foto_coord", f"{campo} fora de ±{lim}")

    # --- estado e transição
    est = reg.get("estado")
    if est not in ESTADOS:
        erro("estado", "estado", f"estado deve ser um de {list(ESTADOS)} (recebido {est!r})")
    else:
        if est == "aprovado" and not str(reg.get("ref_memoria_calculo") or "").strip():
            erro("ref_memoria_calculo", "aprovado_exige_memoria",
                 "estado 'aprovado' exige ref_memoria_calculo (memória de cálculo da medição)")
        if estado_anterior is not None:
            if estado_anterior not in ESTADOS:
                erro("estado_anterior", "estado", f"estado_anterior desconhecido: {estado_anterior!r}")
            elif not transicao_valida(estado_anterior, est):
                erro("estado", "transicao", f"transição inválida {estado_anterior} → {est} "
                                            f"(permitidas: {sorted(TRANSICOES)})")

    # --- coerência com a situação da frente (avisos: o registro pode estar certo e o cadastro, atrasado)
    if a is not None and q is not None and q > 0:
        if a.get("status", "nao_iniciada") == "nao_iniciada":
            avisos.append(f"produção em {aid}, que está 'nao_iniciada' na data de status: conferir início real")
        tot = _num(a.get("quantidade_total"))
        if tot and q > tot:
            avisos.append(f"quantidade {q:g} maior que o total da atividade {aid} ({tot:g}): conferir unidade/lançamento")
        cal = projeto.calendarios.get(a.get("calendario"))
        if tipo == "diario" and "data" in datas and cal is not None and not cal.eh_util(datas["data"]):
            avisos.append(f"produção em dia não útil do calendário da frente ({reg.get('data')}): domingo, "
                          "feriado ou paralisação prevista")
    if est == "aprovado" and estado_anterior is None:
        avisos.append("registro já 'aprovado' sem estado_anterior: sem histórico de conferência do fiscal")

    # --- origem
    if not str(reg.get("origem") or "").strip():
        erro("origem", "origem", "origem obrigatória (quem/qual coletor lançou o registro)")
    if obra_ficticia(projeto):
        avisos.append("obra FICTÍCIA: este registro não é tratado como medição real")
    return {"valido": not erros, "erros": erros, "avisos": avisos}


# =========================================================================== gerador sintético
def _janelas(boletins: list[dict]) -> list[tuple[int, int, dict]]:
    """Janelas [ini, fim) dos boletins de UMA atividade, em ordem: fim = próximo boletim ou +7 dias."""
    bs = sorted(boletins, key=lambda m: m["semana_inicio"])
    out = []
    for i, m in enumerate(bs):
        s = ordinal(m["semana_inicio"])
        fim = s + 7
        if i + 1 < len(bs):
            fim = min(fim, ordinal(bs[i + 1]["semana_inicio"]))
        out.append((s, fim, m))
    return out


def gerar_diarios_sinteticos(projeto: Projeto) -> list[dict]:
    """Diários FICTÍCIOS em memória, derivados dos boletins (regras no docstring do módulo)."""
    if not obra_ficticia(projeto):
        raise ErroFiscalizacao("o gerador de diários sintéticos só roda sobre obra com meta.ficticio = true "
                               "(o texto do aviso não basta); dado real nunca recebe diário inventado")
    meta = projeto.dados["meta"]
    ds = projeto.data_status
    semente = meta.get("semente", 0)
    obra = _cal_obra(projeto)
    chuva = dias_de_chuva(projeto)
    por_ativ = defaultdict(list)
    for m in projeto.dados.get("medicoes", []):
        if m.get("atividade_id") in projeto.atividades:
            por_ativ[m["atividade_id"]].append(m)

    saida = []
    for aid in sorted(por_ativ):
        a = projeto.atividades[aid]
        if not a.get("quantidade_total") or a.get("tipo", "tarefa") != "tarefa":
            continue
        cal = projeto.calendarios[a["calendario"]]
        eqs = max(1, int(a.get("equipes") or 1))
        total = float(a["quantidade_total"])
        tem_km = "km_ini" in a and "km_fim" in a
        acumulado = 0.0
        janelas = _janelas(por_ativ[aid])
        for k, (s, fim_jan, m) in enumerate(janelas):
            n = int(round(m["equipes_dias"] / eqs)) if m["equipes_dias"] > 0 else 0
            uteis, d = [], s
            while len(uteis) < n and d < min(fim_jan, ds):
                if cal.eh_util(d):
                    uteis.append(d)
                d += 1
            ultima = k == len(janelas) - 1
            fim_par = (uteis[-1] + 1) if (ultima and a.get("status") == "concluida" and uteis) \
                else min(fim_jan, ds)
            q_bol = float(m["quantidade"])
            partes = []
            if uteis:
                base = round(q_bol / len(uteis), 3)
                partes = [base] * (len(uteis) - 1)
                partes.append(round(q_bol - sum(partes), 3))
            trabalho = dict(zip(uteis, partes))
            for d in range(s, fim_par):
                trabalhou = d in trabalho
                if not trabalhou and not (obra.eh_util(d) and not cal.eh_util(d)):
                    continue  # domingo/feriado da obra: sem diário desta frente
                hc = horas_chuva_sintetica(semente, d) if d in chuva else 0.0
                oc = []
                reg = {"tipo": "diario", "data": iso(d), "atividade_id": aid, "lote_id": a.get("lote_id"),
                       "segmento_id": a.get("segmento_id"), "servico_id": a.get("servico_id"),
                       "unidade": a.get("unidade"), "horas_chuva": hc}
                if trabalhou:
                    q = trabalho[d]
                    k0 = acumulado
                    acumulado = round(acumulado + q, 6)
                    reg.update(quantidade=q, equipes_dias=eqs)
                    if hc:
                        oc.append(f"Chuva de {hc:g} h; o calendário da frente não paralisa com chuva")
                else:
                    k0 = acumulado
                    reg.update(quantidade=0.0, equipes_dias=0)
                    oc.append(f"Paralisação por chuva ({hc:g} h)" if hc
                              else "Sem serviço nesta frente: dia não útil no calendário da frente "
                                   "(ex.: superfície úmida após chuva)")
                if tem_km:
                    span = a["km_fim"] - a["km_ini"]
                    reg["km_ini_exec"] = round(a["km_ini"] + span * min(1.0, k0 / total), 6)
                    reg["km_fim_exec"] = round(a["km_ini"] + span * min(1.0, acumulado / total), 6)
                reg.update(ocorrencias=oc, fotos=[],
                           estado="lancado" if d >= ds - 7 else "conferido_fiscal",
                           ref_memoria_calculo=None, semana_boletim=m["semana_inicio"],
                           origem=ORIGEM_SINTETICA, sintetico=True)
                saida.append(reg)
    return saida


def boletins_estendidos(projeto: Projeto, diarios: list[dict]) -> list[dict]:
    """Boletim estendido FICTÍCIO por (atividade, semana do boletim), agregando os diários."""
    grupos = defaultdict(list)
    for r in diarios:
        grupos[(r["atividade_id"], r["semana_boletim"])].append(r)
    ultimos = {}
    for (aid, sem) in grupos:
        ultimos[aid] = max(ultimos.get(aid, sem), sem)
    out = []
    for (aid, sem), rs in sorted(grupos.items()):
        rs.sort(key=lambda r: r["data"])
        a = projeto.atividades[aid]
        pendente = sem == ultimos[aid] and a.get("status") == "em_andamento"
        b = {"tipo": "boletim", "atividade_id": aid, "lote_id": a.get("lote_id"), "segmento_id": a.get("segmento_id"),
             "periodo_ini": rs[0]["data"], "periodo_fim": rs[-1]["data"],
             "quantidade": round(sum(r["quantidade"] for r in rs), 3),
             "equipes_dias": sum(r["equipes_dias"] for r in rs),
             "horas_chuva": sum(r["horas_chuva"] for r in rs),
             "dias_chuva": sum(1 for r in rs if r["horas_chuva"] > 0),
             "ocorrencias": [], "fotos": [],
             "estado": "conferido_fiscal" if pendente else "aprovado",
             "ref_memoria_calculo": None if pendente else f"MC-SINT-{aid}-{sem}",
             "origem": ORIGEM_SINTETICA.replace("diário", "boletim estendido"), "sintetico": True}
        if "km_ini_exec" in rs[0]:
            b["km_ini_exec"], b["km_fim_exec"] = rs[0]["km_ini_exec"], rs[-1]["km_fim_exec"]
        out.append(b)
    return out


# =========================================================================== conciliação
def conciliar(projeto: Projeto, diarios: list[dict], boletins: list[dict] | None = None,
              lote: str | None = None, tol_quantidade: float = 0.0005) -> dict:
    """Soma dos diários por janela de boletim × boletim (quantidade e equipes·dia).

    Janela do boletim = [semana_inicio, próximo boletim da atividade ou +7 dias)."""
    boletins = projeto.dados.get("medicoes", []) if boletins is None else boletins

    def no_lote(aid):
        return not lote or projeto.atividades.get(aid, {}).get("lote_id") == lote

    por_ativ = defaultdict(list)
    for m in boletins:
        if no_lote(m.get("atividade_id")):
            por_ativ[m["atividade_id"]].append(m)
    dia_por_ativ = defaultdict(list)
    for r in diarios:
        if no_lote(r.get("atividade_id")):
            dia_por_ativ[r["atividade_id"]].append(r)

    itens, sem_boletim = [], []
    for aid in sorted(set(por_ativ) | set(dia_por_ativ)):
        jan = _janelas(por_ativ.get(aid, []))
        soma = [[0.0, 0.0, 0] for _ in jan]
        for r in dia_por_ativ.get(aid, []):
            d = ordinal(r["data"])
            i = next((i for i, (s, f, _) in enumerate(jan) if s <= d < f), None)
            if i is None:
                if r.get("quantidade", 0) or r.get("equipes_dias", 0):
                    sem_boletim.append({"atividade_id": aid, "data": r["data"], "quantidade": r.get("quantidade", 0),
                                        "equipes_dias": r.get("equipes_dias", 0)})
                continue
            soma[i][0] += float(r.get("quantidade", 0))
            soma[i][1] += float(r.get("equipes_dias", 0))
            soma[i][2] += 1
        for (s, f, m), (qd, ed, n) in zip(jan, soma):
            dq = round(qd - float(m["quantidade"]), 6)
            de = round(ed - float(m["equipes_dias"]), 6)
            ok = abs(dq) <= tol_quantidade and abs(de) <= 1e-9
            itens.append({"atividade_id": aid, "semana_inicio": m["semana_inicio"], "janela_fim": iso(f - 1),
                          "quantidade_boletim": m["quantidade"], "quantidade_diarios": round(qd, 6),
                          "delta_quantidade": dq, "equipes_dias_boletim": m["equipes_dias"],
                          "equipes_dias_diarios": ed, "delta_equipes_dias": de, "n_diarios": n,
                          "sem_diario": n == 0, "ok": ok})
    div = [x for x in itens if not x["ok"]]
    n_div = len(div) + len(sem_boletim)
    return {"lote": lote, "tolerancia_quantidade": tol_quantidade,
            "regra": "janela do boletim = [semana_inicio, próximo boletim da atividade ou +7 dias); "
                     "diverge se |Δquantidade| > tolerância ou Δequipes·dia ≠ 0; produção em diário fora de "
                     "qualquer boletim também é divergência",
            "ok": n_div == 0, "n_boletins": len(itens), "n_divergencias": n_div,
            "n_divergencias_de_boletim": len(div), "n_producao_sem_boletim": len(sem_boletim),
            "divergencias": div,
            "diarios_sem_boletim": sem_boletim, "itens": itens}


# =========================================================================== produtividade
def produtividade_trabalhada_x_calendario(projeto: Projeto, diarios: list[dict], lote: str | None = None) -> dict:
    """Por atividade: un/equipe·dia nos dias TRABALHADOS × nos dias úteis do calendário da OBRA
    (período do primeiro ao último diário). A diferença mede o efeito da chuva/paralisações."""
    obra = _cal_obra(projeto)
    por = defaultdict(list)
    for r in diarios:
        a = projeto.atividades.get(r["atividade_id"])
        if a and (not lote or a.get("lote_id") == lote):
            por[r["atividade_id"]].append(r)
    linhas = []
    for aid in sorted(por):
        rs = sorted(por[aid], key=lambda r: r["data"])
        a = projeto.atividades[aid]
        eqs = max(1, int(a.get("equipes") or 1))
        q = sum(r["quantidade"] for r in rs)
        eqd = sum(r["equipes_dias"] for r in rs)
        d0, d1 = ordinal(rs[0]["data"]), ordinal(rs[-1]["data"])
        uteis_obra = obra.dias_uteis_entre(d0, d1 + 1)
        trab = sum(1 for r in rs if r["equipes_dias"] > 0)
        par_chuva = sum(1 for r in rs if r["equipes_dias"] == 0 and r.get("horas_chuva", 0) > 0)
        p_trab = q / eqd if eqd else None
        p_cal = q / (uteis_obra * eqs) if uteis_obra else None
        linhas.append({"atividade_id": aid, "servico_id": a.get("servico_id"), "lote_id": a.get("lote_id"),
                       "unidade": a.get("unidade"), "quantidade": round(q, 3), "equipes": eqs,
                       "dias_trabalhados": trab, "dias_paralisados_chuva": par_chuva,
                       "dias_paralisados_outros": sum(1 for r in rs if r["equipes_dias"] == 0) - par_chuva,
                       "dias_uteis_obra_no_periodo": uteis_obra, "dias_corridos": d1 - d0 + 1,
                       "prod_por_dia_trabalhado": None if p_trab is None else round(p_trab, 4),
                       "prod_por_dia_util_obra": None if p_cal is None else round(p_cal, 4),
                       "perda_por_paralisacao_pct": None if not p_trab or p_cal is None
                       else round(100 * (1 - p_cal / p_trab), 1)})
    return {"lote": lote, "unidade_produtividade": "unidade da atividade por equipe·dia",
            "regra": "trabalhado = Σq ÷ Σequipes·dia; calendário = Σq ÷ (dias úteis da obra no período × equipes)",
            "atividades": linhas}


# =========================================================================== linha real tempo-km
def linha_real(projeto: Projeto, diarios: list[dict], lote: str | None = None) -> dict:
    """Linha REAL tempo-km por frente, a partir de km_ini_exec/km_fim_exec dos diários.

    Pontos em fronteiras de dia (convenção de calendario.py): ``data`` = início do dia. O primeiro
    ponto é (início do 1º dia trabalhado, km inicial); cada dia trabalhado acrescenta
    (início do dia seguinte, km_fim_exec). Dias sem produção não geram ponto (a linha fica plana)."""
    por = defaultdict(list)
    for r in diarios:
        a = projeto.atividades.get(r.get("atividade_id"))
        if a and (not lote or a.get("lote_id") == lote) and r.get("km_ini_exec") is not None:
            por[r["atividade_id"]].append(r)
    frentes = []
    for aid in sorted(por):
        rs = [r for r in sorted(por[aid], key=lambda r: r["data"]) if r["quantidade"] > 0]
        if not rs:
            continue
        a = projeto.atividades[aid]
        pts = [{"data": rs[0]["data"], "km": rs[0]["km_ini_exec"]}]
        for r in rs:
            pts.append({"data": iso(ordinal(r["data"]) + 1), "km": r["km_fim_exec"]})
        corr = ordinal(pts[-1]["data"]) - ordinal(pts[0]["data"])
        avanco = abs(pts[-1]["km"] - pts[0]["km"])
        frentes.append({"atividade_id": aid, "servico_id": a.get("servico_id"), "lote_id": a.get("lote_id"),
                        "segmento_id": a.get("segmento_id"), "km_ini": a.get("km_ini"), "km_fim": a.get("km_fim"),
                        "sentido": "crescente" if _sentido(a) > 0 else "decrescente",
                        "status": a.get("status"), "km_atual": pts[-1]["km"],
                        "ritmo_medio_km_por_dia_corrido": round(avanco / corr, 6) if corr else None,
                        "pontos": pts})
    return {"lote": lote, "convencao": "data = início do dia (fronteira); km interpolado pelo avanço acumulado",
            "frentes": frentes}


# =========================================================================== cache por obra
_cache_lock = threading.Lock()
_cache: list[tuple[dict, list[dict]]] = []


def diarios_da_obra(projeto: Projeto) -> list[dict]:
    """Diários sintéticos da obra, gerados uma vez por dicionário de dados (identidade)."""
    with _cache_lock:
        for d, regs in _cache:
            if d is projeto.dados:
                return regs
    regs = gerar_diarios_sinteticos(projeto)
    with _cache_lock:
        _cache.append((projeto.dados, regs))
        del _cache[:-8]
    return regs
