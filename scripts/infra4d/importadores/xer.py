"""Primavera P6 XER: importação (só leitura), parser próprio na biblioteca padrão.

Formato texto tabulado: ``ERMHDR`` (cabeçalho), ``%T`` (tabela), ``%F`` (campos),
``%R`` (linha), ``%E`` (fim). Tabelas lidas: PROJECT, CALENDAR, TASK, TASKPRED.

Fontes: os nomes de tabela e de campo seguem a descrição do formato no R02/R04
deste repositório e o conhecimento público do formato; a especificação da
Oracle (XER Import/Export Data Map, docs.oracle.com/cd/F74771_01/...) foi
LOCALIZADA mas NÃO lida (PDF não legível pela ferramenta). A sintaxe de
``clndr_data`` não tem especificação pública encontrada: o suporte é o mínimo
descrito em ``LIMITACOES_XER``. NÃO foi consultado o código de xerparser (GPL).

Compatibilidade com o P6 real NÃO é alegada (não temos o programa): validado
por fixture sintética escrita à mão (``examples/fixtures/p6_minimo.xer``).
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

from ..calendario import Calendario, ErroCalendario, HORIZONTE_FIM, HORIZONTE_INICIO
from ..motor import AtividadeCPM, Relacao
from .comum import (LIMITACOES_COMUNS, MAXIMO_ATIVIDADES, MAXIMO_CALENDARIOS, MAXIMO_NIVEIS, Avisos,
                    ErroImportacao, data_de_texto, datahora_de_texto, dias_de_horas, lag_de_horas, no_horizonte)

PRED_TIPO = {"PR_FS": "FS", "PR_SS": "SS", "PR_FF": "FF", "PR_SF": "SF"}
TIPOS_IGNORADOS = {"TT_LOE": "nível de esforço (LOE)", "TT_WBS": "resumo WBS"}
EPOCA_SERIAL = date(1899, 12, 30)  # datas de exceção no clndr_data: dias desde 30/12/1899
SERIAL_MIN = (HORIZONTE_INICIO - EPOCA_SERIAL).days
SERIAL_MAX = (HORIZONTE_FIM - EPOCA_SERIAL).days

# (obrigatórias, opcionais) por tabela. Obrigatória ausente: arquivo recusado. Opcional: aviso.
COLUNAS = {
    "PROJECT": (["proj_id", "plan_start_date"], ["last_recalc_date", "clndr_id"]),
    "TASK": (["task_id", "proj_id", "status_code", "target_drtn_hr_cnt"],
             ["task_code", "task_name", "task_type", "clndr_id", "remain_drtn_hr_cnt", "act_start_date",
              "act_end_date", "cstr_type", "cstr_date"]),
    "TASKPRED": (["task_id", "pred_task_id", "pred_type"], ["lag_hr_cnt"]),
    "CALENDAR": (["clndr_id"], ["clndr_data", "day_hr_cnt"]),
}
OPCIONAIS_EFEITO = {
    "last_recalc_date": "calculado SEM data de status",
    "clndr_id": "usado o calendário padrão",
    "task_code": "id = TASK<task_id>",
    "task_type": "todas tratadas como TT_Task (marcos não reconhecidos)",
    "remain_drtn_hr_cnt": "remanescente = duração original",
    "act_start_date": "atividades iniciadas serão recusadas por falta de início real",
    "act_end_date": "concluídas serão recusadas por falta de término real",
    "cstr_type": "restrições ignoradas",
    "cstr_date": "restrições ignoradas",
    "lag_hr_cnt": "todos os lags = 0",
    "clndr_data": "calendário segunda a sexta sem feriados",
    "day_hr_cnt": "8 h/dia",
}

LIMITACOES_XER = LIMITACOES_COMUNS + [
    "XER: lê só PROJECT, CALENDAR, TASK e TASKPRED; um projeto por importação (o primeiro, ou o indicado).",
    "XER: calendário (clndr_data) com suporte MÍNIMO: dias úteis da semana (DaysOfWeek: dia com faixa de "
    "horário = útil) e exceções sem horário (dia não útil, data serial desde 30/12/1899). Exceção com "
    "horário (dia útil extra), horas parciais e calendários de recurso são ignorados.",
    "XER: datas do plano usam data de dados = PROJECT.last_recalc_date e início = PROJECT.plan_start_date.",
    "XER: TT_Mile = marco de início, TT_FinMile = marco de término; TT_LOE e TT_WBS são ignorados com suas "
    "relações. Restrições aplicadas (primária ou secundária): CS_MSOA (início não antes de = SNET) e "
    "CS_MEOB (término no ou antes de = FNLT); CS_MSO vira SNET com aviso; demais ignoradas.",
    "XER: duração/lag em horas convertidos pelo day_hr_cnt do calendário (padrão 8 h).",
]


# =============================================================================
# Leitura das tabelas
# =============================================================================
def decodificar(dados: bytes | str) -> str:
    if isinstance(dados, str):
        return dados
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return dados.decode(enc)
        except UnicodeDecodeError:
            continue
    return dados.decode("latin-1")


def ler_tabelas(texto: str) -> dict[str, list[dict[str, str]]]:
    """Texto XER → {tabela: [ {campo: valor} ]}. Linhas fora de tabela são ignoradas."""
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not linhas or not linhas[0].lstrip("﻿").startswith("ERMHDR"):
        raise ErroImportacao("arquivo não começa com ERMHDR: não parece XER")
    tabelas: dict[str, list[dict[str, str]]] = {}
    atual, campos = None, None
    for n, linha in enumerate(linhas, 1):
        if not linha.strip():
            continue
        partes = linha.split("\t")
        marca = partes[0]
        if marca == "%T":
            atual = partes[1].strip() if len(partes) > 1 else None
            campos = None
            tabelas.setdefault(atual, [])
        elif marca == "%F":
            campos = [c.strip() for c in partes[1:]]
        elif marca == "%R":
            if atual is None or campos is None:
                raise ErroImportacao(f"linha {n}: %R fora de tabela ou sem %F")
            valores = partes[1:]
            valores += [""] * (len(campos) - len(valores))
            tabelas[atual].append(dict(zip(campos, valores)))
        elif marca == "%E":
            break
    return tabelas


def ler_campos(texto: str) -> dict[str, list[str]]:
    """{tabela: campos do %F} — para validar colunas obrigatórias."""
    campos, atual = {}, None
    for linha in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        partes = linha.split("\t")
        if partes[0] == "%T":
            atual = partes[1].strip() if len(partes) > 1 else None
        elif partes[0] == "%F" and atual is not None:
            campos[atual] = [c.strip() for c in partes[1:]]
    return campos


# =============================================================================
# clndr_data: (0||nome(params)(filhos))
# =============================================================================
class _ProfundoDemais(Exception):
    """clndr_data aninhado além de MAXIMO_NIVEIS (rodada 5: 3.000 níveis estouravam a recursão)."""


class _No:
    __slots__ = ("nome", "params", "filhos")

    def __init__(self, nome, params, filhos):
        self.nome, self.params, self.filhos = nome, params, filhos


def _arvore(texto: str) -> list[_No]:
    s = re.sub(r"[\x00-\x1f\x7f]", "", texto)  # quebras de linha/DEL embutidos
    pos = 0

    def pular():
        nonlocal pos
        while pos < len(s) and s[pos] == " ":
            pos += 1

    def no(nivel: int = 0) -> _No:
        nonlocal pos
        if nivel > MAXIMO_NIVEIS:
            raise _ProfundoDemais()
        pular()
        if s[pos] != "(":
            raise ValueError(f"esperado '(' na posição {pos}")
        pos += 1
        fim_pref = s.index("||", pos)
        pos = fim_pref + 2
        abre = s.index("(", pos)
        nome = s[pos:abre].strip()
        fecha = s.index(")", abre)
        params = s[abre + 1:fecha]
        pos = fecha + 1
        pular()
        filhos = []
        if pos < len(s) and s[pos] == "(":
            pos += 1
            pular()
            while pos < len(s) and s[pos] == "(":
                filhos.append(no(nivel + 1))
                pular()
            if pos >= len(s) or s[pos] != ")":
                raise ValueError(f"esperado ')' na posição {pos}")
            pos += 1
        pular()
        if pos >= len(s) or s[pos] != ")":
            raise ValueError(f"esperado ')' na posição {pos}")
        pos += 1
        return _No(nome, params, filhos)

    raizes = []
    pular()
    while pos < len(s):
        if s[pos] != "(":
            break
        raizes.append(no())
        pular()
    return raizes


def _buscar(nos: list[_No], nome: str) -> _No | None:
    for n in nos:
        if n.nome == nome:
            return n
        achado = _buscar(n.filhos, nome)
        if achado:
            return achado
    return None


def ler_clndr_data(texto: str, avisos: Avisos, nome_cal: str) -> tuple[tuple[int, ...] | None, set[date]]:
    """→ (dias úteis da semana em convenção Python 0=segunda, ou None; datas não úteis)."""
    if not texto or not texto.strip():
        return None, set()
    try:
        arv = _arvore(texto)
    except _ProfundoDemais:
        raise ErroImportacao(f"calendário {nome_cal}: clndr_data aninhado além de {MAXIMO_NIVEIS} níveis "
                             f"(recusado)") from None
    except (ValueError, IndexError) as e:
        avisos.add("clndr", f"calendário {nome_cal}: clndr_data ilegível ({e}); assumido segunda a sexta")
        return None, set()
    semana = None
    dow = _buscar(arv, "DaysOfWeek")
    if dow is not None:
        uteis = []
        for d in dow.filhos:
            if d.nome.isdigit() and 1 <= int(d.nome) <= 7 and d.filhos:
                uteis.append((int(d.nome) + 5) % 7)  # 1=domingo → 6; 2=segunda → 0
        semana = tuple(sorted(uteis))
    nao = set()
    exc = _buscar(arv, "Exceptions")
    if exc is not None:
        extras = 0
        for e in exc.filhos:
            m = re.search(r"d\|(\d{1,9})(?!\d)", e.params)
            if not m:
                continue
            serial = int(m.group(1))
            if not (SERIAL_MIN <= serial <= SERIAL_MAX):
                continue  # fora do horizonte dos calendários: não afeta o cálculo
            d = EPOCA_SERIAL + timedelta(days=serial)
            if e.filhos:
                extras += 1  # exceção com horário = dia útil extra
            else:
                nao.add(d)
        if extras:
            avisos.add("excecao_util", f"calendário {nome_cal}: {extras} exceção(ões) com horário (dia útil "
                                       f"extra/horário diferente) ignorada(s)")
    return semana, nao


# =============================================================================
# Importação
# =============================================================================
def _num(v: str | None, padrao: float = 0.0) -> float:
    if v is None or not v.strip():
        return padrao
    try:
        f = float(v.replace(",", "."))
    except ValueError as e:
        raise ErroImportacao(f"número ilegível no XER: {v[:40]!r}") from e
    if not math.isfinite(f):
        raise ErroImportacao(f"número não finito no XER: {v[:40]!r}")
    return f


def _validar_colunas(tabelas: dict, campos: dict[str, list[str]], avisos: Avisos) -> None:
    """Colunas OBRIGATÓRIAS ausentes recusam o arquivo; OPCIONAIS ausentes geram aviso que cita a coluna
    (rodada 5: sem task_id todas as relações sumiam e sem status_code todo o progresso virava
    'não iniciada', em silêncio)."""
    for tabela, (obrig, opc) in COLUNAS.items():
        if tabela not in tabelas or (tabela not in ("PROJECT", "TASK") and not tabelas[tabela]):
            continue
        presentes = set(campos.get(tabela, []))
        faltam = [c for c in obrig if c not in presentes]
        if faltam:
            raise ErroImportacao(f"XER: tabela {tabela} sem a(s) coluna(s) obrigatória(s) {', '.join(faltam)}")
        for c in opc:
            if c not in presentes:
                avisos.add("coluna", f"XER: tabela {tabela} sem a coluna {c}; {OPCIONAIS_EFEITO.get(c, 'valor padrão')}")


def importar_xer(dados: bytes | str, proj_id: str | None = None):
    """Lê XER → ``(atividades, relacoes, calendarios, metadados)`` prontos para ``motor.calcular``.

    Toda entrada ruim vira ``ErroImportacao`` (a rota responde 422, nunca 500), com uma rede de
    segurança para estouros residuais (rodada 5)."""
    try:
        return _importar_xer(dados, proj_id)
    except ErroImportacao:
        raise
    except (ErroCalendario, LookupError, OverflowError, RecursionError, ValueError, TypeError,
            MemoryError) as e:
        raise ErroImportacao(f"XER recusado: {type(e).__name__}: {str(e)[:200]}") from None


def _importar_xer(dados: bytes | str, proj_id: str | None = None):
    texto = decodificar(dados)
    tabelas = ler_tabelas(texto)
    avisos = Avisos()
    for t in ("PROJECT", "TASK"):
        if not tabelas.get(t):
            raise ErroImportacao(f"XER sem a tabela {t}")
    _validar_colunas(tabelas, ler_campos(texto), avisos)
    if len(tabelas["TASK"]) > MAXIMO_ATIVIDADES:
        raise ErroImportacao(f"XER com {len(tabelas['TASK'])} atividades; o limite suportado é {MAXIMO_ATIVIDADES}")
    projetos = tabelas["PROJECT"]
    if proj_id is None:
        proj = projetos[0]
        if len(projetos) > 1:
            avisos.add("multi", f"XER com {len(projetos)} projetos; importado só o primeiro "
                                f"({proj.get('proj_short_name')})")
    else:
        proj = next((p for p in projetos if p.get("proj_id") == proj_id), None)
        if proj is None:
            raise ErroImportacao(f"projeto proj_id={proj_id} não encontrado no XER")
    pid = proj.get("proj_id")

    inicio = data_de_texto(proj.get("plan_start_date"))
    data_status = data_de_texto(proj.get("last_recalc_date"))
    if inicio is None:
        raise ErroImportacao("PROJECT sem plan_start_date")
    for nome, d in (("plan_start_date", inicio), ("last_recalc_date", data_status)):
        if d is not None and not no_horizonte(d):
            raise ErroImportacao(f"{nome} {d} fora do horizonte suportado ({HORIZONTE_INICIO} a {HORIZONTE_FIM})")

    # ---------------------------------------------------------- calendários
    cal_linhas = {c.get("clndr_id"): c for c in tabelas.get("CALENDAR", [])}
    cal_padrao_id = proj.get("clndr_id") or next(
        (c.get("clndr_id") for c in cal_linhas.values() if c.get("default_flag") == "Y"), None)

    tarefas_todas = [t for t in tabelas["TASK"] if t.get("proj_id") == pid]
    tarefas = []
    for t in tarefas_todas:
        tt = t.get("task_type", "TT_Task")
        if tt in TIPOS_IGNORADOS:
            avisos.add("tipo", f"atividade {t.get('task_code')}: {TIPOS_IGNORADOS[tt]} ignorada")
            continue
        if tt not in ("TT_Task", "TT_Rsrc", "TT_Mile", "TT_FinMile"):
            avisos.add("tipo", f"atividade {t.get('task_code')}: task_type {tt} desconhecido; tratada como tarefa")
        tarefas.append(t)
    if not tarefas:
        raise ErroImportacao("XER sem atividades utilizáveis no projeto")

    calendarios: dict[str, Calendario] = {}
    horas_dia: dict[str, float] = {}
    chave_cal: dict[str | None, str] = {}

    def cal_de(clndr_id: str | None) -> str:
        cid = clndr_id if clndr_id in cal_linhas else cal_padrao_id
        if clndr_id and clndr_id not in cal_linhas:
            avisos.add("cal_inexistente", f"clndr_id {clndr_id} inexistente; usado o calendário do projeto")
        if cid in chave_cal:
            return chave_cal[cid]
        if len(chave_cal) >= MAXIMO_CALENDARIOS:
            raise ErroImportacao(f"XER usa mais de {MAXIMO_CALENDARIOS} calendários distintos; limite suportado")
        linha = cal_linhas.get(cid)
        if linha is None:
            avisos.add("cal_padrao", "sem calendário utilizável; criado 'PADRAO' segunda a sexta, 8 h/dia")
            chave = "PADRAO"
            calendarios[chave] = Calendario(chave, "Padrão (segunda a sexta)")
            horas_dia[chave] = 8.0
        else:
            nome = (linha.get("clndr_name") or f"CAL-{cid}").strip()
            chave = nome if nome not in calendarios else f"{nome} ({cid})"
            semana, nao = ler_clndr_data(linha.get("clndr_data", ""), avisos, nome)
            if semana is None:
                semana = (0, 1, 2, 3, 4)
            try:
                calendarios[chave] = Calendario(chave, nome, semana, frozenset(d for d in nao if no_horizonte(d)))
            except ErroCalendario as e:
                raise ErroImportacao(f"calendário {nome}: {e}") from e
            hd = _num(linha.get("day_hr_cnt"), 8.0)
            horas_dia[chave] = hd if hd > 0 else 8.0
        chave_cal[cid] = chave
        return chave

    # ------------------------------------------------------------- atividades
    id_por_task: dict[str, str] = {}
    usados = set()
    for t in tarefas:
        codigo = (t.get("task_code") or "").strip() or f"TASK{t.get('task_id')}"
        if codigo in usados:
            avisos.add("id_dup", f"task_code {codigo!r} repetido; usando {codigo}#{t.get('task_id')}")
            codigo = f"{codigo}#{t.get('task_id')}"
        usados.add(codigo)
        id_por_task[t.get("task_id")] = codigo

    atividades: list[AtividadeCPM] = []
    nomes, cal_da = {}, {}
    for t in tarefas:
        aid = id_por_task[t.get("task_id")]
        nomes[aid] = t.get("task_name") or aid
        cal = cal_de(t.get("clndr_id"))
        cal_da[aid] = cal
        hd = horas_dia[cal]
        ctx = f"atividade {aid}"
        tt = t.get("task_type", "TT_Task")
        tipo = {"TT_Mile": "marco_inicio", "TT_FinMile": "marco_termino"}.get(tt, "tarefa")
        sc = t.get("status_code", "TK_NotStart")
        status = {"TK_NotStart": "nao_iniciada", "TK_Active": "em_andamento",
                  "TK_Complete": "concluida"}.get(sc)
        if status is None:
            avisos.add("status", f"{ctx}: status_code {sc!r} desconhecido; tratada como não iniciada")
            status = "nao_iniciada"
        a_ini = datahora_de_texto(t.get("act_start_date"))
        a_fim = datahora_de_texto(t.get("act_end_date"))
        if tipo == "marco_termino" and status == "concluida" and a_ini is None:
            a_ini = a_fim  # marco de término concluído tem só act_end_date
        if tipo == "marco_inicio" and status == "concluida" and a_fim is None:
            a_fim = a_ini
        if status in ("em_andamento", "concluida") and a_ini is None:
            raise ErroImportacao(f"{ctx}: {sc} sem act_start_date")
        if status == "concluida" and a_fim is None:
            raise ErroImportacao(f"{ctx}: TK_Complete sem act_end_date")

        if tipo != "tarefa" or status == "concluida":
            dur = 0
        elif status == "em_andamento":
            dur = dias_de_horas(_num(t.get("remain_drtn_hr_cnt")), hd, avisos, ctx)
            if dur <= 0:
                avisos.add("rem0", f"{ctx}: TK_Active com remanescente 0; considerado 1 dia útil")
                dur = 1
        else:
            bruto = t.get("remain_drtn_hr_cnt") if t.get("remain_drtn_hr_cnt", "").strip() else t.get(
                "target_drtn_hr_cnt")
            if t.get("remain_drtn_hr_cnt", "").strip() and t.get("target_drtn_hr_cnt", "").strip() and \
                    _num(t.get("remain_drtn_hr_cnt")) != _num(t.get("target_drtn_hr_cnt")):
                avisos.add("rem_target", f"{ctx}: não iniciada com remain ≠ target; usada a remanescente")
            dur = dias_de_horas(_num(bruto), hd, avisos, ctx)

        restr, restr_fim = None, None
        for campo_t, campo_d, rotulo in (("cstr_type", "cstr_date", "restrição"),
                                         ("cstr_type2", "cstr_date2", "restrição secundária")):
            ct = (t.get(campo_t) or "").strip()
            if not ct:
                continue
            cd = data_de_texto(t.get(campo_d))
            if ct in ("CS_MSOA", "CS_MSO") and cd is not None and restr is None:
                if ct == "CS_MSO":
                    avisos.add("restr", f"{ctx}: CS_MSO (início em) tratada como SNET (início não antes de)")
                restr = cd.toordinal()
            elif ct == "CS_MEOB" and cd is not None and restr_fim is None:
                restr_fim = cd.toordinal()  # término no ou antes de = FNLT (último dia com trabalho)
            else:
                avisos.add("restr", f"{ctx}: {rotulo} {ct} não suportada; ignorada")

        atividades.append(AtividadeCPM(
            id=aid, duracao=dur, calendario=cal, tipo=tipo, status=status,
            inicio_real=a_ini.date().toordinal() if a_ini and status != "nao_iniciada" else None,
            termino_real=a_fim.date().toordinal() if a_fim and status == "concluida" else None,
            restricao_inicio=restr, restricao_termino=restr_fim,
        ))

    # --------------------------------------------------------------- relações
    relacoes: list[Relacao] = []
    chaves = set()
    ids_todos = {t.get("task_id") for t in tarefas_todas}
    for r in tabelas.get("TASKPRED", []):
        suc_tid, pred_tid = r.get("task_id"), r.get("pred_task_id")
        if suc_tid not in id_por_task and pred_tid not in id_por_task:
            continue  # relação de outro projeto
        if suc_tid not in id_por_task or pred_tid not in id_por_task:
            motivo = "ignorada (LOE/WBS)" if (suc_tid in ids_todos and pred_tid in ids_todos) else "de outro projeto"
            avisos.add("rel_orfa", f"relação {pred_tid}->{suc_tid}: ponta {motivo}; descartada")
            continue
        tipo = PRED_TIPO.get((r.get("pred_type") or "").strip())
        if tipo is None:
            raise ErroImportacao(f"TASKPRED {r.get('task_pred_id')}: pred_type {r.get('pred_type')!r} desconhecido")
        pred, suc = id_por_task[pred_tid], id_por_task[suc_tid]
        ctx = f"relação {pred}->{suc}"
        lag = lag_de_horas(_num(r.get("lag_hr_cnt")), horas_dia[cal_da[pred]], avisos, ctx)
        if (pred, suc, tipo) in chaves:
            avisos.add("rel_dup", f"{ctx}: relação {tipo} duplicada; mantida a primeira")
            continue
        chaves.add((pred, suc, tipo))
        relacoes.append(Relacao(pred, suc, tipo, lag))

    metadados = {
        "formato": "xer",
        "nome": proj.get("proj_short_name"),
        "proj_id": pid,
        "inicio_projeto": inicio.toordinal(),
        "data_status": data_status.toordinal() if data_status else None,
        "nomes": nomes,
        "horas_por_dia": dict(horas_dia),
        "avisos": avisos.lista(),
        "limitacoes": list(LIMITACOES_XER),
    }
    return atividades, relacoes, calendarios, metadados
