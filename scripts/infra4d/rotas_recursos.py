"""Rotas de recursos (histograma, nivelamento, conflitos de linha de balanço).

Este módulo NÃO importa ``api.py`` e não tem estado global de projeto. Ele depende de duas
funções injetáveis (dependências do FastAPI):

- ``obter_projeto()``    -> ``Projeto``
- ``obter_resultado()``  -> função ``cenario -> dict`` (resultado de ``cenarios.executar``)

Ligação (duas formas equivalentes):

1. ``ligar(app, obter_estado)`` — contrato de ``api.registrar_rotas``: ``obter_estado(obra)``
   devolve o ``Estado`` da obra (com ``.projeto`` e ``.resultado(cenario)``); toda rota passa
   a aceitar ``?obra=<id>``.
2. Manual, com um único Estado ``est``::

       app.dependency_overrides[rotas_recursos.obter_projeto] = lambda: est.projeto
       app.dependency_overrides[rotas_recursos.obter_resultado] = lambda: est.resultado
       app.include_router(rotas_recursos.router)

``Estado.resultado`` já valida o cenário (404) e respeita a simulação corrente. Sem ligação,
as rotas respondem 503 (não configurado) em vez de carregar dados por conta própria.
"""

from __future__ import annotations

import re
import threading
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .cenarios import Projeto
from .recursos import conflitos_balanco, histograma, nivelar, sobrealocacao

router = APIRouter(prefix="/api/recursos", tags=["recursos"],
                   responses={404: {"description": "Obra ou cenário desconhecido"}, 503: {"description": "Rotas não ligadas ao app"}})


def obter_projeto(obra: str | None = Query(default=None, description="id da obra; padrão: a do app")) -> Projeto:
    raise HTTPException(503, "rotas de recursos não configuradas: injete obter_projeto (ver rotas_recursos.py)")


def obter_resultado(obra: str | None = Query(default=None, description="id da obra; padrão: a do app")
                    ) -> Callable[[str], dict]:
    raise HTTPException(503, "rotas de recursos não configuradas: injete obter_resultado (ver rotas_recursos.py)")


def ligar(app, obter_estado: Callable[[str | None], object]) -> None:
    """Liga o router a um app cujo estado é por obra (``obter_estado(obra)``)."""

    def _projeto(obra: str | None = Query(default=None, description="id da obra; padrão: a do app")):
        return obter_estado(obra).projeto

    def _resultado(obra: str | None = Query(default=None, description="id da obra; padrão: a do app")):
        return obter_estado(obra).resultado

    app.dependency_overrides[obter_projeto] = _projeto
    app.dependency_overrides[obter_resultado] = _resultado
    app.include_router(router)


def _lote_valido(P: Projeto, lote: str | None) -> None:
    if lote and lote not in {l["id"] for l in P.dados.get("lotes", [])}:
        raise HTTPException(404, f"lote desconhecido: {lote}")


