"""Rotas de fiscalização: ``/api/fiscalizacao``.

Ligação: ``ligar(app, obter_estado)`` — ``obter_estado(obra)`` devolve um objeto com ``.projeto`` e
``.resultado(cenario)``. Toda rota aceita ``?obra=<id>``. Os diários servidos são SINTÉTICOS (gerados em
memória a partir dos boletins fictícios; ver ``fiscalizacao.py``) e toda resposta diz isso.

- ``GET  /diario?atividade_id=&de=&ate=&limite=``
- ``GET  /boletins?lote=``            (boletim estendido)
- ``GET  /conciliacao?lote=``
- ``GET  /produtividade?lote=``       (dia trabalhado × dia útil da obra)
- ``GET  /linha-real?lote=``
- ``GET  /nao-conformidades?lote=&situacao=&exemplos=``  (entidade NC; ``nao_conformidade.py``)
- ``POST /validar``  corpo: um diário (ou ``{"tipo": "boletim", ...}``); ``estado_anterior`` opcional
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Body, FastAPI, HTTPException, Query

from . import fiscalizacao as F


def _envelope(P, corpo: dict) -> dict:
    meta = P.dados.get("meta", {})
    return {"aviso": meta.get("aviso"), "sintetico": F.obra_ficticia(P),
            "origem": F.ORIGEM_SINTETICA, "data_status": meta.get("data_status"), **corpo}


def _lote(P, lote: str | None) -> None:
    if lote and lote not in {l["id"] for l in P.dados.get("lotes", [])}:
        raise HTTPException(404, f"lote desconhecido: {lote}")


def _diarios(P) -> list[dict]:
    try:
        return F.diarios_da_obra(P)
    except F.ErroFiscalizacao as e:
        raise HTTPException(409, str(e)) from None


def _data(v: str | None, nome: str) -> str | None:
    if v is None:
        return None
    if not F._RE_DATA.match(v):  # mesma regra do validar(): só AAAA-MM-DD (o filtro compara texto)
        raise HTTPException(422, f"{nome} deve ser AAAA-MM-DD")
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise HTTPException(422, f"{nome} deve ser AAAA-MM-DD") from None


def criar_router(obter_estado: Callable[[str | None], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/fiscalizacao", tags=["fiscalização"],
                       responses={404: {"description": "Obra desconhecida"}})
    Q_OBRA = Query(default=None, description="id da obra; padrão: a do app")

    @router.get("/diario", responses={404: {"description": "Obra ou atividade desconhecida"}, 409: {"description": "Diários sintéticos só existem em obra fictícia"}, 422: {"description": "Data de/ate fora do formato AAAA-MM-DD"}})
    def diario(atividade_id: str | None = None, de: str | None = None, ate: str | None = None,
               limite: int = Query(default=2000, ge=1, le=20000), obra: str | None = Q_OBRA):
        """Diários de obra (sintéticos, derivados dos boletins na obra fictícia), filtráveis por atividade e período."""
        P = obter_estado(obra).projeto
        if atividade_id and atividade_id not in P.atividades:
            raise HTTPException(404, f"atividade desconhecida: {atividade_id}")
        de_, ate_ = _data(de, "de"), _data(ate, "ate")
        regs = [r for r in _diarios(P)
                if (not atividade_id or r["atividade_id"] == atividade_id)
                and (not de_ or r["data"] >= de_) and (not ate_ or r["data"] <= ate_)]
        regs.sort(key=lambda r: (r["data"], r["atividade_id"]))
        return _envelope(P, {"total": len(regs), "truncado": len(regs) > limite, "diarios": regs[:limite]})

    @router.get("/boletins", responses={404: {"description": "Obra ou lote desconhecido"}, 409: {"description": "Diários sintéticos só existem em obra fictícia"}})
    def boletins(lote: str | None = None, obra: str | None = Q_OBRA):
        """Boletins estendidos por frente × período (quantidade, equipes·dia, chuva), agregados dos diários."""
        P = obter_estado(obra).projeto
        _lote(P, lote)
        bs = [b for b in F.boletins_estendidos(P, _diarios(P)) if not lote or b["lote_id"] == lote]
        return _envelope(P, {"lote": lote, "total": len(bs), "boletins": bs})

    @router.get("/conciliacao", responses={404: {"description": "Obra ou lote desconhecido"}, 409: {"description": "Diários sintéticos só existem em obra fictícia"}})
    def conciliacao(lote: str | None = None, obra: str | None = Q_OBRA):
        """Conciliação diários × boletins: divergências de quantidade/equipes e diários sem boletim."""
        P = obter_estado(obra).projeto
        _lote(P, lote)
        c = F.conciliar(P, _diarios(P), lote=lote)
        c.pop("itens")  # resumo: divergências bastam; itens completos ficam no módulo
        return _envelope(P, c)

    @router.get("/produtividade", responses={404: {"description": "Obra ou lote desconhecido"}, 409: {"description": "Diários sintéticos só existem em obra fictícia"}})
    def produtividade(lote: str | None = None, obra: str | None = Q_OBRA):
        """Produtividade trabalhada × produtividade pelo calendário, por frente."""
        P = obter_estado(obra).projeto
        _lote(P, lote)
        return _envelope(P, F.produtividade_trabalhada_x_calendario(P, _diarios(P), lote=lote))

    @router.get("/linha-real", responses={404: {"description": "Obra ou lote desconhecido"}, 409: {"description": "Diários sintéticos só existem em obra fictícia"}})
    def linha_real(lote: str | None = None, obra: str | None = Q_OBRA):
        """Linha real tempo × km de cada frente, a partir dos diários (para a linha de balanço)."""
        P = obter_estado(obra).projeto
        _lote(P, lote)
        return _envelope(P, F.linha_real(P, _diarios(P), lote=lote))

    @router.get("/nao-conformidades", responses={
        404: {"description": "Obra ou lote desconhecido"},
        409: {"description": "Exemplos sintéticos de NC só existem em obra fictícia (meta.ficticio = true)"},
        422: {"description": "Situação fora de aberta/em_tratamento/encerrada, ou cadastro de NC inválido no dataset "
                             "(todos os erros listados)"}})
    def nao_conformidades(lote: str | None = None, situacao: str | None = None,
                          exemplos: bool = Query(default=False, description="NCs SINTÉTICAS de demonstração "
                                                 "(só obra fictícia) em vez das declaradas no dataset"),
                          obra: str | None = Q_OBRA):
        """Não conformidades (entidade da fiscalização): cada NC com atividade, km, prazo, situação e evidência por
        referência + hash, avaliada contra o cenário independente. Devolve as vencidas (prazo anterior à data de
        status, não encerradas) e os alertas (NC não encerrada em atividade crítica). Obra sem NCs devolve lista
        vazia."""
        est = obter_estado(obra)
        P = est.projeto
        _lote(P, lote)
        from . import nao_conformidade as NC
        try:
            corpo = NC.relatorio(P, est.resultado("independente"), lote=lote, situacao=situacao, exemplos=exemplos)
        except NC.ExemploEmObraReal as e:
            raise HTTPException(409, str(e)) from None
        except NC.ErroNaoConformidade as e:
            raise HTTPException(422, str(e)) from None
        return _envelope(P, corpo)

    @router.post("/validar")
    def validar(registro: Any = Body(...), obra: str | None = Q_OBRA):
        """Valida um diário ou boletim estendido (regras da fiscalização, inspiradas na IN 57/DNIT/2021). Devolve erros por campo; não grava nada."""
        P = obter_estado(obra).projeto
        anterior = registro.get("estado_anterior") if isinstance(registro, dict) else None
        return F.validar(P, registro, estado_anterior=anterior)

    return router


def ligar(app: FastAPI, obter_estado: Callable[[str | None], Any]) -> None:
    app.include_router(criar_router(obter_estado))
