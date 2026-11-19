"""Revisão adversarial — rodada 8: persistencia.py (+ rotas), previsao_es.py e montecarlo.py v2.

Mesmo protocolo: esperado calculado à mão no docstring; defeito confirmado fica
``xfail(strict=True, reason="DEFEITO: ...")``. Nenhum teste deste arquivo usa o banco padrão
(``output/infra4d.sqlite``): todo banco fica em ``tmp_path``.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import montecarlo, painel, previsao_es
from infra4d.calendario import iso
from infra4d.cenarios import Projeto, executar
from infra4d.persistencia import (BANCO_PADRAO, Banco, datas_mensais, evolucao_previsao, projeto_na_data)

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")


@pytest.fixture(scope="module")
def obras():
    return {o: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json") for o in OBRAS}


# =============================================================================
# 1. persistência
# =============================================================================
INJECAO = "x'); DROP TABLE cenarios_salvos;--"


def test_campos_de_texto_nao_injetam_sql(tmp_path):
    """Obra, nome, quem, cenário, data de status, hash e chaves de parâmetros com
    ``x'); DROP TABLE cenarios_salvos;--`` são gravados e lidos como TEXTO; as tabelas continuam lá,
    o registro anterior continua lá, e o filtro por obra/cenário devolve exatamente o registro injetado."""
    b = Banco(tmp_path / "inj.sqlite")
    b.salvar_cenario("o", "normal", [], {"termino": "2027-01-01"}, "h")
    b.salvar_cenario(INJECAO, INJECAO, [], {"termino": INJECAO, "data_status": INJECAO}, INJECAO, INJECAO)
    b.auditar(INJECAO, INJECAO, INJECAO, {INJECAO: INJECAO}, {INJECAO: 1})
    b.gravar_snapshot(INJECAO, INJECAO, {"data_status": INJECAO, "cadeia_determinante": [INJECAO]}, None, INJECAO)
    assert [c["nome"] for c in b.listar_cenarios("o")] == ["normal"]
    assert [c["nome"] for c in b.listar_cenarios(INJECAO)] == [INJECAO]
    assert b.listar_snapshots(INJECAO, INJECAO)[0]["cadeia_determinante"] == [INJECAO]
    reg = b.listar_auditoria(INJECAO)[0]
    assert (reg["quem"], reg["acao"], reg["parametros"]) == (INJECAO, INJECAO, {INJECAO: INJECAO})
    assert b.listar_snapshots("o' OR '1'='1") == [] and b.listar_cenarios("o' OR '1'='1") == []


_TRABALHADOR = """
import sys
sys.path.insert(0, sys.argv[4])
from infra4d.persistencia import Banco
b, p, erros = Banco(sys.argv[1]), sys.argv[2], 0
for i in range(int(sys.argv[3])):
    for f in (lambda: b.salvar_cenario("o", f"{p}-{i}", [], {"termino": "2027-01-01", "x": "y" * 2000}, "h"),
              lambda: b.auditar("a", "o", p, {"i": i}, {}),
              lambda: b.gravar_snapshot("o", "independente", {"data_status": f"{p}-{i}", "termino": "t"}, 1.0, "h"),
              lambda: b.listar_auditoria("o", 50)):
        try:
            f()
        except Exception as e:
            erros += 1
            print(type(e).__name__, e)
