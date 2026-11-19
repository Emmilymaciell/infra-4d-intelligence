"""Rota da produtividade de terraplenagem pela DMT: ``GET /api/produtividade/terraplenagem?obra=``.

Ligação pela API: ``ligar(app, obter_estado)``; ``obter_estado(obra)`` devolve objeto com ``.projeto``.
A resposta traz a análise por segmento, os ``ajustes_recomendados`` no formato da simulação
(``{atividade_id, produtividade}``, para ``POST /api/simulacao``) e o efeito no término.
Os parâmetros de frota são os padrões declarados em ``produtividade_terraplenagem.ParametrosFrota``.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, FastAPI

from .produtividade_terraplenagem import analisar

_lock = threading.Lock()
_cache: list[tuple[dict, dict]] = []

# auditoria de caches (2026-11-13): a resposta declara que NÃO reflete a simulação do usuário
SIMULACAO_DO_USUARIO = "não aplicada: o efeito no término usa só os ajustes pela DMT sobre o independente"


def criar_router(obter_estado) -> APIRouter:
    router = APIRouter(prefix="/api/produtividade", tags=["terraplenagem"],
                       responses={404: {"description": "Obra desconhecida"}})

    @router.get("/terraplenagem")
    def terraplenagem(obra: str | None = None):
        """Produtividade de terraplenagem pela DMT (ciclo de frota escavadeira × caminhões), por frente."""
        est = obter_estado(obra)
        dados = est.projeto.dados
        with _lock:
            for d, r in _cache:
                if d is dados:
                    return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r}
        r = analisar(est.projeto)
        with _lock:
            _cache.append((dados, r))
            del _cache[:-8]
        return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r}

    return router


def ligar(app: FastAPI, obter_estado) -> None:
    app.include_router(criar_router(obter_estado))
