"""Metadados CAD declarados, separados das quantidades contratuais do planejamento.

Valida estrutura, identidade e cobertura das faces. Não homologa BRep ou arquivo
nativo pelo simples recebimento de JSON e não converte volume em medição.
"""
from __future__ import annotations

import math


def _texto(v, nome, maximo=512):
    if not isinstance(v, str) or not v.strip() or len(v) > maximo:
        raise ValueError(f"{nome} deve ser texto não vazio de até {maximo} caracteres")


def _numero(v, nome, positivo=False):
    if type(v) not in (int, float) or not math.isfinite(v) or (v <= 0 if positivo else v < 0):
        raise ValueError(f"{nome} deve ser número finito {'positivo' if positivo else 'não negativo'}")
    return float(v)


def validar_componentes(malha, componentes, atividade_id):
    """Soma os derivados declarados uma vez por peça, sem multiplicar por qtd planejada."""
    if not isinstance(malha, dict) or not isinstance(malha.get("faces"), list):
        raise ValueError("componentes exigem malha com faces")
    if not isinstance(componentes, list) or not 1 <= len(componentes) <= 500:
        raise ValueError("componentes deve ter entre 1 e 500 peças")
    ids, proxima = set(), 0
    volumes, areas, anteriores = [], [], []
    for c in componentes:
        if not isinstance(c, dict):
            raise ValueError("componente deve ser objeto")
        cid = c.get("componente_id")
        _texto(cid, "componente_id")
        if cid in ids:
            raise ValueError("componente_id duplicado")
        ids.add(cid)
        _texto(c.get("nome"), "nome", 256)
        _texto(c.get("material"), "material", 256)
        if c.get("atividade_id") != atividade_id or c.get("tipo_nativo") != "Part::Box":
            raise ValueError("atividade ou tipo nativo divergente")
        inicio, quantidade = c.get("face_inicio"), c.get("face_quantidade")
        if type(inicio) is not int or type(quantidade) is not int or inicio != proxima or quantidade <= 0:
            raise ValueError("intervalos de faces devem ser consecutivos, sem lacunas ou sobreposição")
        proxima = inicio + quantidade
        if proxima > len(malha["faces"]):
            raise ValueError("intervalo fora das faces da malha")
        parametros = c.get("parametros_mm")
        if not isinstance(parametros, dict) or set(parametros) != {"Length", "Width", "Height"}:
            raise ValueError("parametros_mm exige Length, Width e Height")
        for nome, valor in parametros.items():
            _numero(valor, nome, positivo=True)
        cor = c.get("cor_rgb")
        if not isinstance(cor, list) or len(cor) != 3:
            raise ValueError("cor_rgb deve ter três canais")
        for canal in cor:
            if _numero(canal, "canal RGB") > 1:
                raise ValueError("cor_rgb fora de 0 a 1")
        volumes.append(_numero(c.get("volume_m3"), "volume_m3"))
        areas.append(_numero(c.get("area_m2"), "area_m2"))
        if "volume_anterior_m3" in c:
            anteriores.append(_numero(c["volume_anterior_m3"], "volume_anterior_m3"))
    if proxima != len(malha["faces"]):
        raise ValueError("componentes não cobrem todas as faces")
    try:
        volume, area, anterior = math.fsum(volumes), math.fsum(areas), math.fsum(anteriores)
    except OverflowError:
        raise ValueError("soma geométrica fora do intervalo numérico") from None
    resumo = {"volume_m3": volume, "area_m2": area,
              "componentes_contagem": len(componentes), "natureza": "geometrico_declarado_ficticio",
              "metodo": "soma de Shape.Volume/Shape.Area informados pelo FreeCAD; não é medição contratual"}
    if anteriores:
        if len(anteriores) != len(componentes):
            raise ValueError("volume anterior deve estar presente para todas as peças ou nenhuma")
        resumo["volume_anterior_m3"] = anterior
        resumo["delta_volume_m3"] = resumo["volume_m3"] - resumo["volume_anterior_m3"]
    if not all(math.isfinite(v) for v in resumo.values() if type(v) in (int, float)):
        raise ValueError("soma geométrica fora do intervalo numérico")
    return resumo
