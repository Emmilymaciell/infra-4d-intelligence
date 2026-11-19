"""Rotas de referência linear: ``/api/referencia``.

Ligação pela API: ``ligar(app, obter_estado)``. ``obter_estado(obra)`` devolve um objeto com
``.projeto`` (``cenarios.Projeto``) e ``.resultado(cenario)``. Este módulo não guarda estado de obra;
só um cache do eixo por identidade do dicionário de dados.

- ``GET /api/referencia/km?km=&obra=``   (ou ``estaca=`` no lugar de ``km``)
- ``GET /api/referencia/ponto?x=&y=&obra=``

Números na QUERY usam PONTO decimal (``km=12.5``); vírgula (``km=12,5``) dá 422 — decisão declarada
(revisão r6). Na ESTACA, em texto, vírgula e ponto valem (``estaca=625+10,50``).
"""

from __future__ import annotations

from .obra import tipo_obra as _tipo_declarado
import threading

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .referencia_linear import Eixo, ErroReferencia, cobertura

CENARIO = "independente"
_cache_lock = threading.Lock()
_cache: list[tuple[dict, Eixo]] = []


def _eixo(dados: dict) -> Eixo:
    with _cache_lock:
        for d, e in _cache:
            if d is dados:
                return e
        e = Eixo.da_obra(dados)
        _cache.append((dados, e))
        del _cache[:-8]
        return e


def _tipo_obra(estado) -> str:
    return _tipo_declarado(estado.projeto)  # tipo DECLARADO (P8): sem padrão "ferrovia"


def _resumo_atividade(a: dict, r: dict | None) -> dict:
    total = a.get("quantidade_total")
    if total:
        pct = round(100 * a.get("quantidade_executada", 0.0) / total, 1)
    else:
        pct = a.get("percentual_executado", 0.0)
    out = {"id": a["id"], "nome": a.get("nome"), "servico_id": a.get("servico_id"), "lote_id": a.get("lote_id"),
           "segmento_id": a.get("segmento_id"), "km_ini": a.get("km_ini"), "km_fim": a.get("km_fim"),
           "status": a.get("status", "nao_iniciada"), "percentual_executado_data_status": pct}
    if r is not None:
        out.update(inicio=r["inicio"], termino=r["termino"], critica=r["critica"], folga_total=r["folga_total"])
    return out


def criar_router(obter_estado) -> APIRouter:
    router = APIRouter(prefix="/api/referencia", tags=["referência linear"],
                       responses={404: {"description": "Obra desconhecida"}})

    @router.get("/km", responses={422: {"description": "km/estaca inválidos, ambos ou nenhum informado, ou fora do eixo"}})
    def por_km(km: float | None = Query(None, description="km do eixo"),
               estaca: str | None = Query(None, description="alternativa ao km: '1234+15,00'"),
               trecho: int | None = Query(None, ge=0, description="trecho do estaqueamento (equação de estacas)"),
               obra: str | None = None):
        """Referência linear por km ou estaca: coordenadas no eixo, lote, segmento e atividades que cobrem o ponto."""
        est = obter_estado(obra)
        dados = est.projeto.dados
        try:
            eixo = _eixo(dados)
            if (km is None) == (estaca is None):
                raise ErroReferencia("informe exatamente um entre km e estaca")
            if km is None:
                km = eixo.km_da_estaca(estaca, trecho)
            ponto = eixo.ponto_em(km)
        except ErroReferencia as e:
            raise HTTPException(422, str(e)) from None
        cob = cobertura(dados, km)
        res = est.resultado(CENARIO)["atividades"]
        return {
            "obra": obra, "tipo_obra": _tipo_obra(est), "km": km, "estaca": ponto["estaca"],
            **({"estaca_trecho": ponto["estaca_trecho"]} if "estaca_trecho" in ponto else {}),
            "ponto": {k: ponto[k] for k in ("x", "y", "cota", "rumo_graus")},
            "lote": None if not cob["lote"] else {k: cob["lote"].get(k) for k in ("id", "nome", "km_ini", "km_fim",
                                                                                  "construtora")},
            "segmento": cob["segmento"],
            "cenario": CENARIO,
            "atividades": [_resumo_atividade(a, res.get(a["id"])) for a in cob["atividades"]],
        }

    @router.get("/ponto", responses={422: {"description": "Ponto fora do alcance do eixo"}})
    def por_ponto(x: float, y: float, obra: str | None = None):
        """Localiza um ponto (x, y) no eixo: km, estaca e afastamento."""
        est = obter_estado(obra)
        try:
            loc = _eixo(est.projeto.dados).localizar(x, y)
        except ErroReferencia as e:
            raise HTTPException(422, str(e)) from None
        return {"obra": obra, "tipo_obra": _tipo_obra(est), "x": x, "y": y, **loc}

    return router


def ligar(app: FastAPI, obter_estado) -> None:
    app.include_router(criar_router(obter_estado))
