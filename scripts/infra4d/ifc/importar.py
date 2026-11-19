"""Lê um IFC e devolve a TABELA DE VÍNCULO elemento ↔ atividade, a verificação contra o
projeto e, se houver geometria, uma malha triangulada (JSON) ou GLB.

Fontes de vínculo aceitas, em ordem de precedência:

1. ``pset``     — Pset ``INFRA4D_Vinculo.AtividadeId`` (o que ``exportar.py`` grava);
2. ``produto``  — IfcRelAssignsToProduct: a tarefa (IfcTask) "produz" o elemento — é a forma
                  usual de 4D em IFC (Bonsai/Synchro gravam assim);
3. ``processo`` — IfcRelAssignsToProcess: o elemento é entrada/controle de uma IfcTask.

Para as fontes 2 e 3, o id da atividade é ``IfcTask.Identification`` (ou ``Name`` se vazio).
Quando a fonte 1 e as fontes 2/3 discordam, a linha sai com ``conflito`` preenchido.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.alignment
import ifcopenshell.geom
import ifcopenshell.util.element

from . import PSET_VINCULO
from .cronograma import ErroCronograma, cenarios_no_arquivo  # noqa: F401 (reexportados)
from .cronograma import ler as ler_cronograma  # noqa: F401 — mesma tupla de importar_mspdi

RE_ELEMENTO = re.compile(r"^(?P<atv>.+)-E(?P<nn>\d{2,})$")


def abrir(origem: str | Path | bytes) -> ifcopenshell.file:
    """Abre IFC de caminho ou de bytes (STEP). Levanta ``ValueError`` se não for IFC legível."""
    if isinstance(origem, (bytes, bytearray)):
        texto = bytes(origem).decode("latin-1")  # STEP (ISO 10303-21) é ASCII de 7 bits com escapes
        if "ISO-10303-21" not in texto[:200]:
            raise ValueError("conteúdo não é um arquivo IFC STEP (ISO-10303-21)")
        try:
            return ifcopenshell.file.from_string(texto)
        except Exception as e:
            raise ValueError(f"IFC ilegível: {e}") from e
    try:
        return ifcopenshell.open(str(origem))
    except Exception as e:
        raise ValueError(f"IFC ilegível: {e}") from e


def _id_tarefa(t) -> str | None:
    return (getattr(t, "Identification", None) or getattr(t, "Name", None) or None)


def _tarefas_do_elemento(el) -> tuple[list[str], list[str]]:
    """(tarefas por IfcRelAssignsToProduct, tarefas por IfcRelAssignsToProcess)."""
    por_produto, por_processo = [], []
    for rel in getattr(el, "ReferencedBy", None) or ():  # IfcRelAssignsToProduct.RelatingProduct = el
        if rel.is_a("IfcRelAssignsToProduct"):
            por_produto += [_id_tarefa(o) for o in rel.RelatedObjects if o.is_a("IfcProcess")]
    for rel in getattr(el, "HasAssignments", None) or ():  # el em RelatedObjects
        if rel.is_a("IfcRelAssignsToProcess") and rel.RelatingProcess is not None:
            por_processo.append(_id_tarefa(rel.RelatingProcess))
    return [x for x in por_produto if x], [x for x in por_processo if x]


def tabela_vinculo(f: ifcopenshell.file) -> list[dict]:
    """Uma linha por IfcElement (exceto aberturas e elementos geográficos sem vínculo)."""
    linhas = []
    for el in f.by_type("IfcElement"):
        if el.is_a("IfcOpeningElement"):
            continue
        pset = ifcopenshell.util.element.get_pset(el, PSET_VINCULO) or {}
        por_produto, por_processo = _tarefas_do_elemento(el)
        if el.is_a("IfcGeographicElement") and not (pset or por_produto or por_processo):
            continue  # terreno hospedeiro, não é peça de obra
        candidatos = []
        if pset.get("AtividadeId"):
            candidatos.append(("pset", pset["AtividadeId"]))
        candidatos += [("produto", x) for x in por_produto] + [("processo", x) for x in por_processo]
        atv = candidatos[0][1] if candidatos else None
        fonte = candidatos[0][0] if candidatos else None
        outros = sorted({x for _, x in candidatos if x != atv})
        linhas.append({
            "global_id": el.GlobalId,
            "classe": el.is_a(),
            "predefined_type": getattr(el, "PredefinedType", None),
            "nome": el.Name,
            "elemento_id": pset.get("ElementoId") or el.Tag or None,
            "atividade_id": atv,
            "fonte": fonte,
            "conflito": outros or None,
            "km_ini": pset.get("KmInicial"),
            "km_fim": pset.get("KmFinal"),
            "servico_id": pset.get("ServicoId"),
            "lote_id": pset.get("LoteId") or None,
        })
    return linhas


def resumo(f: ifcopenshell.file, linhas: list[dict]) -> dict:
    return {
        "schema": f.schema_identifier,
        "elementos": len(linhas),
        "com_vinculo": sum(1 for l in linhas if l["atividade_id"]),
        "sem_vinculo": sum(1 for l in linhas if not l["atividade_id"]),
        "conflitos": sum(1 for l in linhas if l["conflito"]),
        "por_fonte": dict(Counter(l["fonte"] or "nenhuma" for l in linhas)),
        "por_classe": dict(sorted(Counter(l["classe"] for l in linhas).items())),
        "atividades_distintas": len({l["atividade_id"] for l in linhas if l["atividade_id"]}),
        "tarefas_ifc": len(f.by_type("IfcTask")),
        "alinhamentos": len(f.by_type("IfcAlignment")),
    }


def _divergencia(l: dict, a: dict) -> str | None:
    """Elemento casado por id mas incoerente com a atividade (serviço, lote ou km)."""
    if l["servico_id"] and a.get("servico_id") and l["servico_id"] != a["servico_id"]:
        return f"serviço {l['servico_id']} ≠ {a['servico_id']}"
    if l["lote_id"] and a.get("lote_id") and l["lote_id"] != a["lote_id"]:
        return f"lote {l['lote_id']} ≠ {a['lote_id']}"
    if l["km_ini"] is not None and a.get("km_ini") is not None and a.get("km_fim") is not None:
        tol = 0.01
        if not (a["km_ini"] - tol <= l["km_ini"] and l["km_fim"] <= a["km_fim"] + tol):
            return f"km {l['km_ini']}–{l['km_fim']} fora de {a['km_ini']}–{a['km_fim']}"
    return None


def verificar(linhas: list[dict], dados: dict, projeto_ifc: str | None = None) -> dict:
    """Confronta a tabela com as atividades do projeto (só ``tipo == tarefa`` exigem elemento).

    Casar por id NÃO basta: obras diferentes reutilizam ids (``L1-S01-SUP`` existe na ferrovia e na
    rodovia). Por isso a saída traz ``obra_confere`` (IfcProject.Name × id da obra) e
    ``divergencias`` (casado por id, mas serviço/lote/km incoerentes)."""
    atividades = {a["id"]: a for a in dados["atividades"]}
    tarefas = {aid for aid, a in atividades.items() if a.get("tipo") == "tarefa"}
    casados = [l for l in linhas if l["atividade_id"] in atividades]
    sem_atv = [l for l in linhas if l["atividade_id"] not in atividades]
    com_elem = {l["atividade_id"] for l in casados}
    fora_conv = [l["elemento_id"] for l in casados if l["elemento_id"] and
                 ((m := RE_ELEMENTO.match(l["elemento_id"])) is None or m["atv"] != l["atividade_id"])]
    divergencias = [{"global_id": l["global_id"], "atividade_id": l["atividade_id"], "motivo": m}
                    for l in casados if (m := _divergencia(l, atividades[l["atividade_id"]]))]
    id_obra = (dados.get("ferrovia") or {}).get("id")
    return {
        "obra": id_obra,
        "projeto_ifc": projeto_ifc,
        "obra_confere": None if projeto_ifc is None else projeto_ifc == id_obra,
        "divergencias": divergencias,
        "elementos_casados": len(casados),
        "elementos_sem_atividade": [{"global_id": l["global_id"], "nome": l["nome"], "atividade_id": l["atividade_id"]}
                                    for l in sem_atv],
        "atividades_sem_elemento": sorted(tarefas - com_elem),
        "marcos_ignorados": sorted(aid for aid, a in atividades.items() if a.get("tipo") != "tarefa"),
        "elemento_id_fora_da_convencao": fora_conv,
        "cobertura_atividades": round(len(com_elem & tarefas) / len(tarefas), 4) if tarefas else None,
    }


# ---------------------------------------------------------------------------
# Malha
# ---------------------------------------------------------------------------

def _settings(world: bool = True):
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", world)
    s.set("weld-vertices", True)
    return s


def malha_json(f: ifcopenshell.file, casas: int = 3) -> dict:
    """Malha triangulada por elemento, coords relativas a uma origem local (metros, Z para cima)."""
    pset_por_gid = {}
    brutos = []
    it = ifcopenshell.geom.iterator(_settings(), f, include=f.by_type("IfcElement"))
    if it.initialize():
        while True:
            sh = it.get()
            el = f.by_guid(sh.guid)
            if not el.is_a("IfcOpeningElement"):
                v = sh.geometry.verts
                brutos.append((el, v, list(sh.geometry.faces)))
            if not it.next():
                break
    if not brutos:
        return {"origem": None, "elementos": []}
    ox = min(min(v[0::3]) for _, v, _ in brutos)
    oy = min(min(v[1::3]) for _, v, _ in brutos)
    oz = min(min(v[2::3]) for _, v, _ in brutos)
    elementos = []
    for el, v, faces in brutos:
        if el.GlobalId not in pset_por_gid:
            pset_por_gid[el.GlobalId] = ifcopenshell.util.element.get_pset(el, PSET_VINCULO) or {}
        ps = pset_por_gid[el.GlobalId]
        rel = []
        for i in range(0, len(v), 3):
            rel += [round(v[i] - ox, casas), round(v[i + 1] - oy, casas), round(v[i + 2] - oz, casas)]
        elementos.append({"global_id": el.GlobalId, "classe": el.is_a(), "elemento_id": ps.get("ElementoId"),
                          "atividade_id": ps.get("AtividadeId"), "vertices": rel, "faces": faces})
    return {"unidade": "m", "eixo_vertical": "Z", "origem": [ox, oy, oz], "escala": 1.0,
            "nota": "vertices relativos a 'origem'; somar a origem para voltar às coordenadas do IFC",
            "elementos": elementos}


def exportar_glb(f: ifcopenshell.file, caminho: str | Path) -> dict:
    """GLB pelo serializador nativo do IfcOpenShell (sem dependência extra). Nós com o GlobalId."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    s = _settings(world=False)
    s.set("use-element-guids", True)
    s.set("y-up", True)
    ser = ifcopenshell.geom.serializers.glb(str(caminho), s)
    ser.setFile(f)
    ser.setUnitNameAndMagnitude("METER", 1.0)
    ser.writeHeader()
    n = 0
    it = ifcopenshell.geom.iterator(_settings(world=False), f, include=f.by_type("IfcElement"))
    if it.initialize():
        while True:
            ser.write(it.get())
            n += 1
            if not it.next():
                break
    ser.finalize()
    del ser
    return {"arquivo": str(caminho), "bytes": caminho.stat().st_size, "elementos": n}


