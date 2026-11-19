"""Relatório técnico: números vêm do motor (iguais ao painel) e o HTML é seguro."""

import json

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO, Projeto


@pytest.fixture()
def cliente():
    return TestClient(criar_app(Projeto.carregar()))


def _br(iso):
    a, m, d = iso.split("-")
    return f"{d}/{m}/{a}"


def test_relatorio_responde_html_com_aviso_e_terminos_do_painel(cliente):
    r = cliente.get("/api/relatorio")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    painel = cliente.get("/api/painel").json()
    assert "FICTÍCIOS" in html
    for c in ("linha_base", "construtora", "independente"):
        assert _br(painel["terminos"][c]) in html
    ind = cliente.get("/api/cenarios/independente").json()
    assert all(aid in html for aid in ind["cadeia_determinante"])


def test_relatorio_mostra_simulacao_quando_ativa(cliente):
    ind = cliente.get("/api/cenarios/independente").json()
    aid = next(i for i in ind["cadeia_determinante"] if ind["atividades"][i]["status"] == "nao_iniciada"
               and ind["atividades"][i]["memoria"].get("regra") == "quantidade")
    cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": aid, "equipes": 4}]})
    html = cliente.get("/api/relatorio").text
    assert "Simulação ativa" in html and "Término — simulado" in html


def test_relatorio_escapa_texto_dos_dados():
    """Nome com HTML nos dados não pode virar marcação no relatório."""
    d = json.loads(DATASET_PADRAO.read_text(encoding="utf-8"))
    d["ferrovia"]["nome"] = "<script>alert(1)</script>"
    html = TestClient(criar_app(Projeto(d))).get("/api/relatorio").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_relatorio_confronta_tres_metodos_com_numeros_do_codigo(cliente):
    from infra4d.previsao_es import previsao
    html = cliente.get("/api/relatorio").text
    assert "Previsão por três métodos" in html and "Earned Schedule" in html and "Monte Carlo" in html
    es = previsao(Projeto.carregar())["resultados"][0]
    assert _br(es["IEAC_spi_termino"]) in html


def test_relatorio_de_obra_desconhecida_404(cliente):
    assert cliente.get("/api/relatorio", params={"obra": "zz"}).status_code == 404


# ------------------------------------------------- seções de análise (8 a 12): número do relatório = número da rota
import re
import sys
import time

from infra4d import relatorio as REL


def _num(v, casas=2):
    return REL._num(v, casas)


@pytest.fixture(scope="module")
def cli_obras():
    return TestClient(criar_app())


@pytest.mark.parametrize("obra", ["ferrovia", "rodovia"])
def test_secoes_de_analise_batem_com_as_rotas(cli_obras, obra):
    c = cli_obras
    t0 = time.perf_counter()
    html = c.get("/api/relatorio", params={"obra": obra}).text
    t_frio = time.perf_counter() - t0
    for sec in ("8. Cinco maiores riscos", "9. Tendência do término", "10. Recuperação e aceleração",
                "11. Backtest", "12. Cobertura"):
        assert sec in html, sec
    assert "Indisponível" not in html
    # 8. riscos
    rk = c.get("/api/riscos", params={"obra": obra, "rapido": True}).json()
    for x in rk["riscos"][:5]:
        assert REL.escape(x["titulo"]) in html
        if x["delta_potencial_dias"] is not None:
            assert f"<td class='n'>{x['delta_potencial_dias']}</td>" in html
    assert f"{rk['n_riscos']} riscos no registro" in html
    # 9. tendência
    td = c.get("/api/tendencia", params={"obra": obra}).json()
    m = next(x for x in td["marcos"] if x["id"] == "M-FIM")
    for lado in ("construtora", "independente"):
        assert _num(m["inclinacao_dias_por_semana"][lado], 3) in html
    assert _br(m["divergencia_desde"]) in html if m["divergencia_desde"] else True
    # 10. recuperação e aceleração
    rc = c.get("/api/recuperacao", params={"obra": obra}).json()
    for k in ("prazo", "termino_atual", "termino_alcancado"):
        assert _br(rc[k]) in html
    for x in rc["plano"][:8]:
        assert f"<td>{x['id']}</td><td class='n'>{_num(x['aumento_pct'], 1)}</td>" in html
    ac = c.get("/api/aceleracao", params={"obra": obra}).json()
    assert f"R$ {_num(ac['custo_adicional_total'])}" in html and _br(ac["termino_alcancado"]) in html
    # 11. backtest
    bt = c.get("/api/backtest", params={"obra": obra}).json()
    mae = next(x for x in bt["marcos"] if x["id"] == "M-FIM")["por_referencia"]["realidade_simulada"]["mae_dias"]
    assert f"<td class='n'>{_num(mae['construtora'])}</td>" in html
    assert f"<td class='n'>{_num(mae['independente'])}</td>" in html
    assert "Referência SINTÉTICA" in html
    # 12. cobertura
    co = c.get("/api/cobertura", params={"obra": obra}).json()
    for x in co["marcos"]:
        assert f"<td>{_br(x['termino'])}</td><td>{x['confianca']}</td>" in html
    # tempo declarado; a 2ª geração usa o cache
    assert "Tempo de geração" in html
    t1 = time.perf_counter()
    html2 = c.get("/api/relatorio", params={"obra": obra}).text
    t_quente = time.perf_counter() - t1
    assert "(cache)" in html2
    print(f"\n{obra}: relatório frio {t_frio:.2f} s, quente {t_quente:.2f} s")


