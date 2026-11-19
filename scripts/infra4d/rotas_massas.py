"""Rotas do diagrama de massas: ``/api/massas``.

Ligação pela API: ``ligar(app, obter_estado)``; ``obter_estado(obra)`` devolve um objeto com ``.projeto``.
Cache por (identidade do dicionário de dados, passo).

- ``GET /api/massas/diagrama?obra=&passo_m=20``  estacas (ordenadas, volumes), pontos de passagem, compensações
- ``GET /api/massas/coerencia?obra=``             volume geométrico por segmento vs quantidade TER do dataset
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .massas import ErroMassas, coerencia, massas_da_obra

_lock = threading.Lock()
_cache: list[tuple[dict, float, dict]] = []
_CACHE_MAX = 8


def _massas(dados: dict, passo_m: float) -> dict:
    with _lock:
        for d, p, r in _cache:
            if d is dados and p == passo_m:
                return r
    try:
        r = massas_da_obra(dados, passo_m)
    except ErroMassas as e:
        raise HTTPException(422, str(e)) from None
    with _lock:
        _cache.append((dados, passo_m, r))
        del _cache[:-_CACHE_MAX]
    return r


def criar_router(obter_estado) -> APIRouter:
    router = APIRouter(prefix="/api/massas", tags=["terraplenagem"],
                       responses={404: {"description": "Obra desconhecida"}, 422: {"description": "Seções/perfil da obra inválidos para o diagrama"}})

    @router.get("/diagrama")
    def diagrama(obra: str | None = None, passo_m: float = Query(20.0, ge=1.0, le=1000.0)):
        """Diagrama de massas (Brückner) da obra: volumes acumulados de corte e aterro por estaca."""
        est = obter_estado(obra)
        return {"obra": obra, **_massas(est.projeto.dados, passo_m)}

    @router.get("/coerencia")
    def coerencia_ter(obra: str | None = None):
        """Coerência entre o diagrama de massas e as quantidades de terraplenagem do cronograma."""
        est = obter_estado(obra)
        dados = est.projeto.dados
        return {"obra": obra, **coerencia(dados, massas=_massas(dados, 20.0))}

    return router


def ligar(app: FastAPI, obter_estado) -> None:
    app.include_router(criar_router(obter_estado))
