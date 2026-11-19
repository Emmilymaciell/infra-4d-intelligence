"""Auditoria de caches: nenhuma rota devolve dado velho depois de simular, limpar, importar medições ou trocar de obra.

Cada rota GET com cache (ou que lê um cenário cacheado no Estado) está numa de duas listas DECLARADAS:

- SEGUE_SIMULACAO: o resultado depende da simulação do usuário. Chamar -> aplicar uma simulação que
  muda o término -> chamar de novo tem de REFLETIR a simulação; limpar -> volta EXATAMENTE ao original;
- NAO_SIMULADO: a rota usa só cenários não simulados (declarado, com o motivo). Chamar antes, durante e
  depois da simulação tem de dar o MESMO resultado — e igual ao de um app novo, sem cache (não é dado velho).

Importar medições com ``aplicar=true`` simula em memória e não persiste: nenhuma rota pode mudar.
Duas obras no mesmo app: cache de uma obra não vaza para a outra (cada uma = app novo só com ela).
"""

import hashlib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO, Projeto

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = {"ferrovia": DATASET_PADRAO, "rodovia": DATASET_PADRAO.parent / "rodovia_ficticia.json"}
# simulação que ATRASA o término da ferrovia (terraplenagem crítica do L3 a 1/3 da planejada)
AJUSTE = {"ajustes": [{"atividade_id": "L3-S04-TER", "produtividade": 800}]}
VOLATEIS = {"tempo_s", "tempo_total_s", "tempos_s", "cache", "tempo_ms", "gerado_em"}
# o AVISO "simulacao_do_usuario" pode citar a simulação ativa (ex.: "há 1 ajuste ativo; esta análise usa o
# independente") — é texto declarativo, não o resultado; fica fora da comparação de dado velho
VOLATEIS = VOLATEIS | {"simulacao_do_usuario"}

SEGUE_SIMULACAO = {
    "/api/cenarios/simulado": {},
    "/api/painel": {},
    "/api/estado4d": {"data": "2027-08-02", "cenario": "simulado"},
    "/api/gis/geojson": {"camada": "atividades", "cenario": "simulado"},
    "/api/relatorio": {},
    "/api/recursos/histograma": {"cenario": "simulado"},
    "/api/recursos/nivelamento": {"cenario": "simulado"},
    "/api/ifc/exportar": {"incluir_4d": True},     # cache do IFC tem os ajustes na chave
}
NAO_SIMULADO = {   # rota: (parâmetros, motivo declarado)
    "/api/tendencia": ({"passo_dias": 28}, "MTA: fotografias passadas, construtora e independente"),
    "/api/backtest": ({"passo_dias": 28}, "backtest contra referências fixas"),
    "/api/curva-s": ({}, "LB, construtora, independente e realizado"),
    "/api/sensibilidade": ({}, "tornado sobre o independente"),
    "/api/produtividade/terraplenagem": ({}, "efeito dos próprios ajustes sobre o independente"),
    "/api/massas/diagrama": ({}, "geometria"),
    "/api/massas/coerencia": ({}, "geometria × quantidades"),
    "/api/referencia/km": ({"km": 10}, "estado no cenário independente"),
    "/api/aceleracao": ({}, "plano de aceleração sobre o independente"),
    "/api/clima": ({}, "cenários climáticos sobre o independente"),
    "/api/recuperacao": ({}, "plano de recuperação sobre o independente"),
    "/api/riscos": ({"rapido": True}, "registro de riscos sobre os dados"),
    "/api/previsao-probabilistica": ({"iteracoes": 30}, "Monte Carlo sobre o independente"),
    "/api/historico/evolucao": ({}, "série histórica sintética"),
    "/api/dcma": ({}, "qualidade do cronograma (independente)"),
    "/api/orcamento/resumo": ({}, "EVM na data de status"),
    "/api/previsao/earned-schedule": ({}, "Earned Schedule na data de status"),
    "/api/fiscalizacao/conciliacao": ({}, "diários × boletins"),
    "/api/ifc/vinculo": ({}, "vínculo geometria IFC × atividades (não usa datas)"),
}


def _normal(r, sem_obra=False):
    if "json" not in r.headers.get("content-type", ""):
        corpo = r.content
        if "html" in r.headers.get("content-type", ""):
            # a linha "Tempo de geração: ..." do relatório é medida de desempenho, não dado (varia com o cache)
            corpo = re.sub("Tempo de geração:[^<]*".encode(), b"", corpo)
        return hashlib.sha256(corpo).hexdigest()
    fora = VOLATEIS | ({"obra"} if sem_obra else set())

    def limpa(x):
        if isinstance(x, dict):
            return {k: limpa(v) for k, v in x.items() if k not in fora}
        if isinstance(x, list):
            return [limpa(v) for v in x]
        return x
    return json.dumps(limpa(r.json()), sort_keys=True, ensure_ascii=False)


def _cliente(*obras):
    return TestClient(criar_app(fontes={o: Projeto.carregar(OBRAS[o]) for o in obras}),
                      raise_server_exceptions=False)


