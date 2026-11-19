"""Exportação XER (Primavera P6), simétrica ao MSPDI. Só biblioteca padrão.

Gera ERMHDR + tabelas %T/%F/%R: PROJECT, CALENDAR, TASK e TASKPRED, no subconjunto que o
importador próprio (``xer.py``) lê.

Compatibilidade com o P6 real NÃO é alegada (não temos o programa): validado por ida e volta com
o importador próprio (exportar → importar → ``motor.calcular`` dá as mesmas datas, término e caminho
crítico). O formato segue a descrição pública do XER; nomes de campo não verificados em fonte
primária (ver docstring de ``xer.py``).

Mapeamento
----------
- PROJECT: ``plan_start_date`` = início do projeto; ``last_recalc_date`` = data de status (vazia na
  linha de base); ``clndr_id`` = calendário da obra.
- CALENDAR: ``clndr_data`` no formato mínimo (DaysOfWeek com faixas 08:00–12:00 e 13:00–17:00 nos
  dias úteis + Exceptions com a data serial desde 30/12/1899); ``day_hr_cnt`` = 8.
- TASK: ``task_code`` = id; ``task_type`` TT_Task / TT_Mile (marco de início) / TT_FinMile (marco de
  término); ``status_code`` TK_NotStart / TK_Active / TK_Complete; durações em HORAS a 8 h/dia:
  ``target_drtn_hr_cnt`` = total (realizado em dias úteis até a data de status + remanescente),
  ``remain_drtn_hr_cnt`` = remanescente; ``act_start_date``/``act_end_date`` para em andamento e
  concluídas; restrições: SNET → ``cstr_type`` CS_MSOA; FNLT → CS_MEOB (no 2º par
  ``cstr_type2``/``cstr_date2`` quando houver SNET também).
- TASKPRED: ``pred_type`` PR_FS/PR_SS/PR_FF/PR_SF; ``lag_hr_cnt`` = lag × 8 h (lag no calendário da
  predecessora, como no motor).

NÃO exportado: recursos (RSRC/TASKRSRC), custos, códigos de atividade, WBS (PROJWBS), notas,
UDFs, linha de base do P6 e a memória de cálculo. A lógica de progresso (sobrepor × retida) não
viaja no arquivo: o importador recalcula com a política padrão.
"""

from __future__ import annotations

import re
from datetime import date

from ..calendario import iso, ordinal
from ..obra import tipo_obra
from .xer import EPOCA_SERIAL

HORAS_DIA = 8
NAO_EXPORTADO = ["recursos (RSRC/TASKRSRC)", "custos", "códigos de atividade (ACTVCODE)", "WBS (PROJWBS)",
                 "notas e UDFs", "linha de base do P6", "memória de cálculo", "lógica de progresso (retida)"]


def _txt(v) -> str:
    """Campo XER: sem TAB nem quebra de linha (separadores do formato)."""
    return re.sub(r"[\t\r\n]+", " ", "" if v is None else str(v)).strip()


def _dt(d: int | str | None, hora: str = "08:00") -> str:
    if d is None or d == "":
        return ""
    if isinstance(d, str):
        d = ordinal(d)
    return f"{date.fromordinal(d).isoformat()} {hora}"


def _clndr_data(cal) -> str:
    dias = []
    for dt in range(1, 8):  # 1 = domingo ... 7 = sábado
        wd_py = (dt + 5) % 7
        if wd_py in cal.dias_semana:
            dias.append(f"(0||{dt}()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))")
        else:
            dias.append(f"(0||{dt}()())")
    exc = "".join(f"(0||{i}(d|{(d - EPOCA_SERIAL).days})())" for i, d in enumerate(sorted(cal.nao_uteis)))
    return ("(0||CalendarData()((0||DaysOfWeek()(" + "".join(dias) + "))(0||VIEW(ShowTotal|Y)())"
            "(0||Exceptions()(" + exc + "))))")


def _tabela(linhas: list[str], nome: str, campos: list[str], registros: list[dict]) -> None:
    linhas.append("%T\t" + nome)
    linhas.append("%F\t" + "\t".join(campos))
    for r in registros:
        linhas.append("%R\t" + "\t".join(_txt(r.get(c)) for c in campos))


