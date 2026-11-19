"""Atribuição do erro de previsão por frente (P5): caso-chave da rodovia, coerência com o backtest,
identidade do resíduo, validações, teto e rota."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import infra4d.atribuicao_erro as AT
from infra4d.atribuicao_erro import ErroAtribuicao, atribuir
from infra4d.cenarios import Projeto
import infra4d.rotas_atribuicao as rotas_at

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = {o: RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json" for o in ("ferrovia", "rodovia")}


@pytest.fixture(scope="module")
def projetos():
    return {o: Projeto.carregar(p) for o, p in OBRAS.items()}


@pytest.fixture(scope="module")
def caso_chave(projetos):
    return atribuir(projetos["rodovia"], "M-L2-FIM", "2026-03-30")


def test_caso_chave_cbu_do_l2_explica_quase_todo_o_erro(caso_chave):
    """Pesquisa-verificada mediu à mão: previsão independente em 30/03/2026 erra −59 dias no M-L2-FIM; com a
    produtividade verdadeira só do CBU do L2, o erro vai a ~−1."""
    r = caso_chave
    assert r["erro_dias"] == -59
    top = r["frentes"][0]
    assert (top["lote_id"], top["servico_id"]) == ("L2", "CBU")
    assert abs(top["erro_com_a_frente_corrigida"]) <= 2
    assert top["reducao_dias"] >= 57
    assert all(x["reducao_dias"] <= top["reducao_dias"] for x in r["frentes"])  # ordenado pela redução
    assert "independente" in top["na_cadeia"]


@pytest.mark.parametrize("obra,marco,data", [("rodovia", "M-L2-FIM", "2026-03-30"), ("rodovia", "M-FIM", "2026-06-01"),
                                             ("ferrovia", "M-FIM", "2026-05-04"), ("ferrovia", "M-L3-FIM", "2026-08-03")])
def test_identidade_do_residuo_e_ordem(projetos, obra, marco, data):
    r = atribuir(projetos[obra], marco, data)
    soma = sum(x["variacao_do_erro"] for x in r["frentes"])
    assert soma + r["residuo_interacao"] == r["todas_as_frentes_juntas"]["variacao_do_erro"]
    red = [x["reducao_dias"] for x in r["frentes"]]
    assert red == sorted(red, reverse=True)
    for x in r["frentes"]:
        assert x["reducao_dias"] == abs(r["erro_dias"]) - abs(x["erro_com_a_frente_corrigida"])
        assert x["variacao_do_erro"] == x["erro_com_a_frente_corrigida"] - r["erro_dias"]
    assert r["custo"]["execucoes_do_motor"] == len(r["frentes"]) + 3


@pytest.mark.parametrize("obra,marco", [("rodovia", "M-L2-FIM"), ("ferrovia", "M-FIM")])
def test_erro_de_partida_e_o_mesmo_do_backtest(projetos, obra, marco):
    """Coerência com /api/backtest: na mesma data, o erro da independente contra a realidade simulada é igual."""
    from infra4d.backtest import backtest
    p = projetos[obra]
    b = backtest(p, 7)
    m = next(x for x in b["marcos"] if x["id"] == marco)
    erros = dict(zip(b["datas_de_status"], m["por_referencia"]["realidade_simulada"]["erro_dias"]["independente"]))
    for data in list(erros)[5::12]:
        assert atribuir(p, marco, data)["erro_dias"] == erros[data], data


def test_nao_altera_os_dados(projetos):
    p = projetos["rodovia"]
    antes = copy.deepcopy(p.dados)
    atribuir(p, "M-L2-FIM", "2026-03-30")
    assert p.dados == antes


@pytest.mark.parametrize("marco,data,msg", [("XX", "2026-03-30", "marco"), ("L2-S01-CBU", "2026-03-30", "marco"),
                                            ("M-FIM", None, "data"), ("M-FIM", "30/03/2026", "inválida"),
                                            ("M-FIM", "2020-01-01", "entre"), ("M-FIM", "2030-01-01", "entre")])
def test_parametros_invalidos(projetos, marco, data, msg):
    with pytest.raises(ErroAtribuicao, match=msg):
        atribuir(projetos["rodovia"], marco, data)


def test_obra_sem_realidade_simulada_e_recusada(projetos):
    d = copy.deepcopy(projetos["rodovia"].dados)
    d["meta"]["ficticio"] = False
    with pytest.raises(ErroAtribuicao, match="realidade simulada"):
        atribuir(Projeto(d), "M-L2-FIM", "2026-03-30")


def test_teto_de_frentes(projetos, monkeypatch):
    monkeypatch.setattr(AT, "MAX_FRENTES", 1)
    with pytest.raises(ErroAtribuicao, match="teto"):
        atribuir(projetos["rodovia"], "M-L2-FIM", "2026-03-30")


@pytest.fixture
def cliente(projetos):
    class E:
        def __init__(self, p):
            self.projeto = p

    est = {o: E(p) for o, p in projetos.items()}

    def obter(obra=None):
        obra = obra or "ferrovia"
        if obra not in est:
            raise HTTPException(404, "obra desconhecida")
        return est[obra]

    app = FastAPI()
    rotas_at.ligar(app, obter)
    return TestClient(app)


def test_rota(cliente, caso_chave):
    r = cliente.get("/api/backtest/atribuicao", params={"obra": "rodovia", "marco": "M-L2-FIM", "data": "2026-03-30"})
    assert r.status_code == 200
    j = r.json()
    assert j["erro_dias"] == caso_chave["erro_dias"] and j["frentes"] == caso_chave["frentes"]
    assert j["simulacao_do_usuario"].startswith("não aplicada")
    assert cliente.get("/api/backtest/atribuicao", params={"obra": "rodovia", "marco": "M-L2-FIM",
                                                            "data": "2026-03-30"}).json()["cache"] is True
    assert cliente.get("/api/backtest/atribuicao", params={"obra": "zz", "data": "2026-03-30"}).status_code == 404
    assert cliente.get("/api/backtest/atribuicao", params={"data": "ontem"}).status_code == 422
    assert cliente.get("/api/backtest/atribuicao").status_code == 422  # data obrigatória


# ------------------------------------------------- revisão r19 + P9 (gabarito fora do dataset)
@pytest.mark.parametrize("caso", ["um fator trocado", "fator a mais", "zero", "texto", "lista", "booleano"])
def test_gabarito_adulterado_e_recusado(projetos, caso, tmp_path, monkeypatch):
    """P9: os fatores verdadeiros vêm do GABARITO (examples/synthetic/gabarito/), pelo acessor único. Uma CÓPIA
    adulterada do arquivo (via monkeypatch de ``GABARITO``; o arquivo real não é tocado) é recusada."""
    import json

    import infra4d.dados_sinteticos_rodovia as G
    pub = json.loads(G.GABARITO.read_text(encoding="utf-8"))
    f = pub["fatores_desempenho_simulados"]
    k0 = next(iter(f))
    if caso == "um fator trocado":
        f[k0] = round(f[k0] + 0.01, 3)
    elif caso == "fator a mais":
        f["L9/XXX"] = 1.0
    elif caso == "zero":
        f[k0] = 0
    elif caso == "texto":
        f[k0] = "0,9"
    elif caso == "lista":
        pub["fatores_desempenho_simulados"] = [1, 2]
    else:
        f[k0] = True
    copia = tmp_path / "rodovia_gabarito.json"
    copia.write_text(json.dumps(pub, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(G, "GABARITO", copia)
    with pytest.raises(ErroAtribuicao, match="não confere"):
        atribuir(projetos["rodovia"], "M-L2-FIM", "2026-03-30")


def test_gabarito_ilegivel_obra_nao_ficticia_e_gerador_desconhecido(projetos, tmp_path, monkeypatch):
    import infra4d.dados_sinteticos_rodovia as G
    ruim = tmp_path / "rodovia_gabarito.json"
    ruim.write_text("{nao é json", encoding="utf-8")
    monkeypatch.setattr(G, "GABARITO", ruim)
    with pytest.raises(ErroAtribuicao, match="ilegível"):
        atribuir(projetos["rodovia"], "M-L2-FIM", "2026-03-30")
    monkeypatch.undo()
    for campo, valor, msg in (("ficticio", False, "realidade simulada|ficticio"), ("gerador", "outro.py", "gerador")):
        d = copy.deepcopy(projetos["rodovia"].dados)
        d["meta"][campo] = valor
        with pytest.raises(ErroAtribuicao, match=msg):
            atribuir(Projeto(d), "M-L2-FIM", "2026-03-30")


@pytest.mark.parametrize("fatores", [{"L2/CBU": 0}, {"L2/CBU": "x"}, {"L2/CBU": float("inf")}, {"L2/CBU": True}, [], {}])
def test_gabarito_com_fatores_malformados_e_422(projetos, monkeypatch, fatores):
    """Defesa em profundidade: mesmo que o acessor devolvesse fatores malformados, a atribuição recusa (422)."""
    import infra4d.sintetico_comum as SC
    original = SC.gabarito  # a realidade simulada (backtest) continua íntegra; só os fatores vêm ruins
    monkeypatch.setattr(SC, "gabarito", lambda dados: {**original(dados), "fatores_desempenho_simulados": fatores})
    with pytest.raises(ErroAtribuicao, match="malformado|utilizáveis"):
        atribuir(projetos["rodovia"], "M-L2-FIM", "2026-03-30")


def test_dataset_publicado_nao_traz_mais_o_gabarito(projetos):
    for p in projetos.values():
        assert "fatores_desempenho_simulados" not in p.dados["meta"]
