"""Rota de cenários de recuperação ("o que precisa acontecer para cumprir o prazo").

Ligação: ``ligar(app, obter_estado)`` (contrato de ``api.registrar_rotas``), POR APP via
``dependency_overrides``. ``obter_estado(obra)`` devolve o Estado da obra e levanta 404 para obra
desconhecida.
"""

from __future__ import annotations

import threading
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .aviso_simulacao import com_aviso
from .calendario import ordinal
from .recuperacao import recuperar

router = APIRouter(prefix="/api", tags=["recuperacao"])
_Q_OBRA = Query(default=None, description="id da obra; padrão: a do app")

_cache_lock = threading.Lock()
_cache: list[tuple[object, tuple, dict]] = []


def obter_estado(obra: str | None = _Q_OBRA):
    raise HTTPException(503, "rota de recuperação não configurada: chame ligar(app, obter_estado)")


def ligar(app, obter_estado_app: Callable) -> None:
    def _estado(obra: str | None = _Q_OBRA):
        return obter_estado_app(obra)

    app.dependency_overrides[obter_estado] = _estado
    app.include_router(router)


@router.get("/recuperacao", responses={404: {"description": "obra desconhecida"},
                                       422: {"description": "prazo fora de AAAA-MM-DD, marco desconhecido ou folga_max negativa"},
                                       503: {"description": "rota não ligada (ligar(app, obter_estado))"}})
def rota_recuperacao(prazo: str | None = Query(default=None, description="AAAA-MM-DD; padrão: término da LB "
                                                                          "(ou do marco, na LB)"),
                     marco: str | None = Query(default=None, description="id de marco; padrão: término da obra"),
                     folga_max: int = Query(default=5, ge=0, le=365),
                     est=Depends(obter_estado)):
    """Plano de RECUPERAÇÃO: produtividade (ou equipes) mínima por frente para o cenário independente cumprir o
    prazo (padrão: término da linha de base, ou o marco ``marco``). Guloso sobre o conjunto determinante, com
    relaxação, contraprova pela aceleração antes de declarar inviável e verificação no cenário simulado.
    Viabilidade de cada frente contra a melhor semana medida (até 1,3× = esforço; acima = mudança de método)."""
    P = est.projeto
    prazo = (prazo.strip() or None) if prazo is not None else None  # ?prazo= (vazio) = padrão (r18)
    if prazo is not None:
        try:
            ok = ordinal(prazo) is not None
        except ValueError:
            ok = False
        if not ok:
            raise HTTPException(422, "prazo inválido (use AAAA-MM-DD)")
    chave = (prazo, marco, folga_max)
    with _cache_lock:
        for d, k, saida in _cache:
            if d is P.dados and k == chave:
                return com_aviso(saida, est)
    try:
        saida = recuperar(P, prazo=prazo, marco=marco, folga_max=folga_max)
    except ValueError as e:
        raise HTTPException(422, str(e))
    with _cache_lock:
        _cache.append((P.dados, chave, saida))
        del _cache[:-8]
    return com_aviso(saida, est)
