"""Rotas de persistência e histórico: ``/api/historico``.

Ligação (contrato multi-obra do ``api.py``): ``ligar(app, obter_estado, banco=None)``.
``banco`` padrão: ``persistencia.Banco()`` → ``output/infra4d.sqlite`` (ou a variável de
ambiente ``INFRA4D_BANCO``); o arquivo só é criado no primeiro uso.

- ``POST /cenarios-salvos?obra=``  corpo JSON ``{"nome": ..., "ajustes": [...], "quem": ...}``
- ``GET  /cenarios-salvos?obra=``  lista (sem o resultado completo)
- ``GET  /cenarios-salvos/{id}?obra=``  resultado gravado + conferência de reprodução
- ``POST /snapshots?obra=&quem=``  registra a previsão atual (independente e construtora)
- ``GET  /evolucao?obra=``  série mensal SINTÉTICA + snapshots registrados
- ``GET  /auditoria?obra=&limite=``

"quem" é texto informado: o beta NÃO tem autenticação.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Body, FastAPI, HTTPException, Query, Request

from .cenarios import Ajuste, ErroAjuste
from .persistencia import (Banco, ErroPersistencia, chave_obra, evolucao_previsao, hash_dados,
                           reabrir_e_conferir, salvar_cenario_nomeado)

router = APIRouter(prefix="/api/historico", tags=["histórico"],
                   responses={404: {"description": "Obra desconhecida (parâmetro obra)"}, 503: {"description": "Rotas não ligadas ao app (ligar não foi chamado)"}})
_ATTR_ESTADO = "historico_obter_estado"
_ATTR_BANCO = "historico_banco"
_ATTR_CACHE = "historico_cache_evolucao"
_cache_lock = threading.Lock()


def ligar(app: FastAPI, obter_estado, banco: Banco | None = None) -> None:
    setattr(app.state, _ATTR_ESTADO, obter_estado)
    setattr(app.state, _ATTR_BANCO, banco or Banco())
    setattr(app.state, _ATTR_CACHE, {})
    app.include_router(router)


def _ctx(request: Request, obra: str | None):
    obter = getattr(request.app.state, _ATTR_ESTADO, None)
    banco = getattr(request.app.state, _ATTR_BANCO, None)
    if obter is None or banco is None:
        raise HTTPException(503, "rotas de histórico não ligadas: chame rotas_persistencia.ligar(app, obter_estado)")
    est = obter(obra)  # 404 de obra desconhecida vem daqui
    return est, banco, chave_obra(obra, est.projeto)


@router.post("/cenarios-salvos", responses={409: {"description": "Já existe cenário com este nome na obra"}, 422: {"description": "Nome ausente ou ajuste inválido"}})
def salvar(request: Request, corpo: dict = Body(...), obra: str | None = Query(None)):
    """Salva um cenário nomeado (ajustes de simulação + resultado completo) da obra e registra na auditoria."""
    est, banco, chave = _ctx(request, obra)
    nome = corpo.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        raise HTTPException(422, "informe 'nome' (texto) do cenário")
    brutos = corpo.get("ajustes") or []
    if not isinstance(brutos, list):
        raise HTTPException(422, "'ajustes' deve ser uma lista")
    try:
        ajustes = [Ajuste.de_dict(a) for a in brutos]
        return salvar_cenario_nomeado(banco, est.projeto, chave, nome.strip(), ajustes, corpo.get("quem"))
    except ErroAjuste as e:
        raise HTTPException(422, f"ajuste inválido: {e}") from None
    except ErroPersistencia as e:
        raise HTTPException(409, str(e)) from None


@router.get("/cenarios-salvos")
def listar(request: Request, obra: str | None = Query(None)):
    """Lista os cenários salvos da obra (sem o resultado completo)."""
    _est, banco, chave = _ctx(request, obra)
    return {"obra": chave, "cenarios": banco.listar_cenarios(chave)}


@router.get("/cenarios-salvos/{id_}", responses={404: {"description": "Cenário salvo inexistente ou de outra obra"}})
def reabrir(request: Request, id_: int, obra: str | None = Query(None)):
    """Reabre um cenário salvo e confere se ele se reproduz com os dados atuais da obra."""
    est, banco, chave = _ctx(request, obra)
    try:
        salvo = reabrir_e_conferir(banco, est.projeto, id_)
    except ErroPersistencia as e:
        raise HTTPException(404, str(e)) from None
    if salvo["obra"] != chave:
        raise HTTPException(404, f"cenário salvo {id_} não pertence à obra {chave}")
    return salvo


@router.post("/snapshots")
def registrar_snapshot(request: Request, obra: str | None = Query(None), quem: str | None = Query(None)):
    """Registra a previsão atual (independente e construtora) como snapshot da data de status."""
    from .painel import avanco

    est, banco, chave = _ctx(request, obra)
    h = hash_dados(est.projeto)
    gravados = []
    for cenario in ("independente", "construtora"):
        r = est.resultado(cenario)
        av = round(100 * avanco(est.projeto, r, est.projeto.data_status), 2)
        banco.gravar_snapshot(chave, cenario, r, av, h)
        gravados.append({"cenario": cenario, "data_status": r["data_status"], "termino": r["termino"],
                         "avanco_real_pct": av})
    banco.auditar("registrar_snapshot", chave, quem, {}, {"snapshots": gravados})
    return {"obra": chave, "gravados": gravados}


@router.get("/evolucao")
def evolucao(request: Request, obra: str | None = Query(None)):
    """Série mensal SINTÉTICA de como a previsão evoluiu (independente × construtora), com as simplificações declaradas, mais os snapshots registrados."""
    est, banco, chave = _ctx(request, obra)
    h = hash_dados(est.projeto)
    cache = getattr(request.app.state, _ATTR_CACHE)
    with _cache_lock:
        serie = cache.get((chave, h))
    if serie is None:
        serie = evolucao_previsao(est.projeto)
        with _cache_lock:
            cache[(chave, h)] = serie
    return {"obra": chave, **serie, "snapshots_registrados": banco.listar_snapshots(chave)}


@router.get("/auditoria")
def auditoria(request: Request, obra: str | None = Query(None), limite: int = Query(200, ge=1, le=5000)):
    """Trilha de auditoria da obra (quem, quando, ação, parâmetros e resultado). 'Quem' é texto informado: o beta não tem autenticação."""
    _est, banco, chave = _ctx(request, obra)
    return {"obra": chave, "registros": banco.listar_auditoria(chave, limite)}