def ler(origem: str | Path | bytes, dados: dict | None = None) -> dict:
    """Atalho: abre, monta a tabela, o resumo e (se ``dados``) a verificação."""
    f = abrir(origem)
    linhas = tabela_vinculo(f)
    out = {"resumo": resumo(f, linhas), "alinhamentos": alinhamentos(f), "vinculos": linhas}
    if dados is not None:
        projetos = f.by_type("IfcProject")
        out["verificacao"] = verificar(linhas, dados, projetos[0].Name if projetos else None)
    return out


# ---------------------------------------------------------------------------
# Alinhamento (IfcAlignment) — só o que o arquivo DECLARA; nunca se inventa eixo
# ---------------------------------------------------------------------------

SEM_ALINHAMENTO = "sem alinhamento: o arquivo não tem IfcAlignment (nenhum eixo foi inventado)"


def alinhamentos(f: ifcopenshell.file) -> dict:
    """Lista os IfcAlignment com estaca inicial/final quando o arquivo as declara.

    - ``estaca_inicial``: ``alignment.get_alignment_start_station`` (referente de estaqueamento);
      ``None`` = o arquivo não declara estaqueamento.
    - ``comprimento_horizontal``: soma de ``SegmentLength`` dos IfcAlignmentHorizontalSegment.
    - ``estaca_final``: inicial + comprimento (só se as duas existirem).
    - ``referentes``: IfcReferent com ``Pset_Stationing.Station`` (para conferir a estaca final).
    """
    al = ifcopenshell.api.alignment
    lista = []
    for a in f.by_type("IfcAlignment"):
        h, v, c = al.get_horizontal_layout(a), al.get_vertical_layout(a), al.get_cant_layout(a)
        segs = [x for x in (al.get_layout_segments(h) if h else []) if getattr(x, "DesignParameters", None)]
        comp = sum(float(x.DesignParameters.SegmentLength or 0.0) for x in segs) if segs else None
        try:
            ini = al.get_alignment_start_station(f, a)
        except Exception:  # noqa: BLE001 — arquivo de terceiro: estaqueamento ausente/malformado
            ini = None
        refs = []
        for rel in getattr(a, "IsNestedBy", None) or ():
            for r in rel.RelatedObjects:
                if r.is_a("IfcReferent"):
                    refs.append(_referente(r))
        lista.append({
            "global_id": a.GlobalId, "nome": a.Name,
            "horizontal": h is not None, "vertical": v is not None, "superelevacao": c is not None,
            "segmentos_horizontais": len(segs),
            "comprimento_horizontal": None if comp is None else round(comp, 4),
            "estaca_inicial": ini,
            "estaca_final": _estaca_final(ini, comp, refs),
            "referentes": refs,
        })
    return {"quantidade": len(lista), "mensagem": None if lista else SEM_ALINHAMENTO, "itens": lista}


