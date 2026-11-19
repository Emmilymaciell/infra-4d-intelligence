"""MSPDI (Microsoft Project XML Data Interchange): exportar e importar.

Só biblioteca padrão (``xml.etree``). Especificação consultada (2026-11-12):
referência do schema MSPDI do Project 2007 (mspdi_pj12.xsd) em learn.microsoft.com:

- PredecessorLink: https://learn.microsoft.com/en-us/previous-versions/office/developer/office-2007/bb968712(v=office.12)
  (LinkLag em DÉCIMOS DE MINUTO, filhos PredecessorUID/Type/CrossProject/CrossProjectName/LinkLag/LagFormat);
- Type: https://learn.microsoft.com/en-us/previous-versions/office/developer/office-2007/bb968434(v=office.12)
  (PredecessorLink.Type 0=FF, 1=FS, 2=SF, 3=SS; Exception.Type 1=diária, 2=anual por dia do mês...);
- Exception: https://learn.microsoft.com/en-us/previous-versions/office/developer/office-2007/bb968492(v=office.12).

NÃO verificado em fonte primária (vem de memória e está declarado como limitação):
os valores de ConstraintType (4 = SNET), DayType (1 = domingo ... 7 = sábado),
LagFormat (7 = dias), os FieldID de Text1..Text5 e a ordem exata dos elementos
de Project/Task no XSD. O importador deste módulo lê os atributos estendidos
pelo ALIAS, não pelo FieldID, para não depender desse número.

Compatibilidade com o MS Project real NÃO é alegada (não temos o programa):
validado por ida e volta com o próprio exportador e por fixture sintética
escrita à mão (``examples/fixtures/mspdi_minimo.xml``).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from ..calendario import Calendario, ErroCalendario, HORIZONTE_FIM, HORIZONTE_INICIO, ordinal
from ..motor import AtividadeCPM, Relacao
import math
from xml.parsers import expat

from .comum import (MAXIMO_ATIVIDADES, MAXIMO_CALENDARIOS, MAXIMO_CALENDARIOS_ARQUIVO, MAXIMO_NIVEIS,
                    recortar_ao_horizonte)
from .comum import (LIMITACOES_COMUNS, Avisos, ErroImportacao, data_de_texto, datahora_de_texto,
                    dias_de_horas, lag_de_horas, no_horizonte)

NS = "http://schemas.microsoft.com/project"
MINUTOS_POR_DIA = 480  # exportação assume 8 h/dia
HORAS_POR_DIA = MINUTOS_POR_DIA / 60

TIPO_PARA_MSPDI = {"FF": 0, "FS": 1, "SF": 2, "SS": 3}  # verificado (bb968434)
MSPDI_PARA_TIPO = {v: k for k, v in TIPO_PARA_MSPDI.items()}
CONSTRAINT_SNET = 4  # não verificado em fonte primária
NOMES_CONSTRAINT = {0: "ASAP", 1: "ALAP", 2: "MSO", 3: "MFO", 4: "SNET", 5: "SNLT", 6: "FNET", 7: "FNLT"}
LAGFORMAT_DIAS = 7
LAGFORMAT_DECORRIDO = {4, 6, 8, 10, 12}  # em, eh, ed, ew, emo (não verificado)
LAGFORMAT_PERCENTUAL = {19, 20}  # %, e% (não verificado)

# Atributos estendidos: FieldID de Text1..Text5 (não verificado). O importador usa o ALIAS.
ATRIBUTOS = [
    ("188743731", "Text1", "INFRA4D id"),
    ("188743734", "Text2", "INFRA4D tipo"),
    ("188743737", "Text3", "INFRA4D servico"),
    ("188743740", "Text4", "INFRA4D lote"),
    ("188743743", "Text5", "INFRA4D memoria"),
]
_ALIAS_POR_CHAVE = {"id": "INFRA4D id", "tipo": "INFRA4D tipo", "servico": "INFRA4D servico",
                    "lote": "INFRA4D lote", "memoria": "INFRA4D memoria"}

LIMITACOES_MSPDI = LIMITACOES_COMUNS + [
    "MSPDI: tarefas de resumo (Summary=1), nulas, inativas e a tarefa UID 0 são ignoradas, assim como "
    "relações que as envolvem; links entre projetos (CrossProject) são ignorados.",
    "MSPDI: exceções de calendário suportadas: diária (Type 1, período 1) e anual por dia do mês (Type 2); "
    "outras recorrências são ignoradas com aviso. Calendários derivados herdam dias da semana e exceções "
    "do calendário-base.",
    "MSPDI: o MS Project não distingue marco de início e de término; sem o atributo 'INFRA4D tipo', marco "
    "com predecessoras é tratado como marco de término e sem predecessoras como marco de início.",
    "MSPDI: ConstraintType 4 (SNET) é o único tipo de restrição aplicado; os demais são ignorados com aviso.",
    "MSPDI: o arquivo NÃO carrega a lógica de progresso (sobrepor × lógica retida). Um MSPDI exportado de um "
    "resultado calculado com lógica retida é recalculado na importação com a política padrão (sobrepor / "
    "progress override): o término pode diferir do resultado de origem.",
    "MSPDI: DOCTYPE/ENTITY é recusado em qualquer codificação; tetos de volume (tarefas, calendários no "
    "arquivo e usados, níveis de herança) recusam o arquivo com mensagem clara; exceções de calendário são "
    "recortadas ao horizonte 2020–2040.",
]


# =============================================================================
# Exportação
# =============================================================================
def _dur(dias: int) -> str:
    return f"PT{int(dias) * int(HORAS_POR_DIA)}H0M0S"


def _dt(d: date | int | None, hora: str) -> str | None:
    if d is None:
        return None
    if isinstance(d, int):
        d = date.fromordinal(d)
    return f"{d.isoformat()}T{hora}"


def _sub(pai: ET.Element, tag: str, valor=None) -> ET.Element:
    el = ET.SubElement(pai, f"{{{NS}}}{tag}")
    if valor is not None:
        el.text = str(valor)
    return el


def _faixas(datas) -> list[tuple[date, date]]:
    """Agrupa datas consecutivas em faixas [de, até]."""
    faixas = []
    for d in sorted(datas):
        if faixas and d == faixas[-1][1] + timedelta(days=1):
            faixas[-1][1] = d
        else:
            faixas.append([d, d])
    return [(a, b) for a, b in faixas]


def _daytype(weekday_py: int) -> int:
    """Python 0=segunda..6=domingo → MSPDI DayType 1=domingo..7=sábado."""
    return (weekday_py + 1) % 7 + 1


def _texto_memoria(mem: dict) -> str:
    chaves = ("regra", "quantidade_total", "quantidade_executada", "quantidade_remanescente", "unidade",
              "produtividade", "fonte_produtividade", "equipes", "formula")
    return "; ".join(f"{k}={mem[k]}" for k in chaves if mem.get(k) not in (None, ""))


def exportar_mspdi(projeto, cenario_resultado: dict) -> str:
    """Gera MSPDI a partir do projeto (``cenarios.Projeto``) e do resultado de ``cenarios.executar``.

    Duração em PT#H0M0S com 8 h/dia. Não iniciada: duração total. Em andamento:
    ``ActualDuration`` (dias úteis do início real até a data de status) +
    ``RemainingDuration`` (a duração remanescente do cenário). Concluída: datas reais.
    """
    dados = projeto.dados
    meta = dados["meta"]
    ativs_res = cenario_resultado["atividades"]
    ds_txt = cenario_resultado.get("data_status")
    ds = ordinal(ds_txt) if ds_txt else None

    ET.register_namespace("", NS)
    raiz = ET.Element(f"{{{NS}}}Project")
    _sub(raiz, "SaveVersion", 14)
    _sub(raiz, "Name", f"infra4d-{cenario_resultado['cenario']}.xml")
    _sub(raiz, "Title", f"{dados.get('ferrovia', {}).get('nome', 'Projeto')} — cenário "
                        f"{cenario_resultado['cenario']} (DADOS FICTÍCIOS)")
    _sub(raiz, "ScheduleFromStart", 1)
    _sub(raiz, "StartDate", _dt(projeto.inicio_projeto, "08:00:00"))
    if cenario_resultado.get("termino"):
        _sub(raiz, "FinishDate", _dt(date.fromisoformat(cenario_resultado["termino"]), "17:00:00"))
    cal_uid = {cid: i + 1 for i, cid in enumerate(projeto.calendarios)}
    _sub(raiz, "CalendarUID", cal_uid.get(meta.get("calendario_obra"), 1))
    _sub(raiz, "DefaultStartTime", "08:00:00")
    _sub(raiz, "DefaultFinishTime", "17:00:00")
    _sub(raiz, "MinutesPerDay", MINUTOS_POR_DIA)
    _sub(raiz, "MinutesPerWeek", MINUTOS_POR_DIA * 5)
    _sub(raiz, "DaysPerMonth", 20)
    _sub(raiz, "DurationFormat", 7)
    if ds is not None:
        _sub(raiz, "CurrentDate", _dt(ds, "08:00:00"))
        _sub(raiz, "StatusDate", _dt(ds, "08:00:00"))

    eas = _sub(raiz, "ExtendedAttributes")
    for fid, fname, alias in ATRIBUTOS:
        ea = _sub(eas, "ExtendedAttribute")
        _sub(ea, "FieldID", fid)
        _sub(ea, "FieldName", fname)
        _sub(ea, "Alias", alias)

    # ------------------------------------------------------------ calendários
    cals = _sub(raiz, "Calendars")
    for cid, cal in projeto.calendarios.items():
        c = _sub(cals, "Calendar")
        _sub(c, "UID", cal_uid[cid])
        _sub(c, "Name", cid)
        _sub(c, "IsBaseCalendar", 1)
        _sub(c, "BaseCalendarUID", -1)
        wds = _sub(c, "WeekDays")
        for wd_py in (6, 0, 1, 2, 3, 4, 5):  # domingo..sábado
            w = _sub(wds, "WeekDay")
            _sub(w, "DayType", _daytype(wd_py))
            trabalha = wd_py in cal.dias_semana
            _sub(w, "DayWorking", 1 if trabalha else 0)
            if trabalha:
                wts = _sub(w, "WorkingTimes")
                for de, ate in (("08:00:00", "12:00:00"), ("13:00:00", "17:00:00")):
                    wt = _sub(wts, "WorkingTime")
                    _sub(wt, "FromTime", de)
                    _sub(wt, "ToTime", ate)
        if cal.nao_uteis:
            exs = _sub(c, "Exceptions")
            for de, ate in _faixas(cal.nao_uteis):
                ex = _sub(exs, "Exception")
                _sub(ex, "EnteredByOccurrences", 0)
                tp = _sub(ex, "TimePeriod")
                _sub(tp, "FromDate", _dt(de, "00:00:00"))
                _sub(tp, "ToDate", _dt(ate, "23:59:00"))
                _sub(ex, "Occurrences", (ate - de).days + 1)
                _sub(ex, "Name", "Não útil")
                _sub(ex, "Type", 1)
                _sub(ex, "DayWorking", 0)

    # ---------------------------------------------------------------- tarefas
    ordem = [a["id"] for a in dados["atividades"] if a["id"] in ativs_res]
    uid = {aid: i + 1 for i, aid in enumerate(ordem)}
    preds = {}
    for r in dados["relacoes"]:
        preds.setdefault(r["sucessora"], []).append(r)

    tarefas = _sub(raiz, "Tasks")
    for aid in ordem:
        a = projeto.atividades[aid]
        r = ativs_res[aid]
        cal = projeto.calendarios[a["calendario"]]
        tipo = a.get("tipo", "tarefa")
        status = r["status"]
        rem = int(r["duracao"])
        ini_real = ordinal(a.get("inicio_real")) if status != "nao_iniciada" else None
        fim_real = ordinal(a.get("termino_real")) if status == "concluida" else None
        if status == "concluida":
            atual = 0 if tipo != "tarefa" else cal.dias_uteis_entre(ini_real, fim_real + 1)
            total, rem = atual, 0
        elif status == "em_andamento":
            atual = cal.dias_uteis_entre(ini_real, ds) if ds is not None else 0
            total = atual + rem
        else:
            atual, total = 0, rem
        pct = 100 if status == "concluida" else (min(99, int(100 * atual / total)) if total else 0)

        t = _sub(tarefas, "Task")
        _sub(t, "UID", uid[aid])
        _sub(t, "ID", uid[aid])
        _sub(t, "Name", a.get("nome", aid))
        _sub(t, "Type", 1)  # duração fixa
        _sub(t, "IsNull", 0)
        _sub(t, "WBS", aid)
        _sub(t, "OutlineNumber", uid[aid])
        _sub(t, "OutlineLevel", 1)
        hora_ini = "17:00:00" if tipo == "marco_termino" else "08:00:00"
        _sub(t, "Start", _dt(date.fromisoformat(r["inicio"]), hora_ini))
        _sub(t, "Finish", _dt(date.fromisoformat(r["termino"]),
                              "08:00:00" if tipo == "marco_inicio" else "17:00:00"))
        _sub(t, "Duration", _dur(total))
        _sub(t, "DurationFormat", 7)
        _sub(t, "Milestone", 1 if tipo != "tarefa" else 0)
        _sub(t, "Summary", 0)
        _sub(t, "Critical", 1 if r.get("critica") else 0)
        if r.get("folga_livre") is not None:
            _sub(t, "FreeSlack", int(r["folga_livre"]) * MINUTOS_POR_DIA * 10)
        if r.get("folga_total") is not None:
            _sub(t, "TotalSlack", int(r["folga_total"]) * MINUTOS_POR_DIA * 10)
        _sub(t, "PercentComplete", pct)
        if ini_real is not None:
            _sub(t, "ActualStart", _dt(ini_real, "08:00:00"))
        if fim_real is not None:
            _sub(t, "ActualFinish", _dt(fim_real, "08:00:00" if tipo == "marco_inicio" else "17:00:00"))
        if status != "nao_iniciada":
            _sub(t, "ActualDuration", _dur(atual))
        _sub(t, "RemainingDuration", _dur(rem))
        if a.get("restricao_inicio"):
            _sub(t, "ConstraintType", CONSTRAINT_SNET)
        else:
            _sub(t, "ConstraintType", 0)
        _sub(t, "CalendarUID", cal_uid[a["calendario"]])
        if a.get("restricao_inicio"):
            _sub(t, "ConstraintDate", _dt(date.fromisoformat(a["restricao_inicio"]), "08:00:00"))
        mem = r.get("memoria") or {}
        nota = [f"INFRA4D {aid} — cenário {cenario_resultado['cenario']} (DADOS FICTÍCIOS)"]
        if a.get("servico_id") or a.get("lote_id"):
            nota.append(f"serviço={a.get('servico_id')}; lote={a.get('lote_id')}")
        if mem:
            nota.append(_texto_memoria(mem))
        _sub(t, "Notes", "\n".join(nota))
        for rel in preds.get(aid, []):
            pl = _sub(t, "PredecessorLink")
            _sub(pl, "PredecessorUID", uid[rel["predecessora"]])
            _sub(pl, "Type", TIPO_PARA_MSPDI[rel.get("tipo", "FS")])
            _sub(pl, "CrossProject", 0)
            _sub(pl, "LinkLag", int(rel.get("lag", 0)) * MINUTOS_POR_DIA * 10)
            _sub(pl, "LagFormat", LAGFORMAT_DIAS)
        valores = {"INFRA4D id": aid, "INFRA4D tipo": tipo, "INFRA4D servico": a.get("servico_id"),
                   "INFRA4D lote": a.get("lote_id"), "INFRA4D memoria": _texto_memoria(mem) if mem else None}
        for fid, _fname, alias in ATRIBUTOS:
            if valores.get(alias) not in (None, ""):
                ea = _sub(t, "ExtendedAttribute")
                _sub(ea, "FieldID", fid)
                _sub(ea, "Value", valores[alias])

    ET.indent(raiz, space="  ")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(raiz, encoding="unicode")


# =============================================================================
# Importação
# =============================================================================
_RE_DUR = re.compile(r"^(-)?P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?"
                     r"(?:(\d+(?:\.\d+)?)S)?)?$")


def _horas_de_duracao(texto: str | None, avisos: Avisos, contexto: str) -> float | None:
    if texto is None or not texto.strip():
        return None
    m = _RE_DUR.match(texto.strip())
    if not m:
        raise ErroImportacao(f"{contexto}: duração ISO 8601 ilegível: {texto!r}")
    neg, d, h, mi, s = m.groups()
    if d:
        avisos.add("dur_dias", f"{contexto}: duração com componente em dias ({texto}); "
                               f"tratado como dias ÚTEIS de {HORAS_POR_DIA:g} h")
    total = float(d or 0) * HORAS_POR_DIA + float(h or 0) + float(mi or 0) / 60 + float(s or 0) / 3600
    return -total if neg else total


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _filho(el: ET.Element | None, nome: str) -> ET.Element | None:
    if el is None:
        return None
    for c in el:
        if _local(c.tag) == nome:
            return c
    return None


def _filhos(el: ET.Element | None, nome: str) -> list[ET.Element]:
    return [] if el is None else [c for c in el if _local(c.tag) == nome]


def _txt(el: ET.Element | None, nome: str) -> str | None:
    c = _filho(el, nome)
    if c is None or c.text is None:
        return None
    return c.text.strip()


def _int(el, nome, padrao=None):
    v = _txt(el, nome)
    if v in (None, ""):
        return padrao
    try:
        n = int(v)
    except ValueError:
        # "8.0", "1e3", "inf", "nan", 5.000 dígitos (limite do int do Python): via float, só se finito
        try:
            f = float(v)
        except ValueError:
            raise ErroImportacao(f"campo {nome}: número ilegível {v!r}") from None
        if not math.isfinite(f):
            raise ErroImportacao(f"campo {nome}: número não finito {v[:40]!r}")
        n = int(f)
    if abs(n) > 10**12:
        raise ErroImportacao(f"campo {nome}: número fora de faixa {v[:40]!r}")
    return n


class _DTDEncontrada(Exception):
    pass


class _FimDoProlog(Exception):
    pass


def _recusar_dtd(bruto: bytes) -> None:
    """Pré-varredura com o expat (que já DECODIFICA: UTF-8, UTF-16, declaração de encoding) até a
    primeira tag: qualquer DOCTYPE ou declaração de entidade é recusada, em qualquer posição do
    prólogo e em qualquer codificação (rodada 5: a busca por bytes ASCII deixava passar UTF-16 e
    DOCTYPE depois de 4.096 bytes)."""
    p = expat.ParserCreate()

    def dtd(*_a):
        raise _DTDEncontrada()

    def inicio(*_a):
        raise _FimDoProlog()

    p.StartDoctypeDeclHandler = dtd
    p.EntityDeclHandler = dtd
    p.StartElementHandler = inicio
    try:
        p.Parse(bruto, True)
    except _DTDEncontrada:
        raise ErroImportacao("XML com DOCTYPE/ENTITY recusado (MSPDI não usa DTD; proteção contra "
                             "expansão de entidades)") from None
    except _FimDoProlog:
        return
    except (expat.ExpatError, ValueError, LookupError) as e:
        raise ErroImportacao(f"XML inválido: {e}") from None


def _parse_xml(xml: str | bytes) -> ET.Element:
    if isinstance(xml, str):
        # a declaração pode dizer outro encoding; o texto já está decodificado, então regrava em UTF-8
        xml = re.sub(r'^(\s*<\?xml[^>]*?)\sencoding=["\'][^"\']*["\']', r"\1", xml, count=1)
        bruto = xml.encode("utf-8")
    else:
        bruto = bytes(xml)
    _recusar_dtd(bruto)
    try:
        raiz = ET.fromstring(bruto)
    except ET.ParseError as e:
        raise ErroImportacao(f"XML inválido: {e}") from e
    except (LookupError, ValueError) as e:  # encoding desconhecido etc.
        raise ErroImportacao(f"XML ilegível: {e}") from e
    if _local(raiz.tag) != "Project":
        raise ErroImportacao(f"raiz do XML é <{_local(raiz.tag)}>, esperado <Project> (MSPDI)")
    return raiz


def _datas_excecao(ex: ET.Element, avisos: Avisos, nome_cal: str) -> tuple[set[date], bool] | None:
    """Datas cobertas por uma exceção (formato 2007+) e se é dia útil."""
    tp = _filho(ex, "TimePeriod")
    de = data_de_texto(_txt(tp, "FromDate"))
    ate = data_de_texto(_txt(tp, "ToDate")) or de
    if de is None:
        avisos.add("excecao", f"calendário {nome_cal}: exceção sem TimePeriod/FromDate ignorada")
        return None
    trabalha = _int(ex, "DayWorking", 0) == 1
    tipo = _int(ex, "Type", 1)
    periodo = _int(ex, "Period", 1)
    datas: set[date] = set()
    faixa = recortar_ao_horizonte(de, ate)
    if faixa is None:
        avisos.add("excecao_fora", f"calendário {nome_cal}: exceção {de}..{ate} inteira fora do horizonte "
                                   f"2020–2040; ignorada (não afeta o cálculo)")
        return datas, trabalha
    if faixa != (de, ate):
        avisos.add("excecao_recorte", f"calendário {nome_cal}: exceção {de}..{ate} recortada ao horizonte "
                                      f"{faixa[0]}..{faixa[1]}")
    de, ate = faixa
    if tipo == 1 and periodo in (None, 1):
        d = de
        while d <= ate:
            datas.add(d)
            d += timedelta(days=1)
    elif tipo == 2:  # anual por dia do mês
        mes = _int(ex, "Month")
        dia = _int(ex, "MonthDay")
        if mes is None or dia is None:
            avisos.add("excecao", f"calendário {nome_cal}: exceção anual sem Month/MonthDay ignorada")
            return None
        for ano in range(de.year, ate.year + 1):
            try:
                d = date(ano, mes + 1, dia)
            except ValueError:
                continue
            if de <= d <= ate:
                datas.add(d)
    else:
        avisos.add("excecao", f"calendário {nome_cal}: exceção recorrente Type={tipo}, Period={periodo} "
                              f"('{_txt(ex, 'Name') or ''}') não suportada: ignorada")
        return None
    return datas, trabalha


def _ler_calendarios(raiz: ET.Element, avisos: Avisos) -> dict[int, dict]:
    """Lê cada <Calendar> em forma bruta: dias da semana e exceções próprias."""
    brutos = {}
    todos = _filhos(_filho(raiz, "Calendars"), "Calendar")
    if len(todos) > MAXIMO_CALENDARIOS_ARQUIVO:
        raise ErroImportacao(f"MSPDI com {len(todos)} calendários; o limite suportado é "
                             f"{MAXIMO_CALENDARIOS_ARQUIVO}")
    for c in todos:
        uid = _int(c, "UID")
        nome = _txt(c, "Name") or f"CAL-{uid}"
        semana: dict[int, bool] = {}
        nao_uteis: set[date] = set()
        uteis_ex: set[date] = set()
        for w in _filhos(_filho(c, "WeekDays"), "WeekDay"):
            dt = _int(w, "DayType")
            trabalha = _int(w, "DayWorking", 0) == 1
            if dt is None:
                continue
            if 1 <= dt <= 7:
                semana[(dt + 5) % 7] = trabalha  # 1=domingo → 6; 2=segunda → 0
            elif dt == 0:  # exceção no formato antigo (MSPDI 2003)
                tp = _filho(w, "TimePeriod")
                de = data_de_texto(_txt(tp, "FromDate"))
                ate = data_de_texto(_txt(tp, "ToDate")) or de
                if de is None:
                    continue
                faixa = recortar_ao_horizonte(de, ate)
                if faixa is None:
                    continue
                de, ate = faixa
                d = de
                while d <= ate:
                    (uteis_ex if trabalha else nao_uteis).add(d)
                    d += timedelta(days=1)
        for ex in _filhos(_filho(c, "Exceptions"), "Exception"):
            r = _datas_excecao(ex, avisos, nome)
            if r:
                datas, trabalha = r
                (uteis_ex if trabalha else nao_uteis).update(datas)
        brutos[uid] = {"uid": uid, "nome": nome, "base": _int(c, "BaseCalendarUID", -1),
                       "semana": semana, "nao_uteis": nao_uteis, "uteis_ex": uteis_ex}
    return brutos


def _resolver_calendario(uid: int, brutos: dict, avisos: Avisos) -> tuple[set[int], set[date]]:
    """Resolve a herança por BaseCalendarUID de forma ITERATIVA, com profundidade limitada
    (rodada 5: 2.000 calendários em cadeia estouravam a recursão)."""
    cadeia = [uid]
    while True:
        base = brutos[cadeia[-1]]["base"]
        if base in (None, -1) or base not in brutos:
            break
        if base in cadeia:
            raise ErroImportacao(f"calendário {brutos[uid]['nome']}: herança circular de BaseCalendarUID")
        if len(cadeia) >= MAXIMO_NIVEIS:
            raise ErroImportacao(f"calendário {brutos[uid]['nome']}: herança de calendário com mais de "
                                 f"{MAXIMO_NIVEIS} níveis")
        cadeia.append(base)
    raiz_b = brutos[cadeia[-1]]
    if not raiz_b["semana"]:
        avisos.add("cal_padrao", f"calendário {raiz_b['nome']}: sem WeekDays; assumido segunda a sexta")
    semana, nao = {0, 1, 2, 3, 4}, set()
    for u in reversed(cadeia):  # do base para o derivado
        b = brutos[u]
        for wd, trabalha in b["semana"].items():
            (semana.add if trabalha else semana.discard)(wd)
        nao = (nao | b["nao_uteis"]) - b["uteis_ex"]
    b = brutos[uid]
    extra = {d for d in b["uteis_ex"] if d.weekday() not in semana}
    if extra:
        avisos.add("excecao_util", f"calendário {b['nome']}: {len(extra)} exceção(ões) que tornam útil um dia "
                                   f"não útil da semana foram ignoradas (não suportado)")
    return semana, nao


def importar_mspdi(xml: str | bytes):
    """Lê MSPDI → ``(atividades, relacoes, calendarios, metadados)`` prontos para ``motor.calcular``.

    ``metadados``: ``inicio_projeto`` e ``data_status`` (ordinais; data de status pode ser None),
    ``nomes`` {id: nome}, ``uids`` {id: UID}, ``avisos`` e ``limitacoes``.

    Toda entrada ruim vira ``ErroImportacao`` (a rota responde 422, nunca 500): além das
    validações explícitas, uma rede de segurança converte estouros residuais (rodada 5).
    """
    try:
        return _importar_mspdi(xml)
    except ErroImportacao:
        raise
    except (ErroCalendario, LookupError, OverflowError, RecursionError, ValueError, TypeError,
            MemoryError) as e:
        raise ErroImportacao(f"MSPDI recusado: {type(e).__name__}: {str(e)[:200]}") from None


def _importar_mspdi(xml: str | bytes):
    raiz = _parse_xml(xml)
    avisos = Avisos()
    min_dia = _int(raiz, "MinutesPerDay", MINUTOS_POR_DIA) or MINUTOS_POR_DIA
    horas_dia = min_dia / 60

    inicio = data_de_texto(_txt(raiz, "StartDate"))
    if inicio is None:
        raise ErroImportacao("MSPDI sem <StartDate> do projeto")
    status_txt = _txt(raiz, "StatusDate")
    data_status = data_de_texto(status_txt) if status_txt and status_txt.upper() != "NA" else None
    for nome, d in (("StartDate", inicio), ("StatusDate", data_status)):
        if d is not None and not no_horizonte(d):
            raise ErroImportacao(f"{nome} {d} fora do horizonte suportado ({HORIZONTE_INICIO} a {HORIZONTE_FIM})")

    # alias dos atributos estendidos: FieldID → alias
    alias_por_field = {}
    for ea in _filhos(_filho(raiz, "ExtendedAttributes"), "ExtendedAttribute"):
        fid, alias = _txt(ea, "FieldID"), _txt(ea, "Alias")
        if fid and alias:
            alias_por_field[fid] = alias

    brutos = _ler_calendarios(raiz, avisos)
    cal_projeto = _int(raiz, "CalendarUID")

    # ------------------------------------------------------------- tarefas
    tarefas = []
    ignoradas: set[int] = set()
    todas = _filhos(_filho(raiz, "Tasks"), "Task")
    if len(todas) > MAXIMO_ATIVIDADES:
        raise ErroImportacao(f"MSPDI com {len(todas)} tarefas; o limite suportado é {MAXIMO_ATIVIDADES}")
    for t in todas:
        uid = _int(t, "UID")
        if uid is None:
            continue
        if uid == 0:
            ignoradas.add(uid)
            continue
        if _int(t, "IsNull", 0) == 1 or _int(t, "Active", 1) == 0:
            avisos.add("nula", f"tarefa UID {uid}: nula ou inativa, ignorada")
            ignoradas.add(uid)
            continue
        if _int(t, "Summary", 0) == 1:
            avisos.add("resumo", f"tarefa UID {uid} ({_txt(t, 'Name')}): tarefa de resumo ignorada "
                                 f"(estrutura WBS não é modelada; relações dela também são ignoradas)")
            ignoradas.add(uid)
            continue
        tarefas.append(t)

    atributos_por_uid = {}
    for t in tarefas:
        attrs = {}
        for ea in _filhos(t, "ExtendedAttribute"):
            alias = alias_por_field.get(_txt(ea, "FieldID") or "")
            if alias:
                attrs[alias] = _txt(ea, "Value")
        atributos_por_uid[_int(t, "UID")] = attrs

    id_por_uid: dict[int, str] = {}
    usados: set[str] = set()
    for t in tarefas:
        uid = _int(t, "UID")
        aid = atributos_por_uid[uid].get(_ALIAS_POR_CHAVE["id"]) or f"UID{uid}"
        if aid in usados:
            avisos.add("id_dup", f"id {aid!r} repetido; usando UID{uid}")
            aid = f"UID{uid}"
        usados.add(aid)
        id_por_uid[uid] = aid

    # relações (antes das tarefas: o tipo de marco sem atributo depende de ter predecessora)
    relacoes: list[Relacao] = []
    chaves = set()
    tem_pred: set[str] = set()
    for t in tarefas:
        suc = id_por_uid[_int(t, "UID")]
        for pl in _filhos(t, "PredecessorLink"):
            puid = _int(pl, "PredecessorUID")
            if _int(pl, "CrossProject", 0) == 1:
                avisos.add("cross", f"{suc}: predecessora de outro projeto ignorada")
                continue
            if puid not in id_por_uid:
                motivo = "ignorada (resumo/nula)" if puid in ignoradas else "inexistente"
                avisos.add("rel_orfa", f"{suc}: predecessora UID {puid} {motivo}; relação descartada")
                continue
            tipo_n = _int(pl, "Type", 1)
            if tipo_n not in MSPDI_PARA_TIPO:
                raise ErroImportacao(f"{suc}: PredecessorLink.Type={tipo_n} desconhecido")
            fmt = _int(pl, "LagFormat", LAGFORMAT_DIAS)
            lag_dec_min = _int(pl, "LinkLag", 0) or 0
            ctx = f"relação UID{puid}->{suc}"
            if fmt in LAGFORMAT_PERCENTUAL:
                avisos.add("lag_pct", f"{ctx}: lag em porcentagem não suportado; lag zerado")
                lag = 0
            else:
                if fmt in LAGFORMAT_DECORRIDO:
                    avisos.add("lag_decorrido", f"{ctx}: lag em tempo decorrido (LagFormat {fmt}) tratado como "
                                                f"tempo de trabalho")
                lag = lag_de_horas(lag_dec_min / 600, horas_dia, avisos, ctx)
            pred = id_por_uid[puid]
            tipo = MSPDI_PARA_TIPO[tipo_n]
            if (pred, suc, tipo) in chaves:
                avisos.add("rel_dup", f"{ctx}: relação {tipo} duplicada; mantida a primeira")
                continue
            chaves.add((pred, suc, tipo))
            tem_pred.add(suc)
            relacoes.append(Relacao(pred, suc, tipo, lag))

    # calendários usados
    uids_cal_usados = set()
    cal_tarefa = {}
    for t in tarefas:
        cu = _int(t, "CalendarUID", -1)
        if cu in (None, -1) or cu not in brutos:
            if cu not in (None, -1):
                avisos.add("cal_inexistente", f"tarefa UID {_int(t, 'UID')}: CalendarUID {cu} inexistente; "
                                              f"usado o calendário do projeto")
            cu = cal_projeto
        if cu not in brutos:
            cu = None
        cal_tarefa[_int(t, "UID")] = cu
        uids_cal_usados.add(cu)
    nomes_cal = {}
    contagem_nome = {}
    for b in brutos.values():
        contagem_nome[b["nome"]] = contagem_nome.get(b["nome"], 0) + 1
    calendarios: dict[str, Calendario] = {}
    if len(uids_cal_usados) > MAXIMO_CALENDARIOS:
        raise ErroImportacao(f"MSPDI usa {len(uids_cal_usados)} calendários distintos; o limite suportado é "
                             f"{MAXIMO_CALENDARIOS}")
    for cu in uids_cal_usados:
        if cu is None:
            avisos.add("cal_padrao", "projeto sem calendário utilizável; criado 'PADRAO' segunda a sexta")
            calendarios["PADRAO"] = Calendario("PADRAO", "Padrão (segunda a sexta)")
            nomes_cal[None] = "PADRAO"
            continue
        b = brutos[cu]
        chave = b["nome"] if contagem_nome[b["nome"]] == 1 else f"{b['nome']} (UID {cu})"
        semana, nao = _resolver_calendario(cu, brutos, avisos)
        nao_h = frozenset(d for d in nao if no_horizonte(d))
        try:
            calendarios[chave] = Calendario(chave, b["nome"], tuple(sorted(semana)), nao_h)
        except ErroCalendario as e:
            raise ErroImportacao(str(e)) from e
        nomes_cal[cu] = chave

    atividades: list[AtividadeCPM] = []
    nomes, uids = {}, {}
    for t in tarefas:
        uid = _int(t, "UID")
        aid = id_por_uid[uid]
        attrs = atributos_por_uid[uid]
        nome = _txt(t, "Name") or aid
        nomes[aid], uids[aid] = nome, uid
        ctx = f"tarefa {aid} ({nome})"
        dur_h = _horas_de_duracao(_txt(t, "Duration"), avisos, ctx) or 0.0
        rem_h = _horas_de_duracao(_txt(t, "RemainingDuration"), avisos, ctx)
        marco = _int(t, "Milestone", 0) == 1
        a_ini = datahora_de_texto(_txt(t, "ActualStart"))
        a_fim = datahora_de_texto(_txt(t, "ActualFinish"))
        pct = _int(t, "PercentComplete", 0) or 0
        if a_fim is not None and a_ini is None:
            avisos.add("real", f"{ctx}: ActualFinish sem ActualStart; início real = término real")
            a_ini = a_fim
        status = "concluida" if a_fim else ("em_andamento" if a_ini else "nao_iniciada")
        if pct >= 100 and status != "concluida":
            avisos.add("pct", f"{ctx}: PercentComplete=100 sem ActualFinish; tratada como {status}")

        tipo_attr = attrs.get(_ALIAS_POR_CHAVE["tipo"])
        if marco and dur_h > 0:
            avisos.add("marco_dur", f"{ctx}: marcada como marco com duração > 0; tratada como tarefa")
            marco = False
        if tipo_attr in ("tarefa", "marco_inicio", "marco_termino"):
            tipo = tipo_attr
        elif marco:
            tipo = "marco_termino" if aid in tem_pred else "marco_inicio"
        else:
            tipo = "tarefa"

        if status == "concluida" or tipo != "tarefa":
            dur = 0
        elif status == "em_andamento":
            if rem_h is None:
                rem_h = dur_h * (1 - pct / 100)
                avisos.add("rem", f"{ctx}: sem RemainingDuration; estimada por Duration × (1 − %)")
            dur = dias_de_horas(rem_h, horas_dia, avisos, ctx)
            if dur <= 0:
                avisos.add("rem0", f"{ctx}: em andamento com remanescente 0; considerado 1 dia útil")
                dur = 1
        else:
            dur = dias_de_horas(dur_h, horas_dia, avisos, ctx)

        ini_real = a_ini.date() if a_ini else None
        fim_real = None
        if a_fim is not None:
            fim_real = a_fim.date()
            if a_fim.hour == 0 and a_fim.minute == 0 and ini_real is not None and fim_real > ini_real:
                fim_real -= timedelta(days=1)  # 00:00 do dia seguinte = fim do dia anterior

        restr = None
        ct = _int(t, "ConstraintType", 0) or 0
        if ct == CONSTRAINT_SNET:
            cd = data_de_texto(_txt(t, "ConstraintDate"))
            if cd is None:
                avisos.add("restr", f"{ctx}: SNET sem ConstraintDate; ignorada")
            else:
                restr = cd.toordinal()
        elif ct != 0:
            avisos.add("restr", f"{ctx}: restrição {NOMES_CONSTRAINT.get(ct, ct)} não suportada; ignorada")

        atividades.append(AtividadeCPM(
            id=aid, duracao=dur, calendario=nomes_cal[cal_tarefa[uid]], tipo=tipo, status=status,
            inicio_real=ini_real.toordinal() if ini_real and status != "nao_iniciada" else None,
            termino_real=fim_real.toordinal() if fim_real and status == "concluida" else None,
            restricao_inicio=restr,
        ))

    if not atividades:
        raise ErroImportacao("MSPDI sem tarefas utilizáveis")
    if data_status is None and any(a.status != "nao_iniciada" for a in atividades):
        avisos.add("sem_status", "há tarefas com progresso mas o arquivo não traz <StatusDate>; "
                                 "calculado sem data de status")

    metadados = {
        "formato": "mspdi",
        "nome": _txt(raiz, "Title") or _txt(raiz, "Name"),
        "inicio_projeto": inicio.toordinal(),
        "data_status": data_status.toordinal() if data_status else None,
        "horas_por_dia": horas_dia,
        "nomes": nomes,
        "uids": uids,
        "tarefas_ignoradas": len(ignoradas - {0}),
        "avisos": avisos.lista(),
        "limitacoes": list(LIMITACOES_MSPDI),
    }
    return atividades, relacoes, calendarios, metadados
