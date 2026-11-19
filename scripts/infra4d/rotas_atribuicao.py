"""Rota da atribuição do erro de previsão por frente: ``GET /api/backtest/atribuicao``.

Ligação (contrato multi-obra): ``ligar(app, obter_estado)``. Ver ``atribuicao_erro.py`` (regras, custo).
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .atribuicao_erro import ErroAtribuicao, atribuir

router = APIRouter(prefix="/api/backtest", tags=["backtest"],
                   responses={404: {"description": "Obra desconhecida"},
                              503: {"description": "Rotas não ligadas ao app"}})
_ATTR = "atribuicao_obter_estado"
_lock = threading.Lock()
_cache: list[tuple[object, tuple, dict]] = []
SIMULACAO_DO_USUARIO = "não aplicada: a atribuição refaz a previsão passada trocando só a produtividade de cada frente"


def ligar(app: FastAPI, obter_estado) -> None:
    setattr(app.state, _ATTR, obter_estado)
    app.include_router(router)


@router.get("/atribuicao", responses={422: {"description": "Marco ou data inválidos, data fora do intervalo do "
                                                          "projeto, obra sem realidade simulada ou acima do teto"}})
def rota_atribuicao(request: Request, obra: str | None = Query(None, description="id da obra; padrão: a do app"),
                    marco: str = Query("M-FIM", description="id do marco de término"),
                    data: str = Query(..., description="data de status passada, AAAA-MM-DD")):
    """Atribuição do erro da previsão independente feita em ``data`` para o ``marco``, contra a realidade
    SIMULADA: quanto o erro cai ao corrigir só a produtividade de cada frente (lote, serviço) da cadeia do
    marco, ordenado pela redução, com o resíduo de interação declarado."""
    f = getattr(request.app.state, _ATTR, None)
    if f is None:
        raise HTTPException(503, "rota de atribuição não ligada: chame rotas_atribuicao.ligar(app, obter_estado)")
    projeto = f(obra).projeto
    chave = (marco, data)
    with _lock:
        for d, k, r in _cache:
            if d is projeto.dados and k == chave:
                return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": True}
    try:
        r = atribuir(projeto, marco, data)
    except ErroAtribuicao as e:
        raise HTTPException(422, str(e)) from None
    with _lock:
        _cache.append((projeto.dados, chave, r))
        del _cache[:-16]
    return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": False}
