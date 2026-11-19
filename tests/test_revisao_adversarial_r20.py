"""Revisão adversarial — rodada 20: varredura sistemática de robustez sobre TODAS as rotas do /openapi.json.

Para cada rota GET/POST/DELETE de ``criar_app()``: obra desconhecida, obra vazia e, para cada parâmetro de
consulta ou de caminho, valores de borda (vazio, texto, negativo, zero, enorme, NaN, infinito, data inválida,
datas fora do horizonte, texto longo, marcação HTML, byte nulo); nos POST, corpo vazio, JSON inválido, lista,
objeto vazio e tipos errados. Exigências:

- nunca 500 nem exceção escapando do servidor;
- nenhuma chamada acima de 30 s;
- todo 4xx com ``detail`` legível (texto não vazio, ou a lista de erros de validação com ``msg``).

Leve: TestClient em processo, uma obra por vez, parâmetros baratos nas rotas caras. As contagens exigidas
(rotas cobertas, chamadas) vêm do próprio /openapi.json, não de número cravado.
Defeito confirmado fica ``xfail(strict=True, reason="DEFEITO: ...")``.
"""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d.cenarios import Projeto
from ifc_opcional import SEM_IFC, eh_rota_ifc, requer_ifc

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")
LIMITE_S = 30.0
BORDAS = ["", " ", "abc", "-1", "0", "999999999999", "NaN", "inf", "1e400", "2026-02-30", "0001-01-01", "9999-12-31",
          "null", "true", "<script>alert(1)</script>", "ç" * 300, "a\x00b"]
BORDAS_DE_CAMINHO = ["abc", "-1", "0", "999999999999", "ç", "a b"]
# parâmetros baratos para as rotas caras (o custo máximo de pedido válido é medido à parte, mais abaixo)
BARATOS = {"/api/backtest/sementes": {"n": "1", "passo_dias": "91"}, "/api/backtest": {"passo_dias": "91"},
           "/api/tendencia": {"passo_dias": "91"}, "/api/previsao-probabilistica": {"iteracoes": "10"}}
CORPOS = {"vazio": b"", "JSON inválido": b"{nao json", "lista": b"[]", "objeto vazio": b"{}",
          "tipos errados": b'{"ajustes": "x", "a": 1, "b": 2, "nome": 5, "conteudo": [], "cenario": {}}',
          "nulos": b'{"ajustes": null, "a": null, "b": null, "nome": null}', "número": b"5", "texto": b'"abc"'}


def _defeito(motivo):
    return pytest.mark.xfail(strict=True, reason="DEFEITO: " + motivo)


def _app(obra):
    from infra4d.api import criar_app
    P = Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{obra}_ficticia.json")
    return TestClient(criar_app(fontes={obra: P}), raise_server_exceptions=False), P


def _chamar(c, metodo, url, params, **kw):
    """(status ou 'EXC …', segundos, detail legível?, trecho da resposta)."""
    t = time.perf_counter()
    try:
        r = c.request(metodo, url, params=params, **kw)
    except BaseException as e:  # noqa: BLE001 — exceção escapando do TestClient é achado, não erro do teste
        return f"EXC {type(e).__name__}", time.perf_counter() - t, False, str(e)[:160]
    dt = time.perf_counter() - t
    legivel = True
    if 400 <= r.status_code < 500:
        try:
            det = r.json().get("detail")
        except Exception:  # noqa: BLE001
            det = None
        legivel = (isinstance(det, str) and bool(det.strip())) or (
            isinstance(det, list) and bool(det) and all(isinstance(x, dict) and x.get("msg") for x in det)) or (
            isinstance(det, dict) and bool(det))
    return r.status_code, dt, legivel, r.text[:160]


