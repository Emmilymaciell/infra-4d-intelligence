# R13 — Anexo: rascunho de issue para o IfcOpenShell (NÃO PUBLICADO)

> **Status: rascunho para decisão da titular.** Nada foi enviado. Publicar é ação externa, e só a Emmily decide.
> O texto abaixo está em inglês (idioma do rastreador do projeto) e **não contém dado do projeto nem identificação
> pessoal**. O repro usa só o ifcopenshell, com uma data genérica.
> Origem: `docs/research/R13-interoperabilidade-4d.md` §2.1. O repro e a correção foram executados em 2026-11-13 no
> `.venv` do projeto, e as saídas abaixo são as reais.
> Antes de enviar: procurar se já existe issue igual em https://github.com/IfcOpenShell/IfcOpenShell/issues (não
> verificado) e conferir se o código mudou depois da v0.9.0.

---

**Title:** `util.sequence.is_day_in_work_time`: Finish check overwrites Start check (and both are exclusive), so a dated
ExceptionTime makes every earlier day non-working

**Version:** ifcopenshell 0.9.0.post1 (PyPI wheel), Python 3.13.9, Windows 11. Same code in tag `v0.8.0`.

**File:** `src/ifcopenshell-python/ifcopenshell/util/sequence.py`, `is_day_in_work_time`:

```python
if start := work_time[4]:
    start = ifcopenshell.util.date.ifc2datetime(start)
    if day > start:
        is_day_in_work_time = True
    else:
        is_day_in_work_time = False
if finish := work_time[5]:
    finish = ifcopenshell.util.date.ifc2datetime(finish)
    if day < finish:
        is_day_in_work_time = True
    else:
        is_day_in_work_time = False
```

Two problems:
1. When both StartDate and FinishDate are set, the finish branch **overwrites** the start result. Any day before
   FinishDate is "in" the work time, even long before StartDate.
2. Both comparisons are **exclusive**, but IfcWorkTime says that a non-recurring period "begins at 0:00 on the start
   date and ends at 24:00 on the finish date" (IFC 4.3, IfcWorkTime). So a one-day period (Start = Finish) never
   contains its own day.

Combined effect: a Mon–Fri calendar with a single holiday ExceptionTime (2026-12-25) reports every weekday **before**
the holiday as non-working, and the holiday itself as working. `count_working_days`, `offset_date`,
`cascade_schedule` and `recalculate_schedule` inherit this.

**Minimal repro (only ifcopenshell):**

```python
import datetime, ifcopenshell, ifcopenshell.guid, ifcopenshell.util.sequence as seq

f = ifcopenshell.file(schema="IFC4X3_ADD2")
week = f.createIfcWorkTime(Name="Mon-Fri", RecurrencePattern=f.createIfcRecurrencePattern(
    RecurrenceType="WEEKLY", WeekdayComponent=[1, 2, 3, 4, 5]))
holiday = f.createIfcWorkTime(Name="Holiday", StartDate="2026-12-25", FinishDate="2026-12-25")
cal = f.createIfcWorkCalendar(GlobalId=ifcopenshell.guid.new(), Name="Cal",
                              WorkingTimes=[week], ExceptionTimes=[holiday])

for d in range(21, 30):
    day = datetime.date(2026, 12, d)
    print(day, day.strftime("%a"), seq.is_working_day(day, cal))
print("ifcopenshell", ifcopenshell.version)
```

**Observed (actual output):**

```
2026-12-21 Mon False
2026-12-22 Tue False
2026-12-23 Wed False
2026-12-24 Thu False
2026-12-25 Fri True
2026-12-26 Sat False
2026-12-27 Sun False
2026-12-28 Mon True
2026-12-29 Tue True
ifcopenshell 0.9.0.post1
```

**Expected:** Mon 21 – Thu 24 = True (working), Fri 25 = False (holiday), Sat/Sun = False, Mon 28 – Tue 29 = True.

**Spec reference (IFC 4.3, IfcWorkTime):** "Non-recurring time periods should have a start date (IfcWorkTime.Start) and a
finish date (IfcWorkTime.Finish). In that case it is assumed that the time period begins at 0:00 on the start date and
ends at 24:00 on the finish date." — https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/lexical/IfcWorkTime.htm
(source: https://github.com/buildingSMART/IFC4.x-development/blob/master/docs/schemas/resource/IfcDateTimeResource/Entities/IfcWorkTime.md)

**Suggested fix (inclusive bounds, no overwrite):**

```python
def is_day_in_work_time(day, work_time) -> bool:
    if isinstance(day, datetime.datetime):
        day = day.date()
    if work_time[4] and day < ifcopenshell.util.date.ifc2datetime(work_time[4]):  # StartDate (0:00)
        return False
    if work_time[5] and day > ifcopenshell.util.date.ifc2datetime(work_time[5]):  # FinishDate (24:00)
        return False
    return True
```

With this function patched in (and `is_working_day.cache_clear()` / `is_calendar_applicable.cache_clear()`), the same
repro prints:

```
2026-12-21 Mon True
2026-12-22 Tue True
2026-12-23 Wed True
2026-12-24 Thu True
2026-12-25 Fri False
2026-12-26 Sat False
2026-12-27 Sun False
2026-12-28 Mon True
2026-12-29 Tue True
ifcopenshell 0.9.0.post1
```

Note: `is_calendar_applicable` also calls `is_day_in_work_time` for WorkingTimes with Start/Finish bounds, so bounded
working periods are affected the same way. Separately, WEEKLY/DAILY recurrences with `Interval` or `Occurrences` set
return `False  # TODO`. That is a known limitation, not part of this report.

---

## Notas internas (não enviar)

- Os dois scripts (repro e verificação da correção) ficaram no scratchpad da sessão, fora do repositório.
- Se a titular aprovar o envio, quem envia é ela, pela conta dela. A conta e o nome não entram neste arquivo.
- Se a issue for aceita, revisar R13 §2.1 e o passo 7 do teste manual no Bonsai.
