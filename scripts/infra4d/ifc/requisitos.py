"""Requisitos de informação BIM 4D/5D (o que um IDS verificaria), com IfcOpenShell puro.

Sem ``ifctester``: cada requisito é uma função sobre os ELEMENTOS CONSTRUTIVOS do arquivo
(``IfcElement`` exceto aberturas, terreno ``IfcGeographicElement``, ``IfcElementAssembly`` — que
só agrega peças verificadas individualmente — e ``IfcVirtualElement``). Resultado por requisito:
aprovado/reprovado, contagens e a lista dos reprovados com o motivo. Nada é escondido: um IFC de
terceiro sem 4D REPROVA nos requisitos 4D, e o relatório diz isso.

R1 GlobalId único · R2 vínculo com atividade (Pset ``INFRA4D_Vinculo.AtividadeId`` ou
IfcRelAssignsToProduct para IfcTask) · R3 classificação (IfcClassificationReference) · R4 quantidade
na unidade do serviço (IfcElementQuantity com quantidade do tipo compatível e > 0) · R5 posicionado
no alinhamento (IfcLinearPlacement ou IfcRelPositions a partir de IfcAlignment, e estaca dentro do
eixo quando declarada) · R6 cronograma 4D nativo cobre o elemento (IfcTask com datas planejadas,
dentro de um IfcWorkSchedule).

Também aqui: ``coerencia`` (soma das quantidades por atividade × ``quantidade_total``) e
``custo_modelo`` (Qto × preço FICTÍCIO do orcamento.py × BAC do orçamento pelo dataset).
"""

from __future__ import annotations

from collections import Counter, defaultdict

import ifcopenshell
import ifcopenshell.api.alignment
import ifcopenshell.util.classification
import ifcopenshell.util.element

from . import PSET_VINCULO
from . import quantidades as qt

LIMITE_LISTA = 50  # reprovados listados por requisito (a contagem é sempre completa)
EXCLUIDOS = ("IfcOpeningElement", "IfcGeographicElement", "IfcElementAssembly", "IfcVirtualElement")


def elementos_construtivos(f: ifcopenshell.file) -> list:
    return [e for e in f.by_type("IfcElement") if not any(e.is_a(c) for c in EXCLUIDOS)]


def quantidades_do_elemento(el) -> dict[str, dict[str, object]]:
    """{nome do conjunto: {nome da quantidade: entidade IfcPhysicalSimpleQuantity}}."""
    out: dict[str, dict] = {}
    for rel in getattr(el, "IsDefinedBy", None) or ():
        if rel.is_a("IfcRelDefinesByProperties") and rel.RelatingPropertyDefinition.is_a("IfcElementQuantity"):
            eq = rel.RelatingPropertyDefinition
            out[eq.Name] = {q.Name: q for q in eq.Quantities}
    return out


def _valor(q) -> float:
    return float(q[3])  # Name, Description, Unit, <Valor>, ...


def _tarefas(el) -> list:
    t = []
    for rel in getattr(el, "ReferencedBy", None) or ():
        if rel.is_a("IfcRelAssignsToProduct"):
            t += [o for o in rel.RelatedObjects if o.is_a("IfcTask")]
    for rel in getattr(el, "HasAssignments", None) or ():
        if rel.is_a("IfcRelAssignsToProcess") and rel.RelatingProcess and rel.RelatingProcess.is_a("IfcTask"):
            t.append(rel.RelatingProcess)
    return t


def _no_cronograma(task) -> bool:
    for rel in getattr(task, "HasAssignments", None) or ():
        if rel.is_a("IfcRelAssignsToControl") and rel.RelatingControl.is_a("IfcWorkSchedule"):
            return True
    for rel in getattr(task, "Nests", None) or ():  # tarefa filha de outra que está no cronograma
        if rel.RelatingObject.is_a("IfcTask") and _no_cronograma(rel.RelatingObject):
            return True
    return False


