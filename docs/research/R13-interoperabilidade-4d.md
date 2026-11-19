# R13 — Interoperabilidade do cronograma 4D no IFC (Bonsai, SYNCHRO, Navisworks, Solibri, Trimble Connect)

> Data: **2026-11-13**. Convenção: **[V]** = visto nesta rodada em fonte primária (especificação da buildingSMART ou
> código-fonte do IfcOpenShell/Bonsai na tag `v0.9.0`, URL citada); **[X]** = **executado e observado** nesta
> máquina (ifcopenshell 0.9.0.post1 do `.venv`, script descartável no scratchpad, nada gravado no repositório);
> **[B]** = só resumo de busca ou fórum; **[I]** = inferência minha a partir do código, ainda não testada no
> programa; **[NV]** = não verificado.
> Objeto: o cronograma que `scripts/infra4d/ifc/cronograma.py` grava no IFC:
> - IfcWorkPlan → IfcWorkSchedule por cenário → IfcTask (IfcRelAssignsToControl);
> - IfcTaskTime com `DurationType=WORKTIME`, `ScheduleDuration="P{n}D"`, Schedule/Early/Late*;
> - IfcRelSequence + IfcLagTime WORKTIME;
> - IfcWorkCalendar com IfcRecurrencePattern WEEKLY e `ExceptionTimes` em faixas `StartDate..FinishDate`;
> - IfcRelAssignsToProduct peça → tarefas.

## Resumo

1. **Especificação (IFC 4.3):**
   - WORKTIME = "based on work time (calendar-dependent)"; ELAPSEDTIME = "24 hours per day, independent of
     calendar" [V];
   - um IfcWorkTime **sem** recorrência vai "de 0:00 da data de início a 24:00 da data de término", ou seja, as duas
     pontas são **inclusivas** [V];
   - exceções substituem os períodos de trabalho [V].

   O nosso arquivo segue isso.
2. **Bonsai / IfcOpenShell 0.9.0 lê o nosso cronograma:**
   - acha as tarefas pelo `IfcRelAssignsToControl` do IfcWorkSchedule [V];
   - acha o calendário pelo `IfcRelAssignsToControl` com IfcWorkCalendar [V];
   - liga tarefa → elemento pelo `IfcRelAssignsToProduct` [V];
   - mostra **as datas gravadas** (ScheduleStart/Finish/Duration) sem recalcular ao abrir [V];
   - a animação 4D usa essas datas [V].
3. **DEFEITO NO IFCOPENSHELL 0.9.0, observado [X]:** `util.sequence.is_day_in_work_time` compara `dia > início` e
   depois **sobrescreve** com `dia < término`. Na prática, uma exceção datada `A..B` torna **não úteis TODOS os dias
   anteriores a B** e deixa úteis os dias A e B.
   - Com um único feriado em 25/12/2026 no calendário, a quinta-feira 24/12 sai "não útil" [X].
   - O mesmo código está nas tags v0.8.0 e no ramo antigo `master` [V].
   - **Consequência [I]:** tudo o que o Bonsai CALCULA pelo calendário fica errado com as nossas exceções (e com
     qualquer exceção datada): duração derivada de tarefa-resumo, cascata ("cascade") ao editar e
     `recalculate_schedule`.
   - O que só EXIBE as datas gravadas continua certo: lista de tarefas, Gantt e animação 4D.
4. **Ponta de faixa:** mesmo sem esse defeito, as comparações estritas (`>`/`<`) excluiriam o 1º e o último dia de
   cada exceção, contra o "0:00 → 24:00" da especificação [V]. Feriados de um dia (Start = Finish) seriam ignorados
   [I].
5. **Atividade em andamento:** gravamos `RemainingTime` e deixamos `ScheduleDuration` vazio. A cascata do Bonsai lê
   só `ScheduleDuration` e trataria a duração como 0 [V no código; efeito no programa I].
6. **Lag:** o nosso motor conta o lag no calendário da **predecessora** (ADR-0003). A cascata do Bonsai calcula pelos
   calendários da sucessora **e** da predecessora e considera os dois [V]. Com calendários mistos, pode divergir [I].
7. **SYNCHRO 4D, Navisworks TimeLiner, Solibri, Trimble Connect:** nenhuma documentação oficial aberta diz que eles
   **importam** IfcTask/IfcTaskTime/IfcWorkCalendar de IFC4/4.3 [NV].
   - Relatos: o TimeLiner ficou vazio ao abrir um IFC4 com 4D [B]; o SYNCHRO exporta IFC com IFCTASK +
     IFCRELASSIGNSTASK, entidade do IFC2x3 [B]; a página do SYNCHRO 4D lista importação de IFC até a versão 4, sem
     4.3 (R08) [V].
   - Para eles, o caminho seguro continua sendo o **MSPDI** (que já exportamos) e o IFC só para geometria.

