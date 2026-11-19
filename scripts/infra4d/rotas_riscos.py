"""Rota do registro consolidado de riscos ao prazo: ``GET /api/riscos?obra=&rapido=false``.

Ligação: ``ligar(app, obter_estado)`` (contrato de ``api.registrar_rotas``), POR APP via
``dependency_overrides``. Cache por (dados da obra, rapido); a resposta traz ``tempo_total_s`` do
cálculo original e ``cache`` (True quando veio do cache).
"""

from __future__ import annotations

import threading
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .aviso_simulacao import com_aviso
from .riscos_prazo import registro

router = APIRouter(prefix="/api", tags=["riscos"])
_Q_OBRA = Query(default=None, description="id da obra; padrão: a do app")
_cache_lock = threading.Lock()
_cache: list[tuple[object, tuple, dict]] = []


def obter_estado(obra: str | None = _Q_OBRA):
    raise HTTPException(503, "rota de riscos não configurada: chame ligar(app, obter_estado)")


def _obra(obra: str | None = _Q_OBRA):
    return obra


def ligar(app, obter_estado_app: Callable) -> None:
    def _estado(obra: str | None = _Q_OBRA):
        return obter_estado_app(obra)

    app.dependency_overrides[obter_estado] = _estado
    app.include_router(router)


@router.get("/riscos", responses={404: {"description": "obra desconhecida"},
                                  422: {"description": "parâmetro inválido (ex.: rapido não booleano)"},
                                  503: {"description": "rota não ligada (ligar(app, obter_estado))"}})
def rota_riscos(rapido: bool = Query(default=False, description="pula Monte Carlo e recuperação (caros)"),
                est=Depends(obter_estado), obra: str | None = Depends(_obra)):
    """Registro CONSOLIDADO de riscos ao prazo da obra: produtividade, restrições, clima, tornado, criticidade
    (Monte Carlo), Earned Schedule × CPM, recuperação, linha de balanço e DCMA, deduplicados por frente e
    ordenados pelo Δ no término (dias). Cada risco traz EVIDÊNCIAS (rota GET, parâmetros e caminho no JSON que
    reproduzem o número). ``rapido=true`` pula Monte Carlo e recuperação (declarado em ``fontes_omitidas``).
    Cacheado por obra e modo; ``tempo_total_s`` é o do cálculo original."""
    P = est.projeto
    chave = (obra, rapido)
    with _cache_lock:
        for d, k, saida in _cache:
            if d is P.dados and k == chave:
                return com_aviso({**saida, "cache": True}, est)
    saida = registro(P, obra=obra, rapido=rapido)
    with _cache_lock:
        _cache.append((P.dados, chave, saida))
        del _cache[:-8]
    return com_aviso({**saida, "cache": False}, est)
