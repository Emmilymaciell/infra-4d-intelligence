"""Rota do backtest da previsão de término: ``GET /api/backtest?obra=&passo_dias=7``.

Custo: 2 execuções do motor por data de status + 1 rede da realidade simulada. Medido em 2026-11-13, passo
7: ferrovia ~0,8 s (53 datas) e rodovia ~0,9 s (49 datas). Cache por (dados da obra, passo); a resposta
traz ``tempo_s`` e ``cache``. Ligação: ``ligar(app, obter_estado)``; ``obter_estado(obra)`` devolve objeto
com ``.projeto``.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .backtest import ErroBacktest, backtest, backtest_sementes, tipo_sintetico

_lock = threading.Lock()
_cache: list[tuple[dict, int, dict]] = []
_CACHE_MAX = 8

# auditoria de caches (2026-11-13): a resposta declara que NÃO reflete a simulação do usuário
SIMULACAO_DO_USUARIO = "não aplicada: o backtest compara previsões passadas com referências fixas"


def criar_router(obter_estado) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["backtest"], responses={404: {"description": "Obra desconhecida"}})

    @router.get("/backtest", responses={422: {"description": "passo_dias fora de 1..91"}})
    def rota_backtest(obra: str | None = None, passo_dias: int = Query(7, ge=1, le=91)):
        """Backtest da previsão de término: em cada data passada, erro da construtora, da independente e do
        Earned Schedule (PF = 1 e PF = SPI(t)) contra a realidade simulada (não circular) e contra o término
        independente atual (circular, declarado). MAE, MAPE, viés, acerto em ±10 %, por fase de avanço."""
        projeto = obter_estado(obra).projeto
        dados = projeto.dados
        with _lock:
            for d, p, r in _cache:
                if d is dados and p == passo_dias:
                    return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": True}
        try:
            r = backtest(projeto, passo_dias)
        except ErroBacktest as e:
            raise HTTPException(422, str(e)) from None
        with _lock:
            _cache.append((dados, passo_dias, r))
            del _cache[:-_CACHE_MAX]
        return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": False}

    @router.get("/backtest/sementes", responses={422: {"description": "n, passo_dias ou marco inválido; obra sem gerador sintético"}})
    def rota_backtest_sementes(obra: str | None = None, n: int = Query(10, ge=1, le=30),
                               passo_dias: int = Query(7, ge=1, le=91), marco: str = "M-FIM"):
        """Distribuição do erro de previsão sobre n mundos sintéticos gerados em memória (os JSON não são tocados).

        Só para as obras sintéticas do beta (marca fictícia + gerador reconhecido + dataset coerente; senão 422).
        Custo medido (2026-11-13, n = 10, passo 7): ferrovia ~18 s, rodovia ~13 s; com passo 28, ~4–5 s. Orçamento:
        n × nº de datas <= 900 (≈ 30 s); acima, 422 com o menor passo que cabe. Cache por (obra, n, passo, marco)."""
        projeto = obter_estado(obra).projeto
        try:
            tipo = tipo_sintetico(projeto.dados)
        except ErroBacktest as e:
            raise HTTPException(422, str(e)) from None
        chave = ("sementes", tipo, n, passo_dias, marco)
        with _lock:
            for d, p, r in _cache:
                if d is projeto.dados and p == chave:
                    return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": True}
        try:
            r = backtest_sementes(tipo, n, passo_dias, marco)
        except ErroBacktest as e:
            raise HTTPException(422, str(e)) from None
        with _lock:
            _cache.append((projeto.dados, chave, r))
            del _cache[:-_CACHE_MAX]
        return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **r, "cache": False}

    return router


def ligar(app: FastAPI, obter_estado) -> None:
    app.include_router(criar_router(obter_estado))