## 1. O que a especificação diz (IFC 4.3, fonte: repositório oficial `buildingSMART/IFC4.x-development`)

| Conceito | Texto (resumo fiel) | Fonte | Nosso arquivo |
|---|---|---|---|
| IfcTaskDurationEnum | ELAPSEDTIME: "based on elapsed time (24 hours per day, independent of calendar)"; WORKTIME: "based on work time (calendar-dependent)" | https://github.com/buildingSMART/IFC4.x-development/blob/master/docs/schemas/resource/IfcDateTimeResource/Types/IfcTaskDurationEnum.md | WORKTIME em IfcTaskTime e IfcLagTime ✓ |
| IfcWorkTime | "Non-recurring time periods should have a start date … and a finish date … it is assumed that the time period begins at 0:00 on the start date and ends at 24:00 on the finish date"; com recorrência, Start/Finish são opcionais e só limitam | …/Entities/IfcWorkTime.md | exceções `StartDate..FinishDate` inclusivas ✓; semana com WEEKLY sem datas ✓ |
| IfcRecurrencePattern | WEEKLY usa WeekdayComponent; "An empty interval value is regarded as 1" | …/Entities/IfcRecurrencePattern.md | WEEKLY, 1 = segunda, Interval vazio ✓ |
| IfcWorkCalendar | ExceptionTimes "define exceptions (non-working times)", que se sobrepõem aos períodos de trabalho; o calendário de tarefa é ligado por IfcRelAssignsToControl | https://github.com/buildingSMART/IFC4.x-development/blob/master/docs/schemas/core/IfcProcessExtension/Entities/IfcWorkCalendar.md | IfcRelAssignsToControl tarefa → calendário ✓ |
| IfcLagTime | LagValue é razão ou duração; DurationType diz se é work time ou elapsed time | …/Entities/IfcLagTime.md | IfcDuration + WORKTIME ✓ (lag negativo vai para Pset, R07) |
| MVD de referência | Nenhuma MVD consultada nesta rodada exige cronograma | — | [NV] |

## 2. Bonsai (BlenderBIM) — leitura do código da tag `v0.9.0`

Arquivos lidos:
- `src/ifcopenshell-python/ifcopenshell/util/sequence.py`
- `src/ifcopenshell-python/ifcopenshell/api/sequence/cascade_schedule.py`
- `src/ifcopenshell-python/ifcopenshell/api/sequence/recalculate_schedule.py`
- `src/bonsai/bonsai/tool/sequence.py`

Todos em https://github.com/IfcOpenShell/IfcOpenShell/tree/v0.9.0.

| Pergunta | Resposta | Evidência |
|---|---|---|
| Lê IfcTask? | **Sim.** Tarefas-raiz = `work_schedule.Controls` (IfcRelAssignsToControl) | `get_root_tasks` [V] |
| Usa IfcTaskTime ou recalcula? | **Usa o gravado** ao montar a lista: ScheduleStart/Finish/Duration vêm direto do IfcTaskTime. Recalcula só sob ação do usuário: editar com cascata, ou "recalculate schedule" (que exige `networkx`) | `bonsai/tool/sequence.py` (load da árvore de tarefas, l. ~311–333) [V]; `cascade_schedule`, `recalculate_schedule` [V] |
| 4D (animação) | Usa `derive_date(..., "ScheduleStart"/"ScheduleFinish")` e as **saídas** da tarefa via IfcRelAssignsToProduct, o que casa com o nosso vínculo peça → tarefa | `process_task_status`, `get_task_outputs` [V] |
| WORKTIME × ELAPSEDTIME | Respeita: ELAPSEDTIME ignora o calendário; WORKTIME anda só em dias úteis (`offset_date`, `get_soonest_working_day`) | `util/sequence.py` [V] |
| Duração `P{n}D` | Lida em dias; meses viram 30 dias e anos 360; o dia de início conta (fim = início + n − 1 dia útil, às 17:00). Bate com o nosso "ScheduleFinish = último dia trabalhado" | `get_start_or_finish_date` [V] |
| Calendário: semana WEEKLY | Funciona quando `Interval` e `Occurrences` estão vazios (o nosso caso); com Interval preenchido, o código retorna `False # TODO` | `is_work_time_applicable_to_day` [V] |
| Calendário: exceções datadas | **ERRADO** (ver §2.1) | [X] |
| Tarefa em andamento (`RemainingTime`, sem `ScheduleDuration`) | A cascata usa só `ScheduleDuration`; sem ele, duração 0 | `cascade_schedule` [V]; efeito [I] |
| Lag em calendários mistos | A cascata calcula com o calendário da sucessora e o da predecessora; o nosso motor usa o da predecessora | `cascade_schedule` [V]; divergência [I] |