def _datas_planejadas(task) -> bool:
    """Datas planejadas: ScheduleStart/Finish ou, como o exemplo oficial da buildingSMART grava,
    EarlyStart/Finish (datas do CPM)."""
    tt = task.TaskTime
    if tt is None:
        return False
    return bool((tt.ScheduleStart and tt.ScheduleFinish) or (tt.EarlyStart and tt.EarlyFinish))


def _unidade(el, pset: dict, dados: dict | None) -> str | None:
    if pset.get("Unidade"):
        return pset["Unidade"]
    if dados is None:
        return None
    atv = pset.get("AtividadeId") or next((t.Identification for t in _tarefas(el) if t.Identification), None)
    a = next((x for x in dados["atividades"] if x["id"] == atv), None)
    if a is None:
        return None
    return a.get("unidade") or next((s["unidade"] for s in dados.get("servicos", [])
                                     if s["id"] == a.get("servico_id")), None)


def _req(rid: str, descricao: str, total: int, falhas: list[dict], nota: str | None = None) -> dict:
    return {"id": rid, "descricao": descricao,
            "status": "nao_aplicavel" if total == 0 else ("aprovado" if not falhas else "reprovado"),
            "total": total, "aprovados": total - len(falhas), "reprovados": len(falhas),
            "lista_reprovados": falhas[:LIMITE_LISTA], "lista_truncada": len(falhas) > LIMITE_LISTA,
            "nota": nota}


def _falha(el, motivo: str) -> dict:
    return {"global_id": el.GlobalId, "classe": el.is_a(), "nome": el.Name, "motivo": motivo}