def test_secao_tolera_modulo_ausente(monkeypatch):
    monkeypatch.setitem(sys.modules, "infra4d.backtest", None)
    REL._cache.clear()
    html = TestClient(criar_app(Projeto.carregar())).get("/api/relatorio").text
    assert "11. Backtest" in html and "Indisponível" in html
    assert "12. Cobertura" in html  # as demais seções continuam
    REL._cache.clear()


def test_relatorio_sem_script_nem_handler(cli_obras):
    html = cli_obras.get("/api/relatorio").text
    assert "<script" not in html.lower()
    assert not re.search(r"\son[a-z]+\s*=", html, re.I)


def test_secoes_de_analise_escapam_todo_texto():
    X = "<img src=x onerror=alert(1)>"
    an = {
        "riscos": {"riscos": [{"titulo": X, "nivel": X, "delta_potencial_dias": 3,
                               "evidencias": [{"rota": X, "params": {"a": X}}]}], "n_riscos": 1, "fontes_omitidas": {X: X}},
        "tendencia": {"limiar_divergencia_dias": 15, "marcos": [{"id": "M-FIM", "inclinacao_dias_por_semana":
                                                                  {"construtora": 1.0, "independente": 2.0},
                                                                  "divergencia_desde": None}]},
        "recuperacao": {"prazo": None, "termino_atual": None, "termino_alcancado": None, "cumpre_prazo": False,
                        "viabilidade": X, "plano": [{"id": X, "aumento_pct": 1.0, "equipes_necessarias": 2}]},
        "aceleracao": {"termino_inicial": None, "termino_alcancado": None, "cumpre_prazo": True,
                       "custo_adicional_total": 1.0, "aviso": X, "ajustes_finais": []},
        "backtest": {"referencias": {"realidade_simulada": X}, "marcos": [{"id": "M-FIM", "por_referencia": {
            "realidade_simulada": {"mae_dias": {"construtora": 1, "independente": 2}, "referencia": None}}}]},
        "cobertura": {"fator_estresse": 0.5, "marcos": [{"id": X, "nome": X, "termino": None, "confianca": X}]},
    }
    html = "".join(REL._html_analises(an, REL.escape))
    assert "<img" not in html and "&lt;img" in html
    indisponivel = "".join(REL._html_analises({k: {"indisponivel": X} for k in an}, REL.escape))
    assert "<img" not in indisponivel and indisponivel.count("Indisponível") == 6


# ------------------------------------------------- revisão r18 (regressões próprias)
def test_formato_inesperado_vira_indisponivel_por_secao():
    an = {"riscos": {"riscos": "não é lista", "n_riscos": 1}, "tendencia": {"marcos": [{"id": "M-FIM",
          "inclinacao_dias_por_semana": {"construtora": "x"}, "divergencia_desde": "31/02"}]},
          "recuperacao": {"plano": [{"id": "A", "aumento_pct": 1.0, "equipes_necessarias": None}], "prazo": None,
                          "termino_atual": None, "termino_alcancado": None},
          "aceleracao": {"custo_adicional_total": "caro"}, "backtest": [], "cobertura": {"marcos": [{"sem_id": 1}]}}
    html = "".join(REL._html_analises(an, REL.escape))
    for nome in ("riscos", "tendencia", "aceleracao", "backtest", "cobertura"):
        assert f"Indisponível ({nome})" in html, nome
    assert "<td>A</td><td class='n'>1,0</td><td class='n'>—</td>" in html  # equipes None → "—", não "None"
    assert "None" not in html


def test_monte_carlo_do_relatorio_usa_chave_fixa():
    from infra4d.api import criar_app as _ca
    c = TestClient(_ca(Projeto.carregar()))
    c.get("/api/previsao-probabilistica", params={"iteracoes": 10, "semente": 1, "rho": 0.9})
    html = c.get("/api/relatorio").text
    assert "100 iterações, semente 7, sem as opções v2" in html
