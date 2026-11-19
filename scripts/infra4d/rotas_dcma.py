"""Rotas DCMA 14 pontos: ``/api/dcma``.

Ligação (contrato multi-obra): ``ligar(app, obter_estado)``.

- ``GET  /api/dcma?obra=&cenario=independente``: avalia um cenário do motor próprio
  (simulado usa os ajustes atuais do Estado, se houver).
- ``POST /api/dcma/importado?obra=&formato=``: corpo bruto MSPDI (.xml) ou XER, reaproveitando os
  importadores; responde 422 para arquivo inválido (nunca 500).
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .dcma import avaliar_cenario, avaliar_importado

router = APIRouter(prefix="/api/dcma", tags=["DCMA 14 pontos"],
                   responses={404: {"description": "Obra desconhecida (parâmetro obra)"}, 503: {"description": "Rotas não ligadas ao app (ligar não foi chamado)"}})
_ATTR = "dcma_obter_estado"
CENARIOS = ("linha_base", "construtora", "independente", "simulado")


def ligar(app: FastAPI, obter_estado) -> None:
    setattr(app.state, _ATTR, obter_estado)
    app.include_router(router)


def _estado(request: Request, obra):
    f = getattr(request.app.state, _ATTR, None)
    if f is None:
        raise HTTPException(503, "rotas DCMA não ligadas: chame rotas_dcma.ligar(app, obter_estado)")
    return f(obra)


@router.get("", responses={422: {"description": "Cenário inválido"}})
def dcma_cenario(request: Request, obra: str | None = Query(None), cenario: str = Query("independente")):
    """DCMA 14 pontos sobre um cenário do motor próprio (valor, limite, aprovação e violadoras por ponto)."""
    if cenario not in CENARIOS:
        raise HTTPException(422, f"cenário inválido: {cenario!r}; use um de {', '.join(CENARIOS)}")
    est = _estado(request, obra)
    ajustes = getattr(est, "ajustes", None) if cenario == "simulado" else None
    saida = avaliar_cenario(est.projeto, cenario, ajustes)
    saida["cenario"] = cenario
    saida["simulacao_do_usuario"] = (
        f"aplicada: {len(ajustes or [])} ajuste(s) do usuário no cenário simulado" if cenario == "simulado"
        else f"não aplicada: avaliação do cenário {cenario} (use cenario=simulado para avaliar a simulação)")
    return saida


@router.post("/importado", responses={400: {"description": "Corpo vazio"}, 413: {"description": "Arquivo acima do limite de tamanho"}, 415: {"description": "Formato não reconhecido ou multipart (envie o arquivo no corpo bruto)"}, 422: {"description": "Arquivo inválido, recusado pela validação ou rede rejeitada pelo motor"}})
async def dcma_importado(request: Request, obra: str | None = Query(None),
                         formato: str | None = Query(None, pattern="^(mspdi|xer)$")):
    """DCMA 14 pontos sobre um cronograma importado (MSPDI ou XER no corpo bruto)."""
    from .importadores.rotas import _importar, _ler_corpo  # 415/413/400/422 já tratados lá

    _estado(request, obra)  # 404 de obra desconhecida, por uniformidade
    dados = _importar(await _ler_corpo(request), formato)
    saida = avaliar_importado(dados)
    saida["simulacao_do_usuario"] = "não aplicada: avaliação do cronograma importado (arquivo enviado)"
    return saida