def verificar(f: ifcopenshell.file, dados: dict | None = None) -> dict:
    """Relatório de requisitos. ``dados`` (JSON da obra) só serve para achar a unidade do serviço
    quando o IFC não a declara no Pset."""
    els = elementos_construtivos(f)
    n = len(els)
    psets = {e.id(): ifcopenshell.util.element.get_pset(e, PSET_VINCULO) or {} for e in els}

    # R1
    cont = Counter(e.GlobalId for e in els)
    r1 = [_falha(e, f"GlobalId repetido {cont[e.GlobalId]}×") for e in els if cont[e.GlobalId] > 1]

    # R2
    r2 = [_falha(e, "sem Pset INFRA4D_Vinculo.AtividadeId e sem IfcRelAssignsToProduct para IfcTask")
          for e in els if not psets[e.id()].get("AtividadeId")
          and not any(rel.is_a("IfcRelAssignsToProduct") and any(o.is_a("IfcTask") for o in rel.RelatedObjects)
                      for rel in (getattr(e, "ReferencedBy", None) or ()))]

    # R3
    r3 = [_falha(e, "sem IfcClassificationReference") for e in els
          if not ifcopenshell.util.classification.get_references(e)]

    # R4
    r4 = []
    for e in els:
        un = _unidade(e, psets[e.id()], dados)
        if un is None:
            r4.append(_falha(e, "unidade do serviço não determinável (sem Pset Unidade nem atividade vinculada)"))
            continue
        if un not in qt.UNIDADES:
            r4.append(_falha(e, f"unidade {un!r} sem tipo de quantidade IFC mapeado"))
            continue
        tipo = qt.UNIDADES[un][0]
        ok = [q for conj in quantidades_do_elemento(e).values() for q in conj.values()
              if q.is_a(tipo) and _valor(q) > 0]
        if not ok:
            r4.append(_falha(e, f"nenhuma {tipo} > 0 (unidade do serviço {un})"))

    # R5
    alinhamentos = f.by_type("IfcAlignment")
    fim_eixo = {}
    for a in alinhamentos:
        try:
            ini = ifcopenshell.api.alignment.get_alignment_start_station(f, a)
        except Exception:  # noqa: BLE001
            ini = None
        h = ifcopenshell.api.alignment.get_horizontal_layout(a)
        segs = [s for s in (ifcopenshell.api.alignment.get_layout_segments(h) if h else [])
                if getattr(s, "DesignParameters", None)]
        if ini is not None and segs:
            fim_eixo[a.id()] = (ini, ini + sum(float(s.DesignParameters.SegmentLength or 0) for s in segs))
    posicionados = {}
    for rel in f.by_type("IfcRelPositions"):
        if rel.RelatingPositioningElement.is_a("IfcAlignment"):
            for p in rel.RelatedProducts:
                posicionados[p.id()] = rel.RelatingPositioningElement
    modos = Counter()
    r5 = []
    for e in els:
        lp = e.ObjectPlacement is not None and e.ObjectPlacement.is_a("IfcLinearPlacement")
        al = posicionados.get(e.id())
        if not lp and al is None:
            r5.append(_falha(e, "nem IfcLinearPlacement nem IfcRelPositions a partir de IfcAlignment"
                                + ("" if alinhamentos else " (o arquivo não tem IfcAlignment)")))
            continue
        modos["IfcLinearPlacement" if lp else "IfcRelPositions"] += 1
        ps = psets[e.id()]
        if al is not None and al.id() in fim_eixo and ps.get("KmInicial") is not None:
            a0, a1 = fim_eixo[al.id()]
            k0, k1 = float(ps["KmInicial"]) * 1000, float(ps["KmFinal"]) * 1000
            if k0 < a0 - 1e-6 or k1 > a1 + 1e-6:
                r5.append(_falha(e, f"estaca {k0:.1f}–{k1:.1f} m fora do eixo {a0:.1f}–{a1:.1f} m"))

    # R6
    r6 = []
    for e in els:
        ts = _tarefas(e)
        if not ts:
            r6.append(_falha(e, "não está ligado a nenhuma IfcTask"))
            continue
        no_cron = [t for t in ts if _no_cronograma(t)]
        if not no_cron:
            r6.append(_falha(e, "IfcTask fora de qualquer IfcWorkSchedule (nem direto nem por aninhamento)"))
            continue
        if not any(_datas_planejadas(t) for t in no_cron):
            r6.append(_falha(e, "IfcTask sem datas planejadas (ScheduleStart/Finish nem EarlyStart/Finish)"))

    reqs = [
        _req("R1", "Todo elemento construtivo tem GlobalId único", n, r1),
        _req("R2", "Vínculo com atividade: Pset INFRA4D_Vinculo.AtividadeId ou IfcRelAssignsToProduct → IfcTask", n, r2),
        _req("R3", "Classificação para o 5D (IfcClassificationReference)", n, r3),
        _req("R4", "Quantidade > 0 do tipo compatível com a unidade do serviço (IfcElementQuantity)", n, r4),
        _req("R5", "Posicionado no alinhamento (IfcLinearPlacement ou IfcRelPositions de IfcAlignment; "
                   "estaca do Pset dentro do eixo)", n, r5,
             nota=f"modos: {dict(modos)}" if modos else None),
        _req("R6", "Cronograma 4D nativo cobre o elemento (IfcTask em IfcWorkSchedule, direto ou aninhada, com datas planejadas)", n, r6),
    ]
    reprovados = [r["id"] for r in reqs if r["status"] == "reprovado"]
    if n == 0:
        conclusao = "NÃO VERIFICÁVEL: o arquivo não tem elementos construtivos"
    elif reprovados:
        conclusao = f"REPROVADO em {', '.join(reprovados)}"
    else:
        conclusao = "APROVADO em todos os requisitos"
    return {"schema": f.schema_identifier, "elementos_construtivos": n,
            "excluidos_da_verificacao": list(EXCLUIDOS), "conclusao": conclusao,
            "aprovado": n > 0 and not reprovados, "requisitos": reqs}


# ---------------------------------------------------------------------------
# Coerência de quantidades e custo pelo modelo
# ---------------------------------------------------------------------------

