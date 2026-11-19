"""Contrato estático interface × API (sem Chrome): toda chamada ``/api/...`` de ``web/api.js`` existe no
/openapi.json do ``criar_app()`` com o MÉTODO certo, e todo parâmetro de query que a interface envia está
declarado na rota. Pega rota renomeada ou parâmetro com erro de digitação antes do e2e.

Como lê o JavaScript (análise textual, declarada):
- ``web/api.js`` é o cliente único (o próprio arquivo diz "Todas as chamadas passam por aqui"); os demais
  ``web/*.js`` não podem chamar ``fetch``/``req`` com ``/api/`` direto (teste próprio);
- cada membro do objeto ``api`` é uma unidade; o método vem de ``req('MÉTODO', ...)`` na unidade (sem
  ``req``, é ``fetch``/URL de download: GET);
- caminho: literal que começa com ``/api/``; ``${...}`` no caminho vale qualquer segmento ({param});
- parâmetros: ``nome=`` precedido de ``?``, ``&``, crase, aspas ou ``[`` dentro da unidade;
- ``?obra=`` é acrescentado por ``comObra``/``req`` a toda chamada (exceto ``semObra``): a rota tem de
  declarar ``obra``, ou entra em ``OBRA_IGNORADA_ACEITA`` com o motivo;
- unidades dinâmicas (caminho vindo do servidor, ex.: ``urlEvidencia``) ficam fora, declaradas.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from infra4d.api import criar_app
from ifc_opcional import eh_rota_ifc, requer_ifc

RAIZ = Path(__file__).resolve().parents[1]
API_JS = RAIZ / "web" / "api.js"

DINAMICAS = {"urlEvidencia": "a rota vem da resposta de /api/riscos (evidências); conferida no teste das evidências"}
# rotas que recebem ?obra= da interface mas não dependem de obra (o parâmetro é ignorado, sem erro)
OBRA_IGNORADA_ACEITA = {("GET", "/api/saude"): "saúde da API é global (lista todas as obras)"}

_RE_MEMBRO = re.compile(r"^  (\w+):", re.M)
_RE_METODO = re.compile(r"""req\(\s*['"](GET|POST|PUT|DELETE|PATCH)['"]""")
_RE_CAMINHO = re.compile(r"/api/[A-Za-z0-9_\-/.]*(?:\$\{[^}]*\}[A-Za-z0-9_\-/.]*)*")
_RE_PARAM = re.compile(r"""[?&`'"\[]([a-z_][a-z0-9_]*)=""")


def _sem_comentarios(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return "\n".join(re.sub(r"(^|\s)//.*$", r"\1", ln) for ln in js.splitlines())


def _so_caminho(c: str) -> str:
    """Corta no 1º ``${`` que NÃO abre um segmento (``/produtividade${lote ? ...}`` é query condicional)."""
    i = 0
    while True:
        j = c.find("${", i)
        if j < 0:
            return c
        if j == 0 or c[j - 1] != "/":
            return c[:j]
        i = j + 2


def chamadas_da_interface(js: str) -> list[dict]:
    """[{membro, metodo, caminho (com {p}), params (set), sem_obra}] do objeto ``api`` de api.js."""
    js = _sem_comentarios(js)
    ini = js.index("export const api = {")
    corpo = js[ini:]
    pos = [(m.group(1), m.start()) for m in _RE_MEMBRO.finditer(corpo)]
    saida = []
    for k, (nome, p0) in enumerate(pos):
        bloco = corpo[p0: pos[k + 1][1] if k + 1 < len(pos) else len(corpo)]
        if nome in DINAMICAS:
            continue
        metodos = set(_RE_METODO.findall(bloco)) or {"GET"}
        caminhos = {re.sub(r"\$\{[^}]*\}", "{p}", _so_caminho(c)).rstrip("/") for c in _RE_CAMINHO.findall(bloco)}
        caminhos = {c for c in caminhos if c not in ("/api",)}
        params = set(_RE_PARAM.findall(bloco))
        for c in sorted(caminhos):
            for m in sorted(metodos):
                saida.append({"membro": nome, "metodo": m, "caminho": c, "params": params,
                              "sem_obra": "semObra: true" in bloco})
    return saida


def _casa(caminho_js: str, caminho_api: str) -> bool:
    padrao = re.escape(caminho_api)
    padrao = re.sub(r"\\\{[^}]*\\\}", r"[^/]+", padrao)
    return re.fullmatch(padrao, caminho_js.replace("{p}", "X")) is not None


def divergencias(chamadas: list[dict], openapi: dict) -> list[str]:
    out = []
    for ch in chamadas:
        alvo = [p for p in openapi["paths"] if _casa(ch["caminho"], p)]
        if not alvo:
            out.append(f"{ch['membro']}: {ch['metodo']} {ch['caminho']} não existe na API")
            continue
        ops = [(p, openapi["paths"][p].get(ch["metodo"].lower())) for p in alvo]
        ops = [(p, op) for p, op in ops if op]
        if not ops:
            out.append(f"{ch['membro']}: {ch['caminho']} existe, mas não aceita {ch['metodo']}")
            continue
        p, op = ops[0]
        declarados = {x["name"] for x in op.get("parameters", []) if x.get("in") == "query"}
        for q in sorted(ch["params"] - declarados):
            out.append(f"{ch['membro']}: {ch['metodo']} {p} recebe ?{q}= da interface, mas a rota não o declara")
        if not ch["sem_obra"] and "obra" not in declarados and (ch["metodo"], p) not in OBRA_IGNORADA_ACEITA:
            out.append(f"{ch['membro']}: {ch['metodo']} {p} recebe ?obra= (comObra) mas não declara 'obra'")
    return out


@pytest.fixture(scope="module")
def openapi():
    return criar_app().openapi()


@pytest.fixture(scope="module")
def chamadas():
    return chamadas_da_interface(API_JS.read_text(encoding="utf-8"))


def test_leitura_do_api_js_ve_as_chamadas(chamadas):
    assert len(chamadas) >= 50  # 52 em 2026-11-13
    por = {(c["membro"], c["metodo"]) for c in chamadas}
    assert ("simular", "POST") in por and ("limparSimulacao", "DELETE") in por and ("painel", "GET") in por
    hist = next(c for c in chamadas if c["membro"] == "recursosHistograma")
    assert hist["params"] == {"cenario", "agrupar", "lote"}
    assert next(c for c in chamadas if c["membro"] == "urlExportarCsv")["caminho"] == "/api/exportar/{p}.csv"


def test_toda_chamada_da_interface_existe_com_metodo_e_parametros(chamadas, openapi):
    # as chamadas de IFC são conferidas no teste abaixo (SKIP explícito sem ifcopenshell)
    assert divergencias([c for c in chamadas if not eh_rota_ifc(c["caminho"])], openapi) == []


@requer_ifc
def test_toda_chamada_ifc_da_interface_existe_com_metodo_e_parametros(chamadas, openapi):
    ifc = [c for c in chamadas if eh_rota_ifc(c["caminho"])]
    assert len(ifc) >= 3  # glb, vinculo, exportar
    assert divergencias(ifc, openapi) == []


def test_so_o_api_js_chama_a_api():
    outros = []
    for f in sorted((RAIZ / "web").glob("*.js")):
        if f.name == "api.js":
            continue
        js = _sem_comentarios(f.read_text(encoding="utf-8"))
        for m in re.finditer(r"\b(fetch|req)\s*\(\s*[`'\"]\s*/api/", js):
            outros.append(f"{f.name}: {js[m.start(): m.start() + 60]!r}")
    assert outros == [], "chamada à API fora do web/api.js (o contrato só lê o api.js)"


def test_detector_pega_rota_renomeada_metodo_e_parametro_com_erro(openapi):
    js = """export const api = {
  a: () => req('GET', `/api/painel?lotte=${x}`),
  b: () => req('GET', '/api/painell'),
  c: () => req('PUT', '/api/simulacao'),
  d: () => req('GET', `/api/cenarios/${encodeURIComponent(c)}`),
};"""
    d = divergencias(chamadas_da_interface(js), openapi)
    assert any("?lotte=" in x for x in d)
    assert any("/api/painell não existe" in x for x in d)
    assert any("não aceita PUT" in x for x in d)
    assert not any(x.startswith("d:") for x in d)


@pytest.mark.parametrize("de,para,esperado", [
    ("agrupar=${agrupar}", "agrupr=${agrupar}", "?agrupr="),                 # parâmetro com erro de digitação
    ("'/api/massas/coerencia'", "'/api/massas/coerensia'", "não existe"),    # rota renomeada
    ("req('DELETE', '/api/simulacao')", "req('PATCH', '/api/simulacao')", "não aceita PATCH"),
])
def test_mutacao_do_api_js_real_e_detectada(openapi, de, para, esperado):
    js = API_JS.read_text(encoding="utf-8")
    assert js.count(de) == 1, de
    d = divergencias(chamadas_da_interface(js.replace(de, para)), openapi)
    assert any(esperado in x for x in d), d
