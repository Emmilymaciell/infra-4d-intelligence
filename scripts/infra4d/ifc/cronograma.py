"""Cronograma NATIVO IFC 4.3 por cenário (4D) e a ida e volta pelo motor CPM.

Exportação (``adicionar``):

    IfcWorkPlan "INFRA 4D"  (IfcRelDeclares no IfcProject)
     └ IfcWorkSchedule por cenário (IfcRelAggregates): Identification = cenário;
         linha_base → BASELINE · construtora → PLANNED · independente → USERDEFINED/INDEPENDENTE ·
         simulado → USERDEFINED/SIMULADO (só quando há ajustes)
        └ IfcTask por atividade (IfcRelAssignsToControl): Identification = atividade, Status, IsMilestone,
          ObjectType = tipo do motor; IfcTaskTime WORKTIME com duração em dias úteis, datas da API
          (Schedule*, Early*, Late*), folgas, IsCritical, StatusTime, Actual*, Completion
    IfcWorkCalendar por calendário (compartilhado pelos cenários): dias da semana num
      IfcRecurrencePattern WEEKLY (1 = segunda) e dias não úteis em faixas (ExceptionTimes)
    IfcRelSequence (FS/SS/FF/SF) + IfcLagTime WORKTIME
    IfcRelAssignsToProduct: UM por peça, ligando as tarefas da atividade em todos os cenários

Convenções declaradas:
- ``P{n}D`` em WORKTIME = n dias ÚTEIS do calendário da tarefa (leitura por outros softwares: não verificada).
- EarlyFinish/LateFinish = ``ef``/``lf`` do motor, que são EXCLUSIVOS (dia seguinte ao último dia útil);
  ScheduleFinish = último dia trabalhado (``termino`` da API).
- Valores NEGATIVOS não vão para IfcDuration: o validador do IfcOpenShell aceita até ``"abc"`` nesse
  campo (aceite por omissão, não por regra), e o ISO 8601 não define duração negativa. Folga negativa →
  ``INFRA4D_Folgas`` na tarefa (TotalFloat/FreeFloat ficam vazios); lag negativo → ``INFRA4D_LagsNegativos``
  na tarefa sucessora (IfcRelSequence sem TimeLag; relação não aceita Pset).
- Restrições SNET/FNLT não têm campo no IFC → ``INFRA4D_Restricoes`` (IfcDate).

As datas e sequências são criadas DIRETO nas entidades: ``ifcopenshell.api.sequence.edit_task_time`` e
``assign_sequence`` recalculam datas por um calendário padrão próprio e fazem cascata (R07 §3).

Importação (``ler``): devolve ``(atividades, relacoes, calendarios, metadados)`` — a MESMA forma de
``importadores.importar_mspdi`` — prontos para ``motor.calcular``.
"""

from __future__ import annotations

from datetime import date, timedelta

import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.util.element

from ..calendario import Calendario, ordinal
from ..motor import AtividadeCPM, Relacao

SEQ = {"FS": "FINISH_START", "SS": "START_START", "FF": "FINISH_FINISH", "SF": "START_FINISH"}
SEQ_INV = {v: k for k, v in SEQ.items()}
TIPO_CRONOGRAMA = {"linha_base": ("BASELINE", None), "construtora": ("PLANNED", None),
                   "independente": ("USERDEFINED", "INDEPENDENTE"), "simulado": ("USERDEFINED", "SIMULADO")}
PSET_RESTRICOES = "INFRA4D_Restricoes"
PSET_FOLGAS = "INFRA4D_Folgas"
PSET_LAGS = "INFRA4D_LagsNegativos"


class ErroCronograma(ValueError):
    """O IFC não traz um cronograma legível para o motor."""


# ---------------------------------------------------------------------------- utilidades

def _dt(o: int | None) -> str | None:
    return None if o is None else f"{date.fromordinal(o).isoformat()}T00:00:00"


def _dt_iso(texto: str | None) -> str | None:
    return None if not texto else f"{texto[:10]}T00:00:00"


def _dur(n: int) -> str:
    if n < 0:
        raise ValueError("duração negativa não vai para IfcDuration (ver docstring)")
    return f"P{int(n)}D"


def _dias(texto: str) -> int:
    t = str(texto).strip().upper()
    if not (t.startswith("P") and t.endswith("D")) or "T" in t:
        raise ErroCronograma(f"duração fora da convenção P{{n}}D (dias úteis): {texto!r}")
    try:
        return int(t[1:-1])
    except ValueError:
        raise ErroCronograma(f"duração fora da convenção P{{n}}D (dias úteis): {texto!r}") from None


