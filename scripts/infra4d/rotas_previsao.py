"""Rotas de previsão independente do CPM (Earned Schedule).

Ligação: ``ligar(app, obter_estado)`` — contrato de ``api.registrar_rotas``. ``obter_estado(obra)``
devolve o Estado da obra (``.projeto``, ``.resultado(cenario)``) e levanta 404 para obra
desconhecida. A ligação é POR APP (``dependency_overrides``), sem estado global no módulo.
O Monte Carlo continua no endpoint ``/api/previsao-probabilistica`` da ``api.py``.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .aviso_simulacao import com_aviso
from .previsao_es import previsao

router = APIRouter(prefix="/api/previsao", tags=["previsao"],
                   responses={404: {"description": "Obra desconhecida"}, 503: {"description": "Rotas não ligadas ao app"}})

_Q_OBRA = Query(default=None, description="id da obra; padrão: a do app")


def obter_estado(obra: str | None = _Q_OBRA):
    raise HTTPException(503, "rotas de previsão não configuradas: chame ligar(app, obter_estado)")


def ligar(app, obter_estado_app: Callable) -> None:
    def _estado(obra: str | None = _Q_OBRA):
        return obter_estado_app(obra)

    app.dependency_overrides[obter_estado] = _estado
    app.include_router(router)


@router.get("/earned-schedule", responses={404: {"description": "Obra ou lote desconhecido"}, 422: {"description": "Previsão não calculável (ex.: lote sem atividades)"}})
def rota_earned_schedule(lote: str | None = None, est=Depends(obter_estado)):
    """Previsão independente do término por Earned Schedule (SPI(t), IEAC(t)), confrontável com o CPM."""
    P = est.projeto
    if lote and lote not in {l["id"] for l in P.dados.get("lotes", [])}:
        raise HTTPException(404, f"lote desconhecido: {lote}")
    res = {c: est.resultado(c) for c in ("linha_base", "construtora", "independente")}
    try:
        return com_aviso(previsao(P, lote, res), est)
    except ValueError as e:  # ex.: lote cadastrado sem atividades
        raise HTTPException(422, str(e))
