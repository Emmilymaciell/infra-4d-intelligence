"""Rota da curva S física e financeira: ``GET /api/curva-s?obra=&lote=&base=fisica|financeira&passo_dias=7``.

Curvas planejado (LB), previsto construtora, previsto independente e realizado (boletins), em % do total.
Custo medido em 2026-11-12: ~0,015 s por chamada nas duas obras (cenários já em cache no Estado), por isso
sem cache próprio. Ligação: ``ligar(app, obter_estado)``; ``obter_estado(obra)`` devolve objeto com
``.projeto`` e ``.resultado(cenario)``.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .curva_s import BASES, ErroCurvaS, curva_s

# auditoria de caches (2026-11-13): a resposta declara que NÃO reflete a simulação do usuário
SIMULACAO_DO_USUARIO = "não aplicada: curvas de LB, construtora, independente e realizado (a simulada está em /api/painel)"


def criar_router(obter_estado) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["curva S"], responses={404: {"description": "Obra desconhecida"}})

    @router.get("/curva-s", responses={404: {"description": "Obra ou lote desconhecido"},
                                       422: {"description": "base ou passo_dias inválido; base financeira em obra sem a marca fictícia"}})
    def rota_curva_s(obra: str | None = None, lote: str | None = None, base: str = "fisica",
                     passo_dias: int = Query(7, ge=1, le=91)):
        """Curva S física (esforço planejado) ou financeira (BAC fictício): planejado (LB), previsto construtora,
        previsto independente e realizado (boletins de semana terminada), em % do total, semanal. O realizado
        na data de status é o EV do orçamento (financeira) e o avanço do painel (física)."""
        est = obter_estado(obra)
        if base not in BASES:
            raise HTTPException(422, f"base desconhecida: {base} (use fisica ou financeira)")
        if lote and lote not in {l["id"] for l in est.projeto.dados.get("lotes", [])}:
            raise HTTPException(404, f"lote desconhecido: {lote}")
        res = {c: est.resultado(c) for c in ("linha_base", "construtora", "independente")}
        try:
            return {"obra": obra, "simulacao_do_usuario": SIMULACAO_DO_USUARIO, **curva_s(est.projeto, res, base, lote, passo_dias)}
        except ErroCurvaS as e:
            raise HTTPException(422, str(e)) from None
        except ValueError as e:          # orcamento.ErroOrcamento (obra sem marca fictícia, composição ausente)
            raise HTTPException(422, str(e)) from None

    return router


def ligar(app: FastAPI, obter_estado) -> None:
    app.include_router(criar_router(obter_estado))
