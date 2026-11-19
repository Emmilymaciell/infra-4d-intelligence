"""Rotas de exportação para BI: ``/api/exportar``.

Ligação (contrato multi-obra do ``api.py``): ``ligar(app, obter_estado)``, onde
``obter_estado(obra)`` devolve um objeto com ``.projeto`` e ``.resultado(cenario)``.

- ``GET /api/exportar/pacote.zip?obra=&sep=&decimal=``: todas as tabelas + LEIAME.txt (+ aviso.txt)
- ``GET /api/exportar/tabelas?obra=``: lista das tabelas e colunas (JSON)
- ``GET /api/exportar/{tabela}.csv?obra=&sep=&decimal=``: uma tabela

Nada é gravado em disco: o conteúdo sai só na resposta HTTP.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import Response

from .obra import ErroTipoObra
from .exportacao import (ErroExportacao, chave_obra, montar_tabelas, nome_seguro, pacote_zip, para_csv,
                         parametros_csv)

router = APIRouter(prefix="/api/exportar", tags=["exportação BI"],
                   responses={404: {"description": "Obra desconhecida (parâmetro obra)"}, 503: {"description": "Rotas não ligadas ao app (ligar não foi chamado)"}})
_ATTR = "exportacao_obter_estado"


def ligar(app: FastAPI, obter_estado) -> None:
    setattr(app.state, _ATTR, obter_estado)
    app.include_router(router)


def _montar(request: Request, obra: str | None):
    obter = getattr(request.app.state, _ATTR, None)
    if obter is None:
        raise HTTPException(503, "rotas de exportação não ligadas: chame rotas_exportacao.ligar(app, obter_estado)")
    est = obter(obra)  # 404 de obra desconhecida vem daqui
    try:
        tabelas, notas = montar_tabelas(est.projeto, obra, est.resultado)
    except ErroTipoObra as e:  # P8: obra sem meta.tipo_obra declarado (sem padrão "ferrovia")
        raise HTTPException(422, f"tipo de obra inválido: {e}") from None
    return est, tabelas, notas


def _params(sep, decimal):
    try:
        return parametros_csv(sep, decimal)
    except ErroExportacao as e:
        raise HTTPException(422, str(e)) from None


@router.get("/pacote.zip", responses={422: {"description": "Separador/decimal inválidos ou iguais"}})
def pacote(request: Request, obra: str | None = Query(None), sep: str | None = Query(None),
           decimal: str | None = Query(None)):
    """Pacote ZIP para BI (Power BI/Excel): todas as tabelas em CSV pt-BR com BOM, LEIAME.txt (dicionário de dados) e aviso.txt quando a obra é fictícia."""
    s, d = _params(sep, decimal)
    est, tabelas, notas = _montar(request, obra)
    oid = nome_seguro(chave_obra(obra, est.projeto))  # Content-Disposition: só [A-Za-z0-9._-] (r11)
    return Response(pacote_zip(tabelas, notas, est.projeto, s, d), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="infra4d-{oid}-bi.zip"'})


@router.get("/tabelas")
def listar(request: Request, obra: str | None = Query(None)):
    """Lista as tabelas exportáveis e as colunas de cada uma (tipo, unidade, origem)."""
    _est, tabelas, notas = _montar(request, obra)
    return {"tabelas": [{"nome": t.nome, "descricao": t.descricao, "linhas": len(t.linhas),
                         "colunas": [c.__dict__ for c in t.colunas]} for t in tabelas.values()],
            "notas": notas}


@router.get("/{tabela}.csv", responses={404: {"description": "Tabela ou obra desconhecida"}, 422: {"description": "Separador/decimal inválidos ou iguais"}})
def tabela_csv(request: Request, tabela: str, obra: str | None = Query(None), sep: str | None = Query(None),
               decimal: str | None = Query(None)):
    """Uma tabela em CSV (UTF-8 com BOM; separador e decimal configuráveis; texto com cara de fórmula é neutralizado)."""
    s, d = _params(sep, decimal)
    est, tabelas, notas = _montar(request, obra)
    if tabela not in tabelas:
        raise HTTPException(404, f"tabela desconhecida: {tabela!r}; disponíveis: {', '.join(tabelas)}"
                                 + (f" ({'; '.join(notas)})" if notas else ""))
    oid = nome_seguro(chave_obra(obra, est.projeto))  # Content-Disposition: só [A-Za-z0-9._-] (r11)
    return Response(para_csv(tabelas[tabela], s, d), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{oid}-{nome_seguro(tabela)}.csv"'})