print("ERROS", erros)
"""


def test_tres_processos_no_mesmo_arquivo_nao_travam_nem_perdem_gravacao(tmp_path):
    """3 PROCESSOS, cada um com 15 rodadas de (salvar cenário, auditar, snapshot, ler) no MESMO arquivo.
    Esperado: todos terminam (limite de 120 s), 0 erros, e o banco tem 45 cenários, 45 auditorias e
    45 snapshots. (Medido: 4 processos × 40 rodadas em ~5 s, sem 'database is locked'.)"""
    arq, script = tmp_path / "conc.sqlite", tmp_path / "trabalhador.py"
    script.write_text(_TRABALHADOR, encoding="utf-8")
    procs = [subprocess.Popen([sys.executable, str(script), str(arq), f"P{k}", "15", str(RAIZ / "scripts")],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for k in range(3)]
    for p in procs:
        saida, erro = p.communicate(timeout=120)
        assert p.returncode == 0 and "ERROS 0" in saida, (saida, erro[-400:])
    b = Banco(arq)
    assert (len(b.listar_cenarios("o")), len(b.listar_auditoria("o", 5000)), len(b.listar_snapshots("o"))) == (45, 45, 45)


def test_rotas_de_historico_com_banco_em_tmp_nao_tocam_o_banco_padrao(tmp_path, monkeypatch):
    """Com INFRA4D_BANCO apontando para tmp_path, criar o app e usar as rotas de histórico (salvar cenário
    com nome e 'quem' maliciosos, listar, reabrir, snapshot, auditoria) grava só lá: o arquivo padrão
    output/infra4d.sqlite fica como estava (inexistente ou com o mesmo tamanho e mtime). Nome repetido
    -> 409; id inexistente -> 404; nome vazio -> 422."""
    antes = BANCO_PADRAO.stat() if BANCO_PADRAO.exists() else None
    monkeypatch.setenv("INFRA4D_BANCO", str(tmp_path / "api.sqlite"))
    from infra4d.api import criar_app
    c = TestClient(criar_app(), raise_server_exceptions=False)
    r = c.post("/api/historico/cenarios-salvos", json={"nome": INJECAO, "ajustes": [], "quem": INJECAO})
    assert r.status_code == 200, r.text
    id_ = r.json()["id"]
    assert c.post("/api/historico/cenarios-salvos", json={"nome": INJECAO, "ajustes": []}).status_code == 409
    assert c.post("/api/historico/cenarios-salvos", json={"nome": "  ", "ajustes": []}).status_code == 422
    assert [x["nome"] for x in c.get("/api/historico/cenarios-salvos").json()["cenarios"]] == [INJECAO]
    reaberto = c.get(f"/api/historico/cenarios-salvos/{id_}").json()
    assert reaberto["conferencia"]["reproduz_identico"] is True
    assert c.get("/api/historico/cenarios-salvos/999999").status_code == 404
    assert c.post("/api/historico/snapshots", params={"quem": INJECAO}).status_code == 200
    aud = c.get("/api/historico/auditoria").json()["registros"]
    assert {x["acao"] for x in aud} == {"salvar_cenario", "registrar_snapshot"} and aud[0]["quem"] == INJECAO
    assert (tmp_path / "api.sqlite").exists()
    depois = BANCO_PADRAO.stat() if BANCO_PADRAO.exists() else None
    assert (antes is None) == (depois is None)
    if antes is not None:
        assert (antes.st_size, antes.st_mtime_ns) == (depois.st_size, depois.st_mtime_ns)


def test_nenhum_outro_teste_usa_as_rotas_de_historico_sem_banco_proprio():
    """Qualquer teste que chame as rotas /api/historico com ``criar_app()`` puro gravaria em
    output/infra4d.sqlite — o arquivo compartilhado entre suítes paralelas. A proteção é a fixture autouse de
    sessão ``_banco_isolado_por_sessao`` (tests/conftest.py), que aponta INFRA4D_BANCO para um tmp. Em vez de
    uma lista fixa de arquivos autorizados (rodada 8), confere-se a proteção REAL:
    (1) dentro da suíte, INFRA4D_BANCO está definida e não é o banco padrão;
    (2) ``criar_app()`` sem argumentos liga o histórico a um banco que NÃO é output/infra4d.sqlite, e um GET
        nas rotas de histórico cria o arquivo nesse outro caminho;
    (3) a fixture existe no conftest, é autouse e de sessão (sem ela, (1) e (2) só passariam por acaso).
    Visto falhar em (1) e (2) numa CÓPIA do conftest sem a fixture, e com INFRA4D_BANCO apontando de
    propósito para o banco padrão."""
    from infra4d.api import criar_app
    caminho_env = os.environ.get("INFRA4D_BANCO")
    assert caminho_env, "INFRA4D_BANCO não definida: a fixture _banco_isolado_por_sessao não rodou"
    assert Path(caminho_env).resolve() != BANCO_PADRAO.resolve()
    app = criar_app()
    banco = app.state.historico_banco
    assert banco.caminho.resolve() != BANCO_PADRAO.resolve()
    assert banco.caminho.resolve() == Path(caminho_env).resolve()
    assert TestClient(app).get("/api/historico/cenarios-salvos").status_code == 200
    assert banco.caminho.exists()
    conftest = (RAIZ / "tests" / "conftest.py").read_text(encoding="utf-8")
    i = conftest.index("def _banco_isolado_por_sessao(")
    decorador = conftest[:i].rstrip().splitlines()[-1]
    assert decorador.startswith("@pytest.fixture(") and "autouse=True" in decorador and 'scope="session"' in decorador


@pytest.mark.parametrize("obra", OBRAS)
def test_truncamento_tem_ancora_exata_e_serie_coerente(obras, obra):
    """projeto_na_data na data de status ATUAL devolve dados idênticos aos originais (âncora exata) e os
    mesmos resultados. Na série mensal: avanço real e número de boletins nunca diminuem; o último ponto
    bate com o painel de hoje; em nenhum mês há boletim de atividade 'não iniciada' naquela data, marco
    'em andamento', nem executado maior que o de hoje."""
    p = obras[obra]
    ancora = projeto_na_data(p, p.data_status)
    assert ancora.dados == p.dados
    ev = evolucao_previsao(p)["pontos"]
    av, nb = [x["avanco_real_pct"] for x in ev], [x["n_boletins"] for x in ev]
    assert all(b >= a for a, b in zip(av, av[1:])) and all(b >= a for a, b in zip(nb, nb[1:]))
    hoje = executar(p, "independente")
    assert ev[-1]["termino_independente"] == hoje["termino"]
    assert ev[-1]["avanco_real_pct"] == round(100 * painel.avanco(p, hoje, p.data_status), 2)
    for t in datas_mensais(p):
        q = projeto_na_data(p, t)
        por_id = {a["id"]: a for a in q.dados["atividades"]}
        assert all(por_id[m["atividade_id"]]["status"] != "nao_iniciada" for m in q.dados["medicoes"]), iso(t)
        for a in q.dados["atividades"]:
            o = p.atividades[a["id"]]
            if a["status"] == "em_andamento":
                assert a.get("tipo", "tarefa") == "tarefa", (iso(t), a["id"])
                if a.get("quantidade_total"):
                    teto = o["quantidade_total"] if o["status"] == "concluida" else o.get("quantidade_executada", 0)
                    assert a["quantidade_executada"] <= teto + 1e-6, (iso(t), a["id"])


# =============================================================================
# 2. Earned Schedule — curvas à mão
# =============================================================================
def proj(ativs, rels=(), ds="2026-01-19", lotes=None):
    """Calendário de segunda a sexta; início seg 05/01/2026; peso da atividade = duração fixa."""
    ids = lotes or sorted({a.get("lote_id") for a in ativs if a.get("lote_id")})
    return Projeto({
        "meta": {"inicio_projeto": "2026-01-05", "data_status": ds, "calendario_obra": "c5", "aviso": "FICTÍCIO"},
        "calendarios": [{"id": "c5", "nome": "c5", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []}],
        "atividades": list(ativs), "relacoes": list(rels), "medicoes": [], "servicos": [],
        "lotes": [{"id": x} for x in ids]})


def fx(i, dur, **k):
    d = {"id": i, "nome": i, "tipo": "tarefa", "calendario": "c5", "duracao_fixa": dur, "status": "nao_iniciada",
         "lote_id": "L1"}
    d.update(k)
    return d


def es(projeto, lote=None):
    return previsao_es.previsao(projeto, lote)["resultados"][0]


def test_es_obra_atrasada_adiantada_e_sem_avanco():
    """LB: uma atividade de 10 dias úteis, 05/01 a 16/01 (PD = 12 dias corridos); PV sobe 0,1 por dia útil.
    (a) Status seg 19/01 (AT = 14), 50 % feito: a LB atingiu 0,5 no fim de sex 09/01 e ficou em patamar até
        o início de seg 12/01 -> ES = 7; SPI = 7/14 = 0,5; PF=1: 14 + (12 − 7) = 19 -> 23/01 (5 dias úteis a
        partir de 19/01); PF=SPI: 14 + 5/0,5 = 24 -> 28/01.
    (b) Status seg 12/01 (AT = 7), 80 % feito: LB atinge 0,8 no fim de qua 14/01 -> ES = 10; SPI = 10/7;
        PF=1: 7 + 2 = 9 -> 13/01 (2 dias úteis a partir de 12/01).
    (c) Status seg 12/01, nada feito: ES = 0, SPI = 0, sem projeção por SPI; PF=1: 7 + 12 = 19 -> 23/01."""
    a = es(proj([fx("A", 10, status="em_andamento", inicio_real="2026-01-05", percentual_executado=50)]))
    assert (a["PD_dias"], a["AT_dias"], a["ES_dias"], a["SPI"]) == (12, 14, 7.0, 0.5)
    assert (a["IEAC_pf1_termino"], a["IEAC_spi_termino"]) == ("2026-01-23", "2026-01-28")
    b = es(proj([fx("A", 10, status="em_andamento", inicio_real="2026-01-05", percentual_executado=80)],
                ds="2026-01-12"))
    assert (b["ES_dias"], b["SPI"], b["IEAC_pf1_termino"]) == (10.0, 1.4286, "2026-01-13")
    c = es(proj([fx("A", 10)], ds="2026-01-12"))
    assert (c["ES_dias"], c["SPI"], c["IEAC_spi_termino"], c["IEAC_pf1_termino"]) == (0.0, 0.0, None, "2026-01-23")


def test_es_obra_no_plano_com_status_na_segunda_tem_spi_1():
    """LB: A(5) 05–09/01, B(5) 12–16/01. A concluída como planejado, B não iniciada, status seg 12/01:
    EV = PV = 0,5, ES = AT = 7, SPI = 1 e as duas projeções dão o término da LB, 16/01."""
    r = es(proj([fx("A", 5, status="concluida", inicio_real="2026-01-05", termino_real="2026-01-09"), fx("B", 5)],
                [{"predecessora": "A", "sucessora": "B"}], ds="2026-01-12"))
    assert (r["EV"], r["PV_em_AT"], r["ES_dias"], r["SPI"]) == (0.5, 0.5, 7.0, 1.0)
    assert r["IEAC_pf1_termino"] == r["IEAC_spi_termino"] == r["termino_linha_base"] == "2026-01-16"


@pytest.mark.parametrize("status,at", [("2026-01-10", 5), ("2026-01-11", 6)])
def test_es_obra_no_plano_com_status_no_fim_de_semana_tem_spi_1(status, at):
    """Mesma obra do teste anterior, com a data de status no sábado 10/01 ou no domingo 11/01.
    Continua exatamente no plano: ES = AT, SPI = 1, projeção = 16/01 (término da LB).
    Hoje, no sábado: ES = 7 com AT = 5 -> SPI 1,4; PF=1 dá 14/01 e PF=SPI dá 13/01."""
    r = es(proj([fx("A", 5, status="concluida", inicio_real="2026-01-05", termino_real="2026-01-09"), fx("B", 5)],
                [{"predecessora": "A", "sucessora": "B"}], ds=status))
    assert (r["AT_dias"], r["EV"], r["PV_em_AT"]) == (at, 0.5, 0.5)
    assert r["SPI"] == 1.0
    assert r["IEAC_pf1_termino"] == r["IEAC_spi_termino"] == "2026-01-16"


def test_es_lote_que_ainda_nao_devia_ter_comecado_nao_fica_adiantado():
    """Lote L2: uma atividade de 10 dias com início não antes de 02/02 (LB: 02/02 a 13/02; PD = 40).
    Status seg 19/01 (AT = 14), nada feito, nada planejado até aqui: está NO PLANO. Esperado SPI = 1 e
    projeção = 13/02. Hoje: ES = 28, SPI = 2,0, PF=1 -> 30/01, PF=SPI -> 24/01."""
    p = proj([fx("A", 10, status="em_andamento", inicio_real="2026-01-05", percentual_executado=50),
              fx("B", 10, lote_id="L2", restricao_inicio="2026-02-02")])
    r = es(p, "L2")
    assert (r["EV"], r["PV_em_AT"], r["termino_linha_base"]) == (0.0, 0.0, "2026-02-13")
    assert r["SPI"] == 1.0
    assert r["IEAC_pf1_termino"] == "2026-02-13"


@pytest.mark.parametrize("obra", OBRAS)
def test_es_no_historico_das_obras_no_plano_nao_e_adiantado(obras, obra):
    """Para cada mês do histórico e cada lote: se EV == PV(AT) (com 6 casas), o lote está no plano e o
    SPI tem de ser 1,0. Hoje: ferrovia L3 em 2025-12-01 (SPI 3,04) e 2026-01-01 (1,44); rodovia L3 em
    2026-01-01 (2,26) e 2026-02-01 (1,13) e L2 em 2026-04-01 (1,157)."""
    p = obras[obra]
    fora = []
    for t in datas_mensais(p):
        for r in previsao_es.previsao(projeto_na_data(p, t))["resultados"]:
            if r["EV"] == r["PV_em_AT"] and r["SPI"] is not None and r["SPI"] != 1.0:
                fora.append((iso(t), r["lote"], r["SPI"], r["IEAC_spi_termino"], r["termino_linha_base"]))
    assert fora == []


def test_es_com_status_antes_do_inicio_projeta_a_linha_de_base():
    """Início 05/01, status qui 01/01 (AT = −4), nada feito. A melhor projeção é a própria LB: 16/01.
    Hoje a projeção PF=1 é 12/01."""
    r = es(proj([fx("A", 10)], ds="2026-01-01"))
    assert (r["AT_dias"], r["SPI"]) == (-4, None)
    assert r["IEAC_pf1_termino"] == "2026-01-16"


def test_es_lote_sem_atividades_nao_derruba_a_previsao_da_obra():
    """Obra com L1 (uma atividade) e L2 cadastrado mas vazio. A previsão da obra e de L1 tem de sair;
    L2 fica de fora ou marcado como 'sem atividades'."""
    p = proj([fx("A", 10)], lotes=["L1", "L2"])
    res = previsao_es.previsao(p)["resultados"]
    assert res[0]["lote"] is None and res[0]["termino_linha_base"] == "2026-01-16"


# =============================================================================
# 3. Monte Carlo v2
# =============================================================================
PCT = ("p10", "p50", "p80", "p90", "min", "max")


@pytest.fixture(scope="module")
def v1(obras):
    return montecarlo.simular(obras["ferrovia"], 40, 7)


def faixa(r):
    return [r[k] for k in PCT]


def test_v2_com_opcoes_neutras_reproduz_a_v1(obras, v1):
    """Mesmas 40 iterações e semente: lista de riscos vazia, risco com probabilidade 0, chuva com p = 0 e
    chuva sem meses chuvosos têm de dar exatamente os mesmos percentis e o mesmo histograma da v1
    (o caminho v2 chama o motor por outra função: se divergisse, apareceria aqui)."""
    p = obras["ferrovia"]
    alguma = next(a["id"] for a in p.dados["atividades"] if a.get("tipo", "tarefa") == "tarefa")
    neutras = [dict(com_riscos=True, riscos=[]),
               dict(com_riscos=True, riscos=[{"id": "R", "probabilidade": 0, "atividade_id": alguma,
                                              "impacto_dias_uteis": 50}]),
               dict(com_chuva=True, p_chuva=0.0), dict(com_chuva=True, meses_chuvosos=())]
    assert v1["versao"] == "v1"
    for kw in neutras:
        r = montecarlo.simular(p, 40, 7, comparar_v1=False, **kw)
        assert r["versao"] == "v2" and faixa(r) == faixa(v1) and r["histograma"] == v1["histograma"], kw


def test_riscos_probabilidade_um_desloca_e_entradas_invalidas_sao_recusadas(obras, v1):
    """Risco com probabilidade 1 e +10 dias úteis numa tarefa aberta da cadeia determinante: ocorre em
    100 % das iterações e todos os percentis andam para depois. Atividade inexistente, impacto negativo,
    probabilidade 1,5 e NaN -> ValueError."""
    p = obras["ferrovia"]
    det = executar(p, "independente")
    crit = next(i for i in det["cadeia_determinante"]
                if det["atividades"][i]["status"] != "concluida" and det["atividades"][i]["duracao"] > 0)
    r = montecarlo.simular(p, 40, 7, com_riscos=True, comparar_v1=False,
                           riscos=[{"id": "R", "probabilidade": 1, "atividade_id": crit, "impacto_dias_uteis": 10}])
    assert r["v2"]["riscos"]["frequencia_observada"] == {"R": 1.0}
    assert all(a > b for a, b in zip(faixa(r), faixa(v1)))
    for ruim in ({"atividade_id": "ZZ"}, {"impacto_dias_uteis": -1}, {"probabilidade": 1.5},
                 {"probabilidade": float("nan")}):
        risco = {"id": "R", "probabilidade": 0.5, "atividade_id": crit, "impacto_dias_uteis": 1, **ruim}
        with pytest.raises(ValueError):
            montecarlo.simular(p, 10, 7, com_riscos=True, riscos=[risco], comparar_v1=False)


def test_chuva_so_atrasa_e_parametros_fora_da_faixa_sao_recusados(obras, v1):
    """Chuva padrão (8 % dos dias de nov–mar): nenhum percentil fica antes do da v1 e a média de dias
    perdidos por iteração é positiva. rho fora de [0, 1], p_chuva > 1 e iterações < 10 -> ValueError."""
    p = obras["ferrovia"]
    r = montecarlo.simular(p, 40, 7, com_chuva=True, comparar_v1=False)
    assert all(a >= b for a, b in zip(faixa(r), faixa(v1)))
    assert r["v2"]["chuva"]["media_dias_perdidos_por_iteracao"] > 0
    for kw in (dict(rho=1.5), dict(rho=-0.1), dict(com_chuva=True, p_chuva=1.5), dict(iteracoes=5)):
        with pytest.raises(ValueError):
            montecarlo.simular(p, **{"iteracoes": 10, **kw})


def test_monte_carlo_e_reprodutivel_entre_processos(tmp_path):
    """Dois processos com PYTHONHASHSEED diferentes (1 e 999), v2 completa (rho 0,5 + riscos + chuva,
    25 iterações): percentis, faixa da v1, frequência dos riscos e dias de chuva idênticos."""
    codigo = (
        "import sys, json; sys.path.insert(0, sys.argv[1])\n"
        "from infra4d.cenarios import Projeto\nfrom infra4d import montecarlo as m\n"
        "r = m.simular(Projeto.carregar(), 25, 7, rho=0.5, com_riscos=True, com_chuva=True)\n"
        "print(json.dumps([[r[k] for k in ('p10','p50','p80','p90','min','max')], r['faixa_v1'], r['histograma'],"
        " r['v2']['riscos']['frequencia_observada'], r['v2']['chuva']['media_dias_perdidos_por_iteracao']]))\n")
    saidas = []
    for semente_hash in ("1", "999"):
        r = subprocess.run([sys.executable, "-c", codigo, str(RAIZ / "scripts")], capture_output=True, text=True,
                           timeout=180, env={**os.environ, "PYTHONHASHSEED": semente_hash})
        assert r.returncode == 0, r.stderr[-400:]
        saidas.append(json.loads(r.stdout))
    assert saidas[0] == saidas[1]


@pytest.mark.parametrize("risco", [{"id": "R"}, {"id": "R", "probabilidade": 1, "impacto_dias_uteis": 1.9}])
def test_risco_incompleto_ou_fracionario_e_recusado_com_erro_claro(obras, risco):
    """(a) risco só com id; (b) impacto de 1,9 dia útil. Nos dois casos: ValueError com mensagem
    (ou arredondamento declarado para CIMA: 2). Hoje: KeyError no primeiro; 1 no segundo."""
    p = obras["ferrovia"]
    alvo = next(a["id"] for a in p.dados["atividades"]
                if a.get("tipo", "tarefa") == "tarefa" and a["status"] != "concluida")
    if "impacto_dias_uteis" in risco:
        risco = {**risco, "atividade_id": alvo}
    try:
        r = montecarlo.simular(p, 10, 7, com_riscos=True, riscos=[risco], comparar_v1=False)
    except ValueError:
        return
    assert r["v2"]["riscos"]["lista"][0]["impacto_dias_uteis"] == 2
