"""Revisão adversarial — rodada 15: registro de riscos ao prazo (``riscos_prazo.py`` + ``rotas_riscos.py``)
e IFC etapa 4 (IfcLinearPlacement e IfcReferent/Pset_Stationing em ``ifc/exportar.py`` / ``importar.py``).

Cada teste traz no docstring o resultado esperado calculado à mão ou por conferência independente.
Defeito confirmado fica ``xfail(strict=True, reason="DEFEITO: ...")``.

A parte de IFC é pulada (SKIP, não verde) se ``ifcopenshell`` não estiver no .venv.
"""

import copy
import math
import random
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import riscos_prazo as RP
from infra4d.cenarios import Projeto, executar

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")


def _defeito(motivo):
    return pytest.mark.xfail(strict=True, reason="DEFEITO: " + motivo)


@pytest.fixture(scope="module")
def bases():
    return {o: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json") for o in OBRAS}


@pytest.fixture(scope="module")
def cliente(bases):
    from infra4d.api import criar_app
    return TestClient(criar_app(fontes=bases), raise_server_exceptions=False)


@pytest.fixture(scope="module")
def registros(cliente):
    """GET /api/riscos?rapido=true das duas obras (as fontes caras não entram: máquina com pouca RAM)."""
    out = {}
    for o in OBRAS:
        r = cliente.get("/api/riscos", params={"obra": o, "rapido": "true"})
        assert r.status_code == 200, r.text[:300]
        out[o] = r.json()
    return out


def _sinal(chave, fonte, delta=None, prob=None, nivel="medio"):
    return {"chave": chave, "fonte": fonte, "atividades": [], "nivel": nivel, "delta": delta, "prob": prob,
            "titulo": f"{fonte} {chave}", "texto": "t", "evidencias": []}


def _com_restricoes(base: Projeto, extras: list[dict]) -> Projeto:
    d = copy.deepcopy(base.dados)
    d["restricoes"] = list(d.get("restricoes", [])) + extras
    return Projeto(d)


def _so_restricao(P: Projeto) -> list[dict]:
    return RP.registro(P, obra="x", fontes=[("restricao", dict(RP.FONTES)["restricao"])])["riscos"]


# =============================================================================
# 1a. riscos — o que se sustenta
# =============================================================================
def test_rota_erros_e_cache(cliente, registros):
    """Obra desconhecida 404; ``rapido`` que não é booleano 422; a 2ª chamada vem do cache com o MESMO
    conteúdo (fora a chave ``cache``)."""
    assert cliente.get("/api/riscos", params={"obra": "nao-existe"}).status_code == 404
    assert cliente.get("/api/riscos", params={"obra": "ferrovia", "rapido": "banana"}).status_code == 422
    de_novo = cliente.get("/api/riscos", params={"obra": "ferrovia", "rapido": "true"}).json()
    assert de_novo.pop("cache") is True
    assert de_novo == {k: v for k, v in registros["ferrovia"].items() if k != "cache"}


def test_registro_e_deterministico_entre_apps(bases, registros):
    """Um app novo, com os mesmos dados carregados de novo do disco, devolve os mesmos riscos, na mesma
    ordem e com os mesmos ids (só os tempos mudam)."""
    from infra4d.api import criar_app
    P = Projeto.carregar(RAIZ / "examples" / "synthetic" / "rodovia_ficticia.json")
    c = TestClient(criar_app(fontes={"rodovia": P}), raise_server_exceptions=False)
    assert c.get("/api/riscos", params={"obra": "rodovia", "rapido": "true"}).json()["riscos"] == \
        registros["rodovia"]["riscos"]


@pytest.mark.parametrize("semente", range(5))
def test_ordenacao_nao_depende_da_ordem_dos_sinais(semente):
    """12 sinais de chaves distintas, com empates de exposição (dois Δ = 7) e de nível entre os sem Δ.
    Esperado à mão: Δ 30, 12, 7 (alto), 7 (medio), 2, 1; depois os sem Δ por nível e, no empate, pela chave
    (lote, serviço): alto S4 (L1), S8 (L2); medio S6 (L0), S5 (L2); baixo S3 (L0), S10 (L1). Embaralhando a
    entrada, a MESMA sequência de
    (frente, id): o desempate é pela chave, não pela ordem de chegada."""
    sinais = [_sinal(("frente", f"L{i % 3}", f"S{i}"), "tornado", delta=d, nivel=n)
              for i, (d, n) in enumerate([(7, "medio"), (30, "alto"), (7, "alto"), (None, "baixo"), (None, "alto"),
                                          (None, "medio"), (None, "medio"), (2, "baixo"), (None, "alto"),
                                          (12, "medio"), (None, "baixo"), (1, "baixo")])]
    ref = [(r["frentes"][0]["servico_id"], r["id"]) for r in RP.consolidar(sinais)]
    assert [s for s, _ in ref] == ["S1", "S9", "S2", "S0", "S7", "S11", "S4", "S8", "S6", "S5", "S3", "S10"]
    random.Random(semente).shuffle(sinais)
    assert [(r["frentes"][0]["servico_id"], r["id"]) for r in RP.consolidar(sinais)] == ref


def test_deduplicacao_nao_junta_frentes_diferentes():
    """Mesmo serviço em lotes diferentes, serviços diferentes no mesmo lote, lote ausente e uma chave de
    obra: 5 chaves distintas -> 5 riscos. Só (L1, TER), que recebe 2 fontes, vira um risco de 2 fontes com
    Δ = max(4, 9) = 9."""
    r = RP.consolidar([_sinal(("frente", "L1", "TER"), "tornado", delta=4),
                       _sinal(("frente", "L2", "TER"), "tornado", delta=5),
                       _sinal(("frente", "L1", "DRE"), "produtividade"),
                       _sinal(("frente", None, "TER"), "tornado", delta=6),
                       _sinal(("obra", "clima"), "clima", delta=3),
                       _sinal(("frente", "L1", "TER"), "produtividade", delta=9)])
    assert len(r) == 5
    l1 = next(x for x in r if x["frentes"] == [{"lote_id": "L1", "servico_id": "TER"}])
    assert l1["fontes"] == ["tornado", "produtividade"] and l1["delta_potencial_dias"] == 9
    assert sorted(x["delta_potencial_dias"] for x in r if x["delta_potencial_dias"]) == [3, 5, 6, 9]


@pytest.mark.parametrize("erro", [ValueError("x"), KeyError("k"), StopIteration(), ZeroDivisionError(), RecursionError()])
def test_fonte_quebrada_e_declarada_e_as_outras_seguem(bases, erro):
    """Uma fonte que estoura (qualquer Exception) aparece em ``fontes_omitidas`` com o tipo do erro; a fonte
    de restrição, ao lado, continua entregando o risco da restrição pendente R-TRI-L3."""
    def quebrada(projeto, ind, obra):
        raise erro

    r = RP.registro(bases["ferrovia"], obra="ferrovia",
                    fontes=[("quebrada", quebrada), ("restricao", dict(RP.FONTES)["restricao"])])
    assert list(r["fontes_omitidas"]) == ["quebrada"] and type(erro).__name__ in r["fontes_omitidas"]["quebrada"]
    assert r["fontes_usadas"] == ["restricao"] and r["n_riscos"] == 1
    assert r["riscos"][0]["atividades"] == ["L3-S01-GRA"]


@pytest.mark.parametrize("mutacao", ["sem medições", "sem a chave restricoes", "restricoes nula"])
def test_dataset_degenerado_nao_vira_500(bases, mutacao):
    """Sem boletins, sem a chave ``restricoes`` ou com ``restricoes: null``: a rota responde 200; a fonte
    que não consegue ler o dado fica declarada em ``fontes_omitidas`` (só 'restricao', e só no 3º caso)."""
    from infra4d.api import criar_app
    d = copy.deepcopy(bases["ferrovia"].dados)
    if mutacao == "sem medições":
        d["medicoes"] = []
    elif mutacao == "sem a chave restricoes":
        d.pop("restricoes")
    else:
        d["restricoes"] = None
    c = TestClient(criar_app(fontes={"x": Projeto(d)}), raise_server_exceptions=False)
    r = c.get("/api/riscos", params={"obra": "x", "rapido": "true"})
    assert r.status_code == 200, r.text[:300]
    omit = set(r.json()["fontes_omitidas"]) - set(RP.FONTES_CARAS)
    assert omit == ({"restricao"} if mutacao == "restricoes nula" else set())


# =============================================================================
# 1b. riscos — defeitos
# =============================================================================
# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (as marcas xfail saíram). O que falhava:
#   linha de balanço: o texto do risco citava a distância MÍNIMA do grupo (min sobre os conflitos do par de
#   frentes), mas a evidência gravava `es[0]['distancia_km_min']` e o caminho pegava o 1º conflito do par.
#   Quando o 1º não era o pior, a evidência reproduzia OUTRO número: ferrovia L3 DRE→SUB, texto 0,163 km ×
#   evidência 0,186 km; rodovia L2 CBU→DEF, texto −1,846 km × evidência −1,816 km.
@pytest.mark.parametrize("obra", ["ferrovia", "rodovia"])
def test_evidencia_do_balanco_reproduz_a_distancia_do_texto(registros, cliente, obra):
    """Para cada risco de balanço: o número 'distância mínima X km' da explicação tem de ser o valor da
    evidência, e a evidência tem de sair da rota (rota + params + caminho). Conferência independente: o
    mínimo de ``distancia_km_min`` entre os conflitos do mesmo lote e par de serviços, lido direto de
    GET /api/recursos/conflitos-balanco."""
    riscos = [x for x in registros[obra]["riscos"] if x["fontes"] == ["balanco"]]
    assert riscos
    for x in riscos:
        (ev,) = x["evidencias"]
        j = cliente.get(ev["rota"], params=ev["params"]).json()
        assert RP.extrair(j, ev["caminho"]) == ev["valor"]
        filtro = ev["caminho"][1]
        minimo = min(c["distancia_km_min"] for c in j["conflitos"]
                     if c["lote"] == filtro["lote"] and c["servicos"] == filtro["servicos"])
        texto = float(re.search(r"distância mínima (-?\d+\.\d+) km", x["explicacao"]).group(1))
        assert texto == pytest.approx(minimo, abs=5e-4)
        assert ev["valor"] == pytest.approx(texto, abs=5e-4), (x["titulo"], ev["valor"], texto)


# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("restrição 'pendente' apontando para atividade JÁ CONCLUÍDA vira risco de nível ALTO: a folga total de "
#   "atividade concluída é None e a regra `(ft or 0) <= 10` lê None como folga 0. O texto sai 'tem folga "
#   "total de None dias úteis'. Correção: ignorar (ou rebaixar e dizer) restrição de atividade concluída e "
#   "nunca tratar folga None como 0")
def test_restricao_pendente_em_atividade_concluida_nao_e_risco_alto(bases):
    """L1-S01-SUP está concluída no dataset (status 'concluida'): uma restrição pendente esquecida nela não
    pode atrasar nada. Esperado: nenhum risco 'alto' nem texto com 'None' por causa dela; a restrição real
    R-TRI-L3 (L3-S01-GRA, folga 80 dias úteis > 10) continua 'medio'."""
    P = _com_restricoes(bases["ferrovia"], [{"id": "R-X", "descricao": "esquecida", "atividade_id": "L1-S01-SUP",
                                             "data_liberacao": "2025-12-01", "situacao": "pendente"}])
    assert executar(P, "independente")["atividades"]["L1-S01-SUP"]["status"] == "concluida"
    riscos = _so_restricao(P)
    assert [x["nivel"] for x in riscos if x["atividades"] == ["L3-S01-GRA"]] == ["medio"]
    assert not [x for x in riscos if x["nivel"] == "alto"]
    assert not [x for x in riscos if "None" in x["explicacao"]]


# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("duas restrições pendentes na MESMA frente (atividades diferentes) são fundidas e o título vira '… risco "
#   "ao prazo confirmado por 2 fontes' com fontes == ['restricao', 'restricao']: é a mesma fonte contada "
#   "duas vezes, não uma confirmação independente. Correção: contar fontes distintas (e manter o título "
#   "da restrição quando só há uma fonte)")
def test_duas_restricoes_na_mesma_frente_nao_sao_duas_fontes(bases):
    """R-TRI-L3 (L3-S01-GRA) + uma restrição nova em L3-S02-GRA: a frente (L3, GRA) tem UMA fonte de sinal
    (restrição). Esperado: fontes sem repetição e nenhum título 'confirmado por 2 fontes'."""
    P = _com_restricoes(bases["ferrovia"], [{"id": "R-X", "descricao": "segunda", "atividade_id": "L3-S02-GRA",
                                             "data_liberacao": "2027-02-01", "situacao": "pendente"}])
    riscos = _so_restricao(P)
    assert {a for x in riscos for a in x["atividades"]} == {"L3-S01-GRA", "L3-S02-GRA"}
    for x in riscos:
        assert len(set(x["fontes"])) == len(x["fontes"]), x["fontes"]
        assert "confirmado por" not in x["titulo"], x["titulo"]


# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("restrição em atividade SEM serviço (marco, liberação) recebe a chave de frente (lote, None): o risco sai "
#   "com frentes == [{'lote_id': 'L1', 'servico_id': None}] e, havendo duas atividades sem serviço no mesmo "
#   "lote, os dois sinais — sem relação entre si — fundem-se num risco 'None do L1: risco ao prazo "
#   "confirmado por 2 fontes'. Correção: sem serviço, a chave deve ser a atividade, não a frente")
def test_restricoes_em_marcos_do_mesmo_lote_nao_se_fundem(bases):
    """Chaves montadas como ``_f_restricao`` monta para duas atividades do L1 sem serviço (M-L1-FIM e um
    segundo marco): são dois riscos distintos, e nenhum título/frente cita serviço None."""
    d = copy.deepcopy(bases["ferrovia"].dados)
    marco = copy.deepcopy(next(a for a in d["atividades"] if a["id"] == "M-L1-FIM"))
    marco["id"] = "M-L1-ENTREGA"
    d["atividades"].append(marco)
    d["relacoes"].append({"predecessora": "M-L1-FIM", "sucessora": "M-L1-ENTREGA", "tipo": "FS", "lag": 0})
    d["restricoes"] += [{"id": f"R-{i}", "descricao": f"pendência {i}", "atividade_id": aid,
                         "data_liberacao": "2027-02-01", "situacao": "pendente"}
                        for i, aid in enumerate(["M-L1-FIM", "M-L1-ENTREGA"])]
    riscos = [x for x in _so_restricao(Projeto(d)) if set(x["atividades"]) & {"M-L1-FIM", "M-L1-ENTREGA"}]
    assert sorted(x["atividades"] for x in riscos) == [["M-L1-ENTREGA"], ["M-L1-FIM"]]
    for x in riscos:
        assert "None" not in x["titulo"]
        assert all(f["servico_id"] is not None for f in x["frentes"])


# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("ordenação: exposição = Δ × probabilidade quando há probabilidade, senão Δ puro — ou seja, probabilidade "
#   "AUSENTE vale 1. Um risco que ganha a confirmação do Monte Carlo (p = 0,5) CAI de posição frente a outro "
#   "sem probabilidade e com Δ menor; e a ordem relativa dos mesmos dois riscos muda entre rapido=true e "
#   "rapido=false. Correção: não misturar as duas escalas (ordenar por Δ e mostrar p à parte, ou usar a "
#   "mesma probabilidade de referência para quem não tem)")
def test_confirmacao_por_criticidade_nao_rebaixa_o_risco():
    """A: tornado Δ 20; B: tornado Δ 12. Sem criticidade (modo rápido): A (20) antes de B (12). Com a
    criticidade de A = 0,5 (A foi crítica em metade das iterações — MAIS evidência, não menos), A continua
    tendo o maior Δ e tem de continuar na frente. Pela regra atual: 20 × 0,5 = 10 < 12 -> B passa."""
    a, b = ("frente", "L1", "A"), ("frente", "L1", "B")
    rapido = RP.consolidar([_sinal(a, "tornado", delta=20), _sinal(b, "tornado", delta=12)])
    completo = RP.consolidar([_sinal(a, "tornado", delta=20), _sinal(b, "tornado", delta=12),
                              _sinal(a, "criticidade", prob=0.5)])
    ordem = lambda rs: [x["frentes"][0]["servico_id"] for x in rs]  # noqa: E731
    assert ordem(rapido) == ["A", "B"]
    assert ordem(completo) == ["A", "B"]


# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("sem ?obra= a evidência grava params {'obra': None} (JSON null). 'A rota GET exata e os parâmetros' não "
#   "são reproduzíveis por um cliente que monte a query do JSON: ?obra=null responde 404. Correção: omitir "
#   "o parâmetro ausente ou gravar o id da obra padrão resolvida")
def test_evidencia_sem_obra_nao_traz_parametro_nulo(bases):
    """Chamada sem ``obra`` (obra padrão do app): nenhum parâmetro de evidência pode ser nulo, e montar a
    query como um cliente JSON monta (null -> 'null') tem de responder 200."""
    from infra4d.api import criar_app
    c = TestClient(criar_app(fontes={"ferrovia": bases["ferrovia"]}), raise_server_exceptions=False)
    j = c.get("/api/riscos", params={"rapido": "true"}).json()
    evs = [e for x in j["riscos"] for e in x["evidencias"]]
    assert evs
    e = evs[0]
    q = {k: ("null" if v is None else v) for k, v in e["params"].items()}
    assert c.get(e["rota"], params=q).status_code == 200
    assert all(v is not None for e in evs for v in e["params"].values())


# =============================================================================
# 2. IFC etapa 4 — IfcLinearPlacement e IfcReferent
# =============================================================================
ifcopenshell = pytest.importorskip("ifcopenshell")
import ifcopenshell.api.alignment  # noqa: E402
import ifcopenshell.geom  # noqa: E402
import ifcopenshell.util.element  # noqa: E402
import ifcopenshell.validate  # noqa: E402
import numpy as np  # noqa: E402

from infra4d.ifc import exportar as exp  # noqa: E402
from infra4d.ifc import importar as imp  # noqa: E402

RETO = [[0.0, 0.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0], [2.0, 2000.0, 0.0, 0.0]]
CURVA = [[0.0, 0.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0], [2.0, 1990.0, 140.0, 0.0]]


def _obra(pontos, ativs, eq=None, origem=None) -> dict:
    """Obra mínima: aterro (TER) nos trechos ``ativs`` = [(km_ini, km_fim)] sobre a polilinha ``pontos``."""
    k0, k1 = min(p[0] for p in pontos), max(p[0] for p in pontos)
    d = {"meta": {"aviso": "DADOS FICTÍCIOS de teste", "tipo_obra": "ferrovia"},
         "ferrovia": {"id": "TESTE", "nome": "Obra mínima de teste"},
         "lotes": [{"id": "L1", "nome": "Lote 1", "km_ini": k0, "km_fim": k1}],
         "segmentos": [{"id": "L1-S01", "lote_id": "L1", "km_ini": k0, "km_fim": k1}],
         "servicos": [{"id": "TER", "unidade": "m³"}], "oaes": [], "relacoes": [],
         "atividades": [{"id": f"A{i}", "nome": f"A{i}", "tipo": "tarefa", "lote_id": "L1", "segmento_id": "L1-S01",
                         "servico_id": "TER", "km_ini": a, "km_fim": b, "unidade": "m³", "quantidade_total": 1000.0,
                         "inicio_lb": "2026-01-05", "termino_lb": "2026-01-30"} for i, (a, b) in enumerate(ativs)],
         "alinhamento": {"pontos": pontos}}
    if eq:
        d["meta"]["equacoes_estaca"] = eq
    if origem is not None:
        d["meta"]["estaca_origem"] = origem
    return d


def _vertices(f) -> dict:
    """Vértices em coordenadas do mundo, por nome do elemento, triangulados pelo próprio IfcOpenShell."""
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    out = {}
    it = ifcopenshell.geom.iterator(s, f, include=f.by_type("IfcElement"))
    if it.initialize():
        while True:
            sh = it.get()
            out[f.by_guid(sh.guid).Name] = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
            if not it.next():
                break
    return out


def _desvios(d: dict) -> dict:
    """Distância de Hausdorff, por peça, entre a versão IfcLinearPlacement e a IfcLocalPlacement (esta usa
    direto as coordenadas do JSON, sem projeção na curva)."""
    fl, resumo = exp.construir(d, incluir_4d=False, posicionamento="linear")
    assert resumo["posicionamento"] == "IfcLinearPlacement"
    fa, _ = exp.construir(d, incluir_4d=False, posicionamento="local")
    va, vb = _vertices(fa), _vertices(fl)
    assert set(va) == set(vb) and va
    out = {}
    for nome, x in va.items():
        dd = np.linalg.norm(x[:, None, :] - vb[nome][None, :, :], axis=2)
        out[nome] = float(max(dd.min(axis=1).max(), dd.min(axis=0).max()))
    return out


def _leque(graus: float) -> list:
    t = math.radians(graus)
    return [[0.0, 0.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0],
            [2.0, 1000.0 + 1000.0 * math.cos(t), 1000.0 * math.sin(t), 0.0]]


# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (as marcas xfail de 120° e 150° saíram).
# O que falhava: a projeção de Newton (`CurvaEixo.projetar`) oscilava e parava nas 20 iterações sem convergir;
#   o resíduo ao longo da tangente só era somado em `residuo_projecao_m` e a peça depois do PI saía fora do
#   lugar. Medido na rodada 15: 100° -> 1 mm, 110° -> 0,47 m, 120° -> 112 m, 150° -> 579 m (403 m sobre o PI).
@pytest.mark.parametrize("graus", [60, 90, 120, 150])
def test_peca_com_grande_afastamento_lateral_fica_no_lugar(graus, limite):
    """Eixo de 2 km com deflexão no km 1. O alinhamento IFC arredonda o PI com um arco; a polilinha do JSON
    passa pelo vértice — as peças perto do PI ficam a dezenas/centenas de metros da curva (a 90°, a peça do
    km 1,003 tem OffsetLateral ≈ −184 m). Com IfcLinearPlacement cada peça tem de ficar no MESMO lugar da
    versão IfcLocalPlacement: Hausdorff <= tolerância do manifesto."""
    desv = _desvios(_obra(_leque(graus), [(0.0, 1.0), (1.0, 2.0), (0.9, 1.1), (1.4, 1.6)]))
    assert max(desv.values()) <= limite("tolerancia_posicao_ifc_m"), desv


def test_ziguezague_de_quatro_deflexoes_de_90_graus(limite):
    """Quatro pernas de 1 km em ângulo reto (direita e esquerda alternadas): todas as peças no lugar."""
    pts = [[0.0, 0.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0], [2.0, 1000.0, 1000.0, 0.0], [3.0, 2000.0, 1000.0, 0.0],
           [4.0, 2000.0, 0.0, 0.0]]
    desv = _desvios(_obra(pts, [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)]))
    assert max(desv.values()) <= limite("tolerancia_posicao_ifc_m"), desv


# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (as marcas xfail saíram). O que falhava:
#   `projetar` prendia a distância em [0, comprimento] e o IfcPointByDistanceExpression só levava lateral e
#   vertical — a componente ao longo da tangente era descartada. A peça ANTES do km 0 (km −0,5 a 0) saía com x
#   de 0 a 494 em vez de −497 a −3 (497 m fora do lugar) e a peça DEPOIS do fim (km 2,2 a 2,5) saía 203 m
#   recuada, sem erro nem aviso (só `residuo_projecao_m` no resumo).
@pytest.mark.parametrize("trecho,x_min,x_max", [((-0.5, 0.0), -497.0, -3.0), ((2.2, 2.5), 2203.0, 2497.0)])
def test_peca_fora_da_extensao_do_eixo_fica_no_lugar(trecho, x_min, x_max, limite):
    """Eixo RETO sobre o eixo x (km k -> x = 1000·k), de km 0 a km 2. A peça de aterro do trecho [a, b]
    ocupa, à mão, x de 1000·a + 3 a 1000·b − 3 (folga de 3 m em cada ponta): [−0,5; 0] -> x ∈ [−497, −3];
    [2,2; 2,5] -> x ∈ [2203, 2497]. A versão com placement local dá exatamente isso; a linear tem de dar
    o mesmo."""
    tol = limite("tolerancia_posicao_ifc_m")
    d = _obra(RETO, [trecho, (0.0, 1.0)])
    local, _ = exp.construir(d, incluir_4d=False, posicionamento="local")
    xs = _vertices(local)["A0-E01"][:, 0]
    assert (xs.min(), xs.max()) == (pytest.approx(x_min, abs=tol), pytest.approx(x_max, abs=tol))
    linear, _ = exp.construir(d, incluir_4d=False, posicionamento="linear")
    xs = _vertices(linear)["A0-E01"][:, 0]
    assert (xs.min(), xs.max()) == (pytest.approx(x_min, abs=tol), pytest.approx(x_max, abs=tol))


