"""OpenAPI do app real: toda rota registrada (inclusive as ligadas por ``ligar()``) aparece em
/openapi.json, e cada operação tem DESCRIÇÃO e ao menos uma resposta 4xx PRÓPRIA documentada
(a 422 automática de validação do FastAPI, "Validation Error", não conta).

Rotas de outros donos que ainda não cumprem o critério ficam em ``PENDENTES`` (lista enviada ao
orquestrador). O teste falha se aparecer rota NOVA fora do critério, e também se uma pendente for
corrigida sem sair da lista: a lista só encolhe.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from infra4d.api import criar_app

MEUS = {"infra4d.importadores.rotas", "infra4d.rotas_persistencia", "infra4d.rotas_exportacao", "infra4d.rotas_dcma",
        "infra4d.rotas_medicoes", "infra4d.rotas_revisoes",
        "infra4d.api", "infra4d.relatorio",  # api.py e relatorio.py: dono temporário só para a documentação
        # documentação assumida (só docstrings/responses) a pedido do orquestrador, 2026-11-13:
        "infra4d.rotas_fiscalizacao", "infra4d.rotas_referencia", "infra4d.rotas_massas", "infra4d.rotas_previsao",
        "infra4d.rotas_produtividade", "infra4d.rotas_sensibilidade", "infra4d.rotas_clima", "infra4d.rotas_recursos"}

# Rotas que NÃO têm erro do cliente possível (sem parâmetro, não dependem de obra): exigem descrição, mas
# não um 4xx — documentar um 4xx que nunca acontece seria mentir no contrato.
ISENTAS_4XX = {("GET", "/api/saude"), ("GET", "/api/obras"), ("GET", "/")}

PENDENTES: set[tuple[str, str]] = set()  # zerada em 2026-11-13: toda rota cumpre o critério


def achatar(rotas, prefixo=""):
    """APIRoutes do app, inclusive dentro dos routers incluídos (FastAPI 0.16x embrulha em _IncludedRouter)."""
    for r in rotas:
        if isinstance(r, APIRoute):
            yield prefixo + r.path, r
        elif hasattr(r, "original_router"):
            yield from achatar(r.original_router.routes, prefixo + (getattr(r.include_context, "prefix", "") or ""))


def operacoes(app: FastAPI):
    for p, r in achatar(app.routes):
        if r.include_in_schema:
            for m in sorted(r.methods - {"HEAD"}):
                yield m, p, r


def fora_do_criterio(app: FastAPI) -> dict[tuple[str, str], tuple[str, list[str]]]:
    sp = app.openapi()
    out = {}
    for m, p, r in operacoes(app):
        op = sp["paths"].get(p, {}).get(m.lower())
        if op is None:
            out[(m, p)] = (r.endpoint.__module__, ["ausente do openapi"])
            continue
        faltas = []
        if not (op.get("description") or "").strip():
            faltas.append("sem descrição")
        if (m, p) not in ISENTAS_4XX and not [c for c, v in op.get("responses", {}).items()
                                               if str(c).startswith("4") and v.get("description") != "Validation Error"]:
            faltas.append("sem 4xx próprio documentado")
        if faltas:
            out[(m, p)] = (r.endpoint.__module__, faltas)
    return out


@pytest.fixture(scope="module")
def app():
    return criar_app()


def test_toda_rota_registrada_esta_no_openapi_e_vice_versa(app):
    sp = app.openapi()
    registradas = {(m, p) for m, p, _ in operacoes(app)}
    documentadas = {(m.upper(), p) for p, ops in sp["paths"].items() for m in ops}
    assert registradas == documentadas
    ligados = set(app.state.rotas_ligadas)
    modulos = {r.endpoint.__module__.removeprefix("infra4d.") for _, _, r in operacoes(app)}
    assert ligados <= modulos, ligados - modulos  # cada módulo de ligar() contribuiu rotas ao schema
    assert len(registradas) >= 60


def test_minhas_rotas_tem_descricao_e_4xx(app):
    minhas = {k: v for k, v in fora_do_criterio(app).items() if v[0] in MEUS}
    assert minhas == {}
    n = sum(1 for _, _, r in operacoes(app) if r.endpoint.__module__ in MEUS)
    assert n >= 48  # 31 anteriores + 17 dos 8 arquivos assumidos (contagem de 2026-11-13)


def test_rotas_de_outros_donos_so_podem_sair_da_lista(app):
    faltando = set(fora_do_criterio(app))
    novas = faltando - PENDENTES
    assert not novas, f"rota nova sem descrição ou sem 4xx documentado: {sorted(novas)}"
    corrigidas = PENDENTES - faltando
    assert not corrigidas, f"já cumprem o critério; tire de PENDENTES: {sorted(corrigidas)}"


def test_detector_ve_rota_sem_documentacao():
    a = FastAPI()

    @a.get("/sem")
    def sem(x: int):
        return x

    @a.get("/com", responses={404: {"description": "não achou"}})
    def com():
        """Rota documentada."""
        return 1

    f = fora_do_criterio(a)
    assert f[("GET", "/sem")][1] == ["sem descrição", "sem 4xx próprio documentado"]  # a 422 automática não conta
    assert ("GET", "/com") not in f


@pytest.mark.parametrize("url,modelo", [("/api/historico/auditoria", None), ("/api/exportar/dim_obra.csv",
                                                                            "/api/exportar/{tabela}.csv"),
                                        ("/api/dcma", None), ("/api/cronograma/exportar/mspdi", None),
                                        ("/api/cronograma/exportar/xer", None)])
def test_404_documentado_e_o_que_a_rota_responde(app, url, modelo):
    c = TestClient(app)
    assert c.get(url, params={"obra": "obra-que-nao-existe"}).status_code == 404
    op = app.openapi()["paths"][modelo or url]["get"]
    assert "404" in op["responses"]