def _ord(texto, contexto: str = "data") -> int | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(str(texto)[:10]).toordinal()
    except ValueError:
        raise ErroCronograma(f"{contexto}: data ilegível {texto!r} (esperado AAAA-MM-DD[Thh:mm:ss])") from None


def _faixas(datas) -> list[tuple[date, date]]:
    out: list[list[date]] = []
    for d in sorted(datas):
        if out and d == out[-1][1] + timedelta(days=1):
            out[-1][1] = d
        else:
            out.append([d, d])
    return [(a, b) for a, b in out]


def _pset(f, obj, nome: str, props: dict) -> None:
    valores = []
    for k, (tipo, v) in props.items():
        valores.append(f.create_entity("IfcPropertySingleValue", Name=k, NominalValue=f.create_entity(tipo, v)))
    ps = f.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name=nome, HasProperties=valores)
    f.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[obj],
                    RelatingPropertyDefinition=ps)


# ---------------------------------------------------------------------------- exportação

def _calendarios(f, calendarios: dict[str, Calendario]) -> dict:
    out = {}
    for cid, c in calendarios.items():
        pat = f.create_entity("IfcRecurrencePattern", RecurrenceType="WEEKLY",
                              WeekdayComponent=sorted(d + 1 for d in c.dias_semana))  # IFC: 1 = segunda
        semana = f.create_entity("IfcWorkTime", Name="dias úteis da semana", RecurrencePattern=pat)
        excecoes = [f.create_entity("IfcWorkTime", Name="não útil", StartDate=a.isoformat(), FinishDate=b.isoformat())
                    for a, b in _faixas(c.nao_uteis)]
        out[cid] = f.create_entity("IfcWorkCalendar", GlobalId=ifcopenshell.guid.new(), Name=c.nome,
                                   Identification=cid, WorkingTimes=[semana], ExceptionTimes=excecoes or None,
                                   PredefinedType="NOTDEFINED")
    return out


