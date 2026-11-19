"""Rotas do 5D FICTÍCIO: ``/api/orcamento``.

Ligação: ``ligar(app, obter_estado)`` — ``obter_estado(obra)`` devolve um objeto com ``.projeto``.
Toda rota aceita ``?obra=<id>`` e toda resposta traz o aviso de orçamento FICTÍCIO (``orcamento.AVISO``).

- ``GET /composicoes``
- ``GET /resumo?lote=``
- ``GET /curva-s-financeira?lote=&passo_dias=``
- ``GET /classificacao-ifc?classe=&predefined_type=&object_type=`` (mapa derivado do exportador IFC; 503 sem ifcopenshell)
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, FastAPI, HTTPException, Query

from . import orcamento as O


def _lote(P, lote: str | None) -> None:
    if lote and lote not in {l["id"] for l in P.dados.get("lotes", [])}:
        raise HTTPException(404, f"lote desconhecido: {lote}")


def _executar(fn):
    try:
        return fn()
    except O.ErroOrcamento as e:
        raise HTTPException(422, str(e)) from None


def criar_router(obter_estado: Callable[[str | None], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/orcamento", tags=["orçamento 5D fictício"], responses={
        404: {"description": "Obra desconhecida (``?obra=``) ou lote desconhecido."},
        422: {"description": "Orçamento inconsistente (unidade divergente, linha de base inválida, quantidade "
                             "negativa, lote sem atividade orçada) ou obra sem ``meta.ficticio = true`` "
                             "(custo real sintético recusado)."},
    })
    Q_OBRA = Query(default=None, description="id da obra; padrão: a do app")

    @router.get("/composicoes")
    def composicoes(obra: str | None = Q_OBRA):
        """Composições FICTÍCIAS da obra (código, unidade, custo direto decomposto, preço de venda), o BDI
        declarado (fórmula do TCU, dentro da faixa do Acórdão 2622/2013) e o mapa classe IFC → composição
        derivado do exportador IFC (vazio, com nota, se o ifcopenshell não estiver instalado)."""
        P = obter_estado(obra).projeto
        tipo = _executar(lambda: O.tipo_obra(P))
        bdi = _executar(lambda: O.bdi_da_obra(tipo))
        try:
            mapa, nota = O.mapa_ifc(tipo), "derivado do exportador IFC (ifc/exportar.py)"
        except O.MapaIfcIndisponivel as e:
            mapa, nota = [], str(e)
        except O.ErroOrcamento as e:   # tipo sem composição/mapa: mesma recusa (422) do /resumo, nunca 500
            raise HTTPException(422, str(e)) from None
        return {"aviso": O.AVISO, "ficticio": True, "tipo_obra": tipo, "bdi": round(bdi, 6),
                "bdi_nota": O.bdi_nota(tipo), "bdi_declarado": O.BDI_DECLARADO.get(tipo),
                "faixa_bdi_tcu": O.FAIXA_BDI_TCU, "composicoes": _executar(lambda: O.tabela(tipo)),
                "mapa_ifc": mapa, "mapa_ifc_nota": nota}

    @router.get("/resumo")
    def resumo(lote: str | None = None, obra: str | None = Q_OBRA):
        """EVM de custo FICTÍCIO na data de status (BAC, PV, EV, AC SINTÉTICO, CPI, SPI, EAC, VAC, TCPI), por
        obra, lote e serviço, a preços iniciais e com reajuste por índice sintético. Não usa a simulação do
        usuário (``simulacao_do_usuario``)."""
        P = obter_estado(obra).projeto
        _lote(P, lote)
        return _executar(lambda: O.resumo(P, lote=lote))

    @router.get("/curva-s-financeira")
    def curva(lote: str | None = None, passo_dias: int = Query(default=7, ge=1, le=92),
              obra: str | None = Q_OBRA):
        """Curva S financeira acumulada (PV até o fim da linha de base; EV e AC até a data de status), a
        preços iniciais e reajustada. Mesma regra de semana terminada da curva S física (``curva_s.py``)."""
        P = obter_estado(obra).projeto
        _lote(P, lote)
        return _executar(lambda: O.curva_s(P, lote=lote, passo_dias=passo_dias))

    @router.get("/classificacao-ifc", responses={
        404: {"description": "Obra desconhecida, ou nenhuma composição para a classe/tipo IFC informada."},
        422: {"description": "Obra sem ``meta.tipo_obra`` válido (ausente, vazio, não-texto ou desconhecido)."},
        503: {"description": "Mapa IFC indisponível: exportador IFC (ifcopenshell) não instalado."}})
    def classificacao(classe: str, predefined_type: str | None = None, object_type: str | None = None,
                      obra: str | None = Q_OBRA):
        """Composição FICTÍCIA para um elemento IFC pela classe, PredefinedType e ObjectType, segundo o mesmo
        mapa do exportador IFC. Se mais de um serviço usa a mesma classe/tipo, devolve ``ambiguo`` com os
        candidatos (vale a IfcClassificationReference gravada no elemento)."""
        P = obter_estado(obra).projeto
        tipo = _executar(lambda: O.tipo_obra(P))          # obra sem tipo válido: 422, nunca 500
        try:
            ref = O.classificacao_ifc(tipo, classe, predefined_type, object_type)
        except O.MapaIfcIndisponivel as e:                 # subclasse de ErroOrcamento: tratar ANTES
            raise HTTPException(503, str(e)) from None
        except O.ErroOrcamento as e:
            raise HTTPException(422, str(e)) from None
        if ref is None:
            raise HTTPException(404, f"sem mapeamento fictício para {classe} ({predefined_type})")
        return {"aviso": O.AVISO, **ref}

    return router


def ligar(app: FastAPI, obter_estado: Callable[[str | None], Any]) -> None:
    app.include_router(criar_router(obter_estado))