### 2.1 Defeito observado em `is_day_in_work_time` [X]

Código (v0.9.0; idêntico na v0.8.0 e no ramo `master` antigo [V]):

```python
if start := work_time[4]:        # StartDate
    is_day_in_work_time = day > start          # estrito: exclui o próprio dia de início
if finish := work_time[5]:       # FinishDate
    is_day_in_work_time = day < finish         # SOBRESCREVE o resultado anterior e também é estrito
```

Execução nesta máquina (ifcopenshell 0.9.0.post1). Calendário seg–sáb (WEEKLY [1..6]) com duas exceções: feriado
25/12/2026..25/12/2026 e chuva 05/01/2027..07/01/2027. `util.sequence.is_working_day` respondeu:

| Dia | Esperado (especificação) | IfcOpenShell 0.9.0 |
|---|---|---|
| qui 24/12/2026 | útil | **não útil** |
| sex 25/12/2026 (feriado) | não útil | não útil (por causa da 2ª exceção) |
| sáb 26/12/2026 | útil | **não útil** |
| seg 04/01/2027 | útil | **não útil** |
| ter 05 a qua 06/01/2027 (chuva) | não útil | não útil |
| qui 07/01/2027 (chuva) | não útil | **útil** |
| sex 08/01/2027 | útil | útil |

Conclusão [X]: com exceções datadas, **todo dia anterior ao término da última exceção vira não útil**, e o próprio dia
de término volta a ser útil.

Efeitos:
- No Bonsai [I]: duração derivada de tarefas-resumo (`count_working_days`), cascata e recálculo produzem datas
  erradas para o nosso arquivo **e para qualquer IFC com feriados datados**.
- O que não é afetado [V/I]: as datas gravadas, porque a lista e o 4D só as leem.

Não achei issue aberta sobre isso [NV]. A busca não encontrou nada; o rastreador do GitHub não foi consultado
diretamente.

## 3. Outros programas

| Software | Lê IfcTask/IfcTaskTime de IFC4/4.3? | WORKTIME / calendário | Evidência |
|---|---|---|---|
| **SYNCHRO 4D** (Bentley) | **[NV]**. A página do produto lista importação de IFC 2x–4, sem 4.3 (R08 [V]). Um relato diz que a exportação IFC traz IFCTASK + IFCRELASSIGNSTASK, entidade do IFC2x3 [B]. Cronograma entra por MS Project XML/P6 (documentação de terceiros) [B] | [NV] | https://www.bentley.com/software/synchro/ (R08); https://speckle.community/t/4d-parameters-arent-visible-in-power-bi/8496 [B]; https://techsupport.sds2.com/main/Topics/synchro.htm [B] |
| **Navisworks TimeLiner** (Autodesk) | **[NV], provavelmente não nativo.** Um usuário relatou TimeLiner vazio ao abrir um IFC4 com 4D [B]; plug-in de terceiros para IFC2x3 em 2014 [B]. Fontes documentadas: CSV, MS Project, P6 [B] | [NV] | https://discourse.mcneel.com/t/creating-4d-information-in-gh-and-importing-them-into-navisworks/152453 [B]; https://geometrygym.blogspot.com/2013/10/navisworks-4d-ifc.html [B] |
| **Solibri** | **[NV].** A documentação cita suporte a IFC4 e "suporte inicial" a IFC 4.3 na v24.5.0, sem mencionar entidades de cronograma [B] | [NV] | https://help.solibri.com/hc/en-us/articles/23779405208855 [B] |
| **Trimble Connect** | **[NV].** O "Connect Planner" cria o 4D na própria ferramenta; o TILOS sincroniza tarefas com o Connect; relato de datas 1 dia antes na importação do TILOS [B] | [NV] | https://nordics.construsoft.com/blog/get-started-with-4d-construction-planning-with-trimble-connect-planner-e-learning [B]; https://community.trimble.com/question/tilos-trimble-connect-incorrect-imported-data [B] |
| **Bexel Manager** (citado na comunidade) | Relatos contraditórios: um diz que importa IfcTask mas perde o vínculo com os elementos; outro, que não reconheceu IfcWorkPlan/IfcWorkSchedule [B] | [NV] | https://community.osarch.org/discussion/1132/ [B] |

**Recomendação:**
- Para SYNCHRO e Navisworks, entregar o cronograma por **MSPDI** (`/api/cronograma/exportar/mspdi`, já existe) e o IFC
  só com geometria, mais o Pset de vínculo (`INFRA4D_Vinculo.AtividadeId`) para casar tarefa × elemento.
