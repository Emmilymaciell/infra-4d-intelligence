"""Gera pacote local de autoria; executar apps externos é uma etapa separada.

python -m infra4d.interop_pacote --destino output/releases/demo-ferrovia-vNext
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import csv
import io
from html import escape

from .cenarios import CENARIOS, Projeto, executar
from .interop import aplicar_revisao, exportar_pacote


def registrar_retorno(projeto: Projeto, baseline: Path, revisao: Path, saida: Path) -> dict:
    """Registra uma prova de retorno sobre cópia; não publica revisão na API."""
    b = json.loads(Path(baseline).read_text(encoding="utf-8-sig"))
    r = json.loads(Path(revisao).read_text(encoding="utf-8-sig"))
    _, relatorio = aplicar_revisao(projeto, b, r)
    saida = Path(saida)
    if saida.exists():
        raise FileExistsError("relatório de retorno já existe; escolha revisão nova")
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return relatorio


def complementar(projeto: Projeto, destino: Path, incluir_ifc: bool = False) -> dict:
    """Acrescenta intercâmbio real pelos exportadores existentes, sem sobrescrever.

    IFC/GLB opcionais demandam IfcOpenShell. Não cria extensões nativas fictícias.
    """
    from .importadores.mspdi import exportar_mspdi
    from .importadores.xer_exportar import exportar_xer
    from .gis import geojson
    resultados = {c: executar(projeto, c) for c in CENARIOS}
    destino = Path(destino)
    escritos = []
    def gravar(rel, valor):
        p = destino / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            return
        p.write_text(valor, encoding="utf-8")
        escritos.append(rel)
    for c in ("linha_base", "construtora", "independente"):
        gravar(f"05-cronograma/{c}.xml", exportar_mspdi(projeto, resultados[c]))
        gravar(f"05-cronograma/{c}.xer", exportar_xer(projeto, resultados[c]))
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=";")
    w.writerow(("atividade_id", "servico_id", "lote_id", "unidade", "quantidade_total", "quantidade_executada", "fonte", "ficticio"))
    for a in projeto.dados["atividades"]:
        w.writerow((a["id"], a.get("servico_id"), a.get("lote_id"), a.get("unidade"),
                    a.get("quantidade_total"), a.get("quantidade_executada"), "dataset sintetico publicado", True))
    gravar("06-quantitativos/quantidades-ficticias.csv", "\ufeff" + buf.getvalue())
    gravar("01-gis-qgis/eixo.geojson", json.dumps(geojson(projeto, resultados, "eixo"), ensure_ascii=False, indent=2))
    linhas = "".join(f"<tr><td>{escape(c)}</td><td>{escape(resultados[c]['termino'])}</td></tr>" for c in resultados)
    gravar("08-relatorios/resumo-cpm.html", "<!doctype html><html lang='pt-BR'><meta charset='utf-8'><title>INFRA 4D — resumo</title>"
           "<h1>Resumo do motor CPM — 100% FICTÍCIO</h1><p>Datas calculadas pelo motor existente; não é parecer de engenharia.</p>"
           "<table><tr><th>Cenário</th><th>Término ISO</th></tr>" + linhas + "</table></html>")
    gravar("02-cad-parametrico/LEIAME.txt", "FreeCAD: instalação/autorização e edição nativa pendentes. Nenhum FCStd/STEP produzido nesta etapa.\n")
    gravar("03-bim-bonsai/LEIAME.txt", "IFC gerado pelo exportador existente; Bonsai ainda não comprovado. Não confundir parser com autoria GUI.\n")
    gravar("05-cronograma/LEIAME.txt", "MSPDI/XER gerados pelos exportadores existentes. ProjectLibre/P6/Project ainda sem prova de abertura e edição.\n")
    gravar("06-quantitativos/LEIAME.txt", "CSV com unidades e origem. Não é ODS/XLSX nativo com fórmulas, ainda pendente de validação em Calc.\n")
    if incluir_ifc:
        from .ifc.exportar import construir
        from .ifc.importar import exportar_glb, tabela_vinculo
        pifc = destino / "03-bim-bonsai/ferrovia-ficticia.ifc"
        f, resumo = construir(projeto.dados)
        if not pifc.exists():
            f.write(str(pifc))
            escritos.append("03-bim-bonsai/ferrovia-ficticia.ifc")
        gravar("07-federacao-web/vinculos-ifc.json", json.dumps(tabela_vinculo(f), ensure_ascii=False, indent=2))
        glb = destino / "07-federacao-web/ferrovia-ifc.glb"
        if not glb.exists():
            local, _ = construir(projeto.dados, incluir_4d=False, posicionamento="local")
            exportar_glb(local, glb)
            escritos.append("07-federacao-web/ferrovia-ifc.glb")
        gravar("08-relatorios/exportacao-ifc.json", json.dumps(resumo, ensure_ascii=False, indent=2))
    return {"arquivos_acrescentados": escritos, "ifc_solicitado": incluir_ifc,
            "apps_gui_homologados": False, "nativos_nao_inventados": True}


def gerar(projeto: Projeto, destino: Path) -> dict:
    destino = Path(destino)
    partes = ("00-manifesto", "01-gis-qgis", "02-cad-parametrico", "03-bim-bonsai", "04-visual-blender",
              "05-cronograma", "06-quantitativos", "07-federacao-web", "08-relatorios", "09-evidencias", "10-demo")
    destino.mkdir(parents=True, exist_ok=True)
    for nome in partes:
        (destino / nome).mkdir(exist_ok=True)
    for app, pasta, arquivo in (("QGIS", "01-gis-qgis", "atividades-qgis.geojson"),
                                ("Blender", "04-visual-blender", "atividades-blender.geojson")):
        alvo = destino / pasta / arquivo
        if alvo.exists():
            raise FileExistsError(f"pacote já existe: {alvo}; use destino novo para preservar revisão")
        alvo.write_text(json.dumps(exportar_pacote(projeto, app), ensure_ascii=False, indent=2), encoding="utf-8")
    for nome, pasta in (("interop_qgis.py", "01-gis-qgis"), ("interop_blender.py", "04-visual-blender")):
        shutil.copyfile(Path(__file__).with_name(nome), destino / pasta / nome)
    manifesto = {"schema": "infra4d.pacote/1", "ficticio": True,
                 "aviso": "100% FICTÍCIO. Fonte nativa e evidências só existem após executar o aplicativo correspondente.",
                 "estado_inicial": {"QGIS": "formato gerado", "Blender": "formato gerado",
                                    "Bonsai": "não validado", "FreeCAD": "não validado", "ProjectLibre": "não validado"},
                 "origem": "dataset sintético publicado", "nenhum_dado_prog": True,
                 "licencas": "QGIS/Blender usados como aplicativos externos GPL; não redistribuídos neste pacote",
                 "formatos": "GeoJSON de troca; .qgz/.gpkg/.blend/.glb produzidos somente pelos aplicativos reais"}
    (destino / "00-manifesto" / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    (destino / "LEIAME.txt").write_text(
        "INFRA 4D — 100% FICTÍCIO\n\n"
        "1. QGIS: executar o script interop_qgis.py no Python do QGIS com --entrada atividades-qgis.geojson --destino <pasta nova>.\n"
        "2. Blender: blender --background --factory-startup --python interop_blender.py -- --entrada atividades-blender.geojson --destino <pasta nova>.\n"
        "3. Abrir os nativos na GUI, conferir e registrar a evidência separadamente.\n"
        "4. Enviar baseline e revisao para reconciliação; nunca sobrescrever a obra congelada.\n"
        "A API oficial em background comprova o motor do app. Não comprova observação GUI nem homologação de engenharia.\n"
        "QGIS: edição de quantidade de planejamento. Blender: edição de escala ilustrativa; nenhuma quantidade inferida.\n"
        "CRS GIS WGS84 EPSG:4326 com âncora FICTÍCIA; modelo local métrico sem datum vertical oficial.\n",
        encoding="utf-8")
    hashes = []
    for p in sorted(destino.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            hashes.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(destino).as_posix()}")
    (destino / "00-manifesto" / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    return manifesto


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destino", type=Path)
    p.add_argument("--baseline", type=Path)
    p.add_argument("--revisao", type=Path)
    p.add_argument("--relatorio", type=Path)
    p.add_argument("--complementar", action="store_true")
    p.add_argument("--incluir-ifc", action="store_true")
    args = p.parse_args()
    if args.destino:
        resultado = (complementar(Projeto.carregar(), args.destino, args.incluir_ifc) if args.complementar
                     else gerar(Projeto.carregar(), args.destino))
    elif args.baseline and args.revisao and args.relatorio:
        resultado = registrar_retorno(Projeto.carregar(), args.baseline, args.revisao, args.relatorio)
    else:
        p.error("use --destino ou --baseline + --revisao + --relatorio")
    print(json.dumps(resultado, ensure_ascii=False))
