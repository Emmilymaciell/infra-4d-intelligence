"""Autoria paramétrica ilustrativa no FreeCAD externo, nunca no processo FastAPI.

FreeCADCmd.exe executa um runner com runpy.run_path(caminho_deste_script,
run_name="__main__"). INFRA4D_FREECAD_JOB aponta para JSON {entrada, destino,
limites}. A execução direta do arquivo não garante chamada do __main__ no app.
Runtime Python próprio do app; unidades CAD em mm.
Três componentes demonstrativos, não uma OAE completa ou dimensionada.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path


def preparar_componentes(pacote):
    """Descritores explícitos; nenhum volume geométrico vira quantidade contratual."""
    meta = pacote.get("meta", {})
    if meta.get("ficticio") is not True or meta.get("source_app") != "FreeCAD":
        raise ValueError("exigida publicação fictícia do adaptador FreeCAD")
    features = {f["properties"]["atividade_id"]: f["properties"] for f in pacote["features"]}
    ids = ("OAE3-FUN", "OAE3-MES", "OAE3-SUE")
    if any(i not in features for i in ids):
        raise ValueError("fragmento exige atividades OAE3-FUN/MES/SUE da obra fictícia")
    a, b = features[ids[-1]]["pontos_locais_m"]
    angulo = math.atan2(b[1] - a[1], b[0] - a[0])
    c, s = math.cos(angulo), math.sin(angulo)
    centro = [(a[i] + b[i]) / 2 for i in range(3)]
    matriz = [[c, -s, 0, centro[0]], [s, c, 0, centro[1]],
              [0, 0, 1, centro[2]], [0, 0, 0, 1]]
    componentes = [
        {"nome": "Bloco", "atividade_id": ids[0], "dimensoes_mm": [4000, 4000, 1500],
         "posicao_mm": [-2000, -2000, -9500]},
        {"nome": "Pilar", "atividade_id": ids[1], "dimensoes_mm": [1200, 1200, 8000],
         "posicao_mm": [-600, -600, -8000]},
        {"nome": "Tabuleiro", "atividade_id": ids[2], "dimensoes_mm": [12000, 8000, 1000],
         "posicao_mm": [-6000, -4000, 0]},
    ]
    for d in componentes:
        p = features[d["atividade_id"]]
        d["unidade_planejamento"] = p["unidade"]
        d["quantidade_planejamento"] = p["quantidade_total"]
        d["quantidade_executada"] = p["quantidade_executada"]
    return componentes, matriz


def malha_em_metros(vertices_mm, faces, matriz):
    """Shape.tessellate já inclui Placement local; não aplicar a posição de novo."""
    vertices = [[float(v[i]) / 1000 for i in range(3)] for v in vertices_mm]
    if not all(math.isfinite(n) for v in vertices for n in v):
        raise ValueError("vértice não finito")
    return {"vertices": vertices, "faces": [list(f) for f in faces],
            "matrix_world": matriz, "unidade": "m", "ilustrativa": True,
            "origem": "FreeCAD FCStd paramétrico salvo e reaberto; fragmento demonstrativo"}


def executar_freecad(entrada, destino, limites):
    import FreeCAD as App
    import Part

    entrada, destino = Path(entrada).resolve(), Path(destino).resolve()
    pacote = json.loads(entrada.read_text(encoding="utf-8-sig"))
    componentes, matriz = preparar_componentes(pacote)
    tolerancia_m = float(limites["tolerancia_visual_federacao_m"])
    tolerancia_volume = float(limites["tolerancia_volume_cad_m3"])
    if not 0 < tolerancia_m <= 0.01 or not 0 < tolerancia_volume <= 1e-6:
        raise ValueError("limites de verificacao CAD ausentes ou fora do envelope da prova")
    destino.mkdir(parents=True, exist_ok=False)  # recusa inclusive pasta parcial existente
    doc = App.newDocument("Infra4DFragmentoFicticio")
    grupo = doc.addObject("App::DocumentObjectGroup", "INFRA4D")
    grupo.addProperty("App::PropertyString", "Aviso", "INFRA4D")
    grupo.Aviso = "100% FICTICIO. Fragmento ilustrativo; nao e dimensionamento estrutural."
    grupo.addProperty("App::PropertyString", "TransformacaoLocalMetros", "INFRA4D")
    grupo.TransformacaoLocalMetros = json.dumps(matriz)
    for d in componentes:
        obj = doc.addObject("Part::Box", d["nome"])
        obj.Length, obj.Width, obj.Height = d["dimensoes_mm"]
        obj.Placement.Base = App.Vector(*d["posicao_mm"])
        for campo, valor in (("AtividadeId", d["atividade_id"]),
                             ("ElementoId", "atividade:" + d["atividade_id"]),
                             ("UnidadePlanejamento", d["unidade_planejamento"]),
                             ("ModelId", pacote["meta"]["model_id"]),
                             ("FonteQuantidade", "planejamento sintetico publicado; nao derivado da forma CAD"),
                             ("TipoDado", "ficticio")):
            obj.addProperty("App::PropertyString", campo, "INFRA4D")
            setattr(obj, campo, valor)
        for campo, valor in (("QuantidadePlanejamento", d["quantidade_planejamento"]),
                             ("QuantidadeExecutada", d["quantidade_executada"])):
            obj.addProperty("App::PropertyFloat", campo, "INFRA4D")
            setattr(obj, campo, valor)
        grupo.addObject(obj)
    doc.recompute()
    r0, r1 = destino / "oae-r0.FCStd", destino / "oae-r1.FCStd"
    doc.saveAs(str(r0))
    volume_antes = float(doc.getObject("Tabuleiro").Shape.Volume) / 1e9
    doc.getObject("Tabuleiro").Height = 1250  # parâmetro CAD real, mm
    doc.recompute()
    doc.saveAs(str(r1))
    App.closeDocument(doc.Name)
    doc = App.openDocument(str(r1))
    objetos = [doc.getObject(d["nome"]) for d in componentes]
    for obj, d in zip(objetos, componentes):
        assert obj.TypeId == "Part::Box" and obj.AtividadeId == d["atividade_id"]
        assert obj.ElementoId == "atividade:" + d["atividade_id"] and obj.Shape.isValid()
        assert obj.QuantidadePlanejamento == d["quantidade_planejamento"]
        assert obj.QuantidadeExecutada == d["quantidade_executada"]
        assert obj.UnidadePlanejamento == d["unidade_planejamento"]
    alvo = doc.getObject("Tabuleiro")
    assert abs(alvo.Height.Value / 1000 - 1.25) <= tolerancia_m
    assert abs(alvo.Shape.BoundBox.ZLength / 1000 - 1.25) <= tolerancia_m
    step = destino / "oae-r1.step"
    Part.export(objetos, str(step))
    retorno_step = Part.Shape()
    retorno_step.read(str(step))
    assert retorno_step.isValid() and len(retorno_step.Solids) == 3
    volume_total = sum(o.Shape.Volume for o in objetos)
    assert abs(retorno_step.Volume - volume_total) / 1e9 <= tolerancia_volume
    composto = Part.makeCompound([o.Shape for o in objetos])
    for atributo in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"):
        assert abs(getattr(composto.BoundBox, atributo) - getattr(retorno_step.BoundBox, atributo)) / 1000 <= tolerancia_m
    revisao = copy.deepcopy(pacote)
    revisao["meta"].update(revision="freecad-r1", evidence_level="editar/salvar/reabrir via FreeCAD oficial",
                            source_version=".".join(App.Version()[:3]))
    por_id = {o.AtividadeId: o for o in objetos}
    for f in revisao["features"]:
        obj = por_id.get(f["properties"]["atividade_id"])
        if obj is None:
            continue
        vs, fs = obj.Shape.tessellate(1.0)
        malha = malha_em_metros(vs, fs, matriz)
        for eixo, letra in enumerate("XYZ"):
            for operador, sufixo in ((min, "Min"), (max, "Max")):
                valor = operador(v[eixo] for v in malha["vertices"])
                assert abs(valor - getattr(obj.Shape.BoundBox, letra + sufixo) / 1000) <= tolerancia_m
        f["properties"]["geometria_local_m"] = malha
    (destino / "revisao-freecad.geojson").write_text(json.dumps(revisao, ensure_ascii=False, indent=2), encoding="utf-8")
    rel = {"status": "pass", "aplicativo": "FreeCAD", "versao": ".".join(App.Version()[:3]),
           "modo": "runtime oficial headless; GUI nao observada", "salvo_reaberto": True,
           "arquivos": [str(r0), str(r1), str(step)], "objetos_parametricos": len(objetos),
           "atividade_editada": alvo.AtividadeId, "tipo_nativo": alvo.TypeId,
           "altura_antes_m": 1.0, "altura_depois_m": alvo.Height.Value / 1000,
           "volume_ilustrativo_antes_m3": volume_antes, "volume_ilustrativo_depois_m3": alvo.Shape.Volume / 1e9,
           "step_reimportado_solidos": len(retorno_step.Solids),
           "ids_publicacao_preservados": len(revisao["features"]), "ids_nativos_verificados": len(por_id),
           "quantidades_planejamento_alteradas": False, "gui_observada": False,
           "limites": limites,
           "limitacoes": "fragmento de tres componentes; STEP nao preserva arvore parametrica ou IDs customizados",
           "hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (r0, r1, step)}}
    (destino / "prova-freecad.json").write_text(json.dumps(rel, indent=2), encoding="utf-8")
    App.closeDocument(doc.Name)
    print(json.dumps(rel))
    return rel


if __name__ == "__main__":
    job = json.loads(Path(os.environ["INFRA4D_FREECAD_JOB"]).read_text(encoding="utf-8-sig"))
    executar_freecad(job["entrada"], job["destino"], job["limites"])