def _publico(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


# cache do nivelamento: chave = (identidade do resultado do cenário, capacidades normalizadas). O Estado do
# api.py troca o objeto quando a simulação muda; o próprio objeto fica guardado para a identidade não ser
# reutilizada.
_cache_lock = threading.Lock()
_cache: list[tuple[dict, tuple, dict]] = []
_CACHE_MAX = 8
_RE_CAP = re.compile(r"^\s*([^:\s]+/[^:\s]+)\s*:\s*(-?\d+)\s*$")


def _recursos_existentes(P: Projeto) -> set[str]:
    out = set()
    for a in P.dados["atividades"]:
        if a.get("tipo", "tarefa") == "tarefa" and a.get("servico_id"):
            out.add(f"{a.get('lote_id') or '-'}/{a['servico_id']}")
            out.add(f"*/{a['servico_id']}")
    return out


def parse_capacidades(P: Projeto, brutas: list[str] | None) -> dict[str, int]:
    """``["*/TER:2", "L1/TER:3"]`` -> ``{"*/TER": 2, "L1/TER": 3}``. Formato inválido, N < 1, recurso
    inexistente ou repetido -> HTTP 422 com a causa."""
    caps: dict[str, int] = {}
    existentes = None
    for txt in brutas or []:
        m = _RE_CAP.match(txt or "")
        if not m:
            raise HTTPException(422, f"capacidade inválida {txt!r}: use RECURSO:N, com RECURSO = LOTE/SERVIÇO "
                                     f"ou */SERVIÇO (ex.: */TER:2)")
        rec, n = m.group(1), int(m.group(2))
        if n < 1:
            raise HTTPException(422, f"capacidade inválida {txt!r}: N deve ser inteiro >= 1")
        existentes = existentes or _recursos_existentes(P)
        if rec not in existentes:
            raise HTTPException(422, f"capacidade inválida {txt!r}: recurso {rec!r} inexistente nesta obra")
        if rec in caps:
            raise HTTPException(422, f"capacidade repetida para {rec!r}")
        caps[rec] = n
    return caps


def _nivelar_cacheado(P: Projeto, res: dict, caps: dict[str, int]) -> dict:
    chave = tuple(sorted(caps.items()))
    with _cache_lock:
        for r, k, saida in _cache:
            if r is res and k == chave:
                return saida
    saida = _publico(nivelar(P, res, caps or None))
    saida["capacidades_informadas"] = dict(chave)
    with _cache_lock:
        _cache.append((res, chave, saida))
        del _cache[:-_CACHE_MAX]
    return saida


@router.get("/histograma", responses={404: {"description": "Obra, cenário ou lote desconhecido"}})
def rota_histograma(cenario: str = "independente", lote: str | None = None,
                    agrupar: str = Query(default="semana", pattern="^(dia|semana)$"),
                    P: Projeto = Depends(obter_projeto), resultado=Depends(obter_resultado)):
    """Histograma de equipes por recurso (lote/serviço) e sobrealocação, por dia ou semana."""
    _lote_valido(P, lote)
    res = resultado(cenario)
    saida = histograma(P, res, lote=lote, agrupar=agrupar)
    sob = sobrealocacao(P, res, lote=lote)
    saida["sobrealocacao"] = {"total_dias_sobrealocados": sob["total_dias_sobrealocados"],
                              "recursos": [{k: v for k, v in r.items() if k != "sobrealocacao"}
                                           | {"dias": [d["data"] for d in r["sobrealocacao"]]}
                                           for r in sob["recursos"] if r["dias_sobrealocados"]]}
    return saida


@router.get("/nivelamento", responses={422: {"description": "Capacidade inválida, repetida ou de recurso inexistente"}})
def rota_nivelamento(cenario: str = "independente",
                     capacidade: list[str] | None = Query(default=None, description="repetível: RECURSO:N, "
                                                          "ex.: */TER:2 ou L1/TER:3"),
                     P: Projeto = Depends(obter_projeto), resultado=Depends(obter_resultado)):
    """A resposta ecoa ``capacidades_informadas`` (o que veio na URL) e ``capacidades`` (todas as
    aplicadas: padrão + informadas)."""
    caps = parse_capacidades(P, capacidade)
    return _nivelar_cacheado(P, resultado(cenario), caps)


@router.get("/conflitos-balanco", responses={404: {"description": "Obra, cenário ou lote desconhecido"}, 503: {"description": "Linha real indisponível (módulo de fiscalização ausente) ou rotas não ligadas"}})
def rota_conflitos(cenario: str = "independente", buffer_km: float = Query(default=1.0, ge=0, le=100),
                   buffer_dias: float = Query(default=0.0, ge=0, le=3650), lote: str | None = None,
                   com_linha_real: bool = Query(default=False, description='inclui conflitos JÁ OCORRIDOS '
                                                'entre as linhas reais dos diários (fiscalizacao.linha_real)'),
                   P: Projeto = Depends(obter_projeto), resultado=Depends(obter_resultado)):
    """Conflitos de frentes na linha de balanço (km × tempo), previstos e, opcionalmente, já ocorridos."""
    _lote_valido(P, lote)
    real = None
    if com_linha_real:
        try:
            from . import fiscalizacao
        except Exception as e:  # noqa: BLE001 — módulo de outro agente; ausência vira 503 explícito
            raise HTTPException(503, f'linha real indisponível: {type(e).__name__}: {e}')
        real = fiscalizacao.linha_real(P, fiscalizacao.diarios_da_obra(P), lote)
    return conflitos_balanco(P, resultado(cenario), buffer_km=buffer_km, buffer_dias=buffer_dias, lote=lote,
                             linha_real=real)
