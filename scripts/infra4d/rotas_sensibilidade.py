"""Rota da análise de sensibilidade (tornado) do término: ``GET /api/sensibilidade?obra=&p=0.1&equipes=1``.

Ligação pela API: ``ligar(app, obter_estado)``; ``obter_estado(obra)`` devolve objeto com ``.projeto``.
Custo: 1 + (2 ou 3) × nº de grupos execuções do motor. Por isso há CACHE por (dados da obra, p, equipes);
a resposta traz ``tempo_s`` (do cálculo original) e ``cache`` (True quando veio do cache).
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .sensibilidade import ErroSensibilidade, tornado

_lock = threading.Lock()
_cache: list[tuple[dict, float, int, dict]] = []
_CACHE_MAX = 16

# auditoria de caches (2026-11-13): a resposta declara que NÃO reflete a simulação do usuário
SIMULACAO_DO_USUARIO = "não aplicada: o tornado varia cada grupo sobre o cenário independente"


def criar_router(obter_estado) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["sensibilidade"],
                       responses={404: {"description": "Obra desconhecida"}})

    @router.get("/sensibilidade", responses={422: {"description": "Parâmetros levam a duração fora do horizonte ou análise não calculável"}})
    def sensibilidade(obra: str | None = None, p: float = Query(0.10, ge=0.0, lt=1.0),
                      equipes: int = Query(1, ge=0, le=10)):
        """Análise de sensibilidade (tornado) do término: variação de ±p na produtividade e de equipes por serviço."""
        projeto = obter_estado(obra).projeto
        dados = projeto.dados
        with _lock:
            for d, pp, eq, r in _cache:
                if d is dados and pp == p and eq == equipes:
                    return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": True}
        try:
            r = tornado(projeto, p, equipes)
        except ErroSensibilidade as e:
            raise HTTPException(422, str(e)) from None
        with _lock:
            _cache.append((dados, p, equipes, r))
            del _cache[:-_CACHE_MAX]
        return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": False}

    return router


def ligar(app: FastAPI, obter_estado) -> None:
    app.include_router(criar_router(obter_estado))