# Regressão: defeito da rodada 15, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   eixo que começa (ou termina) em km NÃO inteiro: os PIs do IfcAlignment usavam só os pontos de km inteiro,
#   então a curva IFC começava no km 1 e não no km 0,3 — mas `start_station` e o referente inicial recebiam a
#   estaca do km 0,3. Resultado: referentes do km 0,3 (15+00) e do km 1 (50+00) no MESMO ponto (distância 0),
#   a peça do km 0,3–1,0 exportada 690 m fora do lugar e o trecho final 2,0–2,6 sem eixo.
# Correção DESTE teste (erro meu na rodada 15): eu exigia 700,00 m entre os referentes do km 0,3 e do km 1,
#   como se o eixo fosse reto até o km 1. O km 1 é um PI: o alinhamento passa por um arco de concordância e o
#   referente fica no pé da perpendicular do PI sobre o arco, a 700 − T + RΔ/2 (≈ 699,48 m), não a 700.
def test_eixo_que_comeca_em_km_fracionario(limite):
    """Polilinha km 0,3 (x=300) -> km 1 (x=1000) -> km 2 (1990, 140) -> km 2,6. O eixo IFC começa no ponto do
    km 0,3 (distância 0) e arredonda o PI do km 1 com um arco de raio R (lido do PRÓPRIO arquivo, no segmento
    horizontal CIRCULARARC). Deflexão no PI: Δ = atan2(140, 990). À mão:
    - tangente T = R·tan(Δ/2); a 1ª reta mede 700 − T;
    - o ponto do eixo mais próximo do PI é o MEIO do arco (o PI está na bissetriz), a R·Δ/2 do início do arco;
    - logo o referente do km 1 fica a (700 − T) + R·Δ/2 do referente do km 0,3 — um pouco menos que 700 m
      (T − RΔ/2 ≈ RΔ³/24).
    E a peça do km 0,3–1,0 fica onde a versão com placement local a põe."""
    pts = [[0.3, 300.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0], [2.0, 1990.0, 140.0, 0.0], [2.6, 2590.0, 140.0, 0.0]]
    d = _obra(pts, [(0.3, 1.0), (2.0, 2.6)])
    f, _ = exp.construir(d, incluir_4d=False)
    refs = {r["km"]: r for r in imp.alinhamentos(f)["itens"][0]["referentes"]}
    assert refs[0.3]["estaca"] == pytest.approx(300.0) and refs[1.0]["estaca"] == pytest.approx(1000.0)
    al = ifcopenshell.api.alignment
    segs = [s.DesignParameters for s in al.get_layout_segments(al.get_horizontal_layout(f.by_type("IfcAlignment")[0]))
            if getattr(s, "DesignParameters", None)]
    reta, arco = segs[0], next(s for s in segs if s.PredefinedType == "CIRCULARARC")
    raio = abs(float(arco.StartRadiusOfCurvature))
    delta = math.atan2(140.0, 990.0)
    tangente = raio * math.tan(delta / 2)
    assert reta.PredefinedType == "LINE" and abs(float(reta.SegmentLength)) == pytest.approx(700.0 - tangente, abs=1e-6)
    esperado = 700.0 - tangente + raio * delta / 2
    assert 699.0 < esperado < 700.0
    assert refs[0.3]["distancia_ao_longo"] == pytest.approx(0.0, abs=limite("tolerancia_estaca_m"))
    assert refs[1.0]["distancia_ao_longo"] == pytest.approx(esperado, abs=limite("tolerancia_estaca_m"))
    desv = _desvios(d)
    assert max(desv.values()) <= limite("tolerancia_posicao_ifc_m"), desv