def adicionar(f, projeto, cenarios: list[str], elementos_por_atividade: dict[str, list],
              ajustes: list | None = None, guid=None) -> dict:
    """Grava os cronogramas dos ``cenarios`` no arquivo ``f``. ``simulado`` só entra com ``ajustes``.
    ``guid(chave) -> GlobalId`` torna os GlobalIds das tarefas estáveis entre exportações.
    Devolve um resumo com contagens."""
    guid = guid or (lambda _chave: ifcopenshell.guid.new())
    from ..cenarios import executar, montar_entrada

    cenarios = [c for c in cenarios if c != "simulado" or ajustes]
    for c in cenarios:
        if c not in TIPO_CRONOGRAMA:
            raise ErroCronograma(f"cenário desconhecido: {c}")
    proj_ifc = f.by_type("IfcProject")[0]
    plano = f.create_entity("IfcWorkPlan", GlobalId=ifcopenshell.guid.new(), Name="INFRA 4D (dados fictícios)",
                            CreationDate=_dt(projeto.data_status), StartTime=_dt(projeto.inicio_projeto),
                            PredefinedType="PLANNED")
    f.create_entity("IfcRelDeclares", GlobalId=ifcopenshell.guid.new(), RelatingContext=proj_ifc,
                    RelatedDefinitions=[plano])
    cals = _calendarios(f, projeto.calendarios)
    tarefas_por_atividade: dict[str, list] = {}
    n_tarefas = n_seq = n_neg = 0
    cronogramas = []
    for cen in cenarios:
        aj = ajustes if cen == "simulado" else None
        ativs, rels, _mem = montar_entrada(projeto, cen, aj)
        res = executar(projeto, cen, aj)
        pt, ot = TIPO_CRONOGRAMA[cen]
        ds = None if cen == "linha_base" else projeto.data_status
        cron = f.create_entity("IfcWorkSchedule", GlobalId=guid(f"cronograma/{cen}"), Name=f"Cenário {cen}",
                               Identification=cen, ObjectType=ot, PredefinedType=pt,
                               CreationDate=_dt(ds if ds is not None else projeto.inicio_projeto),
                               StartTime=_dt(projeto.inicio_projeto), FinishTime=_dt_iso(res["termino"]))
        f.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=plano,
                        RelatedObjects=[cron])
        cronogramas.append(cron)
        tarefas, por_cal = {}, {}
        for a in ativs:
            ra = res["atividades"][a.id]
            dados_a = projeto.atividades.get(a.id, {})
            andamento = a.status == "em_andamento"
            completion = None
            if dados_a.get("quantidade_total"):
                q = float(dados_a.get("quantidade_executada", 0.0)) / float(dados_a["quantidade_total"])
                completion = min(q, 1.0) if q > 0 else None  # IfcPositiveRatioMeasure: > 0
            elif a.status == "concluida":
                completion = 1.0
            ft, fl = ra.get("folga_total"), ra.get("folga_livre")
            cal = projeto.calendarios[a.calendario]
            # R13-3: em andamento também leva ScheduleDuration = dias úteis de início a término do cenário
            # (leitores que só olham ScheduleDuration, como a cascata do Bonsai, veriam 0). O nosso `ler`
            # continua tirando a duração REMANESCENTE de RemainingTime: a ida e volta não muda.
            dur_total = cal.dias_uteis_entre(ordinal(ra["inicio"]), ordinal(ra["termino"]) + 1) if andamento else None
            # concluída: duração 0 no motor (ScheduleDuration P0D, que o `ler` usa); a duração REAL vai em
            # ActualDuration = dias úteis entre início e término reais
            dur_real = (cal.dias_uteis_entre(a.inicio_real, a.termino_real + 1)
                        if a.status == "concluida" and a.inicio_real and a.termino_real else None)
            tt = f.create_entity(
                "IfcTaskTime", DurationType="WORKTIME",
                ScheduleDuration=_dur(dur_total) if andamento else _dur(a.duracao),
                RemainingTime=_dur(a.duracao) if andamento else None,
                ActualDuration=_dur(dur_real) if dur_real is not None and dur_real >= 0 else None,
                ScheduleStart=_dt_iso(ra["inicio"]), ScheduleFinish=_dt_iso(ra["termino"]),
                EarlyStart=_dt_iso(ra.get("es")), EarlyFinish=_dt_iso(ra.get("ef")),
                LateStart=_dt_iso(ra.get("ls")), LateFinish=_dt_iso(ra.get("lf")),
                TotalFloat=_dur(ft) if ft is not None and ft >= 0 else None,
                FreeFloat=_dur(fl) if fl is not None and fl >= 0 else None,
                IsCritical=bool(ra.get("critica")), StatusTime=_dt(ds),
                ActualStart=_dt(a.inicio_real), ActualFinish=_dt(a.termino_real), Completion=completion)
            t = f.create_entity("IfcTask", GlobalId=guid(f"tarefa/{cen}/{a.id}"),
                                Name=dados_a.get("nome", a.id), Identification=a.id, ObjectType=a.tipo,
                                Status=a.status, IsMilestone=a.tipo.startswith("marco"), TaskTime=tt,
                                PredefinedType="CONSTRUCTION")
            if (ft is not None and ft < 0) or (fl is not None and fl < 0):
                _pset(f, t, PSET_FOLGAS, {k: ("IfcInteger", int(v)) for k, v in
                                          (("FolgaTotal", ft), ("FolgaLivre", fl)) if v is not None})
                n_neg += 1
            if a.restricao_inicio or a.restricao_termino:
                _pset(f, t, PSET_RESTRICOES, {k: ("IfcDate", date.fromordinal(o).isoformat()) for k, o in
                                              (("InicioNaoAntesDe", a.restricao_inicio),
                                               ("TerminoNaoDepoisDe", a.restricao_termino)) if o})
            tarefas[a.id] = t
            por_cal.setdefault(a.calendario, []).append(t)
            tarefas_por_atividade.setdefault(a.id, []).append(t)
        f.create_entity("IfcRelAssignsToControl", GlobalId=ifcopenshell.guid.new(),
                        RelatedObjects=list(tarefas.values()), RelatingControl=cron)
        for cid, ts in por_cal.items():
            f.create_entity("IfcRelAssignsToControl", GlobalId=ifcopenshell.guid.new(), RelatedObjects=ts,
                            RelatingControl=cals[cid])
        negativos: dict[str, dict] = {}
        for r in rels:
            lag = None
            if r.lag > 0:
                lag = f.create_entity("IfcLagTime", LagValue=f.create_entity("IfcDuration", _dur(r.lag)),
                                      DurationType="WORKTIME")
            elif r.lag < 0:
                negativos.setdefault(r.sucessora, {})[f"{r.predecessora}|{r.tipo}"] = ("IfcInteger", int(r.lag))
            f.create_entity("IfcRelSequence", GlobalId=ifcopenshell.guid.new(),
                            RelatingProcess=tarefas[r.predecessora], RelatedProcess=tarefas[r.sucessora],
                            TimeLag=lag, SequenceType=SEQ[r.tipo])
            n_seq += 1
        for suc, props in negativos.items():
            _pset(f, tarefas[suc], PSET_LAGS, props)
            n_neg += 1
        n_tarefas += len(tarefas)
    for aid, els in elementos_por_atividade.items():
        ts = tarefas_por_atividade.get(aid)
        if not ts:
            continue
        for el in els:
            f.create_entity("IfcRelAssignsToProduct", GlobalId=ifcopenshell.guid.new(), RelatedObjects=ts,
                            RelatingProduct=el)
    return {"cenarios": cenarios, "tarefas": n_tarefas, "sequencias": n_seq,
            "calendarios": len(cals), "registros_negativos_em_pset": n_neg}