- Não alegar "4D em IFC compatível com X" sem o teste manual de cada programa.

## 4. Teste de aceitação manual no Bonsai (gratuito)

**Pré-requisitos:** Blender 4.x com o add-on Bonsai (https://bonsaibim.org/) e o IFC da obra exportado com
cronograma:

```powershell
.\run-beta.ps1
# no navegador: http://127.0.0.1:8765/api/ifc/exportar?obra=ferrovia   (salve como ferrovia.ifc)
```

Ao abrir **Bonsai → Scene properties → "Costing and Scheduling" → Work Schedules**:

| # | Passo | Critério de aceite (anote "passou/falhou" e a versão do Bonsai) |
|---|---|---|
| 1 | Abrir o IFC (File → Open IFC Project) | Abre sem erro; há 3 IfcWorkSchedule (linha de base, construtora, independente) |
| 2 | Expandir "independente" | A lista mostra as **113** tarefas da ferrovia (137 na rodovia), com Identification = id da atividade |
| 3 | Comparar a atividade **L3-S04-TER** com `GET /api/cenarios/independente` | Início e término **iguais** aos da API (ScheduleStart/Finish gravados); duração = `P{n}D` com o n da memória de cálculo |
| 4 | Selecionar a tarefa → Outputs | Lista as peças `L3-S04-TER-E01…` (vínculo IfcRelAssignsToProduct) |
| 5 | Animação 4D ("Visualise Work Schedule Date Range") na data de status 09/11/2026 | Peças concluídas/em execução/não iniciadas coerentes com a aba Modelo 3D/4D do INFRA 4D |
| 6 | Abrir o calendário da tarefa (painel "Work Calendars"; nome do painel não verificado nesta versão) | Mostra a semana seg–sáb e as exceções (feriados e chuva) |
| 7 | **Teste do defeito (§2.1):** numa tarefa de calendário com chuva, mudar a duração em 1 dia e deixar a cascata recalcular | **Esperado: FALHA.** O término recalculado vai ignorar dias úteis antes da última exceção. Registrar o resultado. Se passar, a versão do Bonsai corrigiu o defeito e esta nota precisa ser revista |
| 8 | Tarefa **em andamento** (status em_andamento), cascata ligada | Registrar se a duração vira 0 (esperado pela leitura do código, §2) |

Resultado esperado hoje: passos 1–6 passam (leitura e 4D pelas datas gravadas); 7 e 8 mostram os limites do
**cálculo** do Bonsai.

## 5. Recomendações

| # | Recomendação | Tipo |
|---|---|---|
| R13-1 | Documentar no exportador e no relatório: "as datas do IFC são as do motor INFRA 4D; programas que recalculam pelo calendário podem divergir". O Bonsai 0.9.0 diverge com exceções datadas (§2.1) | doc |
| R13-2 | Montar o relato do defeito para o IfcOpenShell: repro mínimo de 10 linhas (§2.1) e correção sugerida (`start <= dia <= finish`, sem sobrescrever) | decisão da titular: é publicação externa |
| R13-3 | Em andamento: gravar também `ScheduleDuration` (duração total original) além de `RemainingTime`, para programas que só leem ScheduleDuration. Checar antes se isso não muda a ida e volta do `ler_cronograma` | código (dono: bim-ifc) |
| R13-4 | Para SYNCHRO/Navisworks: MSPDI + IFC de geometria com `INFRA4D_Vinculo`; não alegar 4D IFC até o teste manual | posicionamento |
| R13-5 | Rodar o §4 numa versão do Bonsai posterior à 0.9.0 e registrar aqui | teste manual |

## Fontes

- IFC 4.3 (repositório oficial):
  - https://github.com/buildingSMART/IFC4.x-development/blob/master/docs/schemas/resource/IfcDateTimeResource/Types/IfcTaskDurationEnum.md
  - …/Entities/IfcWorkTime.md
  - …/Entities/IfcRecurrencePattern.md
  - …/Entities/IfcLagTime.md
  - https://github.com/buildingSMART/IFC4.x-development/blob/master/docs/schemas/core/IfcProcessExtension/Entities/IfcWorkCalendar.md
- IfcOpenShell/Bonsai v0.9.0:
  - https://github.com/IfcOpenShell/IfcOpenShell/blob/v0.9.0/src/ifcopenshell-python/ifcopenshell/util/sequence.py
  - …/api/sequence/cascade_schedule.py
  - …/api/sequence/recalculate_schedule.py
  - https://github.com/IfcOpenShell/IfcOpenShell/blob/v0.9.0/src/bonsai/bonsai/tool/sequence.py
- Fóruns e terceiros [B]: os listados na §3.