def test_equacao_de_estacas_com_volta(limite):
    """Equação no km 1 que RECUA a estaca de 50+00 (1000 m) para 20+00 (400 m), num eixo com curva no km 1.
    À mão: km 0 -> 0 m; km 1 -> 400 m (vale o trecho novo); km 2 -> 400 + 1000 = 1400 m (70+00). O
    ``IncomingStation`` do km 1 é o que o IFC traz por continuidade desde o km 0 (0 + distância ao longo
    até o km 1, ~999,42 m pela curva) e o do km 2 é 400 + curva entre km 1 e km 2. A estaca 'atrás' na
    medida do projeto (1000 m) vai em INFRA4D_Referencia.EstacaAnteriorMedida. Estaca final do eixo: 1400.
    As peças não se movem e o arquivo valida sem erro (esquema + regras EXPRESS)."""
    tol = limite("tolerancia_estaca_m")
    d = _obra(CURVA, [(0.0, 2.0)], eq=[{"km": 1.0, "estaca": "20+00,00"}])
    f, resumo = exp.construir(d, incluir_4d=False)
    assert resumo["equacoes_estaca"] == 1 and resumo["referentes_km"] == 1
    item = imp.alinhamentos(f)["itens"][0]
    refs = {r["km"]: r for r in item["referentes"]}
    assert [refs[k]["estaca"] for k in (0.0, 1.0, 2.0)] == [pytest.approx(v, abs=tol) for v in (0.0, 400.0, 1400.0)]
    assert [refs[k]["estaca_texto"] for k in (0.0, 1.0, 2.0)] == ["0+00,00", "20+00,00", "70+00,00"]
    d1, d2 = refs[1.0]["distancia_ao_longo"], refs[2.0]["distancia_ao_longo"]
    assert 990.0 < d1 < 1000.0 and 1990.0 < d2 < 2000.0   # a curva encurta: menos que a medida
    assert refs[1.0]["estaca_de_volta"] == pytest.approx(d1, abs=tol)
    assert refs[2.0]["estaca_de_volta"] == pytest.approx(400.0 + d2 - d1, abs=tol)
    assert item["estaca_final"] == pytest.approx(1400.0, abs=tol)
    eq = next(r for r in f.by_type("IfcReferent") if "equação" in (r.Description or ""))
    assert ifcopenshell.util.element.get_pset(eq, "INFRA4D_Referencia")["EstacaAnteriorMedida"] == \
        pytest.approx(1000.0, abs=tol)
    assert imp.comparar_estacas(f, d)["max_dif_m"] <= tol
    assert max(_desvios(d).values()) <= limite("tolerancia_posicao_ifc_m")
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    assert log.statements == [], [str(s)[:200] for s in log.statements[:3]]


