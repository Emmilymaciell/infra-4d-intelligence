"""Retorno de FCStd existente e autoria detalhada, pelo runtime oficial do CAD.

Job JSON em INFRA4D_FREECAD_JOB; executar via runner runpy com __main__.
Todos os arquivos são gerados em destino novo. Nenhum arquivo fonte é salvo por cima.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infra4d.interop_freecad import preparar_componentes, malha_em_metros
from infra4d.cad_contrato import validar_componentes


def validar_edicoes(edicoes):
    if not isinstance(edicoes, dict):
        raise ValueError("editar deve ser objeto por nome nativo")
    for nome, campos in edicoes.items():
        if not isinstance(nome, str) or not nome or not isinstance(campos, dict) or not campos:
            raise ValueError("edição sem objeto ou parâmetros")
        for campo, valor in campos.items():
            if campo not in ("Length", "Width", "Height") or type(valor) not in (int, float):
                raise ValueError("somente dimensões numéricas Length/Width/Height podem ser editadas")
            if not math.isfinite(valor) or not 0 < valor <= 1e6:
                raise ValueError("dimensão CAD deve estar em (0, 1000000] mm")
    return edicoes


def _hash(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _objetos(doc, base):
    por_id = {f["properties"]["atividade_id"]: f["properties"] for f in base["features"]}
    grupo = doc.getObject("INFRA4D")
    if grupo is None or not str(getattr(grupo, "Aviso", "")).startswith("100% FICTICIO"):
        raise ValueError("FCStd não declara o protocolo fictício INFRA4D")
    matriz = json.loads(grupo.TransformacaoLocalMetros)
    _, esperada = preparar_componentes(base)
    if matriz != esperada:
        raise ValueError("transformação local alterada: revisão exige conferência de georreferência")
    legado, _ = preparar_componentes(base)
    if hasattr(grupo, "ManifestoComponentes"):
        from infra4d.oae_parametrica import preparar_oae
        descritores, _ = preparar_oae(base)
        esperado = {d["nome"]: d["atividade_id"] for d in descritores}
        if json.loads(grupo.ManifestoComponentes) != esperado:
            raise ValueError("manifesto nativo diverge do mapeamento confiável da publicação")
    else:
        esperado = {d["nome"]: d["atividade_id"] for d in legado}
    # FreeCAD expõe Shape composto no DocumentObjectGroup; não contá-lo de novo.
    objetos = [o for o in doc.Objects if o.TypeId != "App::DocumentObjectGroup" and hasattr(o, "Shape") and not o.Shape.isNull()]
    if not 1 <= len(objetos) <= 500 or {o.Name for o in objetos} != set(esperado):
        raise ValueError("componentes acrescentados/removidos exigem mapeamento explícito")
    ids = set()
    for o in objetos:
        aid = getattr(o, "AtividadeId", None)
        if o.TypeId != "Part::Box" or aid not in por_id or esperado[o.Name] != aid:
            raise ValueError("tipo ou vínculo nativo incompatível")
        p = por_id[aid]
        if o.ElementoId != p["elemento_id"] or o.ModelId != base["meta"]["model_id"] or o.TipoDado != "ficticio":
            raise ValueError("identidade/classificação nativa alterada")
        if o.UnidadePlanejamento != p["unidade"] or o.QuantidadePlanejamento != p["quantidade_total"] or o.QuantidadeExecutada != p["quantidade_executada"]:
            raise ValueError("quantidade de planejamento/executada ou unidade alterada no CAD")
        cid = getattr(o, "ComponenteId", base["meta"]["model_id"] + ":fc:" + o.Name)
        if cid != base["meta"]["model_id"] + ":fc:" + o.Name:
            raise ValueError("identidade do componente nativo alterada")
        if cid in ids:
            raise ValueError("ID nativo duplicado")
        ids.add(cid)
        if not o.Shape.isValid() or not math.isfinite(o.Shape.Volume) or o.Shape.Volume <= 0:
            raise ValueError("forma CAD inválida")
    return objetos, matriz


def criar_oae(App, base):
    from infra4d.oae_parametrica import preparar_oae
    descritores, matriz = preparar_oae(base)
    doc = App.newDocument("OAEFicticiaDetalhada")
    g = doc.addObject("App::DocumentObjectGroup", "INFRA4D")
    for campo, valor in (("Aviso", "100% FICTICIO. Trecho demonstrativo parcial; sem dimensionamento estrutural."),
                         ("TransformacaoLocalMetros", json.dumps(matriz)),
                         ("ManifestoComponentes", json.dumps({d["nome"]: d["atividade_id"] for d in descritores}))):
        g.addProperty("App::PropertyString", campo, "INFRA4D"); setattr(g, campo, valor)
    for d in descritores:
        o = doc.addObject("Part::Box", d["nome"])
        o.Length, o.Width, o.Height = d["dimensoes_mm"]
        o.Placement.Base = App.Vector(*d["posicao_mm"])
        for campo, valor in (("AtividadeId", d["atividade_id"]), ("ElementoId", "atividade:" + d["atividade_id"]),
                             ("ModelId", base["meta"]["model_id"]), ("ComponenteId", base["meta"]["model_id"] + ":fc:" + d["nome"]),
                             ("TipoDado", "ficticio"), ("UnidadePlanejamento", d["unidade_planejamento"]),
                             ("MaterialNome", d.get("material", "concreto ilustrativo")),
                             ("CorRGB", json.dumps(d.get("cor_rgb", d.get("cor", [.65, .65, .62]))))):
            o.addProperty("App::PropertyString", campo, "INFRA4D"); setattr(o, campo, valor)
        for campo, valor in (("QuantidadePlanejamento", d["quantidade_planejamento"]), ("QuantidadeExecutada", d["quantidade_executada"])):
            o.addProperty("App::PropertyFloat", campo, "INFRA4D"); setattr(o, campo, valor)
        g.addObject(o)
    doc.recompute()
    return doc


def executar_job(job):
    import FreeCAD as App
    import Part
    base = json.loads(Path(job["entrada"]).read_text(encoding="utf-8-sig"))
    preparar_componentes(base)  # exige origem FreeCAD e marca fictícia
    edicoes = validar_edicoes(job.get("editar", {}))
    destino = Path(job["destino"]).resolve()
    if destino.exists():
        raise ValueError("destino já existe; usar pasta nova")
    tol = float(job["limites"]["tolerancia_visual_federacao_m"])
    tolvol = float(job["limites"]["tolerancia_volume_cad_m3"])
    if not 0 < tol <= .01 or not 0 < tolvol <= 1e-6:
        raise ValueError("limites CAD ausentes ou inválidos")
    revision = job["revision"]
    if not isinstance(revision, str) or not revision.strip() or revision == base["meta"]["revision"]:
        raise ValueError("revision deve ser identificador novo")
    fonte = Path(job["fonte_fcstd"]).resolve() if job.get("fonte_fcstd") else None
    hash_fonte = _hash(fonte) if fonte else None
    doc = App.openDocument(str(fonte)) if fonte else criar_oae(App, base)
    objetos, matriz = _objetos(doc, base)
    antes = {o.Name: o.Shape.Volume / 1e9 for o in objetos}
    identidades = {o.Name: (o.AtividadeId, getattr(o, "ComponenteId", base["meta"]["model_id"] + ":fc:" + o.Name)) for o in objetos}
    destino.mkdir(parents=True)
    if not fonte:
        doc.saveAs(str(destino / "ponte-r0.FCStd"))
    for nome, campos in edicoes.items():
        o = doc.getObject(nome)
        if o not in objetos:
            raise ValueError("objeto de edição desconhecido")
        for campo, valor in campos.items():
            setattr(o, campo, valor)
    doc.recompute()
    saida = destino / "modelo-revisado.FCStd"
    doc.saveAs(str(saida)); App.closeDocument(doc.Name)
    doc = App.openDocument(str(saida)); objetos, matriz = _objetos(doc, base)
    if identidades != {o.Name: (o.AtividadeId, getattr(o, "ComponenteId", base["meta"]["model_id"] + ":fc:" + o.Name)) for o in objetos}:
        raise ValueError("IDs não preservados ao reabrir")
    for nome, campos in edicoes.items():
        for campo, valor in campos.items():
            if abs(getattr(doc.getObject(nome), campo).Value - valor) / 1000 > tol:
                raise ValueError("edição não preservada ao reabrir")
    step = destino / "modelo-revisado.step"
    Part.export(objetos, str(step)); importado = Part.Shape(); importado.read(str(step))
    composto = Part.makeCompound([o.Shape for o in objetos])
    if not importado.isValid() or len(importado.Solids) != len(objetos) or abs(importado.Volume - composto.Volume) / 1e9 > tolvol:
        raise ValueError("STEP diverge da geometria de origem")
    for atributo in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"):
        if abs(getattr(composto.BoundBox, atributo) - getattr(importado.BoundBox, atributo)) / 1000 > tol:
            raise ValueError("posicionamento STEP divergente")
    por_atividade = {}
    for o in objetos:
        vs, fs = o.Shape.tessellate(1.0)
        g = por_atividade.setdefault(o.AtividadeId, {"vertices": [], "faces": [], "componentes": []})
        deslocamento, inicio = len(g["vertices"]), len(g["faces"])
        malha = malha_em_metros(vs, fs, matriz)
        for eixo, letra in enumerate("XYZ"):
            for fn, sufixo in ((min, "Min"), (max, "Max")):
                if abs(fn(v[eixo] for v in malha["vertices"]) - getattr(o.Shape.BoundBox, letra + sufixo) / 1000) > tol:
                    raise ValueError("conversão mm/m ou Placement divergente")
        g["vertices"].extend(malha["vertices"])
        g["faces"].extend([[i + deslocamento for i in f] for f in malha["faces"]])
        g["componentes"].append({"componente_id": identidades[o.Name][1], "nome": o.Name,
            "atividade_id": o.AtividadeId, "tipo_nativo": o.TypeId, "face_inicio": inicio, "face_quantidade": len(fs),
            "parametros_mm": {k: getattr(o, k).Value for k in ("Length", "Width", "Height")},
            "volume_m3": o.Shape.Volume / 1e9, "area_m2": o.Shape.Area / 1e6,
            **({"volume_anterior_m3": antes[o.Name]} if edicoes else {}),
            "material": getattr(o, "MaterialNome", "concreto ilustrativo"),
            "cor_rgb": json.loads(getattr(o, "CorRGB", "[0.65,0.65,0.62]"))})
    revisao = copy.deepcopy(base)
    revisao["meta"].update(revision=revision, source_version=".".join(App.Version()[:3]),
                           evidence_level="FCStd existente aberto/salvo/reaberto via FreeCAD oficial; GUI não observada",
                           comparativo_volume="abertura do FCStd antes da edição do job" if edicoes else "sem referência anterior; volume atual somente",
                           source_fcstd_sha256=_hash(saida), created_from_fcstd_sha256=hash_fonte)
    derivados = {}
    for f in revisao["features"]:
        aid = f["properties"]["atividade_id"]
        if aid not in por_atividade:
            continue
        g = por_atividade[aid]
        malha = {"vertices": g["vertices"], "faces": g["faces"], "matrix_world": matriz,
                 "unidade": "m", "ilustrativa": True, "origem": "FreeCAD FCStd salvo e reaberto"}
        resumo = validar_componentes(malha, g["componentes"], aid)
        f["properties"].update(geometria_local_m=malha, componentes_nativos=g["componentes"])
        derivados[aid] = resumo
    revisao_path = destino / "revisao-freecad.geojson"
    revisao_path.write_text(json.dumps(revisao, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    App.closeDocument(doc.Name)
    if fonte and _hash(fonte) != hash_fonte:
        raise ValueError("arquivo fonte foi alterado")
    prova = {"status": "pass", "aplicativo": "FreeCAD", "versao": ".".join(App.Version()[:3]),
             "gui_observada": False, "fonte_preservada": True, "fonte_fcstd_sha256": hash_fonte,
             "ids_nativos_verificados": len(objetos), "ids_publicacao_preservados": len(revisao["features"]),
             "edicoes_mm": edicoes, "derivados_geometricos_declarados": derivados,
             "quantidades_planejamento_alteradas": False, "step_solidos": len(importado.Solids),
             "limites": job["limites"], "hashes": {p.name: _hash(p) for p in (saida, step, revisao_path)}}
    (destino / "prova-retorno.json").write_text(json.dumps(prova, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in prova.items() if k != "derivados_geometricos_declarados"}))
    return prova


if __name__ == "__main__":
    executar_job(json.loads(Path(os.environ["INFRA4D_FREECAD_JOB"]).read_text(encoding="utf-8-sig")))
