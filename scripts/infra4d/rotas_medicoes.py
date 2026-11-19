"""Rota de importação de medições por CSV: ``POST /api/medicoes/importar``.

Ligação (contrato multi-obra): ``ligar(app, obter_estado)``.

``POST /api/medicoes/importar?obra=&aplicar=false&nome=planilha.csv`` com o CSV no CORPO bruto
(``text/csv``, ``text/plain`` ou ``application/octet-stream``; sem multipart).
- ``aplicar=false``: só o relatório de validação.
- ``aplicar=true``: se o arquivo for aprovado, simula em MEMÓRIA (não persiste nada) e devolve o
  ``comparar()`` do cenário independente atual × independente com as medições novas.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from .calendario import ErroCalendario, ordinal
from .cenarios import comparar, executar
from .importar_medicoes import MAX_BYTES, ErroArquivo, importar
from .motor import ErroRede

router = APIRouter(prefix="/api/medicoes", tags=["medições (CSV)"],
                   responses={404: {"description": "Obra desconhecida (parâmetro obra)"}, 503: {"description": "Rotas não ligadas ao app (ligar não foi chamado)"}})
_ATTR = "medicoes_obter_estado"


def ligar(app: FastAPI, obter_estado) -> None:
    setattr(app.state, _ATTR, obter_estado)
    app.include_router(router)


@router.post("/importar", responses={400: {"description": "Corpo vazio"}, 413: {"description": "Arquivo acima do limite"}, 415: {"description": "Multipart não suportado (envie o CSV no corpo bruto)"}, 422: {"description": "Arquivo recusado (encoding, cabeçalho, marca de fictício) ou medições que invalidam a rede"}})
async def importar_csv(request: Request, obra: str | None = Query(None), aplicar: bool = Query(False),
                       nome: str = Query("planilha.csv", max_length=200)):
    """Valida uma planilha CSV de medições (boletins/diários) linha a linha; com aplicar=true e arquivo aprovado, simula em memória o cenário independente com as medições novas (nada é persistido)."""
    obter = getattr(request.app.state, _ATTR, None)
    if obter is None:
        raise HTTPException(503, "rota de medições não ligada: chame rotas_medicoes.ligar(app, obter_estado)")
    est = obter(obra)  # 404 de obra desconhecida
    if (request.headers.get("content-type") or "").lower().startswith("multipart/"):
        raise HTTPException(415, "multipart não suportado: envie o CSV no corpo bruto (text/csv)")
    corpo = bytearray()
    async for parte in request.stream():
        corpo.extend(parte)
        if len(corpo) > MAX_BYTES:
            raise HTTPException(413, f"arquivo maior que {MAX_BYTES} bytes")
    if not bytes(corpo).strip():
        raise HTTPException(400, "corpo vazio: envie o conteúdo do CSV")
    try:
        rel = importar(est.projeto, bytes(corpo), nome)
    except ErroArquivo as e:
        raise HTTPException(422, f"arquivo recusado: {e}") from None
    projeto_novo = rel.pop("_projeto", None)
    rel["aplicado"] = False
    if aplicar:
        if projeto_novo is None:
            rel["simulacao"] = None
            rel["motivo_nao_aplicado"] = rel["motivo"]
        else:
            try:
                ref = est.resultado("independente")
                novo = executar(projeto_novo, "independente")
            except (ErroRede, ErroCalendario) as e:
                raise HTTPException(422, {"erro": f"as medições novas tornam a rede inválida: {e}",
                                          "relatorio": rel}) from None
            cmp = comparar(est.projeto, ref, novo)
            cmp["alvo"] = "independente + medições importadas (simulação em memória)"
            rel["aplicado"] = True
            rel["simulacao"] = {
                "persistido": False,
                "termino_antes": ref["termino"], "termino_depois": novo["termino"],
                "delta_dias_corridos": ordinal(novo["termino"]) - ordinal(ref["termino"]),
                "comparacao": cmp,
            }
    return rel