def test_duas_equacoes_fora_de_km_inteiro_com_origem_deslocada(limite):
    """estaca_origem 50 (km 0 = 1000 m); equação no km 0,4 que RECUA para 5+00 (100 m) e outra no km 1,6
    que SALTA para 300+00 (6000 m). À mão: km 0,4 -> 100; km 1 -> 100 + 600 = 700; km 1,6 -> 6000;
    km 2 -> 6000 + 400 = 6400. 'De volta' na medida do projeto: no km 0,4 -> 1000 + 400 = 1400; no km 1,6
    -> 100 + 1200 = 1300. Referentes em ordem de distância ao longo."""
    tol = limite("tolerancia_estaca_m")
    d = _obra(CURVA, [(0.0, 2.0)], origem=50,
              eq=[{"km": 0.4, "estaca": "5+00,00"}, {"km": 1.6, "estaca": "300+00,00"}])
    f, resumo = exp.construir(d, incluir_4d=False)
    assert resumo["equacoes_estaca"] == 2
    lista = imp.alinhamentos(f)["itens"][0]["referentes"]
    refs = {r["km"]: r for r in lista}
    esperado = {0.0: 1000.0, 0.4: 100.0, 1.0: 700.0, 1.6: 6000.0, 2.0: 6400.0}
    assert {k: refs[k]["estaca"] for k in esperado} == {k: pytest.approx(v, abs=tol) for k, v in esperado.items()}
    dist = [refs[k]["distancia_ao_longo"] for k in sorted(esperado)]
    assert dist == sorted(dist) and len(set(dist)) == 5
    volta = {ifcopenshell.util.element.get_pset(r, "INFRA4D_Referencia")["Km"]:
             ifcopenshell.util.element.get_pset(r, "INFRA4D_Referencia")["EstacaAnteriorMedida"]
             for r in f.by_type("IfcReferent") if "equação" in (r.Description or "")}
    assert volta == {0.4: pytest.approx(1400.0, abs=tol), 1.6: pytest.approx(1300.0, abs=tol)}