def _referente(r) -> dict:
    """IfcReferent → estaca (Pset_Stationing), tipo, distância ao longo (IfcLinearPlacement) e km do
    projeto (``INFRA4D_Referencia.Km``, quando o arquivo é nosso)."""
    ps = ifcopenshell.util.element.get_pset(r, "Pset_Stationing") or {}
    nosso = ifcopenshell.util.element.get_pset(r, "INFRA4D_Referencia") or {}
    dist = None
    pl = r.ObjectPlacement
    if pl is not None and pl.is_a("IfcLinearPlacement"):
        loc = pl.RelativePlacement.Location
        if loc.is_a("IfcPointByDistanceExpression"):
            dist = float(getattr(loc.DistanceAlong, "wrappedValue", loc.DistanceAlong))
    st = ps.get("Station")
    return {"nome": r.Name, "tipo": r.PredefinedType, "estaca": st,
            "estaca_texto": None if st is None else _texto_estaca(st),
            "estaca_de_volta": ps.get("IncomingStation"), "distancia_ao_longo": dist, "km": nosso.get("Km")}


def _texto_estaca(metros: float) -> str | None:
    from ..referencia_linear import Estaca, ErroReferencia
    try:
        return Estaca.de_metros(float(metros)).texto()
    except ErroReferencia:
        return None


