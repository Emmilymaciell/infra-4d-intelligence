"""Rota da aceleração com custo (crashing): ``GET /api/aceleracao?obra=&prazo=&limite_extra=2``.

Ligação: ``ligar(app, obter_estado)`` (contrato de ``api.registrar_rotas``), POR APP via
``dependency_overrides``. Cache por (dados da obra, prazo, limite_extra).
"""

from __future__ import annotations

import threading
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .aceleracao import EQUIPES_MAX, LIMITE_EXTRA_PADRAO, acelerar
from .aviso_simulacao import com_aviso

router = APIRouter(prefix="/api", tags=["aceleracao"])
_Q_OBRA = Query(default=None, description="id da obra; padrão: a do app")
_cache_lock = threading.Lock()
_cache: list[tuple[object, tuple, dict]] = []


def obter_estado(obra: str | None = _Q_OBRA):
    raise HTTPException(503, "rota de aceleração não configurada: chame ligar(app, obter_estado)")


def ligar(app, obter_estado_app: Callable) -> None:
    def _estado(obra: str | None = _Q_OBRA):
        return obter_estado_app(obra)

    app.dependency_overrides[obter_estado] = _estado
    app.include_router(router)


@router.get("/aceleracao", responses={404: {"description": "obra desconhecida"},
                                      422: {"description": "prazo fora de AAAA-MM-DD ou limite_extra fora de 1..20"},
                                      503: {"description": "rota não ligada (ligar(app, obter_estado))"}})
def rota_aceleracao(prazo: str | None = Query(default=None, description="AAAA-MM-DD; padrão: término da LB"),
                    limite_extra: int = Query(default=LIMITE_EXTRA_PADRAO, ge=1, le=EQUIPES_MAX,
                                              description="equipes extras por frente"),
                    est=Depends(obter_estado)):
    """ACELERAÇÃO com custo (crashing): equipes extras nas frentes do caminho determinante pelo MENOR custo
    adicional FICTÍCIO (orçamento de demonstração) até cumprir o prazo. Devolve a curva tempo × custo (cada
    passo) e ``ajustes_finais`` aplicáveis em POST /api/simulacao. Guloso, não ótimo global."""
    P = est.projeto
    prazo = prazo.strip() or None if prazo is not None else None  # ?prazo= (vazio) = padrão (r16)
    chave = (prazo, limite_extra)
    with _cache_lock:
        for d, k, saida in _cache:
            if d is P.dados and k == chave:
                return com_aviso(saida, est)
    try:
        saida = acelerar(P, prazo=prazo, limite_extra=limite_extra)
    except ValueError as e:
        raise HTTPException(422, str(e))
    with _cache_lock:
        _cache.append((P.dados, chave, saida))
        del _cache[:-8]
    return com_aviso(saida, est)
