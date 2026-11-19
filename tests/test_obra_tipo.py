"""P8: ``meta.tipo_obra`` sem padrão silencioso. Helper único (``infra4d.obra``) e, por rota, obra sem tipo
declarado → 422 claro, nunca 500 e nunca "assumiu ferrovia"."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d.cenarios import Projeto
from infra4d.obra import TIPOS_OBRA, ErroTipoObra, tipo_obra
from ifc_opcional import eh_rota_ifc, requer_ifc

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts" / "infra4d"


@pytest.fixture(scope="module")
def ferrovia():
    return Projeto.carregar(RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json")


# ------------------------------------------------------------------ helper
@pytest.mark.parametrize("meta,esperado", [
    ({"tipo_obra": "ferrovia"}, "ferrovia"),
    ({"tipo_obra": " rodovia "}, "rodovia"),
    ({}, "sem meta.tipo_obra declarado"),
    ({"tipo_obra": ""}, "sem meta.tipo_obra declarado"),
    ({"tipo_obra": "   "}, "sem meta.tipo_obra declarado"),
    ({"tipo_obra": None}, "sem meta.tipo_obra declarado"),
    ({"tipo_obra": 1}, "sem meta.tipo_obra declarado"),
    ({"tipo_obra": ["ferrovia"]}, "sem meta.tipo_obra declarado"),
    ({"tipo_obra": "hidrovia"}, "desconhecido"),
    ({"tipo_obra": "Ferrovia"}, "desconhecido"),
])
def test_helper(meta, esperado):
    if esperado in TIPOS_OBRA:
        assert tipo_obra({"meta": meta}) == esperado
    else:
        with pytest.raises(ErroTipoObra, match=esperado):
            tipo_obra({"meta": meta})


def test_helper_aceita_projeto_e_recusa_sem_meta(ferrovia):
    assert tipo_obra(ferrovia) == "ferrovia" and tipo_obra(ferrovia.dados) == "ferrovia"
    for ruim in ({}, {"meta": "x"}, [], None):
        with pytest.raises(ErroTipoObra, match="meta"):
            tipo_obra(ruim)
    assert issubclass(ErroTipoObra, ValueError)


def test_nenhum_modulo_assume_ferrovia_por_padrao():
    """Guarda estática: o padrão silencioso não volta (``.get("tipo_obra", "ferrovia")``, ``or "ferrovia"``,
    ``else "ferrovia"``)."""
    rx = re.compile(r"""get\(\s*["']tipo_obra["']\s*,\s*["']ferrovia["']|(or|else)\s+["']ferrovia["']""")
    achados = [f"{p.relative_to(SCRIPTS)}:{i}" for p in SCRIPTS.rglob("*.py")
               for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if rx.search(ln)]
    assert achados == []


# ------------------------------------------------------------------ rotas
@pytest.fixture(scope="module")
def cliente_sem_tipo(ferrovia):
    from infra4d.api import criar_app
    d = copy.deepcopy(ferrovia.dados)
    d["meta"].pop("tipo_obra")
    return TestClient(criar_app(fontes={"semtipo": Projeto(d), "ferrovia": ferrovia}), raise_server_exceptions=False)


ROTAS = [
    ("/api/projeto", {"obra": "semtipo"}),
    ("/api/gis/geojson", {"obra": "semtipo"}),
    ("/api/massas/diagrama", {"obra": "semtipo"}),
    ("/api/massas/coerencia", {"obra": "semtipo"}),
    ("/api/referencia/km", {"obra": "semtipo", "km": 1}),
    ("/api/exportar/pacote.zip", {"obra": "semtipo"}),
    ("/api/exportar/dim_obra.csv", {"obra": "semtipo"}),
    ("/api/cronograma/exportar/xer", {"obra": "semtipo"}),
    ("/api/ifc/exportar", {"obra": "semtipo"}),
]


PARAM_ROTAS = [pytest.param(u, p, id=u, marks=[requer_ifc] if eh_rota_ifc(u) else []) for u, p in ROTAS]


@pytest.mark.parametrize("url,params", PARAM_ROTAS)
def test_rota_com_obra_sem_tipo_e_422_claro(cliente_sem_tipo, url, params):
    r = cliente_sem_tipo.get(url, params=params)
    assert r.status_code == 422, (r.status_code, r.text[:300])
    assert "tipo_obra" in r.text or "tipo de obra" in r.text


@pytest.mark.parametrize("url,params", PARAM_ROTAS)
def test_mesmas_rotas_funcionam_com_o_tipo_declarado(cliente_sem_tipo, url, params):
    r = cliente_sem_tipo.get(url, params={**params, "obra": "ferrovia"})
    assert r.status_code == 200, (url, r.status_code, r.text[:200])


def test_lista_de_obras_nao_esconde_as_outras_nem_assume_ferrovia(cliente_sem_tipo):
    obras = {o["id"]: o for o in cliente_sem_tipo.get("/api/obras").json()}
    assert obras["ferrovia"]["tipo"] == "ferrovia"
    assert obras["semtipo"]["tipo"] is None and "tipo_obra" in obras["semtipo"]["erro_tipo_obra"]


def test_historico_sem_obra_explicita_e_422_e_com_obra_funciona(ferrovia, tmp_path):
    from fastapi import FastAPI
    import infra4d.rotas_persistencia as rp
    from infra4d.persistencia import Banco
    d = copy.deepcopy(ferrovia.dados)
    d["meta"].pop("tipo_obra")

    class E:
        projeto = Projeto(d)

    app = FastAPI()

    @app.exception_handler(ErroTipoObra)
    def _h(_r, exc):  # o api.py real tem este handler (P8)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={"detail": f"tipo de obra inválido: {exc}"})

    rp.ligar(app, lambda obra=None: E, Banco(tmp_path / "b.sqlite"))
    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/api/historico/auditoria").status_code == 422      # chave da obra viria do tipo
    assert c.get("/api/historico/auditoria", params={"obra": "x"}).status_code == 200  # id explícito
