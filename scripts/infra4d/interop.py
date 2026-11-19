"""Publicação e reconciliação de modelos fictícios, sem dependência de aplicativo GPL.

O arquivo nativo permanece a fonte da geometria. Uma revisão recebida é proposta,
nunca sobrescreve a obra publicada e só altera planejamento após aprovação explícita.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

from .cenarios import CENARIOS, Projeto, executar
from .gis import geojson
from .cad_contrato import validar_componentes

SCHEMA = "infra4d.interop/1"
APLICATIVOS = ("QGIS", "Blender", "FreeCAD")
IMUTAVEIS = ("id", "atividade_id", "elemento_id", "servico_id", "lote_id", "segmento_id",
             "km_ini", "km_fim", "unidade", "quantidade_executada", "origem_evidencia",
             "tipo_dado", "classificacao", "visibilidade_demo")


class ErroInterop(ValueError):
    """Pacote ou revisão incompatível com a publicação de origem."""


def checksum(valor: object) -> str:
    try:
        bruto = json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise ErroInterop("conteúdo não é JSON finito") from None
    return hashlib.sha256(bruto).hexdigest()


def _numero(valor, nome, minimo=0):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor) or valor < minimo:
        raise ErroInterop(f"{nome} deve ser número finito >= {minimo}")
    return float(valor)


def _ficticio(projeto):
    if projeto.dados.get("meta", {}).get("ficticio") is not True:
        raise ErroInterop("adaptador de demonstração aceita somente meta.ficticio is True")


def _equivalente(a, b):
    """Igualdade JSON: 1 e 1.0 equivalem; true e 1 NUNCA equivalem.

    JavaScript normaliza números integrais ao serializar JSON. A identidade da
    publicação continua protegida pelo checksum original enviado como texto.
    """
    if type(a) in (int, float) and type(b) in (int, float):
        return math.isfinite(a) and math.isfinite(b) and a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_equivalente(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_equivalente(x, y) for x, y in zip(a, b))
    return a == b


def exportar_pacote(projeto: Projeto, source_app: str = "QGIS", model_id: str | None = None,
                    revision: str = "r0") -> dict:
    """FeatureCollection RFC 7946 com contrato, vínculos e quantidades de planejamento.

    Uma feição representa uma atividade linear, não uma peça IFC. ``elemento_id``
    declara esse nível de agregação; não é apresentado como GlobalId IFC.
    """
    _ficticio(projeto)
    if source_app not in APLICATIVOS:
        raise ErroInterop("source_app deve ser QGIS, Blender ou FreeCAD")
    if not isinstance(revision, str) or not revision.strip():
        raise ErroInterop("revision deve ser texto não vazio")
    obra = projeto.dados["ferrovia"].get("id", "obra-ficticia")
    model_id = model_id or f"{obra}:atividades-lineares"
    if not isinstance(model_id, str) or not model_id.strip():
        raise ErroInterop("model_id deve ser texto não vazio")
    resultados = {c: executar(projeto, c) for c in CENARIOS}
    pacote = geojson(projeto, resultados, "atividades")
    for f in pacote["features"]:
        p = f["properties"]
        a = projeto.atividades[p["id"]]
        p.update(atividade_id=a["id"], elemento_id=f"atividade:{a['id']}",
                 unidade=a.get("unidade") or "sem_quantidade",
                 quantidade_total=a.get("quantidade_total") or 0,
                 quantidade_executada=a.get("quantidade_executada") or 0,
                 origem_evidencia="dataset sintético publicado; quantidade de planejamento, não volume da malha",
                 tipo_dado="ficticio", classificacao="publico-ficticio", visibilidade_demo=True)
        # Coordenadas locais servem só à autoria ilustrativa Blender; o CRS GIS permanece WGS84.
        pontos = projeto.dados["alinhamento"]["pontos"]
        def ponto(km):
            for pa, pb in zip(pontos, pontos[1:]):
                if pa[0] <= km <= pb[0]:
                    t = (km - pa[0]) / (pb[0] - pa[0])
                    return [pa[j] + t * (pb[j] - pa[j]) for j in (1, 2, 3)]
            raise ErroInterop("atividade fora do eixo")
        p["pontos_locais_m"] = [ponto(a["km_ini"]), ponto(a["km_fim"])]
    pacote["meta"].update(schema=SCHEMA, source_app=source_app, model_id=model_id, revision=revision,
                           base_checksum=checksum(projeto.dados), crs="EPSG:4326",
                           datum_vertical="local sintético; sem datum vertical oficial",
                           units="coordenadas GIS em graus; autoria local em metros; quantidade por unidade",
                           evidence_level="formato gerado", source_version="infra4d-beta",
                           geometry_authority="arquivo nativo; geometria ilustrativa não define quantidade contratual")
    pacote["meta"]["publication_checksum"] = checksum(pacote)
    return pacote


def _indexar(pacote):
    if not isinstance(pacote, dict) or pacote.get("type") != "FeatureCollection":
        raise ErroInterop("esperado FeatureCollection")
    feats = pacote.get("features")
    if not isinstance(feats, list) or not feats or len(feats) > 10000:
        raise ErroInterop("features deve ter entre 1 e 10000 feições")
    saida = {}
    for f in feats:
        if not isinstance(f, dict) or f.get("type") != "Feature" or not isinstance(f.get("properties"), dict):
            raise ErroInterop("feição inválida")
        p = f["properties"]
        aid = p.get("atividade_id")
        if not isinstance(aid, str) or not aid or aid in saida:
            raise ErroInterop("atividade_id ausente ou duplicado")
        checksum(f)  # recusa NaN inclusive em geometria/propriedades
        geom = f.get("geometry")
        if not isinstance(geom, dict) or geom.get("type") != "LineString":
            raise ErroInterop("geometria deve ser LineString")
        coords = geom.get("coordinates")
        if not isinstance(coords, list) or not 2 <= len(coords) <= 10000:
            raise ErroInterop("LineString exige entre 2 e 10000 posições")
        for pos in coords:
            if not isinstance(pos, list) or len(pos) not in (2, 3):
                raise ErroInterop("posição GIS inválida")
            for v in pos:
                _numero(v, "coordenada", -1e9)
            if not (-180 <= pos[0] <= 180 and -90 <= pos[1] <= 90):
                raise ErroInterop("coordenadas fora de EPSG:4326")
        saida[aid] = f
    return saida


def _validar_malha(m):
    if not isinstance(m, dict) or m.get("unidade") != "m" or m.get("ilustrativa") is not True:
        raise ErroInterop("malha deve declarar unidade m e ilustrativa true")
    vs, fs, matriz = m.get("vertices"), m.get("faces"), m.get("matrix_world")
    if not isinstance(vs, list) or not 3 <= len(vs) <= 10000:
        raise ErroInterop("malha exige 3 a 10000 vértices")
    for v in vs:
        if not isinstance(v, list) or len(v) != 3:
            raise ErroInterop("vértice local deve ter xyz")
        for n in v:
            _numero(n, "vértice local", -1e9)
    if not isinstance(fs, list) or not 1 <= len(fs) <= 10000:
        raise ErroInterop("faces locais inválidas")
    for face in fs:
        if not isinstance(face, list) or not 3 <= len(face) <= 16 or any(type(i) is not int or not 0 <= i < len(vs) for i in face):
            raise ErroInterop("índice de face fora da malha")
    if not isinstance(matriz, list) or len(matriz) != 4 or any(not isinstance(l, list) or len(l) != 4 for l in matriz):
        raise ErroInterop("matrix_world deve ser 4x4")
    for linha in matriz:
        for n in linha:
            _numero(n, "matriz local", -1e9)
    if matriz[3] != [0, 0, 0, 1]:
        raise ErroInterop("matrix_world deve ser afim")


def reconciliar_revisao(projeto: Projeto, baseline: dict, revisao: dict) -> dict:
    """Valida fidelidade e calcula diff. Não executa merge nem altera ``projeto``."""
    _ficticio(projeto)
    b, r = _indexar(baseline), _indexar(revisao)
    bm, rm = baseline.get("meta", {}), revisao.get("meta", {})
    if not isinstance(bm, dict) or not isinstance(rm, dict):
        raise ErroInterop("meta deve ser objeto JSON")
    if bm.get("schema") != SCHEMA or rm.get("schema") != SCHEMA:
        raise ErroInterop("schema de intercâmbio incompatível")
    if bm.get("base_checksum") != checksum(projeto.dados):
        raise ErroInterop("obra mudou desde a publicação; revisão exige nova base")
    for campo in ("base_checksum", "publication_checksum", "model_id", "source_app", "crs", "datum_vertical",
                  "units", "georreferencia", "geometry_authority", "origem", "origem_evidencia"):
        if not _equivalente(rm.get(campo), bm.get(campo)):
            raise ErroInterop(f"metadado de origem divergente: {campo}")
    # O cliente não pode escolher uma baseline falsa que ignore vínculos/propriedades.
    original = exportar_pacote(projeto, bm.get("source_app"), bm.get("model_id"), bm.get("revision"))
    if not _equivalente(baseline, original):
        raise ErroInterop("baseline adulterada ou não reproduzível")
    if rm.get("ficticio") is not True or bm.get("crs") != "EPSG:4326":
        raise ErroInterop("marca fictícia/CRS inválidos")
    if not isinstance(rm.get("revision"), str) or rm["revision"] == bm.get("revision") or not rm["revision"].strip():
        raise ErroInterop("revisão deve ter identificador novo não vazio")
    if set(b) != set(r):
        raise ErroInterop("IDs adicionados/removidos exigem mapeamento manual; conjunto deve ser preservado")
    mudancas, derivados, ids_componentes = [], {}, set()
    for aid, bf in b.items():
        rf = r[aid]
        bp, rp = bf["properties"], rf["properties"]
        for campo in IMUTAVEIS:
            if type(rp.get(campo)) is not type(bp.get(campo)) or rp.get(campo) != bp.get(campo):
                # JSON números podem ser int ou float após OGR; booleanos nunca são números.
                numeros = (type(rp.get(campo)) in (int, float) and type(bp.get(campo)) in (int, float))
                if not (numeros and rp[campo] == bp[campo]):
                    raise ErroInterop(f"vínculo/propriedade protegida divergente: {aid}.{campo}")
        qtd = _numero(rp.get("quantidade_total"), "quantidade_total")
        if qtd < bp["quantidade_executada"]:
            raise ErroInterop(f"quantidade_total menor que executada: {aid}")
        if qtd != bp["quantidade_total"]:
            if not projeto.atividades[aid].get("quantidade_total"):
                raise ErroInterop(f"atividade sem quantidade mensurável: {aid}")
            mudancas.append({"atividade_id": aid, "campo": "quantidade_total", "antes": bp["quantidade_total"],
                             "depois": qtd, "unidade": bp["unidade"], "efeito": "planejamento requer aprovação explícita"})
        if not _equivalente(bf["geometry"], rf["geometry"]):
            mudancas.append({"atividade_id": aid, "campo": "geometry", "efeito": "apenas geometria federada; quantidade não inferida"})
        if rp.get("transformacao_visual") != bp.get("transformacao_visual"):
            v = rp.get("transformacao_visual")
            if not isinstance(v, dict) or set(v) != {"escala"} or not isinstance(v["escala"], list) or len(v["escala"]) != 3:
                raise ErroInterop("transformacao_visual deve declarar escala xyz")
            for escala in v["escala"]:
                _numero(escala, "escala", 1e-6)
            mudancas.append({"atividade_id": aid, "campo": "transformacao_visual", "antes": None,
                             "depois": v, "efeito": "volume ilustrativo; quantidade de planejamento preservada"})
        if not _equivalente(rp.get("geometria_local_m"), bp.get("geometria_local_m")):
            if bm["source_app"] not in ("Blender", "FreeCAD"):
                raise ErroInterop("malha local só é aceita pelos adaptadores Blender e FreeCAD")
            _validar_malha(rp.get("geometria_local_m"))
            mudancas.append({"atividade_id": aid, "campo": "geometria_local_m",
                             "efeito": "malha nativa ilustrativa; nenhuma quantidade inferida"})
        if "componentes_nativos" in rp:
            if bm["source_app"] != "FreeCAD" or "geometria_local_m" not in rp:
                raise ErroInterop("componentes nativos exigem malha do adaptador FreeCAD")
            _validar_malha(rp["geometria_local_m"])
            try:
                derivados[aid] = validar_componentes(rp["geometria_local_m"], rp["componentes_nativos"], aid)
            except ValueError as e:
                raise ErroInterop(f"componentes CAD recusados: {e}") from None
            for componente in rp["componentes_nativos"]:
                cid = componente["componente_id"]
                if cid in ids_componentes:
                    raise ErroInterop("componente_id duplicado entre atividades")
                ids_componentes.add(cid)
            if not _equivalente(rp["componentes_nativos"], bp.get("componentes_nativos")):
                mudancas.append({"atividade_id": aid, "campo": "componentes_nativos",
                                 "efeito": "propriedades e derivados CAD declarados; planejamento preservado"})
    return {"schema": SCHEMA, "status": "revisao_validada_aguarda_aprovacao", "source_app": bm["source_app"],
            "model_id": bm["model_id"], "revision": rm["revision"], "base_checksum": bm["base_checksum"],
            "revision_checksum": checksum(revisao), "ids_preservados": len(b), "mudancas": mudancas,
            "aprovacao_necessaria": True, "dataset_original_alterado": False,
            "aviso": "100% FICTÍCIO. Geometria ilustrativa não é projeto executivo nem medição contratual.",
            **({"derivados_geometricos": derivados} if derivados else {})}


def aplicar_revisao(projeto: Projeto, baseline: dict, revisao: dict) -> tuple[Projeto, dict]:
    """Merge explícito em CÓPIA; o chamador deve exigir aprovação antes de chamar.

    Só quantidade_total é aceita como alteração de planejamento. Coordenadas/escala
    são devolvidas na revisão federada, sem redesenhar o eixo nem estimar quantidade.
    """
    relatorio = reconciliar_revisao(projeto, baseline, revisao)
    dados = copy.deepcopy(projeto.dados)
    por_id = {a["id"]: a for a in dados["atividades"]}
    for m in relatorio["mudancas"]:
        if m["campo"] == "quantidade_total":
            por_id[m["atividade_id"]]["quantidade_total"] = m["depois"]
    novo = Projeto(dados)
    antes, depois = executar(projeto, "independente"), executar(novo, "independente")
    relatorio.update(status="aplicada_em_copia", checksum_resultado=checksum(dados),
                     termino_antes=antes["termino"], termino_depois=depois["termino"],
                     dataset_original_alterado=False)
    return novo, relatorio
