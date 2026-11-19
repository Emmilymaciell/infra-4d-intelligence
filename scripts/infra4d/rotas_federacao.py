"""Revisões fictícias isoladas: receber, conferir e publicar sem substituir a demo.

O arquivo nativo permanece a fonte da geometria. A publicação é explícita, em
memória, e não aplica quantidades da revisão ao projeto de referência.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading

from fastapi import FastAPI, HTTPException, Query, Request

from .calendario import ordinal
from .cenarios import executar
from .gis import georref_da_obra
from .interop import ErroInterop, aplicar_revisao, exportar_pacote
from .obra import tipo_obra

MAX_BYTES = 10 * 1024 * 1024
MAX_REVISOES = 12


def _sem_constante(texto):
    raise ValueError(f"número JSON inválido: {texto}")


def _pares_unicos(pares):
    resultado = {}
    for chave, valor in pares:
        if chave in resultado:
            raise ValueError(f"chave JSON repetida: {chave}")
        resultado[chave] = valor
    return resultado


def _publico(registro, completo=False):
    chaves = ("id", "obra", "source_app", "revision", "termino_antes", "termino_depois",
              "delta_dias_corridos", "relatorio", "aviso")
    saida = {k: registro[k] for k in chaves}
    if completo:
        saida.update({k: registro[k] for k in ("geojson", "linhas_locais", "resultado_4d")})
    return copy.deepcopy(saida)


def ligar(app: FastAPI, obter_estado):
    """Cada app possui seu acervo em memória; sem banco global compartilhado."""
    registros = {}
    trava = threading.Lock()

    @app.get("/api/federacao/exportar", tags=["federação experimental"],
             responses={404: {"description": "Obra inexistente"},
                        422: {"description": "Aplicativo ou dataset não permitido"}})
    def exportar(obra: str | None = None, source_app: str = Query("QGIS", max_length=50)):
        """Gera GeoJSON editável com identidade, unidades e checksum da base fictícia."""
        try:
            return exportar_pacote(obter_estado(obra).projeto, source_app=source_app)
        except ErroInterop as e:
            raise HTTPException(422, str(e)) from None

    @app.get("/api/federacao/revisoes", tags=["federação experimental"],
             responses={404: {"description": "Obra inexistente"}})
    def listar(obra: str | None = None):
        """Lista revisões publicadas neste processo; reiniciar o servidor limpa o acervo."""
        est = obter_estado(obra)
        chave = id(est)
        with trava:
            return {"persistido": False, "revisoes": [_publico(r) for (o, _), r in registros.items() if o == chave]}

    @app.get("/api/federacao/revisoes/{revisao_id}", tags=["federação experimental"],
             responses={404: {"description": "Obra ou revisão inexistente"}})
    def consultar(revisao_id: str, obra: str | None = None):
        """Devolve geometria publicada e cálculo da revisão isolada, sem alterar a referência."""
        est = obter_estado(obra)
        with trava:
            registro = registros.get((id(est), revisao_id))
            if registro is None:
                raise HTTPException(404, "revisão não publicada nesta obra/processo")
            return _publico(registro, completo=True)

    @app.post("/api/federacao/revisoes", tags=["federação experimental"],
              responses={400: {"description": "JSON inválido ou corpo vazio"},
                         404: {"description": "Obra inexistente"},
                         409: {"description": "Acervo em memória cheio"},
                         413: {"description": "Corpo maior que 10 MiB"},
                         422: {"description": "Revisão, identidade, quantidade ou rede recusada"}})
    async def receber(request: Request, obra: str | None = None, publicar: bool = False):
        """Confere baseline+revisao; publicar=true guarda uma revisão isolada em memória.

        Corpo: {baseline: FeatureCollection, revisao: FeatureCollection}. Quantidades
        explícitas recalculam somente a cópia; geometria ilustrativa não gera medição.
        """
        est = obter_estado(obra)
        corpo = bytearray()
        async for parte in request.stream():
            if len(corpo) + len(parte) > MAX_BYTES:
                raise HTTPException(413, "revisão maior que 10 MiB")
            corpo.extend(parte)
        try:
            payload = json.loads(corpo, parse_constant=_sem_constante, object_pairs_hook=_pares_unicos)
        except (ValueError, UnicodeError, RecursionError):  # RecursionError: aninhamento excessivo (Python 3.12)
            raise HTTPException(400, "JSON inválido: use números finitos e chaves únicas") from None
        if not isinstance(payload, dict) or set(payload) != {"baseline", "revisao"}:
            raise HTTPException(422, "envie exatamente baseline e revisao")
        try:
            novo, relatorio = aplicar_revisao(est.projeto, payload["baseline"], payload["revisao"])
            antes = est.resultado("independente")
            depois = executar(novo, "independente")
            revisao = payload["revisao"]
            serializado = json.dumps(revisao, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
            revisao_id = hashlib.sha256(serializado).hexdigest()[:24]
            g = georref_da_obra(est.projeto.dados)
            linhas = []
            for f in revisao["features"]:
                geometria = f.get("geometry") or {}
                if geometria.get("type") != "LineString":
                    continue
                pontos = []
                for coordenada in geometria["coordinates"]:
                    x, y = g.para_xy(coordenada[0], coordenada[1])
                    pontos.append([x, y, coordenada[2] if len(coordenada) > 2 else None])
                linhas.append({"properties": copy.deepcopy(f["properties"]), "pontos": pontos})
            meta = revisao.get("meta", {})
            registro = {"id": revisao_id, "obra": obra or tipo_obra(est.projeto),
                        "source_app": meta.get("source_app"), "revision": meta.get("revision"),
                        "termino_antes": antes["termino"], "termino_depois": depois["termino"],
                        "delta_dias_corridos": ordinal(depois["termino"]) - ordinal(antes["termino"]),
                        "relatorio": relatorio, "geojson": copy.deepcopy(revisao), "linhas_locais": linhas,
                        "resultado_4d": depois,
                        "aviso": "100% FICTÍCIO. Revisão isolada; referência e simulação da demo preservadas. "
                                 "Geometria ilustrativa não comprova quantitativo de engenharia. Acervo em memória."}
        except (ValueError, TypeError, KeyError, OverflowError) as e:
            raise HTTPException(422, f"revisão recusada: {e}") from None
        if publicar:
            with trava:
                chave = (id(est), revisao_id)
                if chave not in registros and len(registros) >= MAX_REVISOES:
                    raise HTTPException(409, "acervo cheio: preserve arquivos e reinicie o beta para nova rodada")
                registros[chave] = registro
        return {"publicado": publicar, "persistido": False, **_publico(registro, completo=True)}