def _quantidade_servico(el, nome: str, un: str) -> float | None:
    q = quantidades_do_elemento(el).get(qt.QSET_SERVICO, {}).get(nome)
    return None if q is None else qt.de_modelo(un, _valor(q))


def coerencia(f: ifcopenshell.file, dados: dict) -> dict:
    """Soma por atividade da quantidade geométrica e da contratual × ``quantidade_total`` do dataset."""
    ativ = {a["id"]: a for a in dados["atividades"]}
    soma_geo, soma_con, pecas = defaultdict(float), defaultdict(float), Counter()
    geo_ausente = set()
    for e in elementos_construtivos(f):
        ps = ifcopenshell.util.element.get_pset(e, PSET_VINCULO) or {}
        aid, un = ps.get("AtividadeId"), ps.get("Unidade")
        if aid not in ativ or un not in qt.UNIDADES:
            continue
        pecas[aid] += 1
        g = _quantidade_servico(e, "QuantidadeGeometrica", un)
        c = _quantidade_servico(e, "QuantidadeContratual", un)
        if g is None:
            geo_ausente.add(aid)
        else:
            soma_geo[aid] += g
        if c is not None:
            soma_con[aid] += c
    linhas, por_servico = [], defaultdict(list)
    for aid in sorted(pecas):
        a = ativ[aid]
        tot = a.get("quantidade_total")
        g = None if aid in geo_ausente else soma_geo[aid]
        razao = (g / tot) if (g is not None and tot) else None
        linhas.append({"atividade_id": aid, "servico_id": a.get("servico_id"), "unidade": a.get("unidade"),
                       "pecas": pecas[aid], "quantidade_total": tot, "soma_contratual": soma_con.get(aid),
                       "soma_geometrica": g, "razao_geometrica": razao})
        por_servico[a.get("servico_id")].append(razao)
    servicos = {}
    for s, rs in sorted(por_servico.items()):
        val = [r for r in rs if r is not None]
        servicos[s] = {"atividades": len(rs),
                       "razao_min": min(val) if val else None, "razao_max": max(val) if val else None,
                       "sem_geometrica": len(rs) - len(val)}
    return {"nota": ("soma_contratual deve igualar quantidade_total (rateio). razao_geometrica = "
                     "soma da geometria esquemática / quantidade_total: mede quanto a peça representa "
                     "a quantidade de projeto; ≠ 1 porque a seção é a do visualizador."),
            "atividades": linhas, "por_servico": servicos}


def custo_modelo(f: ifcopenshell.file, dados: dict, tipo: str) -> dict:
    """Custo pelo MODELO (Σ quantidade × preço de venda FICTÍCIO da composição classificada)."""
    from .. import orcamento
    comps = {c["codigo"]: c for c in orcamento.COMPOSICOES.get(tipo, {}).values()}
    por_ativ_con, por_ativ_geo = defaultdict(float), defaultdict(float)
    sem_classe = 0
    for e in elementos_construtivos(f):
        ps = ifcopenshell.util.element.get_pset(e, PSET_VINCULO) or {}
        refs = ifcopenshell.util.classification.get_references(e)
        comp = next((comps[r.Identification] for r in refs if r.Identification in comps), None)
        if comp is None or ps.get("Unidade") != comp["unidade"]:
            sem_classe += 1
            continue
        pv = orcamento.preco_venda(comp)
        c = _quantidade_servico(e, "QuantidadeContratual", comp["unidade"])
        g = _quantidade_servico(e, "QuantidadeGeometrica", comp["unidade"])
        if c is not None:
            por_ativ_con[ps["AtividadeId"]] += c * pv
        if g is not None:
            por_ativ_geo[ps["AtividadeId"]] += g * pv
    return {"por_atividade_contratual": dict(por_ativ_con), "por_atividade_geometrico": dict(por_ativ_geo),
            "total_contratual": sum(por_ativ_con.values()), "total_geometrico": sum(por_ativ_geo.values()),
            "elementos_sem_composicao": sem_classe, "ficticio": True}