@pytest.fixture(scope="module")
def cli():
    return _cliente("ferrovia")


def _get(c, rota, params, obra="ferrovia"):
    r = c.get(rota, params={"obra": obra, **params})
    return r


def _ligada(c, rota, params):
    r = _get(c, rota, params)
    if r.status_code == 404 and "obra" not in r.text and "lote" not in r.text:
        pytest.skip(f"rota {rota} não registrada neste app")
    assert r.status_code == 200, (rota, r.status_code, r.text[:200])
    return r


@pytest.mark.parametrize("rota", list(SEGUE_SIMULACAO))
def test_rota_que_segue_a_simulacao_reflete_e_volta(cli, rota):
    params = SEGUE_SIMULACAO[rota]
    antes = _normal(_ligada(cli, rota, params))
    try:
        s = cli.post("/api/simulacao", params={"obra": "ferrovia"}, json=AJUSTE)
        assert s.status_code == 200 and s.json()["comparacao"]["delta_dias_corridos"] > 0
        durante = _normal(_ligada(cli, rota, params))
        assert durante != antes, f"{rota}: não refletiu a simulação (cache velho?)"
        if rota == "/api/painel":
            assert json.loads(durante)["terminos"]["simulado"] == s.json()["comparacao"]["termino_alvo"]
    finally:
        cli.delete("/api/simulacao", params={"obra": "ferrovia"})
    assert _normal(_ligada(cli, rota, params)) == antes, f"{rota}: não voltou ao original depois de limpar"


@pytest.mark.parametrize("rota", list(NAO_SIMULADO))
def test_rota_declarada_nao_simulada_nao_muda_e_nao_e_velha(cli, rota):
    params, _motivo = NAO_SIMULADO[rota]
    antes = _normal(_ligada(cli, rota, params))
    try:
        s = cli.post("/api/simulacao", params={"obra": "ferrovia"}, json=AJUSTE)
        assert s.status_code == 200
        durante = _normal(_ligada(cli, rota, params))
    finally:
        cli.delete("/api/simulacao", params={"obra": "ferrovia"})
    depois = _normal(_ligada(cli, rota, params))
    assert durante == antes == depois, f"{rota}: declarada não simulada, mas mudou com a simulação"
    novo = _normal(_ligada(_cliente("ferrovia"), rota, params))
    assert novo == antes, f"{rota}: difere de um app novo (dado velho em cache?)"


def test_importar_medicoes_com_aplicar_nao_persiste_nem_muda_rotas(cli):
    csv = (RAIZ / "examples" / "fixtures" / "medicoes_validas.csv").read_bytes()
    amostra = ["/api/painel", "/api/curva-s", "/api/tendencia", "/api/cenarios/independente"]
    antes = {r: _normal(_ligada(cli, r, NAO_SIMULADO.get(r, ({},))[0] if r in NAO_SIMULADO else {})) for r in amostra}
    s = cli.post("/api/medicoes/importar", params={"obra": "ferrovia", "aplicar": True}, content=csv,
                 headers={"Content-Type": "text/csv"})
    if s.status_code == 404:
        pytest.skip("rota de importação não registrada")
    assert s.status_code == 200 and s.json()["aplicado"] is True and s.json()["simulacao"]["persistido"] is False
    assert s.json()["simulacao"]["delta_dias_corridos"] != 0          # a importação mudaria o término...
    for r in amostra:                                                  # ...mas nada foi persistido
        assert _normal(_ligada(cli, r, NAO_SIMULADO[r][0] if r in NAO_SIMULADO else {})) == antes[r], r


@pytest.mark.parametrize("rota, params", [("/api/tendencia", {"passo_dias": 28}), ("/api/curva-s", {}),
                                          ("/api/sensibilidade", {}), ("/api/massas/diagrama", {}),
                                          ("/api/backtest", {"passo_dias": 28}), ("/api/riscos", {"rapido": True}),
                                          ("/api/painel", {})])
def test_cache_de_uma_obra_nao_vaza_para_a_outra(rota, params):
    duas = _cliente("ferrovia", "rodovia")
    f1 = _normal(_ligada(duas, rota, params), sem_obra=True)
    r1 = _normal(_get(duas, rota, params, obra="rodovia"), sem_obra=True)
    assert f1 != r1, f"{rota}: a rodovia recebeu o resultado da ferrovia (cache sem a obra na chave)"
    assert r1 == _normal(_get(_cliente("rodovia"), rota, params, obra="rodovia"), sem_obra=True)
    assert _normal(_ligada(duas, rota, params), sem_obra=True) == f1


@pytest.mark.parametrize("rota", ["/api/tendencia", "/api/backtest", "/api/curva-s", "/api/sensibilidade",
                                  "/api/produtividade/terraplenagem"])
def test_rota_nao_simulada_declara_isso_na_resposta(cli, rota):
    """A tela não pode deixar o usuário achar que a simulação foi ignorada por engano."""
    j = _ligada(cli, rota, NAO_SIMULADO[rota][0]).json()
    assert j["simulacao_do_usuario"].startswith("não aplicada")