def _varrer(obra: str) -> dict:
    c, _ = _app(obra)
    spec = c.get("/openapi.json").json()
    chamadas, operacoes = [], []
    for rota, ops in sorted(spec["paths"].items()):
        for metodo, op in sorted(ops.items()):
            if metodo not in ("get", "post", "delete"):
                continue
            operacoes.append((metodo, rota))
            ps = op.get("parameters", [])
            consulta = [p["name"] for p in ps if p["in"] == "query" and p["name"] != "obra"]
            caminho = [p["name"] for p in ps if p["in"] == "path"]
            base = {"obra": obra, **BARATOS.get(rota, {})}
            for p in ps:
                if p["in"] == "query" and p.get("required") and p["name"] not in base:
                    base[p["name"]] = "2026-06-01" if "data" in p["name"] else "1"
            url = rota
            for k in caminho:
                url = url.replace("{" + k + "}", "1")
            casos = [("base", url, base), ("obra desconhecida", url, {**base, "obra": "nao-existe"}),
                     ("obra vazia", url, {**base, "obra": ""}), ("sem obra", url, {k: v for k, v in base.items() if k != "obra"})]
            casos += [(f"{nome}={v[:24]!r}", url, {**base, nome: v}) for nome in consulta for v in BORDAS]
            casos += [(f"caminho {k}={v!r}", rota.replace("{" + k + "}", v), base) for k in caminho for v in BORDAS_DE_CAMINHO]
            for rotulo, u, params in casos:
                corpos = list(CORPOS.items()) if metodo == "post" and rotulo == "base" else (
                    [("vazio", b"")] if metodo == "post" else [(None, None)])
                for nome_corpo, corpo in corpos:
                    kw = {} if corpo is None else {"content": corpo, "headers": {"Content-Type": "application/json"}}
                    st, dt, legivel, trecho = _chamar(c, metodo.upper(), u, params, **kw)
                    chamadas.append({"op": f"{metodo.upper()} {rota}", "caso": rotulo + (f" · corpo {nome_corpo}" if nome_corpo else ""),
                                     "status": st, "s": dt, "legivel": legivel, "trecho": trecho})
    return {"operacoes": operacoes, "chamadas": chamadas}


@pytest.fixture(scope="module", params=OBRAS)
def varredura(request):
    return _varrer(request.param)


def test_a_varredura_cobre_todas_as_operacoes_do_openapi(varredura):
    """Toda operação GET/POST/DELETE declarada no /openapi.json foi chamada (pelo menos: base, obra
    desconhecida, obra vazia e sem obra) e a rota de documentação lista mais de 50 caminhos."""
    feitas = {x["op"] for x in varredura["chamadas"]}
    assert feitas == {f"{m.upper()} {r}" for m, r in varredura["operacoes"]}
    assert len(varredura["operacoes"]) > 50
    por_op = {}
    for x in varredura["chamadas"]:
        por_op[x["op"]] = por_op.get(x["op"], 0) + 1
    assert min(por_op.values()) >= 4


def test_nenhuma_entrada_de_borda_da_500(varredura):
    """Nenhuma das chamadas da varredura responde 5xx nem deixa exceção escapar."""
    ruins = [(x["op"], x["caso"], x["status"], x["trecho"][:80]) for x in varredura["chamadas"]
             if not isinstance(x["status"], int) or x["status"] >= 500]
    if SEM_IFC:  # sem ifcopenshell, classificacao-ifc responde 503 por contrato (OpenAPI); só esse 503 é aceito
        ruins = [r for r in ruins if not (r[2] == 503 and eh_rota_ifc(r[0].split(" ", 1)[1]))]
    assert ruins == [], ruins[:10]


@requer_ifc
def test_classificacao_ifc_nunca_da_5xx_com_o_ifc_instalado(varredura):
    ruins = [(x["op"], x["caso"], x["status"]) for x in varredura["chamadas"]
             if eh_rota_ifc(x["op"].split(" ", 1)[1]) and (not isinstance(x["status"], int) or x["status"] >= 500)]
    assert ruins == [], ruins[:10]


def test_nenhuma_chamada_passa_de_30_segundos(varredura):
    lentas = [(x["op"], x["caso"], round(x["s"], 1)) for x in varredura["chamadas"] if x["s"] > LIMITE_S]
    assert lentas == [], lentas[:10]


def test_todo_4xx_tem_detail_legivel(varredura):
    """Todo 4xx traz ``detail``: texto não vazio, lista de erros de validação com ``msg``, ou objeto não vazio."""
    mudos = [(x["op"], x["caso"], x["status"], x["trecho"][:80]) for x in varredura["chamadas"]
             if isinstance(x["status"], int) and 400 <= x["status"] < 500 and not x["legivel"]]
    assert mudos == [], mudos[:10]


