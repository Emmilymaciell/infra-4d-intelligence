"""Rota de cenários climáticos (chuvoso / seco / estação deslocada) sobre o cenário independente.

Ligação: ``ligar(app, obter_estado)`` (contrato de ``api.registrar_rotas``), POR APP via
``dependency_overrides``; ``obter_estado(obra)`` levanta 404 para obra desconhecida.
"""

from __future__ import annotations

import threading
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .aviso_simulacao import com_aviso
from .clima import cenarios_climaticos

router = APIRouter(prefix="/api", tags=["clima"],
                   responses={404: {"description": "Obra desconhecida"}, 503: {"description": "Rotas não ligadas ao app"}})
_Q_OBRA = Query(default=None, description="id da obra; padrão: a do app")
_cache_lock = threading.Lock()
_cache: list[tuple[object, tuple, dict]] = []


def obter_estado(obra: str | None = _Q_OBRA):
    raise HTTPException(503, "rota de clima não configurada: chame ligar(app, obter_estado)")


def ligar(app, obter_estado_app: Callable) -> None:
    def _estado(obra: str | None = _Q_OBRA):
        return obter_estado_app(obra)

    app.dependency_overrides[obter_estado] = _estado
    app.include_router(router)


@router.get("/clima", responses={422: {"description": "Cenário climático não calculável com estes parâmetros"}})
def rota_clima(intensidade: float = Query(default=0.3, ge=0, le=1,
                                          description="fração da chuva do mês acrescentada (chuvoso) e devolvida (seco)"),
               deslocamento_semanas: int = Query(default=0, ge=-26, le=26,
                                                 description="estação chuvosa N semanas mais tarde (+) ou cedo (−)"),
               est=Depends(obter_estado)):
    """Cenários climáticos (chuvoso, seco, estação deslocada) sobre o cenário independente: término de cada um."""
    P = est.projeto
    chave = (round(intensidade, 6), deslocamento_semanas)
    with _cache_lock:
        for d, k, saida in _cache:
            if d is P.dados and k == chave:
                return com_aviso(saida, est)
    try:
        saida = cenarios_climaticos(P, intensidade=intensidade, deslocamento_semanas=deslocamento_semanas)
    except ValueError as e:
        raise HTTPException(422, str(e))
    with _cache_lock:
        _cache.append((P.dados, chave, saida))
        del _cache[:-8]
    return com_aviso(saida, est)
