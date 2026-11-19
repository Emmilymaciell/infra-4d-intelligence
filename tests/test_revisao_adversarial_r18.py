"""Revisão adversarial — rodada 18: ``relatorio.py`` (seções de análise, escape, cache por obra, tempo),
``backtest.backtest_sementes`` (/api/backtest/sementes), ``recuperacao.py`` com o certificado pela aceleração
e ``aviso_simulacao.py``.

Cada teste traz no docstring o resultado esperado calculado à mão ou por conferência independente.
Defeito confirmado fica ``xfail(strict=True, reason="DEFEITO: ...")``.
"""

import copy
import hashlib
import math
import random
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import backtest as B
from infra4d.calendario import iso, ordinal
from infra4d.cenarios import Ajuste, Projeto, executar
from infra4d.motor import ErroRede
from infra4d.recuperacao import recuperar

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")
ARQUIVOS = {o: RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json" for o in OBRAS}


def _defeito(motivo):
    return pytest.mark.xfail(strict=True, reason="DEFEITO: " + motivo)


@pytest.fixture(scope="module")
def bases():
    return {o: Projeto.carregar(p) for o, p in ARQUIVOS.items()}


def _app(fontes):
    from infra4d.api import criar_app
    return TestClient(criar_app(fontes=fontes), raise_server_exceptions=False)


@pytest.fixture(scope="module")
def cliente(bases):
    return _app(bases)


def _br(t):
    return f"{t[8:10]}/{t[5:7]}/{t[0:4]}"


def _linha_mc(html: str):
    """(datas P50 / P80, começo da descrição) da linha de Monte Carlo da seção 1b."""
    m = re.search(r"Monte Carlo[^<]*</td><td><b>([^<]*)</b></td><td class='mu'>([^<]{0,40})", html)
    return m.groups() if m else None


# =============================================================================
# 1. relatório
# =============================================================================
@pytest.mark.parametrize("obra,outra", [("ferrovia", "rodovia"), ("rodovia", "ferrovia")])
def test_relatorio_de_cada_obra_traz_os_numeros_das_rotas_dela(cliente, obra, outra):
    """No MESMO app, com as duas obras: a seção 10 do relatório de uma obra mostra o término alcançado e o
    custo da aceleração DESSA obra (GET /api/aceleracao?obra=) e a recuperação dessa obra
    (GET /api/recuperacao?obra=), e não os da outra — o cache das seções é por obra. A 2ª geração vem
    inteira do cache (6 seções marcadas '(cache)') e mostra os mesmos números."""
    html = cliente.get("/api/relatorio", params={"obra": obra}).text
    for o in (obra, outra):
        cliente.get("/api/relatorio", params={"obra": o})
    de_novo = cliente.get("/api/relatorio", params={"obra": obra}).text
    assert de_novo.count("(cache)") == 6

    def secao10(h):
        return h.split("<h2>10.")[1].split("<h2>11.")[0]

    assert secao10(html) == secao10(de_novo)
    ac = {o: cliente.get("/api/aceleracao", params={"obra": o}).json() for o in (obra, outra)}
    rc = cliente.get("/api/recuperacao", params={"obra": obra}).json()
    assert ac[obra]["termino_alcancado"] != ac[outra]["termino_alcancado"]
    s = secao10(html)
    assert f"{_br(ac[obra]['termino_inicial'])} → {_br(ac[obra]['termino_alcancado'])}" in s
    assert f"{_br(ac[outra]['termino_inicial'])} → {_br(ac[outra]['termino_alcancado'])}" not in s
    assert f"término atual {_br(rc['termino_atual'])} → alcançado {_br(rc['termino_alcancado'])}" in s
    assert f"viabilidade: {rc['viabilidade']}." in s


def test_relatorio_escapa_texto_malicioso_em_todas_as_secoes(bases):
    """Nome de atividade, aviso da obra, descrição de restrição e nome de lote com marcação HTML: o relatório
    responde 200 e nenhuma dessas marcações aparece crua (nem ``<script``, nem ``onerror=1>``, nem ``<b on``)."""
    d = copy.deepcopy(bases["ferrovia"].dados)
    for a in d["atividades"]:
        a["nome"] = "<script>x</script>"
    d["meta"]["aviso"] = "<img src=x onerror=1>"
    for r in d["restricoes"]:
        r["descricao"] = "<b onmouseover=1>"
    r = _app({"x": Projeto(d)}).get("/api/relatorio", params={"obra": "x"})
    assert r.status_code == 200
    assert "<script" not in r.text and "onerror=1>" not in r.text and "<b onmouseover" not in r.text
    assert "&lt;script&gt;x&lt;/script&gt;" in r.text


# Regressão: defeito da rodada 18, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("a linha 'Monte Carlo — P50 / P80' do relatório pega QUALQUER Monte Carlo que esteja no cache do Estado "
#   "(`next(v for k in est.cache if k.startswith('mc:'))`). Se alguém chamou antes "
#   "/api/previsao-probabilistica?iteracoes=10&semente=1&rho=0.9&com_chuva=true&com_riscos=true, o relatório "
#   "mostra esse P50/P80 (ferrovia: 30/09/2027 / 05/10/2027 em vez de 10/09/2027 / 13/09/2027), rotulado "
#   "'sobre a produtividade medida'. O mesmo relatório, da mesma obra e dos mesmos dados, muda conforme o "
#   "histórico de chamadas. Correção: usar sempre a chave fixa do relatório (100 iterações, semente 7, sem "
#   "opções) e declarar os parâmetros na linha")
def test_monte_carlo_do_relatorio_nao_depende_de_chamadas_anteriores(bases):
    """Dois apps com os mesmos dados. No 1º só se pede o relatório. No 2º pede-se antes um Monte Carlo com
    10 iterações, semente 1, correlação 0,9, chuva e riscos. A linha de Monte Carlo do relatório tem de ser
    a MESMA nos dois (o relatório declara 100 iterações, semente 7)."""
    limpo = _linha_mc(_app({"ferrovia": bases["ferrovia"]}).get("/api/relatorio").text)
    c = _app({"ferrovia": Projeto(copy.deepcopy(bases["ferrovia"].dados))})
    assert c.get("/api/previsao-probabilistica", params={"iteracoes": 10, "semente": 1, "rho": 0.9,
                                                         "com_chuva": "true", "com_riscos": "true"}).status_code == 200
    assert limpo is not None and limpo[1].startswith("100 iterações")
    assert _linha_mc(c.get("/api/relatorio").text) == limpo


@pytest.mark.parametrize("caso", ["restrição pendente sem data_liberacao", "restrição pendente sem descricao",
                                  "meta sem aviso", "atividade sem nome"])
# Regressão: defeito da rodada 18, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("dado incompleto derruba o relatório inteiro com 500: restrição pendente sem `data_liberacao` ou sem "
#   "`descricao` (seção 6: `r['data_liberacao']`, `r['descricao']`), `meta` sem `aviso` (cabeçalho) e "
#   "atividade sem `nome` (seção 3: `a['nome']`). O painel já tolera restrição incompleta; o relatório "
#   "não. Correção: `.get` com '—' nesses campos (como o resto do arquivo faz)")
def test_relatorio_com_dado_incompleto_nao_e_500(bases, caso):
    """Cada caso retira UM campo descritivo do dataset. O relatório responde 200 (com '—' no lugar)."""
    d = copy.deepcopy(bases["ferrovia"].dados)
    if caso == "restrição pendente sem data_liberacao":
        d["restricoes"].append({"id": "Z", "descricao": "z", "atividade_id": "L3-S01-GRA", "situacao": "pendente"})
    elif caso == "restrição pendente sem descricao":
        d["restricoes"].append({"id": "Z", "atividade_id": "L3-S01-GRA", "situacao": "pendente",
                                "data_liberacao": "2027-01-01"})
    elif caso == "meta sem aviso":
        d["meta"].pop("aviso")
    else:
        for a in d["atividades"]:
            a.pop("nome", None)
    assert _app({"x": Projeto(d)}).get("/api/relatorio", params={"obra": "x"}).status_code == 200


# =============================================================================
# 2. backtest por sementes
# =============================================================================
def test_mundos_em_memoria_nao_tocam_json_nem_estado_global(bases):
    """Gerar um mundo e rodar o backtest dele: os dois JSON versionados ficam com o mesmo SHA-256, o gerador
    aleatório global do Python fica no mesmo estado, e o 1º mundo (semente base) dá exatamente o MAE do
    backtest da obra publicada (mesmo passo) — é o mesmo mundo."""
    antes = {o: hashlib.sha256(p.read_bytes()).hexdigest() for o, p in ARQUIVOS.items()}
    estado = random.getstate()
    r = B.backtest_sementes("ferrovia", 1, 91)
    assert {o: hashlib.sha256(p.read_bytes()).hexdigest() for o, p in ARQUIVOS.items()} == antes
    assert random.getstate() == estado
    assert r["sementes"] == [bases["ferrovia"].dados["meta"]["semente"]] and r["n"] == 1
    publicada = next(m for m in B.backtest(bases["ferrovia"], 91)["marcos"] if m["id"] == "M-FIM")
    assert r["por_semente"][0]["mae_dias"] == publicada["por_referencia"]["realidade_simulada"]["mae_dias"]


def test_rota_sementes_parametros(cliente):
    """n fora de 1..30, passo 0 e marco desconhecido: 422. n = 1, passo 91, marco M-L1-FIM: 200 e 1 semente."""
    for p in ({"n": 0}, {"n": 31}, {"passo_dias": 0}, {"marco": "NAO-EXISTE", "n": 1, "passo_dias": 91}):
        assert cliente.get("/api/backtest/sementes", params={"obra": "ferrovia", **p}).status_code == 422, p
    r = cliente.get("/api/backtest/sementes", params={"obra": "ferrovia", "n": 1, "passo_dias": 91, "marco": "M-L1-FIM"})
    assert r.status_code == 200 and len(r.json()["sementes"]) == 1 and r.json()["marco"] == "M-L1-FIM"


@pytest.mark.parametrize("caso", ["obra real (meta.ficticio = false)", "obra de outro gerador"])
# Regressão: defeito da rodada 18, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("/api/backtest/sementes só olha `meta.tipo_obra`: em QUALQUER obra de tipo rodovia/ferrovia — inclusive "
#   "uma sem a marca fictícia ou gerada por outro gerador — responde 200 com a distribuição do erro dos "
#   "mundos do gerador sintético do beta, com `obra` = id pedido. O resultado não tem relação com os dados "
#   "da obra consultada e nada na resposta diz isso. O /api/backtest da mesma obra declara a realidade "
#   "simulada 'indisponível'. Correção: exigir a mesma condição de `realidade_da_obra` (marca fictícia + "
#   "gerador reconhecido) e responder 422 fora dela")
def test_sementes_recusa_obra_que_nao_e_a_sintetica(bases, caso):
    """Obra com os dados da rodovia, mas (a) sem a marca fictícia e sem gerador, ou (b) com gerador
    desconhecido. O backtest dela declara a realidade simulada indisponível; logo o backtest por sementes
    não pode devolver, em nome dela, números do gerador sintético: esperado 422."""
    d = copy.deepcopy(bases["rodovia"].dados)
    if caso.startswith("obra real"):
        d["meta"]["ficticio"] = False
        d["meta"].pop("gerador", None)
    else:
        d["meta"]["gerador"] = "scripts/outro_gerador.py"
    assert B.realidade_da_obra(d)[0] is None
    r = _app({"x": Projeto(d)}).get("/api/backtest/sementes", params={"obra": "x", "n": 1, "passo_dias": 91})
    assert r.status_code == 422, r.text[:200]


# =============================================================================
# 3. recuperação (com o certificado pela aceleração)
# =============================================================================
def _rede(rng: random.Random, n: int) -> Projeto:
    """Tarefas por quantidade (TER, 10 un/equipe·dia, 1 a 3 equipes), relações FS/SS/FF com lag 0 a 2,
    calendário corrido, início = data de status = 01/01/2026, sem boletins."""
    ats, rels = [], []
    for i in range(n):
        ats.append({"id": f"T{i}", "nome": f"T{i}", "tipo": "tarefa", "lote_id": "L1", "servico_id": "TER",
                    "quantidade_total": float(rng.choice([40, 60, 90, 100, 150, 240, 330])),
                    "produtividade_planejada": 10.0, "equipes": rng.choice([1, 1, 2, 3]), "calendario": "C",
                    "status": "nao_iniciada", "unidade": "m³"})
        for p in (rng.sample(range(i), k=min(i, rng.randint(1, 2))) if i else []):
            rels.append({"predecessora": f"T{p}", "sucessora": f"T{i}", "tipo": rng.choice(["FS", "FS", "FS", "SS", "FF"]),
                         "lag": rng.choice([0, 0, 1, 2])})
    return Projeto({"meta": {"inicio_projeto": "2026-01-01", "data_status": "2026-01-01", "calendario_obra": "C",
                             "termino_linha_base": "2026-12-31", "ficticio": True, "aviso": "FICTÍCIO"},
                    "lotes": [{"id": "L1"}], "servicos": [], "medicoes": [],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                    "atividades": ats, "relacoes": rels})


def _termino_com(P: Projeto, dur: dict) -> int:
    """Término com as durações impostas, pela via pública: Ajuste(produtividade = quantidade ÷ (equipes × D))."""
    aj = [Ajuste(atividade_id=a["id"], produtividade=a["quantidade_total"] / (a["equipes"] * dur[a["id"]]))
          for a in P.dados["atividades"]]
    return ordinal(executar(P, "simulado", aj)["termino"])


def test_fuzz_recuperacao_cumpre_so_com_plano_verificado_e_dentro_do_fator():
    """200 redes sorteadas, prazo sorteado entre (melhor término possível − 1) e (término atual − 1),
    fator_max em {1,5; 2; 3}. Conferências independentes do módulo:
    - nenhuma frente do plano passa de fator_max × a produtividade medida (com ou sem cumprir);
    - 'cumpre' só com verificação pelo cenário simulado dizendo que cumpre, e término ≤ prazo;
    - viabilidade 'inviavel' se e somente se não cumpre;
    - 'inviável' nunca é falso: nem com todas as frentes na duração mínima permitida, nem em 200
      combinações sorteadas de durações em [mínima, atual], o prazo é cumprido."""
    rng = random.Random(18)
    cumpre = inviavel = 0
    for caso in range(200):
        P = _rede(rng, rng.randint(2, 6))
        try:
            t0 = ordinal(executar(P, "independente")["termino"])
        except ErroRede:
            continue
        fmax = rng.choice([1.5, 2.0, 3.0])
        atual = {a["id"]: math.ceil(a["quantidade_total"] / (10.0 * a["equipes"]) - 1e-9) for a in P.dados["atividades"]}
        minima = {a["id"]: max(1, math.ceil(a["quantidade_total"] / (10.0 * fmax * a["equipes"]) - 1e-9))
                  for a in P.dados["atividades"]}
        t_min = _termino_com(P, minima)
        prazo = rng.randint(min(t_min, t0) - 1, t0 - 1)
        r = recuperar(P, prazo=iso(prazo), fator_max=fmax)
        for p in r["plano"]:
            assert p["produtividade_necessaria"] / p["produtividade_medida"] <= fmax + 1e-9, (caso, p["id"])
        assert (r["viabilidade"] == "inviavel") == (not r["cumpre_prazo"]), caso
        if r["cumpre_prazo"]:
            cumpre += 1
            v = r["verificacao"]["produtividade"]
            assert v["cumpre"] is True and ordinal(v["termino"]) <= prazo and ordinal(r["termino_alcancado"]) <= prazo, caso
        else:
            inviavel += 1
            assert t_min > prazo, caso
            for _ in range(200):
                assert _termino_com(P, {i: rng.randint(minima[i], atual[i]) for i in atual}) > prazo, caso
    assert cumpre > 100 and inviavel > 5


@pytest.mark.parametrize("obra", OBRAS)
def test_obras_plano_de_recuperacao_dentro_do_fator_e_verificado(bases, obra):
    """Nas duas obras, prazo padrão: toda frente do plano fica em até 2 × a produtividade medida (aumento
    ≤ 100 %); se 'cumpre', o término verificado pelo cenário simulado com os ajustes de produtividade
    devolvidos é ≤ prazo (reexecutado aqui, fora do módulo)."""
    P = bases[obra]
    r = recuperar(P)
    assert all(p["aumento_pct"] <= 100.0 + 1e-6 for p in r["plano"])
    if r["cumpre_prazo"]:
        sim = executar(P, "simulado", [Ajuste(**a) for a in r["ajustes_produtividade"]])["termino"]
        assert ordinal(sim) <= ordinal(r["prazo"]) and sim == r["verificacao"]["produtividade"]["termino"]


# Regressão: defeito da rodada 18, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("GET /api/recuperacao?prazo= (parâmetro vazio): `ordinal('')` devolve None sem erro, a rota aceita, e em "
#   "`recuperar` a comparação `t0 > t_prazo` estoura TypeError -> 500. É o mesmo defeito que a aceleração "
#   "tinha na rodada 16 (lá já corrigido). Correção: prazo vazio = padrão ou 422")
def test_recuperacao_prazo_vazio_nao_e_500(cliente):
    """``?prazo=`` é o que um formulário com o campo em branco envia. 'abc' dá 422; vazio dá 200 ou 422."""
    assert cliente.get("/api/recuperacao", params={"obra": "ferrovia", "prazo": "abc"}).status_code == 422
    assert cliente.get("/api/recuperacao", params={"obra": "ferrovia", "prazo": ""}).status_code in (200, 422)


# =============================================================================
# 4. aviso de simulação não aplicada
# =============================================================================
ROTAS_COM_AVISO = [("/api/aceleracao", {}), ("/api/recuperacao", {}), ("/api/riscos", {"rapido": "true"}),
                   ("/api/clima", {}), ("/api/previsao/earned-schedule", {})]


def test_aviso_de_simulacao_acompanha_o_estado_e_os_numeros_nao_mudam(bases):
    """Sem simulação: as 5 rotas dizem 'não há simulação ativa'. Depois de POST /api/simulacao com 1 ajuste
    (dobrar as equipes de uma tarefa crítica não iniciada), as MESMAS rotas — já em cache — passam a dizer
    'há 1 ajuste(s)', e todo o resto da resposta é idêntico (a análise continua no cenário independente).
    Depois de DELETE /api/simulacao voltam a 'não há simulação ativa'."""
    P = Projeto(copy.deepcopy(bases["rodovia"].dados))
    c = _app({"rodovia": P})
    ind = executar(P, "independente")["atividades"]
    alvo = next(i for i, x in ind.items() if x["critica"] and x["status"] == "nao_iniciada"
                and P.atividades[i].get("quantidade_total"))

    def coletar():
        out = {}
        for rota, p in ROTAS_COM_AVISO:
            r = c.get(rota, params=p)
            assert r.status_code == 200, (rota, r.text[:200])
            j = r.json()
            aviso = j.pop("simulacao_do_usuario")
            for volatil in ("cache", "tempo_s", "tempo_total_s", "tempos_s"):
                j.pop(volatil, None)
            out[rota] = (aviso, j)
        return out

    antes = coletar()
    assert all("não há simulação ativa" in a for a, _ in antes.values())
    r = c.post("/api/simulacao", json={"ajustes": [{"atividade_id": alvo, "equipes": 2 * int(P.atividades[alvo]["equipes"])}]})
    assert r.status_code == 200, r.text[:200]
    durante = coletar()
    assert all("há 1 ajuste(s) de simulação ativo(s)" in a for a, _ in durante.values())
    assert {k: v[1] for k, v in durante.items()} == {k: v[1] for k, v in antes.items()}
    assert c.delete("/api/simulacao").status_code == 200
    assert all("não há simulação ativa" in a for a, _ in coletar().values())