# ---------------------------------------------------------------------------- importação

def cenarios_no_arquivo(f) -> list[str]:
    return [c.Identification for c in f.by_type("IfcWorkSchedule") if c.Identification]


def _calendario_ifc(wc) -> Calendario:
    nome = wc.Identification or wc.Name or f"#{wc.id()}"
    semana = [wt for wt in (wc.WorkingTimes or ()) if wt.RecurrencePattern is not None]
    if not semana or semana[0].RecurrencePattern.RecurrenceType != "WEEKLY":
        raise ErroCronograma(f"calendário {nome}: sem padrão semanal (WEEKLY) de dias úteis")
    comp = semana[0].RecurrencePattern.WeekdayComponent
    if not comp or any(not (1 <= d <= 7) for d in comp):
        raise ErroCronograma(f"calendário {nome}: padrão WEEKLY sem WeekdayComponent válido (1 = segunda … 7 = domingo)")
    dias = tuple(sorted(d - 1 for d in comp))
    nao = set()
    for wt in wc.ExceptionTimes or ():
        if wt.RecurrencePattern is not None or not wt.StartDate:
            raise ErroCronograma(f"calendário {nome}: exceção {wt.Name or '#' + str(wt.id())} sem StartDate "
                                 "(exceção só por recorrência não é suportada)")
        a = date.fromordinal(_ord(wt.StartDate, f"calendário {nome}, exceção"))
        b = date.fromordinal(_ord(wt.FinishDate or wt.StartDate, f"calendário {nome}, exceção"))
        if b < a or (b - a).days > 3660:
            raise ErroCronograma(f"calendário {nome}: exceção de {a} a {b} inválida (invertida ou > 10 anos)")
        while a <= b:
            nao.add(a)
            a += timedelta(days=1)
    cid = nome
    return Calendario(id=cid, nome=wc.Name or cid, dias_semana=dias, nao_uteis=frozenset(nao))