def exportar_xer(projeto, cenario_resultado: dict) -> str:
    """XER a partir do projeto (``cenarios.Projeto``) e do resultado de ``cenarios.executar``."""
    dados = projeto.dados
    meta = dados["meta"]
    res = cenario_resultado["atividades"]
    ds_txt = cenario_resultado.get("data_status")
    ds = ordinal(ds_txt) if ds_txt else None
    cal_id = {cid: str(i + 1) for i, cid in enumerate(projeto.calendarios)}
    linhas = ["\t".join(["ERMHDR", "19.12", date.today().isoformat(), "Project", "INFRA4D",
                         _txt(f"INFRA 4D — cenário {cenario_resultado['cenario']} (DADOS FICTÍCIOS)"
                              if meta.get("ficticio") else f"INFRA 4D — cenário {cenario_resultado['cenario']}"),
                         "dbxDatabaseNoName", "Project Management", "BRL"])]
    nome_obra = (dados.get(tipo_obra(dados)) or dados.get("ferrovia") or {}).get("nome", "Projeto")  # tipo declarado (P8)
    _tabela(linhas, "PROJECT", ["proj_id", "proj_short_name", "plan_start_date", "last_recalc_date", "clndr_id"],
            [{"proj_id": "1", "proj_short_name": f"INFRA4D-{cenario_resultado['cenario']}",
              "plan_start_date": _dt(projeto.inicio_projeto), "last_recalc_date": _dt(ds, "00:00"),
              "clndr_id": cal_id.get(meta.get("calendario_obra"), "1")}])
    _tabela(linhas, "CALENDAR", ["clndr_id", "default_flag", "clndr_name", "clndr_type", "day_hr_cnt", "week_hr_cnt",
                                 "clndr_data"],
            [{"clndr_id": cal_id[cid], "default_flag": "Y" if cid == meta.get("calendario_obra") else "N",
              "clndr_name": cid, "clndr_type": "CA_Base", "day_hr_cnt": HORAS_DIA,
              "week_hr_cnt": HORAS_DIA * len(cal.dias_semana), "clndr_data": _clndr_data(cal)}
             for cid, cal in projeto.calendarios.items()])

    ordem = [a["id"] for a in dados["atividades"] if a["id"] in res]
    tid = {aid: str(i + 1) for i, aid in enumerate(ordem)}
    tarefas = []
    for aid in ordem:
        a, r = projeto.atividades[aid], res[aid]
        cal = projeto.calendarios[a["calendario"]]
        tipo = a.get("tipo", "tarefa")
        status = r["status"]
        rem = int(r["duracao"])
        ini = ordinal(a.get("inicio_real")) if status != "nao_iniciada" else None
        fim = ordinal(a.get("termino_real")) if status == "concluida" else None
        if status == "concluida":
            total, rem = (0 if tipo != "tarefa" else cal.dias_uteis_entre(ini, fim + 1)), 0
        elif status == "em_andamento":
            total = (cal.dias_uteis_entre(ini, ds) if ds is not None else 0) + rem
        else:
            total = rem
        snet = a.get("restricao_inicio")
        # montar_entrada ignora FNLT na linha de base
        fnlt = None if cenario_resultado["cenario"] == "linha_base" else a.get("restricao_termino")
        c1 = ("CS_MSOA", _dt(snet)) if snet else (("CS_MEOB", _dt(fnlt, "17:00")) if fnlt else ("", ""))
        c2 = ("CS_MEOB", _dt(fnlt, "17:00")) if (snet and fnlt) else ("", "")
        tarefas.append({
            "task_id": tid[aid], "proj_id": "1", "clndr_id": cal_id[a["calendario"]], "task_code": aid,
            "task_name": a.get("nome", aid),
            "task_type": {"marco_inicio": "TT_Mile", "marco_termino": "TT_FinMile"}.get(tipo, "TT_Task"),
            "status_code": {"nao_iniciada": "TK_NotStart", "em_andamento": "TK_Active",
                            "concluida": "TK_Complete"}[status],
            "target_drtn_hr_cnt": total * HORAS_DIA, "remain_drtn_hr_cnt": rem * HORAS_DIA,
            "act_start_date": _dt(ini) if ini is not None else "",
            "act_end_date": _dt(fim, "08:00" if tipo == "marco_inicio" else "17:00") if fim is not None else "",
            "early_start_date": _dt(r.get("inicio")), "early_end_date": _dt(r.get("termino"), "17:00"),
            "cstr_type": c1[0], "cstr_date": c1[1], "cstr_type2": c2[0], "cstr_date2": c2[1],
        })

    _tabela(linhas, "TASK", ["task_id", "proj_id", "clndr_id", "task_code", "task_name", "task_type", "status_code",
                             "target_drtn_hr_cnt", "remain_drtn_hr_cnt", "act_start_date", "act_end_date",
                             "early_start_date", "early_end_date", "cstr_type", "cstr_date", "cstr_type2",
                             "cstr_date2"], tarefas)
    preds = [{"task_pred_id": str(i + 1), "task_id": tid[r["sucessora"]], "pred_task_id": tid[r["predecessora"]],
              "proj_id": "1", "pred_proj_id": "1", "pred_type": "PR_" + r.get("tipo", "FS"),
              "lag_hr_cnt": int(r.get("lag", 0)) * HORAS_DIA}
             for i, r in enumerate(dados["relacoes"]) if r["sucessora"] in tid and r["predecessora"] in tid]
    _tabela(linhas, "TASKPRED", ["task_pred_id", "task_id", "pred_task_id", "proj_id", "pred_proj_id", "pred_type",
                                 "lag_hr_cnt"], preds)
    linhas.append("%E")
    return "\r\n".join(linhas) + "\r\n"
