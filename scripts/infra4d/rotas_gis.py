"""Rota GeoJSON para SIG: ``GET /api/gis/geojson?obra=&camada=&data=&cenario=``.

Resposta ``application/geo+json`` (RFC 7946) com georreferência FICTÍCIA declarada em ``meta``.
``camada``: eixo | lotes | segmentos | atividades | marcos | restricoes | conflitos | estacas | faixa | todas.
``data``: AAAA-MM-DD do estado 4D (padrão: data de status). ``cenario``: linha_base | construtora |
independente | simulado. Ligação: ``ligar(app, obter_estado)``; ``obter_estado(obra)`` devolve objeto com
``.projeto`` e ``.resultado(cenario)``.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .calendario import ordinal
from .cenarios import CENARIOS
from .gis import CAMADAS, ErroGis, geojson

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def criar_router(obter_estado) -> APIRouter:
    router = APIRouter(prefix="/api/gis", tags=["gis"], responses={404: {"description": "Obra desconhecida"}})

    @router.get("/geojson", response_class=JSONResponse, responses={
        200: {"content": {"application/geo+json": {}}, "description": "FeatureCollection RFC 7946"},
        422: {"description": "Camada, data (AAAA-MM-DD) ou cenário inválido"}})
    def rota_geojson(obra: str | None = None, camada: str = "todas", data: str | None = None,
                     cenario: str = "independente"):
        """GeoJSON (RFC 7946, WGS84, [lon, lat]) da obra com GEORREFERÊNCIA FICTÍCIA declarada em ``meta``.

        Camadas: eixo, lotes, segmentos, atividades (estado 4D na data), marcos, restrições pendentes, conflitos
        de linha de balanço, estacas e faixa (polígono); ``todas`` junta todas. Para QGIS/SIG: visualização,
        não locação."""
        est = obter_estado(obra)
        if camada != "todas" and camada not in CAMADAS:
            raise HTTPException(422, f"camada desconhecida: {camada} (use {', '.join(CAMADAS)} ou todas)")
        if cenario not in CENARIOS:
            raise HTTPException(422, f"cenário desconhecido: {cenario}")
        t = None
        if data is not None:
            try:
                if not _RE_DATA.match(data):
                    raise ValueError
                t = ordinal(data)
            except ValueError:
                raise HTTPException(422, "data inválida (use AAAA-MM-DD)") from None
        resultados = {c: est.resultado(c) for c in CENARIOS}
        conf = None
        if camada in ("conflitos", "todas"):
            from .recursos import conflitos_balanco
            conf = conflitos_balanco(est.projeto, resultados[cenario])
        try:
            corpo = geojson(est.projeto, resultados, camada, t, cenario, conf)
        except ErroGis as e:
            raise HTTPException(422, str(e)) from None
        return JSONResponse(corpo, media_type="application/geo+json")

    return router


def ligar(app: FastAPI, obter_estado) -> None:
    app.include_router(criar_router(obter_estado))