def test_obra_desconhecida_nunca_e_atendida(varredura):
    """Com ``obra=nao-existe`` nenhuma operação que recebe a obra responde 200 com dados de outra obra: ou é
    404, ou é erro de validação anterior (4xx). Só três operações não dependem de obra e respondem 200: a
    página inicial, a lista de obras e a saúde."""
    atendidas = {x["op"] for x in varredura["chamadas"] if x["caso"].startswith("obra desconhecida")
                 and x["status"] == 200}
    assert atendidas <= {"GET /", "GET /api/obras", "GET /api/saude"}, sorted(atendidas)


# =============================================================================
# corpos de POST com forma válida e valores de borda
# =============================================================================
@pytest.fixture(scope="module")
def rodovia():
    c, P = _app("rodovia")
    alvo = next(a["id"] for a in P.dados["atividades"] if a.get("quantidade_total") and a["status"] == "nao_iniciada")
    return c, alvo


def _simular(c, corpo):
    r = c.post("/api/simulacao", params={"obra": "rodovia"},
               content=corpo if isinstance(corpo, bytes) else corpo.encode(), headers={"Content-Type": "application/json"})
    c.delete("/api/simulacao", params={"obra": "rodovia"})
    return r


SIMULACAO = {
    # nome: (função(alvo) -> corpo, status esperado)
    "produtividade Infinity": (lambda a: '{"ajustes":[{"atividade_id":"%s","produtividade":Infinity}]}' % a, 422),
    "produtividade 0": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "produtividade": 0}]}), 422),
    "produtividade negativa": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "produtividade": -1}]}), 422),
    "produtividade ínfima (estoura o calendário)": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "produtividade": 1e-300}]}), 422),
    "produtividade em texto": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "produtividade": "abc"}]}), 422),
    "equipes 0": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "equipes": 0}]}), 422),
    "equipes 1e9": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "equipes": 10 ** 9}]}), 422),
    "equipes fracionárias": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "equipes": 2.5}]}), 422),
    "atividade inexistente": (lambda a: json.dumps({"ajustes": [{"atividade_id": "NAO", "equipes": 2}]}), 422),
    "atividade nula": (lambda a: json.dumps({"ajustes": [{"atividade_id": None, "equipes": 2}]}), 422),
    "ajuste vazio": (lambda a: json.dumps({"ajustes": [{}]}), 422),
    "ajustes nulo": (lambda a: '{"ajustes": null}', 422),
    "id de 1 MB": (lambda a: json.dumps({"ajustes": [{"atividade_id": "A" * 1_000_000, "equipes": 2}]}), 422),
    "100 mil colchetes aninhados": (lambda a: "[" * 100_000 + "]" * 100_000, 400),
    "inteiro de 5000 dígitos": (lambda a: '{"ajustes":[{"atividade_id":"%s","equipes":%s}]}' % (a, "9" * 5000), 400),
    "5000 ajustes válidos": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "equipes": 2}] * 5000}), 200),
    "equipes válidas": (lambda a: json.dumps({"ajustes": [{"atividade_id": a, "equipes": 2}]}), 200),
}


@pytest.mark.parametrize("nome", sorted(SIMULACAO))
def test_simulacao_valores_de_borda(rodovia, nome):
    """POST /api/simulacao com a forma certa e um valor de borda: recusa com 4xx e detail (ou aceita, nos dois
    casos válidos), em menos de 30 s, e a simulação anterior fica como estava (nenhum ajuste ativo depois)."""
    c, alvo = rodovia
    corpo, esperado = SIMULACAO[nome]
    t = time.perf_counter()
    r = _simular(c, corpo(alvo))
    assert time.perf_counter() - t < LIMITE_S
    assert r.status_code == esperado, (r.status_code, r.text[:200])
    if esperado >= 400:
        assert r.json()["detail"]
    assert c.get("/api/simulacao", params={"obra": "rodovia"}).json().get("ajustes", []) == []


@pytest.mark.parametrize("nome,corpo", [
    ("produtividade NaN", '{"ajustes":[{"atividade_id":"%s","produtividade":NaN}]}'),
    ("produtividade -Infinity", '{"ajustes":[{"atividade_id":"%s","produtividade":-Infinity}]}'),
    ("equipes 1e400", '{"ajustes":[{"atividade_id":"%s","equipes":1e400}]}')])
