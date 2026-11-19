"""Revisão adversarial — rodada 19: ``atribuicao_erro.py`` (/api/backtest/atribuicao), o modo P4 do Monte Carlo
(``incerteza_sem_medicao``, via /api/previsao-probabilistica) e a guarda ``tests/test_gabarito_isolado.py``
(o gabarito do mundo sintético não pode chegar à previsão).

Cada teste traz no docstring o resultado esperado calculado à mão ou por conferência independente.
Defeito confirmado fica ``xfail(strict=True, reason="DEFEITO: ...")``.
"""

import copy
import importlib
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import montecarlo as MC
from infra4d.atribuicao_erro import atribuir
from infra4d.backtest import realidade_da_obra
from infra4d.calendario import iso, ordinal
from infra4d.cenarios import Ajuste, Projeto, executar
from infra4d.tendencia import fotografia

RAIZ = Path(__file__).resolve().parents[1]
CODIGO = RAIZ / "scripts" / "infra4d"
OBRAS = ("ferrovia", "rodovia")


def _defeito(motivo):
    return pytest.mark.xfail(strict=True, reason="DEFEITO: " + motivo)


@pytest.fixture(scope="module")
def bases():
    return {o: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json") for o in OBRAS}


def _app(fontes):
    from infra4d.api import criar_app
    return TestClient(criar_app(fontes=fontes), raise_server_exceptions=False)


# =============================================================================
# 1. gabarito isolado — o que a guarda estática pega e o que não pega
# =============================================================================
def _guarda():
    """Carrega tests/test_gabarito_isolado.py pelo caminho (sem depender de sys.path) para usar a lista
    PERMITIDOS dele; a regra dele é: arquivo .py cujo TEXTO contém 'fatores_desempenho_simulados' e cujo
    nome não está em PERMITIDOS."""
    spec = importlib.util.spec_from_file_location("gabarito_isolado", RAIZ / "tests" / "test_gabarito_isolado.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _acusados_pela_guarda(pasta: Path) -> list[str]:
    """Nomes dos arquivos que a guarda acusa, pela função ``acusados`` DELA (regra e lista de permitidos atuais)."""
    return sorted(Path(k).name for k in _guarda().acusados(pasta))


TRAPACAS = {
    "chave montada em pedaços":
        "def prever(meta):\n    return meta['fatores_' + 'desempenho_simulados']\n",
    "varre o meta sem citar a chave":
        "def prever(meta):\n    return next(v for k, v in meta.items() if k.startswith('fatores_'))\n",
    "importa a tabela do gerador":
        "from infra4d.dados_sinteticos import FATOR_DESEMPENHO\n\ndef prever(a):\n    return FATOR_DESEMPENHO\n",
    "pede a realidade ao gerador pela semente":
        "from infra4d.dados_sinteticos import realidade_simulada\n\n"
        "def prever(meta):\n    return realidade_simulada(meta['semente'])\n",
    "lava pelo módulo de avaliação":
        "from infra4d.backtest import realidade_da_obra\n\ndef prever(dados):\n    return realidade_da_obra(dados)[0]\n",
}


@pytest.mark.parametrize("nome", sorted(TRAPACAS))
# Regressão: defeito da rodada 19, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("a guarda de tests/test_gabarito_isolado.py só procura o TEXTO 'fatores_desempenho_simulados'. Cinco "
#   "caminhos de leitura do gabarito passam por ela sem acusação: (1) a chave montada em pedaços; (2) varrer "
#   "`meta.items()`; (3) importar `FATOR_DESEMPENHO` do gerador; (4) chamar `realidade_simulada(meta['semente'])` "
#   "— o TÉRMINO verdadeiro de cada atividade, pior que os fatores; (5) importar `backtest.realidade_da_obra` "
#   "(módulo permitido) de dentro de um módulo de previsão. Correção: a guarda estática também tem de "
#   "barrar import do gerador/da avaliação fora da lista permitida, e a proteção de verdade é o teste "
#   "CONTRAFACTUAL (abaixo): trocar o gabarito e exigir previsões idênticas")
def test_guarda_estatica_acusa_modulo_de_previsao_que_le_o_gabarito(tmp_path, nome):
    """Um módulo de 'previsão' falso que obtém o gabarito por um caminho que não cita a chave literal.
    A guarda (mesma regra e mesma lista de permitidos do arquivo dela) tem de acusá-lo. Controle: o módulo
    que cita a chave literal é acusado."""
    pasta = tmp_path / "infra4d"
    pasta.mkdir()
    (pasta / "controle.py").write_text("f = meta['fatores_desempenho_simulados']\n", encoding="utf-8")
    assert _acusados_pela_guarda(pasta) == ["controle.py"]
    (pasta / "previsao_trapaceira.py").write_text(TRAPACAS[nome], encoding="utf-8")
    assert "previsao_trapaceira.py" in _acusados_pela_guarda(pasta)


PODEM_IMPORTAR_GERADOR = {"dados_sinteticos.py", "dados_sinteticos_rodovia.py", "sintetico_comum.py", "backtest.py",
                          "atribuicao_erro.py"}   # desde a correção da r19: confere os fatores com o gerador
PODEM_IMPORTAR_AVALIACAO = {"backtest.py", "atribuicao_erro.py", "rotas_backtest.py", "rotas_atribuicao.py",
                            "relatorio.py"}   # relatório: só exibe a seção de backtest


def test_hoje_nenhum_modulo_de_previsao_importa_o_gerador_nem_a_avaliacao():
    """Varredura mais larga que a da guarda, sobre o código real: fora das listas acima, nenhum módulo de
    scripts/infra4d importa ``dados_sinteticos*``/``sintetico_comum``, nem ``backtest``/``atribuicao_erro``,
    nem cita ``realidade_simulada(`` ou ``FATOR_DESEMPENHO``. (Passa hoje; é o que a guarda deveria cobrir.)"""
    achados = []
    for p in CODIGO.rglob("*.py"):
        linhas = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
        codigo = [ln for ln in linhas if ln.startswith(("import ", "from ")) or "realidade_simulada(" in ln
                  or "FATOR_DESEMPENHO" in ln]
        for ln in codigo:
            gerador = any(x in ln for x in ("dados_sinteticos", "sintetico_comum", "realidade_simulada(", "FATOR_DESEMPENHO"))
            avaliacao = ln.startswith(("import ", "from ")) and any(
                x in ln for x in (".backtest import", "import backtest", ".atribuicao_erro import", "import atribuicao_erro"))
            if gerador and p.name not in PODEM_IMPORTAR_GERADOR:
                achados.append((p.name, ln))
            if avaliacao and p.name not in PODEM_IMPORTAR_AVALIACAO:
                achados.append((p.name, ln))
    assert achados == []


VOLATEIS = {"cache", "tempo_s", "tempo_total_s", "tempos_s", "segundos", "custo", "calculos_cpm", "calculos",
            "execucoes_motor", "gerado_em", "sugestao"}
ROTAS_DE_PREVISAO = [
    ("/api/painel", {}), ("/api/cenarios/construtora", {}), ("/api/cenarios/independente", {}),
    ("/api/previsao-probabilistica", {"iteracoes": 30}),
    ("/api/previsao-probabilistica", {"iteracoes": 30, "incerteza_sem_medicao": "true", "por_marco": "true"}),
    ("/api/previsao/earned-schedule", {}), ("/api/riscos", {"rapido": "true"}), ("/api/cobertura", {}),
    ("/api/tendencia", {"passo_dias": 56}), ("/api/recuperacao", {}), ("/api/aceleracao", {}), ("/api/clima", {}),
    ("/api/sensibilidade", {}),
]
GERADOR = {"ferrovia": "infra4d.dados_sinteticos", "rodovia": "infra4d.dados_sinteticos_rodovia"}


def _limpo(x):
    if isinstance(x, dict):
        return {k: _limpo(v) for k, v in x.items() if k not in VOLATEIS}
    if isinstance(x, list):
        return [_limpo(v) for v in x]
    return x


def _gabarito_adulterado(obra: str, pasta: Path, mudar) -> Path:
    """CÓPIA do arquivo de gabarito publicado, com ``mudar(conteúdo)`` aplicado. O arquivo real não é tocado;
    quem o usa é apontado para a cópia por monkeypatch de ``<gerador>.GABARITO``."""
    original = importlib.import_module(GERADOR[obra]).GABARITO
    g = json.loads(original.read_text(encoding="utf-8"))
    mudar(g)
    copia = pasta / original.name
    copia.write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    return copia


@pytest.mark.parametrize("obra", OBRAS)
def test_contrafactual_trocar_o_gabarito_nao_muda_nenhuma_previsao(bases, obra, tmp_path, monkeypatch):
    """Desde o P9 o gabarito não está mais no dataset: fica em examples/synthetic/gabarito/ e só se chega a ele
    por ``sintetico_comum.gabarito(dados)``, que o confere contra o gerador. O dataset publicado não pode mais
    trazer ``fatores_desempenho_simulados`` no ``meta`` (nem aninhado), e ``termino_realidade_simulada_oculta``
    é só uma nota em texto.

    Quatro mundos com os MESMOS dados observáveis e gabarito diferente:
    (a) o original;
    (b) o arquivo de gabarito trocado por uma CÓPIA adulterada (fatores × 0,5 e todos os términos reais
        iguais a 2030-01-01);
    (c) o arquivo de gabarito ausente;
    (d) o dataset com outra semente e outro gerador (nenhum gabarito pode ser obtido nem recalculado).
    As 13 respostas de previsão (painel, cenários, Monte Carlo com e sem P4, Earned Schedule, riscos,
    cobertura, tendência, recuperação, aceleração, clima, sensibilidade) têm de ser IDÊNTICAS nos quatro —
    qualquer leitura do gabarito, por qualquer caminho, apareceria aqui. Controle do detector: a AVALIAÇÃO
    (/api/backtest) tem a realidade simulada em (a) e (c), e a declara indisponível em (b) e (d)."""
    a = bases[obra].dados
    assert "fatores_desempenho_simulados" not in json.dumps(a["meta"])        # nem aninhado
    assert not isinstance(a["meta"].get("termino_realidade_simulada_oculta"), (dict, list))   # só a nota em texto
    mod = importlib.import_module(GERADOR[obra])

    def adulterar(g):
        g["fatores_desempenho_simulados"] = {k: v * 0.5 for k, v in g["fatores_desempenho_simulados"].items()}
        g["termino_realidade_simulada"] = {k: "2030-01-01" for k in g["termino_realidade_simulada"]}

    d = copy.deepcopy(a)
    d["meta"]["semente"] = a["meta"]["semente"] + 1
    d["meta"]["gerador"] = "scripts/outro_gerador.py"

    def respostas(dados):
        cli = _app({"x": Projeto(copy.deepcopy(dados))})      # app e Projeto novos: nenhum cache reaproveitado
        out = {}
        for rota, p in ROTAS_DE_PREVISAO:
            r = cli.get(rota, params={"obra": "x", **p})
            assert r.status_code == 200, (rota, r.text[:200])
            out[rota + repr(sorted(p.items()))] = repr(_limpo(r.json()))
        avaliacao = cli.get("/api/backtest", params={"obra": "x", "passo_dias": 91}).json()["referencias"]["realidade_simulada"]
        return out, not avaliacao.startswith("indisponível")

    ra, tem_a = respostas(a)
    with monkeypatch.context() as m:
        m.setattr(mod, "GABARITO", _gabarito_adulterado(obra, tmp_path, adulterar))
        rb, tem_b = respostas(a)
    with monkeypatch.context() as m:
        m.setattr(mod, "GABARITO", tmp_path / "nao_existe.json")
        rc, tem_c = respostas(a)
    rd, tem_d = respostas(d)
    for chave in ra:
        assert ra[chave] == rb[chave], f"{chave}: muda com o arquivo de gabarito adulterado"
        assert ra[chave] == rc[chave], f"{chave}: muda sem o arquivo de gabarito"
        assert ra[chave] == rd[chave], f"{chave}: muda com outra semente/outro gerador"
    assert (tem_a, tem_b, tem_c, tem_d) == (True, False, True, False)


# =============================================================================
# 2. atribuição do erro
# =============================================================================
@pytest.mark.parametrize("obra", OBRAS)
def test_atribuicao_conferida_pela_via_publica(bases, obra):
    """Data = 20 semanas antes da data de status, marco M-FIM. Refeito aqui, sem o módulo:
    - erro = término independente da fotografia em d − término do marco na realidade simulada;
    - para a 1ª frente da lista: cenário simulado sobre a fotografia, com produtividade = planejada × fator
      verdadeiro (do gabarito, pelo acessor único) em toda atividade aberta por quantidade dessa frente
      -> erro com a frente corrigida;
    - redução = |erro| − |erro corrigido|; variação = erro corrigido − erro;
    - resíduo = variação de todas juntas − Σ variações isoladas (identidade);
    - a lista vem ordenada pela redução (maior primeiro)."""
    from infra4d.sintetico_comum import gabarito
    P = bases[obra]
    d = P.data_status - 140
    r = atribuir(P, "M-FIM", iso(d))
    foto = Projeto(fotografia(P.dados, d))
    real, _ = realidade_da_obra(P.dados)
    t_real = ordinal(real["M-FIM"])
    erro = ordinal(executar(foto, "independente")["atividades"]["M-FIM"]["termino"]) - t_real
    assert r["erro_dias"] == erro and r["termino_realidade_simulada"] == real["M-FIM"]
    x = r["frentes"][0]
    fator = gabarito(P.dados)["fatores_desempenho_simulados"][f"{x['lote_id']}/{x['servico_id']}"]
    aj = [Ajuste(atividade_id=a["id"], produtividade=a["produtividade_planejada"] * fator)
          for a in foto.dados["atividades"] if (a.get("lote_id"), a.get("servico_id")) == (x["lote_id"], x["servico_id"])
          and a.get("quantidade_total") and a.get("status") != "concluida"]
    corrigido = ordinal(executar(foto, "simulado", aj)["atividades"]["M-FIM"]["termino"]) - t_real
    assert x["fator_verdadeiro"] == fator and x["erro_com_a_frente_corrigida"] == corrigido
    assert x["variacao_do_erro"] == corrigido - erro and x["reducao_dias"] == abs(erro) - abs(corrigido)
    assert r["residuo_interacao"] == r["todas_as_frentes_juntas"]["variacao_do_erro"] - sum(
        y["variacao_do_erro"] for y in r["frentes"])
    reducoes = [y["reducao_dias"] for y in r["frentes"]]
    assert reducoes == sorted(reducoes, reverse=True)


def test_rota_atribuicao_entradas_ruins(bases):
    """Sem data: 422 (campo obrigatório); data vazia, 30/02, igual à data de status ou ao início: 422; marco
    que não é marco de término: 422; obra cuja semente não é a do gerador: 422 (sem realidade simulada)."""
    P = bases["rodovia"]
    d = copy.deepcopy(P.dados)
    d["meta"]["semente"] += 1
    c = _app({"rodovia": P, "outra": Projeto(d)})
    for p in ({}, {"data": ""}, {"data": "2026-02-30"}, {"data": iso(P.data_status)}, {"data": iso(P.inicio_projeto)},
              {"data": "2026-06-01", "marco": "L1-S01-SUP"}):
        assert c.get("/api/backtest/atribuicao", params={"obra": "rodovia", **p}).status_code == 422, p
    assert c.get("/api/backtest/atribuicao", params={"obra": "outra", "data": "2026-06-01"}).status_code == 422
    assert c.get("/api/backtest/atribuicao", params={"obra": "rodovia", "data": "2026-06-01",
                                                     "marco": "M-L2-FIM"}).status_code == 200


def _so_fatores(valor_de):
    def mudar(g):
        g["fatores_desempenho_simulados"] = valor_de(g["fatores_desempenho_simulados"])
    return mudar


ADULTERACOES = {
    "todos os fatores 1,0": _so_fatores(lambda f: {k: 1.0 for k in f}),
    "fatores zerados": _so_fatores(lambda f: {k: 0.0 for k in f}),
    "fatores em texto": _so_fatores(lambda f: {k: "abc" for k in f}),
    "fatores em lista": _so_fatores(lambda f: [1, 2]),
    "um término real trocado": lambda g: g["termino_realidade_simulada"].update(
        {next(iter(g["termino_realidade_simulada"])): "2030-01-01"}),
}


# Regressão: defeitos da rodada 19, já corrigidos pelo dono do módulo. O que falhava: a atribuição lia
#   `meta.fatores_desempenho_simulados` sem conferir com o gerador — fatores trocados por 1,0 davam 200 com
#   "todas as frentes juntas" em −43 (em vez de 0) rotulado como verdadeiro; fator 0, texto ou lista davam 500.
# Desde o P9 os fatores saíram do dataset: o teste adultera uma CÓPIA do arquivo de gabarito.
@pytest.mark.parametrize("nome", sorted(ADULTERACOES))
def test_atribuicao_recusa_gabarito_que_nao_confere_com_o_gerador(bases, nome, tmp_path, monkeypatch):
    """Com o gabarito íntegro: 200 e 'todas as frentes juntas' com erro 0 (rodovia, 20 semanas atrás). Com o
    arquivo de gabarito trocado por uma cópia adulterada (fatores 1,0; fatores zerados; em texto; em lista;
    um término real trocado), a rota responde 422 dizendo que o gabarito não confere — nunca uma atribuição
    diferente com o rótulo de verdadeira, nem 500. Arquivo ilegível também é 422."""
    P = bases["rodovia"]
    data = iso(P.data_status - 140)
    mod = importlib.import_module(GERADOR["rodovia"])
    integro = _app({"x": Projeto(copy.deepcopy(P.dados))}).get("/api/backtest/atribuicao", params={"obra": "x", "data": data})
    assert integro.status_code == 200 and integro.json()["todas_as_frentes_juntas"]["erro_dias"] == 0
    monkeypatch.setattr(mod, "GABARITO", _gabarito_adulterado("rodovia", tmp_path, ADULTERACOES[nome]))
    r = _app({"x": Projeto(copy.deepcopy(P.dados))}).get("/api/backtest/atribuicao", params={"obra": "x", "data": data})
    assert r.status_code == 422 and "gabarito" in str(r.json()["detail"]), (r.status_code, r.text[:200])
    ilegivel = tmp_path / "ilegivel.json"
    ilegivel.write_text("{nao json", encoding="utf-8")
    monkeypatch.setattr(mod, "GABARITO", ilegivel)
    r = _app({"x": Projeto(copy.deepcopy(P.dados))}).get("/api/backtest/atribuicao", params={"obra": "x", "data": data})
    assert r.status_code == 422, r.status_code


# =============================================================================
# 3. Monte Carlo — modo P4 (incerteza das frentes sem medição)
# =============================================================================
@pytest.fixture(scope="module")
def mc(bases):
    """200 iterações, semente 7: sem P4 e com P4 (alargamento padrão), por obra."""
    return {o: (MC.simular(P, 200, 7), MC.simular(P, 200, 7, incerteza_sem_medicao=True, por_marco=True))
            for o, P in bases.items()}


@pytest.mark.parametrize("obra", OBRAS)
def test_p4_marca_exatamente_as_frentes_sem_boletim_proprio(bases, mc, obra):
    """Conferência independente: frentes (lote, serviço) com tarefa por quantidade em aberto e NENHUM boletim
    no par. Ferrovia: L3/GRA, L3/LAS, L3/SOL. Rodovia: L2/SHV, L3/CBU, L3/DEF, L3/SHV, L3/SVV. O modo declara
    esses grupos, um índice por frente medida, e os percentis de M-FIM em 'marcos' são os do término da obra."""
    dados = bases[obra].dados
    ativ = {a["id"]: a for a in dados["atividades"]}
    medidas = {(ativ[m["atividade_id"]]["lote_id"], ativ[m["atividade_id"]]["servico_id"]) for m in dados["medicoes"]}
    abertas = {(a["lote_id"], a["servico_id"]) for a in dados["atividades"]
               if a.get("quantidade_total") and a.get("status") != "concluida"}
    esperado = sorted(f"{lote}/{serv}" for lote, serv in abertas - medidas)
    assert esperado == {"ferrovia": ["L3/GRA", "L3/LAS", "L3/SOL"],
                        "rodovia": ["L2/SHV", "L3/CBU", "L3/DEF", "L3/SHV", "L3/SVV"]}[obra]
    sem, com = mc[obra]
    info = com["incerteza_sem_medicao"]
    assert info["ativo"] is True and info["grupos"] == esperado and info["indices_observados"] == len(medidas)
    assert "incerteza_sem_medicao" not in sem
    assert {k: com["marcos"]["M-FIM"][k] for k in ("p10", "p50", "p80", "p90")} == {k: com[k] for k in ("p10", "p50", "p80", "p90")}


def test_p4_desligado_ou_sem_frente_medida_nao_muda_nada(bases):
    """(a) Padrão desligado: a saída é a mesma de antes (sem a chave do modo). (b) Obra sem nenhum boletim:
    não há índice observado; o modo declara 'sem efeito' e os percentis são os de sem P4.
    (c) alargamento fora de [0, 1) é recusado."""
    P = bases["rodovia"]
    assert MC.simular(P, 30, 7) == MC.simular(P, 30, 7, incerteza_sem_medicao=False, alargamento=0.5)
    d = copy.deepcopy(P.dados)
    d["medicoes"] = []
    V = Projeto(d)
    a, b = MC.simular(V, 30, 7), MC.simular(V, 30, 7, incerteza_sem_medicao=True)
    assert b["incerteza_sem_medicao"]["ativo"] is False and "sem efeito" in b["incerteza_sem_medicao"]["nota"]
    assert {k: a[k] for k in ("p10", "p50", "p80", "p90")} == {k: b[k] for k in ("p10", "p50", "p80", "p90")}
    for ruim in (1.0, -0.1):
        with pytest.raises(ValueError):
            MC.simular(P, 30, 7, incerteza_sem_medicao=True, alargamento=ruim)


def test_p4_pela_rota_com_as_outras_opcoes(bases):
    """Pela rota: P4 com correlação, chuva, riscos, criticidade e só-aprovados responde 200 e devolve os 4
    marcos em 'marcos' quando ``por_marco`` é pedido; alargamento 0,95 é 422."""
    c = _app({"rodovia": bases["rodovia"]})
    for extra in ({"rho": 0.5}, {"com_chuva": "true"}, {"com_riscos": "true"}, {"com_criticidade": "true"},
                  {"so_aprovados": "true"}):
        r = c.get("/api/previsao-probabilistica", params={"iteracoes": 20, "incerteza_sem_medicao": "true",
                                                          "por_marco": "true", **extra})
        assert r.status_code == 200, (extra, r.text[:200])
        assert sorted(r.json()["marcos"]) == ["M-FIM", "M-L1-FIM", "M-L2-FIM", "M-L3-FIM"], extra
    assert c.get("/api/previsao-probabilistica", params={"incerteza_sem_medicao": "true",
                                                         "alargamento": 0.95}).status_code == 422


# Regressão: defeito da rodada 19, já corrigido pelo dono do módulo (as marcas xfail saíram). O que falhava:
#   o modo P4 não só ALARGAVA a incerteza das frentes sem medição: DESLOCAVA a distribuição para o lado otimista.
#   Trocava a analogia do MESMO serviço em outros lotes por um índice sorteado entre TODAS as frentes medidas da
#   obra (média perto de 0,9). Na rodada 19, 200 iterações, semente 7: ferrovia P90 14/09/2027 → 11/09/2027 e
#   P50 10/09 → 04/09; rodovia P50 12/07/2027 → 06/07/2027 (o L3/CBU deixava de herdar o índice 0,59 do L2).
@pytest.mark.parametrize("obra,percentil", [("ferrovia", "p90"), ("ferrovia", "p50"), ("rodovia", "p50"),
                                            ("rodovia", "p90")])
def test_p4_nao_antecipa_a_previsao(mc, obra, percentil):
    """Ligar a incerteza das frentes SEM medição acrescenta dúvida, não informação favorável: o P50 e o P90
    com P4 não podem ser ANTERIORES aos de sem P4 (mesmas 200 iterações, mesma semente)."""
    sem, com = mc[obra]
    assert ordinal(com[percentil]) >= ordinal(sem[percentil]), (sem[percentil], com[percentil])