def ler(f, cenario: str):
    """IFC → ``(atividades, relacoes, calendarios, metadados)`` do cronograma ``cenario``."""
    cron = next((c for c in f.by_type("IfcWorkSchedule") if c.Identification == cenario), None)
    if cron is None:
        raise ErroCronograma(f"o arquivo não tem IfcWorkSchedule do cenário {cenario!r} "
                             f"(tem: {cenarios_no_arquivo(f)})")
    if not cron.StartTime:
        raise ErroCronograma(f"cronograma {cenario}: sem StartTime (início do projeto)")
    tarefas = [t for rel in (cron.Controls or ()) if rel.is_a("IfcRelAssignsToControl")
               for t in rel.RelatedObjects if t.is_a("IfcTask")]
    if not tarefas:
        raise ErroCronograma(f"cronograma {cenario}: nenhuma IfcTask atribuída (IfcRelAssignsToControl)")
    vistos: set[str] = set()
    for t in tarefas:
        if not t.Identification:
            raise ErroCronograma(f"tarefa #{t.id()} ({t.Name!r}) sem Identification (id da atividade)")
        if t.Identification in vistos:
            raise ErroCronograma(f"duas tarefas com a mesma Identification {t.Identification!r}")
        vistos.add(t.Identification)
        if t.TaskTime is None:
            raise ErroCronograma(f"tarefa {t.Identification}: sem IfcTaskTime")
    avisos: list[str] = []
    cals: dict[str, Calendario] = {}
    cal_de: dict[str, str] = {}
    ativs = []
    for t in tarefas:
        wc = next((rel.RelatingControl for rel in t.HasAssignments if rel.is_a("IfcRelAssignsToControl")
                   and rel.RelatingControl.is_a("IfcWorkCalendar")), None)
        if wc is None:
            raise ErroCronograma(f"tarefa {t.Identification}: sem IfcWorkCalendar")
        c = _calendario_ifc(wc)
        cals.setdefault(c.id, c)
        cal_de[t.Identification] = c.id
        tt = t.TaskTime
        texto = tt.RemainingTime if t.Status == "em_andamento" else tt.ScheduleDuration
        if texto is None:
            raise ErroCronograma(f"tarefa {t.Identification}: sem duração")
        rest = ifcopenshell.util.element.get_pset(t, PSET_RESTRICOES) or {}
        if tt.DurationType == "ELAPSEDTIME":
            avisos.append(f"tarefa {t.Identification}: duração em ELAPSEDTIME (dias corridos) lida como dias úteis")
        ctx = f"tarefa {t.Identification}"
        ativs.append(AtividadeCPM(id=t.Identification, duracao=_dias(texto), calendario=c.id,
                                  tipo=t.ObjectType or ("marco_termino" if t.IsMilestone else "tarefa"),
                                  status=t.Status or "nao_iniciada",
                                  inicio_real=_ord(tt.ActualStart, ctx), termino_real=_ord(tt.ActualFinish, ctx),
                                  restricao_inicio=_ord(rest.get("InicioNaoAntesDe"), ctx),
                                  restricao_termino=_ord(rest.get("TerminoNaoDepoisDe"), ctx)))
    ids = {t.id() for t in tarefas}
    neg = {t.Identification: ifcopenshell.util.element.get_pset(t, PSET_LAGS) or {} for t in tarefas}
    rels = []
    for rs in f.by_type("IfcRelSequence"):
        if rs.RelatingProcess.id() not in ids:
            continue
        if rs.RelatedProcess.id() not in ids:
            raise ErroCronograma(f"relação {rs.RelatingProcess.Identification}→{rs.RelatedProcess.Identification}: "
                                 "sucessora fora do cronograma deste cenário")
        pre, suc = rs.RelatingProcess.Identification, rs.RelatedProcess.Identification
        if rs.SequenceType not in SEQ_INV:
            raise ErroCronograma(f"relação {pre}→{suc}: SequenceType {rs.SequenceType!r} não suportado "
                                 f"(aceitos: {', '.join(SEQ_INV)})")
        tipo = SEQ_INV[rs.SequenceType]
        if rs.TimeLag is not None:
            lv = rs.TimeLag.LagValue
            if lv is None or not lv.is_a("IfcDuration"):
                raise ErroCronograma(f"relação {pre}→{suc}: lag que não é IfcDuration "
                                     f"({lv.is_a() if lv is not None else 'vazio'}) não é suportado")
            lag = _dias(lv.wrappedValue)
            if rs.TimeLag.DurationType == "ELAPSEDTIME":
                avisos.append(f"relação {pre}→{suc}: lag em ELAPSEDTIME (dias corridos) lido como dias úteis")
        else:
            lag = int(neg[suc].get(f"{pre}|{tipo}", 0))
        rels.append(Relacao(pre, suc, tipo, lag))
    status = {tt for tt in (t.TaskTime.StatusTime for t in tarefas) if tt}
    if len(status) > 1:
        raise ErroCronograma(f"cronograma {cenario}: mais de uma data de status ({sorted(status)})")
    return ativs, rels, cals, {"inicio_projeto": _ord(cron.StartTime, f"cronograma {cenario}, StartTime"),
                               "data_status": _ord(next(iter(status)), "StatusTime") if status else None,
                               "nomes": {t.Identification: t.Name for t in tarefas}, "cenario": cenario,
                               "avisos": avisos}


def datas_gravadas(f, cenario: str) -> dict[str, dict]:
    """{atividade: datas/folgas/criticidade gravadas no IfcTaskTime} — para conferir contra a API."""
    cron = next(c for c in f.by_type("IfcWorkSchedule") if c.Identification == cenario)
    out = {}
    for rel in cron.Controls or ():
        for t in rel.RelatedObjects:
            if not t.is_a("IfcTask"):
                continue
            tt = t.TaskTime
            folgas = ifcopenshell.util.element.get_pset(t, PSET_FOLGAS) or {}
            out[t.Identification] = {
                "inicio": (tt.ScheduleStart or "")[:10] or None, "termino": (tt.ScheduleFinish or "")[:10] or None,
                "es": (tt.EarlyStart or "")[:10] or None, "ef": (tt.EarlyFinish or "")[:10] or None,
                "ls": (tt.LateStart or "")[:10] or None, "lf": (tt.LateFinish or "")[:10] or None,
                "folga_total": folgas.get("FolgaTotal", _dias(tt.TotalFloat) if tt.TotalFloat else None),
                "folga_livre": folgas.get("FolgaLivre", _dias(tt.FreeFloat) if tt.FreeFloat else None),
                "critica": bool(tt.IsCritical)}
    return out


__all__ = ["adicionar", "ler", "datas_gravadas", "cenarios_no_arquivo", "ErroCronograma"]
