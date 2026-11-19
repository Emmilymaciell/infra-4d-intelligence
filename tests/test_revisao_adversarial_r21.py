"""Revisão adversarial — rodada 21 (curta): P8, tipo de obra sem padrão silencioso (``scripts/infra4d/obra.py``).

Perguntas: algum caminho ainda assume "ferrovia"? alguma rota dá 500 com tipo inválido? /api/obras mostra a
obra mal declarada sem quebrar a lista?

Cada teste traz no docstring o resultado esperado. Defeito confirmado fica ``xfail(strict=True, ...)``.
"""

import copy
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d.cenarios import Projeto
from infra4d.obra import ErroTipoObra, tipo_obra
from ifc_opcional import SEM_IFC, eh_rota_ifc, requer_ifc

RAIZ = Path(__file__).resolve().parents[1]
INVALIDOS = {"ausente": None, "vazio": "", "desconhecido": "metro", "número": 5, "lista": ["rodovia"],
             "maiúscula": "Rodovia"}
BARATOS = {"/api/backtest/sementes": {"n": "1", "passo_dias": "91"}, "/api/backtest": {"passo_dias": "91"},
           "/api/tendencia": {"passo_dias": "91"}, "/api/previsao-probabilistica": {"iteracoes": "10"}}
# rotas cujo resultado DEPENDE do tipo (composições, classes IFC, camadas, nomes): têm de recusar com 422
PRECISAM_DO_TIPO = ["/api/orcamento/resumo", "/api/orcamento/composicoes", "/api/orcamento/curva-s-financeira",
                    "/api/aceleracao", "/api/exportar/pacote.zip", "/api/ifc/exportar", "/api/gis/geojson",
                    "/api/projeto"]


def _defeito(motivo):
    return pytest.mark.xfail(strict=True, reason="DEFEITO: " + motivo)


def _com_tipo(base: Projeto, valor) -> Projeto:
    d = copy.deepcopy(base.dados)
    if valor is None:
        d["meta"].pop("tipo_obra", None)
    else:
        d["meta"]["tipo_obra"] = valor
    return Projeto(d)


@pytest.fixture(scope="module")
def cliente():
    """Um app com a rodovia íntegra ('boa'), uma variante por tipo inválido e uma com espaços em volta."""
    from infra4d.api import criar_app
    base = Projeto.carregar(RAIZ / "examples" / "synthetic" / "rodovia_ficticia.json")
    fontes = {"boa": base, "espacos": _com_tipo(base, " rodovia ")}
    fontes.update({nome: _com_tipo(base, v) for nome, v in INVALIDOS.items()})
    return TestClient(criar_app(fontes=fontes), raise_server_exceptions=False)


@pytest.mark.parametrize("nome", sorted(INVALIDOS))
def test_helper_recusa_e_nao_assume_ferrovia(nome):
    """``tipo_obra`` levanta ErroTipoObra para tipo ausente, vazio, desconhecido, não-texto e com maiúscula —
    nunca devolve 'ferrovia'. Espaços em volta de um tipo válido são aceitos."""
    meta = {} if INVALIDOS[nome] is None else {"tipo_obra": INVALIDOS[nome]}
    with pytest.raises(ErroTipoObra):
        tipo_obra({"meta": meta})
    with pytest.raises(ErroTipoObra):
        tipo_obra({})
    assert tipo_obra({"meta": {"tipo_obra": " rodovia "}}) == "rodovia"


def test_lista_de_obras_mostra_a_mal_declarada_sem_quebrar(cliente):
    """/api/obras responde 200 com as 8 obras do app. A íntegra e a de espaços vêm com tipo 'rodovia' e sem
    erro; cada mal declarada vem com ``tipo: null`` e ``erro_tipo_obra`` explicando — e continua com nome,
    lotes e atividades (a lista não perde a linha)."""
    r = cliente.get("/api/obras")
    assert r.status_code == 200
    obras = {o["id"]: o for o in r.json()}
    assert set(obras) == {"boa", "espacos", *INVALIDOS}
    for oid in ("boa", "espacos"):
        assert obras[oid]["tipo"] == "rodovia" and "erro_tipo_obra" not in obras[oid]
    for oid in INVALIDOS:
        o = obras[oid]
        assert o["tipo"] is None and "tipo_obra" in o["erro_tipo_obra"]
        assert o["nome"] == obras["boa"]["nome"] and o["atividades"] == obras["boa"]["atividades"]


@pytest.mark.parametrize("nome", sorted(INVALIDOS))
def test_rotas_que_dependem_do_tipo_recusam_com_422(cliente, nome):
    """Nas 8 rotas cujo resultado depende do tipo, a obra mal declarada dá 422 com 'tipo' no detail; a mesma
    rota na obra íntegra dá 200. (Sem ifcopenshell, /api/ifc/exportar fica para o teste seguinte — SKIP.)"""
    rotas = [r for r in PRECISAM_DO_TIPO if not (SEM_IFC and eh_rota_ifc(r))]
    for rota in rotas:
        r = cliente.get(rota, params={"obra": nome})
        assert r.status_code == 422 and "tipo" in str(r.json()["detail"]), (rota, r.status_code, r.text[:120])
    if nome == "ausente":   # controle, uma vez só
        for rota in rotas:
            assert cliente.get(rota, params={"obra": "boa"}).status_code == 200, rota