# Regressão: defeito da rodada 20, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("POST /api/simulacao responde 500 quando o JSON traz NaN ou −Infinity em `produtividade`, ou 1e400 (que o "
#   "leitor JSON do Python converte em infinito) em `equipes`. `Infinity` em produtividade já dá 422 "
#   "('deve ser um número positivo'); nos outros três, a exceção observada é `ValueError: Out of range "
#   "float values are not JSON compliant` ao serializar a resposta (o valor não finito é ecoado no JSON de "
#   "saída). Correção: recusar número não finito no modelo do ajuste (ex.: `allow_inf_nan=False`) e "
#   "devolver 422")
def test_simulacao_com_numero_nao_finito_e_422(rodovia, nome, corpo):
    """O leitor JSON do servidor aceita os literais NaN, Infinity e −Infinity. Esperado: 422 com detail, como
    já acontece com Infinity; e nenhum ajuste fica ativo."""
    c, alvo = rodovia
    r = _simular(c, corpo % alvo)
    assert r.status_code == 422, r.status_code
    assert c.get("/api/simulacao", params={"obra": "rodovia"}).json().get("ajustes", []) == []


@pytest.mark.parametrize("tipo", ["application/octet-stream", "text/csv"])
# Regressão: defeito da rodada 20, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("POST /api/historico/cenarios-salvos com corpo que não é UTF-8 (bytes 0x80–0xFF) responde 500: a "
#   "exceção observada é `UnicodeDecodeError` dentro do codificador de resposta do FastAPI (o corpo bruto, "
#   "em bytes, é ecoado na resposta de erro de validação). Com Content-Type application/json o mesmo corpo "
#   "dá 4xx. Correção: ler o corpo na rota e validar à mão (como /api/revisoes/comparar faz), ou um "
#   "tratador de erro de validação que não ecoe o corpo")
def test_cenario_salvo_com_corpo_binario_e_4xx(rodovia, tipo):
    """256 valores de byte repetidos, enviados como octet-stream ou CSV: resposta 4xx com detail."""
    c, _ = rodovia
    r = c.post("/api/historico/cenarios-salvos", params={"obra": "rodovia"}, content=bytes(range(256)) * 100,
               headers={"Content-Type": tipo})
    assert 400 <= r.status_code < 500, r.status_code


# =============================================================================
# custo máximo de pedidos VÁLIDOS
# =============================================================================
CUSTO_MAXIMO = [
    ("/api/tendencia", {"passo_dias": 1}, 200),
    ("/api/backtest", {"passo_dias": 1}, 200),
    ("/api/backtest/sementes", {"n": 30, "passo_dias": 1}, 422),          # recusado pelo orçamento de custo
    ("/api/previsao-probabilistica", {"iteracoes": 500, "com_criticidade": "true", "com_chuva": "true",
                                      "com_riscos": "true", "rho": 0.5, "por_marco": "true",
                                      "incerteza_sem_medicao": "true"}, 200),
    ("/api/aceleracao", {"limite_extra": 20, "prazo": "2026-12-01"}, 200),
    ("/api/recuperacao", {"prazo": "2026-12-01"}, 200),
    ("/api/curva-s", {"passo_dias": 1}, 200),
    ("/api/orcamento/curva-s-financeira", {"passo_dias": 1}, 200),
    ("/api/relatorio", {}, 200),
    ("/api/ifc/exportar", {}, 200),
]


@pytest.mark.parametrize("rota,params,esperado", [
    pytest.param(r, p, e, id=r, marks=[requer_ifc] if eh_rota_ifc(r) else []) for r, p, e in CUSTO_MAXIMO])
def test_pedido_valido_mais_caro_fica_abaixo_de_30_segundos(rodovia, rota, params, esperado):
    """Os parâmetros mais caros que cada rota ACEITA (passo de 1 dia, limite máximo de equipes, prazo
    inalcançável, todas as opções do Monte Carlo com 500 iterações) respondem em menos de 30 s; o backtest por
    sementes com 30 mundos e passo 1 é recusado na hora pelo orçamento de custo (422), não executado."""
    c, _ = rodovia
    t = time.perf_counter()
    r = c.get(rota, params={"obra": "rodovia", **params})
    dt = time.perf_counter() - t
    assert r.status_code == esperado, (r.status_code, r.text[:200])
    assert dt < LIMITE_S, round(dt, 1)
