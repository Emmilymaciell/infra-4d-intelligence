"""Script externo bpy: .blend nativo + GLB e retorno de revisão ilustrativa.

blender --background --factory-startup --python interop_blender.py -- --entrada ... --destino ...
Não alega Bonsai/IFC paramétrico. Não altera quantidade de planejamento pela escala.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import sys


def executar_blender(entrada: Path, destino: Path):
    import bpy
    entrada, destino = entrada.resolve(), destino.resolve()
    destino.mkdir(parents=True, exist_ok=True)
    r0, r1 = destino / "ferrovia-r0.blend", destino / "ferrovia-r1.blend"
    if r0.exists() or r1.exists():
        raise RuntimeError("arquivos nativos já existem; escolha pasta nova")
    pacote = json.loads(entrada.read_text(encoding="utf-8-sig"))
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1
    bpy.context.scene["aviso"] = "100% FICTÍCIO. Malhas ilustrativas editáveis; não é modelo executivo nem Bonsai."
    bpy.context.scene["model_id"] = pacote["meta"]["model_id"]
    materiais = {}
    for f in pacote["features"]:
        p = f["properties"]
        a, b = p["pontos_locais_m"]
        L = math.dist(a, b)
        sid = p["servico_id"]
        if sid not in materiais:
            mat = bpy.data.materials.new("Serviço " + sid)
            cor = {"TER": (.38, .23, .10, 1), "LAS": (.35, .38, .4, 1), "TRI": (.16, .2, .23, 1)}.get(sid, (.25, .5, .35, 1))
            mat.diffuse_color = cor
            materiais[sid] = mat
        # Uma faixa autorável por atividade, explicitamente ilustrativa, com unidades m.
        vertices = [(x, y, z) for x in (-L/2, L/2) for y in (-4, 4) for z in (-.2, .2)]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        mesh = bpy.data.meshes.new(p["elemento_id"])
        mesh.from_pydata(vertices, [], faces)
        obj = bpy.data.objects.new(p["elemento_id"], mesh)
        bpy.context.collection.objects.link(obj)
        obj.location = tuple((a[i] + b[i]) / 2 for i in range(3))
        obj.rotation_euler[2] = math.atan2(b[1] - a[1], b[0] - a[0])
        for campo in ("atividade_id", "elemento_id", "servico_id", "lote_id", "unidade", "quantidade_total", "quantidade_executada"):
            if p.get(campo) is not None:
                obj[campo] = p[campo]
        obj["tipo_dado"] = "ficticio"
        obj["geometria"] = "faixa ilustrativa agregada por atividade; quantidade não derivada da malha"
        obj.data.materials.append(materiais[sid])
    bpy.ops.wm.save_as_mainfile(filepath=str(r0))
    alvo = bpy.data.objects.get("atividade:L3-S04-TER") or next(o for o in bpy.data.objects if "atividade_id" in o)
    alvo_id = alvo["atividade_id"]
    alvo.scale.z = 1.25
    alvo["nota_revisao"] = "espessura ilustrativa +25%; quantidade de planejamento inalterada"
    bpy.ops.wm.save_as_mainfile(filepath=str(r1))
    bpy.ops.wm.open_mainfile(filepath=str(r1))
    objetos = {o["atividade_id"]: o for o in bpy.data.objects if "atividade_id" in o}
    if len(objetos) != len(pacote["features"]) or abs(objetos[alvo_id].scale.z - 1.25) > 1e-6:
        raise RuntimeError("Blender não preservou IDs/edição ao reabrir")
    glb = destino / "ferrovia-r1.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", export_extras=True)
    rev = copy.deepcopy(pacote)
    rev["meta"]["revision"] = "blender-r1"
    rev["meta"]["evidence_level"] = "editar/salvar/reabrir via bpy oficial"
    for f in rev["features"]:
        o = objetos[f["properties"]["atividade_id"]]
        f["properties"]["geometria_local_m"] = {
            "vertices": [list(v.co) for v in o.data.vertices],
            "faces": [list(p.vertices) for p in o.data.polygons],
            "matrix_world": [list(linha) for linha in o.matrix_world],
            "unidade": "m", "origem": "Blender .blend reaberto", "ilustrativa": True}
        if tuple(o.scale) != (1, 1, 1):
            f["properties"]["transformacao_visual"] = {"escala": list(o.scale)}
    rel = {"aplicativo": "Blender", "versao": bpy.app.version_string,
           "modo": "aplicativo oficial background/bpy, sem GUI observada", "arquivo_r0": str(r0), "arquivo_r1": str(r1),
           "glb": str(glb), "objetos_vinculados": len(objetos), "salvo_reaberto": True, "gui_observada": False,
           "atividade_editada": alvo_id, "escala_z_depois": float(objetos[alvo_id].scale.z),
           "quantidade_planejamento_alterada": False, "bonsai_validado": False,
           "limitacoes": "faixas de atividade ilustrativas; escala visual não é quantidade de projeto"}
    (destino / "revisao-blender.geojson").write_text(json.dumps(rev, ensure_ascii=False, indent=2), encoding="utf-8")
    (destino / "prova-blender.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(rel, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, required=True)
    p.add_argument("--destino", type=Path, required=True)
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    executar_blender(args.entrada, args.destino)