@requer_ifc
@pytest.mark.parametrize("nome", sorted(INVALIDOS))
def test_rota_ifc_que_depende_do_tipo_recusa_com_422(cliente, nome):
    for rota in [r for r in PRECISAM_DO_TIPO if eh_rota_ifc(r)]:
        r = cliente.get(rota, params={"obra": nome})
        assert r.status_code == 422 and "tipo" in str(r.json()["detail"]), (rota, r.status_code, r.text[:120])
        assert cliente.get(rota, params={"obra": "boa"}).status_code == 200, rota


def _varrer(cliente, obra):
    spec = cliente.get("/openapi.json").json()
    out = {}
    for rota, ops in sorted(spec["paths"].items()):
        op = ops.get("get")
        if not op:
            continue
        p = {"obra": obra, **BARATOS.get(rota, {})}
        for q in op.get("parameters", []):
            if q["in"] == "query" and q.get("required") and q["name"] not in p:
                p[q["name"]] = "2026-06-01" if "data" in q["name"] else "1"
        url = rota
        for q in op.get("parameters", []):
            if q["in"] == "path":
                url = url.replace("{" + q["name"] + "}", "1")
        out[rota] = cliente.get(url, params=p).status_code
    return out


CLASSIFICACAO = "/api/orcamento/classificacao-ifc"


@pytest.mark.parametrize("nome", ["ausente", "desconhecido"])
def test_nenhuma_rota_get_da_500_com_tipo_invalido(cliente, nome):
    """Todas as rotas GET do /openapi.json com a obra mal declarada: nenhuma 5xx (fora a do defeito abaixo,
    conferida à parte). As que não dependem do tipo (painel, cenários, tendência…) respondem 200 com os
    mesmos status da obra íntegra."""
    ruim, boa = _varrer(cliente, nome), _varrer(cliente, "boa")
    assert len(ruim) > 40
    assert [r for r, st in ruim.items() if st >= 500 and r != CLASSIFICACAO] == []
    for rota, st in ruim.items():
        if st == 200:
            assert boa[rota] == 200, rota


@pytest.mark.parametrize("nome", ["ausente", "desconhecido"])
# Regressão: defeito da rodada 21, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("GET /api/orcamento/classificacao-ifc responde 500 quando a obra não tem tipo válido: a rota chama "
#   "`O.classificacao_ifc(O.tipo_obra(P), …)` fora do `_executar` e só trata MapaIfcIndisponivel; o "
#   "ErroOrcamento ('obra sem meta.tipo_obra declarado…') escapa. É a única rota GET que ainda dá 500 com "
#   "tipo inválido. Correção: passar a chamada por `_executar` (422)")
@requer_ifc
def test_classificacao_ifc_com_tipo_invalido_e_422(cliente, nome):
    """Mesma obra mal declarada: 422 com 'tipo' no detail (na obra íntegra, classe inexistente dá 404)."""
    assert cliente.get(CLASSIFICACAO, params={"obra": "boa", "classe": "IfcNaoExiste"}).status_code == 404
    r = cliente.get(CLASSIFICACAO, params={"obra": nome, "classe": "IfcCourse"})
    assert r.status_code == 422 and "tipo" in str(r.json()["detail"]), r.status_code


def test_espacos_em_volta_do_tipo_valem_como_o_tipo(cliente):
    """' rodovia ' é aceito como 'rodovia': as rotas que dependem do tipo respondem 200 e o BDI é o da rodovia."""
    a = cliente.get("/api/orcamento/composicoes", params={"obra": "espacos"}).json()
    b = cliente.get("/api/orcamento/composicoes", params={"obra": "boa"}).json()
    assert a["tipo_obra"] == "rodovia" and a["bdi"] == b["bdi"]


def test_nenhum_modulo_python_tem_padrao_ferrovia_para_o_tipo():
    """Varredura do código do servidor: nenhuma linha lê ``tipo_obra`` com valor padrão
    (``.get("tipo_obra", …)``), nem faz ``or "ferrovia"`` / ``|| 'ferrovia'`` sobre um tipo. As ocorrências
    de ``dados["ferrovia"]`` que restam são o BLOCO de identificação da obra (chave do esquema, usada pelos
    dois tipos), não o tipo."""
    achados = []
    for p in (RAIZ / "scripts" / "infra4d").rglob("*.py"):
        for n, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"""get\(\s*["']tipo_obra["']\s*,""", ln) or re.search(r"""tipo\w*\s*(or|\|\|)\s*["']ferrovia["']""", ln):
                achados.append((p.name, n, ln.strip()[:100]))
    assert achados == []


# Regressão: defeito da rodada 21, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("o frontend ainda assume 'ferrovia': web/apresentacao.js monta o texto da apresentação guiada com "
#   "`(p && p.obra && p.obra.tipo) || 'ferrovia'`. Quando o projeto não carrega (obra mal declarada: "
#   "/api/projeto responde 422) ou vem sem tipo, o tour diz 'A obra (ferrovia)…'. É o padrão silencioso "
#   "que o P8 tirou do servidor. Correção: mostrar '—' ou 'tipo não declarado'")
def test_frontend_nao_tem_padrao_ferrovia_para_o_tipo():
    """Nenhum arquivo de web/ usa ``|| 'ferrovia'`` (ou ``?? 'ferrovia'``) como valor padrão."""
    achados = []
    for p in (RAIZ / "web").rglob("*.js"):
        for n, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"""(\|\||\?\?)\s*["']ferrovia["']""", ln):
                achados.append((p.name, n))
    assert achados == []
