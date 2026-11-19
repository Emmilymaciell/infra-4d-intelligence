"""Rota da cobertura da previsão: ``GET /api/cobertura?obra=&cenario=independente&folga_alerta_du=10``.

Para cada marco de término (ver ``cobertura.py``): confiança pelo ESTRESSE no motor (produtividade sem medição ×
f e medida × f, f = pior índice medida/planejada já observado na obra), alerta de antecessoras sem medição com
folga ≤ folga_alerta_du dias úteis até o marco, e o relatório por origem em equipe·dia (informativo).
Custo: 3 execuções do motor + 1 por marco com candidatas ao alerta (sub-rede).

Ligação: ``ligar(app, obter_estado)`` (contrato de ``api.registrar_rotas``); ``obter_estado(obra)`` devolve
objeto com ``.projeto`` (e ``.ajustes`` para o cenário simulado) e levanta 404 para obra desconhecida.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .cobertura import CENARIOS_COBERTURA, FOLGA_ALERTA_PADRAO_DU, ErroCobertura, cobertura

_ATTR = "cobertura_obter_estado"
router = APIRouter(prefix="/api", tags=["cobertura da previsão"],
                   responses={404: {"description": "Obra desconhecida (parâmetro obra)"},
                              503: {"description": "Rota não ligada ao app (ligar não foi chamado)"}})


def ligar(app: FastAPI, obter_estado) -> None:
    setattr(app.state, _ATTR, obter_estado)
    app.include_router(router)


@router.get("/cobertura", responses={422: {"description": "Cenário inválido (use construtora, independente ou simulado)"}})
def rota_cobertura(request: Request, obra: str | None = Query(None, description="id da obra; padrão: a do app"),
                   cenario: str = Query("independente", description="construtora, independente ou simulado"),
                   folga_alerta_du: int = Query(FOLGA_ALERTA_PADRAO_DU, ge=0, le=3650,
                                                description="dias úteis de folga até o marco para o alerta de "
                                                            "frentes sem medição (valor do projeto no manifesto)")):
    """Cobertura da previsão por marco: nível de confiança (alta / media / baixa / sem_historico / concluido)
    pelo Δ do término quando a produtividade SEM medição (analogia ou planejada) rende × f, comparado ao Δ
    quando a MEDIDA rende × f; alerta de frentes sem medição quase-críticas para o marco; e o relatório da
    cadeia determinante por origem da produtividade, em equipe·dia e %."""
    if cenario not in CENARIOS_COBERTURA:
        raise HTTPException(422, f"cenário inválido: {cenario!r}; use um de {', '.join(CENARIOS_COBERTURA)}")
    f = getattr(request.app.state, _ATTR, None)
    if f is None:
        raise HTTPException(503, "rota de cobertura não ligada: chame rotas_cobertura.ligar(app, obter_estado)")
    est = f(obra)
    try:
        saida = cobertura(est.projeto, cenario, getattr(est, "ajustes", None) if cenario == "simulado" else None,
                          folga_alerta_du=folga_alerta_du)
    except ErroCobertura as e:
        raise HTTPException(422, str(e)) from None
    return {"obra": obra, **saida}