def _estaca_final(ini, comp, refs) -> float | None:
    """Estaca no fim do eixo: último referente STATION com estaca e distância + o que falta de curva
    (o IFC conta 1 m de estaca por metro de curva depois do último referente)."""
    if comp is None:
        return None
    est = sorted((r for r in refs if r["tipo"] == "STATION" and r["estaca"] is not None
                  and r["distancia_ao_longo"] is not None), key=lambda r: r["distancia_ao_longo"])
    if est:
        u = est[-1]
        return round(float(u["estaca"]) + comp - u["distancia_ao_longo"], 4)
    return None if ini is None else round(ini + comp, 4)


def comparar_estacas(f: ifcopenshell.file, dados: dict) -> dict:
    """Estaca E POSIÇÃO de cada IfcReferent com km × o projeto (``referencia_linear``, a mesma conta de
    ``/api/referencia/km``).

    - ``dif_m``: estaca do IFC − estaca do projeto naquele km;
    - ``desvio_longitudinal_m``: o ponto do eixo IFC onde o referente está (avaliado pelo IfcOpenShell na
      sua ``DistanceAlong``) tem de ser o PÉ DA PERPENDICULAR do ponto do km no eixo do projeto — a
      componente ao longo da tangente entre os dois tem de ser ~0 (r15: dois referentes no MESMO ponto
      passavam porque só se comparava o texto da estaca);
    - ``afastamento_m``: distância lateral entre o ponto do projeto e o eixo IFC (a curva de concordância
      no PI não passa pelo vértice da polilinha): informativo.
    """
    import numpy as np

    import ifcopenshell.api.alignment

    from ..referencia_linear import Eixo
    from .exportar import CurvaEixo
    eixo = Eixo.da_obra(dados)
    linhas = []
    for al in f.by_type("IfcAlignment"):
        base = ifcopenshell.api.alignment.get_basis_curve(al)
        curva = CurvaEixo(base) if base is not None and base.is_a("IfcCompositeCurve") else None
        nest = ifcopenshell.api.alignment.get_stationing_nest(f, al)
        for r_ifc in (nest.RelatedObjects if nest else ()):
            if not r_ifc.is_a("IfcReferent"):
                continue
            r = _referente(r_ifc)
            if r["km"] is None or r["estaca"] is None:
                continue
            esperado = eixo.estaqueamento.km_para_estaca(r["km"])
            linha = {"km": r["km"], "estaca_ifc": r["estaca_texto"], "estaca_projeto": esperado.texto(),
                     "dif_m": abs(float(r["estaca"]) - esperado.metros), "tipo": r["tipo"],
                     "distancia_ao_longo": r["distancia_ao_longo"],
                     "desvio_longitudinal_m": None, "afastamento_m": None}
            if curva is not None and r["distancia_ao_longo"] is not None:
                R, o = curva.quadro(r["distancia_ao_longo"])
                pt = eixo.ponto_em(r["km"])
                v = np.array([pt["x"], pt["y"], 0.0]) - np.array([o[0], o[1], 0.0])
                linha["desvio_longitudinal_m"] = abs(float(np.dot(v, R[:, 0])))
                linha["afastamento_m"] = abs(float(np.dot(v, R[:, 1])))
            linhas.append(linha)
    desvios = [x["desvio_longitudinal_m"] for x in linhas if x["desvio_longitudinal_m"] is not None]
    return {"referentes": linhas, "max_dif_m": max((x["dif_m"] for x in linhas), default=None),
            "max_desvio_longitudinal_m": max(desvios, default=None),
            "max_afastamento_m": max((x["afastamento_m"] for x in linhas if x["afastamento_m"] is not None),
                                     default=None)}


def inspecionar(origem: str | Path | bytes) -> dict:
    """Ficha de um IFC de terceiro: schema, georreferência, alinhamento, cronograma e vínculo."""
    f = abrir(origem)
    linhas = tabela_vinculo(f)
    return {
        "resumo": resumo(f, linhas),
        "georreferenciado": bool(f.by_type("IfcMapConversion")),
        "crs": [c.Name for c in f.by_type("IfcProjectedCRS")],
        "alinhamentos": alinhamentos(f),
        "vinculos": linhas,
    }
