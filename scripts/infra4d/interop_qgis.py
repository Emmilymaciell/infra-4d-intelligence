"""Executar SOMENTE no Python externo do QGIS; não importar QGIS no servidor.

python-qgis-ltr.bat interop_qgis.py --entrada atividades-qgis.geojson --destino pasta
Cria e reabre projetos nativos; GUI/engenheiro são etapas de evidência separadas.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path


def executar_qgis(entrada: Path, destino: Path) -> dict:
    from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsProject,
                           QgsVectorLayer, QgsVectorFileWriter, QgsLineSymbol,
                           QgsSingleSymbolRenderer)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QgsApplication([], False)
    app.initQgis()
    entrada, destino = entrada.resolve(), destino.resolve()
    destino.mkdir(parents=True, exist_ok=True)
    pacote = json.loads(entrada.read_text(encoding="utf-8-sig"))
    projeto = QgsProject.instance()
    layer = QgsVectorLayer(str(entrada), "Atividades — 100% FICTÍCIO", "ogr")
    if not layer.isValid():
        raise RuntimeError("QGIS não abriu GeoJSON")
    n = layer.featureCount()
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    # OGR pode deduzir EPSG:4979 de LineStringZ; o contrato só declara CRS
    # horizontal WGS84. Z é local sintético, NÃO altura elipsoidal homologada.
    layer.setCrs(crs)
    projeto.setCrs(crs)
    def gravar(fonte, nome):
        op = QgsVectorFileWriter.SaveVectorOptions()
        op.driverName = "GPKG"
        op.layerName = "atividades"
        arq = destino / f"{nome}.gpkg"
        if arq.exists():
            raise RuntimeError(f"saída já existe: {arq}; escolha pasta nova")
        res = QgsVectorFileWriter.writeAsVectorFormatV3(fonte, str(arq), projeto.transformContext(), op)
        if res[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(f"erro ao gravar GPKG: {res}")
        return arq
    r0 = gravar(layer, "ferrovia-r0")
    r1 = gravar(layer, "ferrovia-r1")
    del layer
    def salvar_projeto(gpkg, nome):
        projeto.clear()
        projeto.setCrs(crs)
        l = QgsVectorLayer(str(gpkg) + "|layername=atividades", "Atividades — quantidades editáveis — FICTÍCIO", "ogr")
        if not l.isValid() or l.featureCount() != n:
            raise RuntimeError("GPKG ilegível ou contagem divergente")
        l.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"line_color": "30,120,210", "line_width": "1"})))
        projeto.addMapLayer(l)
        projeto.setTitle("INFRA 4D — Ferrovia 100% FICTÍCIA — " + nome)
        projeto.viewSettings().setDefaultViewExtent(__import__("qgis.core", fromlist=["QgsReferencedRectangle"]).QgsReferencedRectangle(l.extent(), crs))
        qgz = destino / f"{nome}.qgz"
        if not projeto.write(str(qgz)):
            raise RuntimeError("QGIS não salvou projeto")
        return l, qgz
    _, q0 = salvar_projeto(r0, "ferrovia-r0")
    l, q1 = salvar_projeto(r1, "ferrovia-r1")
    id_campo = l.fields().indexFromName("atividade_id")
    qtd_campo = l.fields().indexFromName("quantidade_total")
    alvo = next((f for f in l.getFeatures() if f[id_campo] == "L3-S04-TER"), None)
    if alvo is None:
        alvo = next(f for f in l.getFeatures() if float(f[qtd_campo] or 0) > 0)
    antes = float(alvo[qtd_campo])
    depois = round(antes * 1.10, 3)
    if not l.startEditing() or not l.changeAttributeValue(alvo.id(), qtd_campo, depois) or not l.commitChanges():
        raise RuntimeError("QGIS não confirmou edição da quantidade")
    if not projeto.write(str(q1)):
        raise RuntimeError("não salvou revisão")
    # Fechar e reabrir do disco; valida a persistência, não só o objeto em memória.
    projeto.clear()
    if not projeto.read(str(q1)):
        raise RuntimeError("QGIS não reabriu .qgz")
    l = next(iter(projeto.mapLayers().values()))
    if not l.isValid() or l.crs().authid() != "EPSG:4326" or l.featureCount() != n:
        raise RuntimeError("reabertura não preservou camada/CRS/contagem")
    rev = copy.deepcopy(pacote)
    rev["meta"]["revision"] = "qgis-r1"
    rev["meta"]["evidence_level"] = "editar/salvar/reabrir via API oficial QGIS"
    por_id = {f["properties"]["atividade_id"]: f for f in rev["features"]}
    for f in l.getFeatures():
        p = por_id[str(f["atividade_id"])]["properties"]
        p["quantidade_total"] = float(f["quantidade_total"])
        por_id[p["atividade_id"]]["geometry"] = json.loads(f.geometry().asJson(15))
    rel = {"aplicativo": "QGIS", "versao": Qgis.QGIS_VERSION, "modo": "API oficial, sem interface gráfica",
           "arquivo_r0": str(q0), "arquivo_r1": str(q1), "feicoes": n, "crs": l.crs().authid(),
           "atividade_editada": str(alvo[id_campo]), "quantidade_antes": antes, "quantidade_depois": depois,
           "salvo_reaberto": True, "gui_observada": False,
           "limitacoes": "georreferência e quantidades fictícias; nenhum levantamento real"}
    (destino / "revisao-qgis.geojson").write_text(json.dumps(rev, ensure_ascii=False, indent=2), encoding="utf-8")
    (destino / "prova-qgis.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    projeto.clear()
    return rel


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", type=Path, required=True)
    p.add_argument("--destino", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(executar_qgis(args.entrada, args.destino), ensure_ascii=False))
