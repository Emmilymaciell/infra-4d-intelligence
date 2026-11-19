"""Rota da análise de tendência de marcos (MTA): ``GET /api/tendencia?obra=&passo_dias=7&limiar_dias=15``.

Custo: 2 execuções do motor por data de status (uma fotografia por passo). Medido em 2026-11-12, nesta
máquina: passo 7 → ferrovia 0,97 s (53 datas) e rodovia 1,03 s (49 datas); passo 14 → 0,47 / 0,72 s;
passo 28 → 0,23 / 0,36 s. Com a máquina carregada (outros agentes rodando) o passo 7 chegou a 3,7 / 5,2 s. Por isso há CACHE por (dados da obra, passo, limiar) e a resposta traz ``tempo_s``,
``cache`` e, se o cálculo passar de ``TEMPO_ALVO_S``, uma ``sugestao`` de passo maior (14 ou 28 dias).
Ligação: ``ligar(app, obter_estado)``; ``obter_estado(obra)`` devolve objeto com ``.projeto``.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .tendencia import LIMIAR_DIVERGENCIA_DIAS, ErroTendencia, tendencia

TEMPO_ALVO_S = 2.0
_lock = threading.Lock()
_cache: list[tuple[dict, int, int, dict]] = []
_CACHE_MAX = 8

# auditoria de caches (2026-11-13): a resposta declara que NÃO reflete a simulação do usuário
SIMULACAO_DO_USUARIO = "não aplicada: a MTA recalcula construtora e independente em fotografias passadas"


def criar_router(obter_estado) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["tendência"], responses={404: {"description": "Obra desconhecida"}})

    @router.get("/tendencia", responses={422: {"description": "passo_dias fora de 1..91 ou limiar_dias < 0"}})
    def rota_tendencia(obra: str | None = None, passo_dias: int = Query(7, ge=1, le=91),
                       limiar_dias: int = Query(LIMIAR_DIVERGENCIA_DIAS, ge=0, le=3650)):
        """Análise de tendência de marcos (MTA): término de cada marco por data de status semanal, recalculado
        só com o que se sabia em cada data (boletins de semana terminada, datas reais anteriores, restrições
        pela data prevista). Traz inclinação (dias de deslize por semana) e a 1ª divergência entre
        independente e construtora acima do limiar. Não aplica a simulação do usuário."""
        projeto = obter_estado(obra).projeto
        dados = projeto.dados
        with _lock:
            for d, p, lim, r in _cache:
                if d is dados and p == passo_dias and lim == limiar_dias:
                    return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": True}
        try:
            r = tendencia(projeto, passo_dias, limiar_dias)
        except ErroTendencia as e:
            raise HTTPException(422, str(e)) from None
        if r["tempo_s"] > TEMPO_ALVO_S:
            r["sugestao"] = (f"cálculo levou {r['tempo_s']} s (> {TEMPO_ALVO_S} s); use passo_dias=14 ou 28 "
                             "para uma tendência mais rápida (o resultado da última data não muda)")
        with _lock:
            _cache.append((dados, passo_dias, limiar_dias, r))
            del _cache[:-_CACHE_MAX]
        return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": False}

    return router


def ligar(app: FastAPI, obter_estado) -> None:
    app.include_router(criar_router(obter_estado))
