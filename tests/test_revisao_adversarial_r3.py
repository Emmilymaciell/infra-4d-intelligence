"""Revisão adversarial — rodada 3: marcos/instantes no gerador aleatório e a API.

Mesmo protocolo: esperado calculado à mão no docstring. Os 9 casos que nasceram como
``xfail(strict=True)`` (6 defeitos) foram corrigidos e viraram REGRESSÃO normal.

Calendários: c5 = seg–sex; c6 = seg–sáb; cF = seg–sex com feriados em 07, 08, 19,
20 e 21/01/2026. 2026-01-05 é segunda. Status de teste: qua 14/01.
"""

import itertools
import random
import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.calendario import Calendario
from infra4d.cenarios import CENARIOS, Projeto
from infra4d.motor import AtividadeCPM as A
from infra4d.motor import Relacao as R, calcular

SEG = date(2026, 1, 5).toordinal()
DS = date(2026, 1, 14).toordinal()
CALS = {
    "c5": Calendario("c5", "5 dias"),
    "c6": Calendario("c6", "6 dias", (0, 1, 2, 3, 4, 5)),
    "cF": Calendario("cF", "5 dias com feriados", (0, 1, 2, 3, 4), frozenset(
        {date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 19), date(2026, 1, 20), date(2026, 1, 21)})),
}


def o(s):
    return date.fromisoformat(s).toordinal()


def rodar(ativs, rels, **kw):
    res = calcular(ativs, rels, CALS, SEG, **kw)
    by = {a.id: a for a in ativs}
    return res, {k: v.como_dict(CALS[by[k].calendario], by[k]) for k, v in res.atividades.items()}


def termino_iso(res):
    return date.fromordinal(res.termino_projeto_data).isoformat()


def MT(i, cal="c5", **k):
    return A(i, 0, cal, tipo="marco_termino", **k)


def MI(i, cal="c5", **k):
    return A(i, 0, cal, tipo="marco_inicio", **k)


# =============================================================================
# 1. Propriedades com marcos e tarefas de duração 0
# =============================================================================
def _rede(rng, com_progresso):
    n = rng.randint(2, 5)
    ativs = []
    for i in range(n):
        c = rng.choice(["c5", "c6", "cF"])
        x = rng.random() if com_progresso else 1.0
        if x < 0.15:
            ativs.append(A(f"N{i}", 0, c, status="concluida", inicio_real=SEG, termino_real=SEG + rng.randint(0, 8)))
        elif x < 0.35:
            ativs.append(A(f"N{i}", rng.randint(1, 6), c, status="em_andamento", inicio_real=SEG + rng.randint(0, 8)))
        else:
            y = rng.random()
            if y < 0.15:
                ativs.append(MI(f"N{i}", c))
            elif y < 0.30:
                ativs.append(MT(f"N{i}", c))
            elif y < 0.40:
                ativs.append(A(f"N{i}", 0, c))
            else:
                ativs.append(A(f"N{i}", rng.randint(1, 6), c))
    rels, vistos = [], set()
    for j in range(1, n):
        for i in rng.sample(range(j), min(j, rng.randint(1, 2))):
            t = rng.choice(["FS", "SS", "FF", "SF"])
            if (i, j, t) not in vistos:
                vistos.add((i, j, t))
                rels.append(R(f"N{i}", f"N{j}", t, rng.randint(-3, 4)))
    return ativs, rels


@pytest.mark.parametrize("com_progresso", [False, True])
def test_propriedades_que_resistem_com_marcos_e_instantes(com_progresso):
    """1500 redes aleatórias (semente fixa) com marcos de início/término, tarefas de duração 0,
    calendários c5/c6/cF, FS/SS/FF/SF lag -3..4, com e sem progresso. O que TEM de valer e vale:
    (a) término exibido >= início exibido; (b) não iniciada nunca é exibida antes da véspera do piso;
    (c) folga livre entre 0 e max(folga total, 0);
    (d) relações de sucessora não iniciada satisfeitas (FS/SS: ES >= alvo em tempo de trabalho;
        FF/SF com trabalho: último dia >= último dia útil da predecessora antes do alvo).
    Folga >= 0 e folga exata NÃO entram aqui: falham — ver os xfail abaixo."""
    ds = DS if com_progresso else None
    piso = date.fromordinal(max(SEG, ds or 0) - 1).isoformat()
    rng = random.Random(5)
    for _ in range(1500):
        ativs, rels = _rede(rng, com_progresso)
        res = calcular(ativs, rels, CALS, SEG, data_status=ds)
        ra, by = res.atividades, {a.id: a for a in ativs}
        ctx = (ativs, rels)
        for a in ativs:
            d = ra[a.id].como_dict(CALS[a.calendario], a)
            assert d["termino"] >= d["inicio"], (a.id, ctx)
            if a.status == "nao_iniciada":
                assert d["inicio"] >= piso, (a.id, ctx)
            if a.status != "concluida":
                assert 0 <= d["folga_livre"] <= max(d["folga_total"], 0), (a.id, ctx)
        for rel in rels:
            sa = by[rel.sucessora]
            if sa.status != "nao_iniciada":
                continue
            p, s = ra[rel.predecessora], ra[rel.sucessora]
            pc, sc = CALS[by[rel.predecessora].calendario], CALS[sa.calendario]
            alvo = pc.somar(p.ef if rel.tipo in ("FS", "FF") else p.es, rel.lag)
            if sa.duracao > 0 and rel.tipo in ("FF", "SF"):
                assert s.ef - 1 >= pc.ultimo_dia_util(alvo), (rel, ctx)
            else:
                valor = s.es if rel.tipo in ("FS", "SS") else s.ef
                assert valor >= alvo or (pc.dias_uteis_entre(valor, alvo) == 0
                                         and sc.dias_uteis_entre(valor, alvo) == 0), (rel, ctx)


def test_cadeia_de_marcos_de_termino_apos_sexta_nao_gera_folga_negativa():
    """A(5) seg5–sex9 -> M1 -> M2 (marcos de término, FS+0). Caminho único, sem restrição:
    os três são críticos com folga total 0, e ambos os marcos são exibidos em sex 09/01.
    O motor devolve folga -1 para A e para M1."""
    res, r = rodar([A("A", 5, "c5"), MT("M1"), MT("M2")], [R("A", "M1"), R("M1", "M2")])
    assert (r["M1"]["termino"], r["M2"]["termino"], termino_iso(res)) == ("2026-01-09", "2026-01-09", "2026-01-09")
    assert [r[k]["folga_total"] for k in ("A", "M1", "M2")] == [0, 0, 0]


@pytest.mark.parametrize("instante", [MI("M"), A("M", 0, "c5"), MT("M")])
def test_consumir_a_folga_de_um_instante_solto_nao_muda_o_termino_exibido(instante):
    """A(2) seg5–ter6: término do projeto 06/01. Instante M solto (marco de início, tarefa de duração 0
    ou marco de término) pode ocorrer em 05/01 ou 06/01 sem alterar o término: folga total = 1.
    O motor informa 2; atrasando M 2 dias úteis (SNET qua 07/01) o término exibido vai para 07/01."""
    res, r = rodar([A("A", 2, "c5"), instante], [])
    ft = r["M"]["folga_total"]
    atrasado = A("M", 0, "c5", tipo=instante.tipo, restricao_inicio=SEG + ft)
    res2, _ = rodar([A("A", 2, "c5"), atrasado], [])
    assert termino_iso(res) == "2026-01-06"
    assert termino_iso(res2) == "2026-01-06"
    assert ft == 1


def test_marco_nao_e_exibido_antes_de_predecessora_de_duracao_zero():
    """A(4) seg5–qui8 -> Z (tarefa de duração 0) -> M (marco de término); também A -> M.
    Z é exibida em sex 09/01. M sucede Z (FS+0): não pode ser exibido antes de 09/01. O motor exibe 08/01."""
    _, r = rodar([A("A", 4, "c5"), A("Z", 0, "c5"), MT("M")], [R("A", "Z"), R("A", "M"), R("Z", "M")])
    assert r["Z"]["termino"] == "2026-01-09"
    assert r["M"]["termino"] >= r["Z"]["termino"]


def test_folga_com_sf_para_marco_de_inicio_e_feriado_na_predecessora():
    """N0(1, cF) seg5 --SF+0--> M (marco de início, c5) --SS-2--> N2(5, c6) seg5..sex9 = término.
    M pode ir até qua 07/01 (07/01 − 2 úteis = seg5, N2 não se move). N0 precisa COMEÇAR até 07/01;
    em cF, 07 e 08/01 são feriados: último início possível = ter 06/01. Folga total de N0 = 1.
    O motor devolve 2; começando N0 em sex 09/01 (2 dias úteis de cF depois), M vai a 09/01, N2 a 07/01
    e o término do projeto anda."""
    rels = [R("N0", "M", "SF", 0), R("M", "N2", "SS", -2)]
    res, r = rodar([A("N0", 1, "cF"), MI("M"), A("N2", 5, "c6")], rels)
    ft = r["N0"]["folga_total"]
    res2, _ = rodar([A("N0", 1, "cF", restricao_inicio=CALS["cF"].proximo_util(CALS["cF"].somar(SEG, ft))),
                     MI("M"), A("N2", 5, "c6")], rels)
    assert termino_iso(res) == "2026-01-09"
    assert res2.termino_projeto == res.termino_projeto, "consumir a folga total informada atrasou a obra"
    assert ft == 1


# =============================================================================
# 2. API
# =============================================================================
@pytest.fixture(scope="module")
def projeto():
    return Projeto.carregar()


@pytest.fixture()
def cliente(projeto):
    return TestClient(criar_app(projeto), raise_server_exceptions=False)


@pytest.fixture(scope="module")
def ids(projeto):
    ats = projeto.dados["atividades"]

    def primeiro(f):
        return next(a["id"] for a in ats if f(a))

    return {
        "concluida": primeiro(lambda a: a["status"] == "concluida" and a.get("quantidade_total")),
        "marco": primeiro(lambda a: a.get("tipo", "tarefa") != "tarefa"),
        "fixa": primeiro(lambda a: a.get("tipo", "tarefa") == "tarefa" and not a.get("quantidade_total")),
        "aberta": primeiro(lambda a: a["status"] == "nao_iniciada" and a.get("quantidade_total")),
        "andamento": primeiro(lambda a: a["status"] == "em_andamento" and a.get("quantidade_total")),
    }


def test_api_recusa_ajuste_sem_alvo_ajustavel_e_nao_altera_o_estado(cliente, ids):
    """422 para ajuste em concluída, marco, duração fixa, lista mista (um válido + um em concluída),
    serviço inexistente, lote inexistente e lote sem serviço. Depois de cada recusa a simulação
    continua vazia (simulacao_ativa False)."""
    corpos = [
        [{"atividade_id": ids["concluida"], "produtividade": 1}],
        [{"atividade_id": ids["marco"], "equipes": 2}],
        [{"atividade_id": ids["fixa"], "equipes": 2}],
        [{"atividade_id": ids["aberta"], "produtividade": 1}, {"atividade_id": ids["concluida"], "produtividade": 1}],
        [{"servico_id": "NAO-EXISTE", "produtividade": 1}],
        [{"servico_id": "TER", "lote_id": "L9", "produtividade": 1}],
        [{"lote_id": "L1", "produtividade": 1}],
    ]
    for corpo in corpos:
        assert cliente.post("/api/simulacao", json={"ajustes": corpo}).status_code == 422, corpo
        assert cliente.get("/api/painel").json()["simulacao_ativa"] is False


def test_api_comparacao_entre_qualquer_par_de_cenarios(cliente):
    """Os 16 pares (ref, alvo) respondem 200 com explicação não vazia; par igual tem delta 0;
    cenário desconhecido responde 404."""
    for ref, alvo in itertools.product(CENARIOS, CENARIOS):
        r = cliente.get("/api/comparacao", params={"ref": ref, "alvo": alvo})
        assert r.status_code == 200, (ref, alvo, r.text[:200])
        assert r.json()["explicacao"]
        if ref == alvo:
            assert r.json()["delta_dias_corridos"] == 0 and not r.json()["duracoes_alteradas"]
    assert cliente.get("/api/comparacao", params={"ref": "xyz"}).status_code == 404


def test_api_simulacao_e_coerente_entre_rotas_e_o_cache_e_invalidado(cliente, ids):
    """POST (produtividade/4 numa atividade aberta) -> a duração dela muda; painel, cenário simulado e
    comparação devolvem o MESMO término. Trocar a simulação por outra (equipes em outra atividade) desfaz
    a primeira. DELETE volta ao independente. O cenário independente em cache não é alterado."""
    ind = cliente.get("/api/cenarios/independente").json()
    prod = ind["atividades"][ids["aberta"]]["memoria"]["produtividade"]
    r = cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": ids["aberta"], "produtividade": prod / 4}]})
    assert r.status_code == 200
    sim, painel = cliente.get("/api/cenarios/simulado").json(), cliente.get("/api/painel").json()
    assert sim["atividades"][ids["aberta"]]["duracao"] > ind["atividades"][ids["aberta"]]["duracao"]
    assert r.json()["comparacao"]["termino_alvo"] == sim["termino"] == painel["terminos"]["simulado"]
    assert painel["simulacao_ativa"] is True
    e4 = cliente.get("/api/estado4d", params={"data": sim["termino"], "cenario": "simulado"})
    assert e4.status_code == 200

    cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": ids["andamento"], "equipes": 5}]})
    sim2 = cliente.get("/api/cenarios/simulado").json()
    assert sim2["atividades"][ids["aberta"]]["duracao"] == ind["atividades"][ids["aberta"]]["duracao"]
    assert sim2["atividades"][ids["andamento"]]["duracao"] < ind["atividades"][ids["andamento"]]["duracao"]
    assert cliente.get("/api/painel").json()["terminos"]["simulado"] == sim2["termino"]

    d = cliente.delete("/api/simulacao").json()
    painel = cliente.get("/api/painel").json()
    assert d["ajustes"] == [] and d["comparacao"]["duracoes_alteradas"] == []
    assert painel["simulacao_ativa"] is False
    assert painel["terminos"]["simulado"] == painel["terminos"]["independente"] == ind["termino"]
    assert cliente.get("/api/cenarios/independente").json() == ind


def test_api_parametros_extremos(cliente, projeto):
    """Data no ano 1: toda fração 0. Data no ano 9999: toda fração 1 e estado 'concluido'.
    Datas inválidas, iterações fora de 10..2000 e lote em minúsculas: 422/404, nunca 500."""
    n = len(projeto.dados["atividades"])
    a = cliente.get("/api/estado4d", params={"data": "0001-01-01"}).json()["atividades"]
    z = cliente.get("/api/estado4d", params={"data": "9999-12-31"}).json()["atividades"]
    assert len(a) == len(z) == n
    assert all(v["fracao"] == 0 for v in a.values())
    assert all(v["fracao"] == 1 and v["estado"] == "concluido" for v in z.values())
    for data in ("2026-02-30", "hoje", "2026-11-09T00:00", " "):
        assert cliente.get("/api/estado4d", params={"data": data}).status_code == 422, data
    assert cliente.get("/api/estado4d").status_code == 422
    assert cliente.get("/api/estado4d", params={"data": "2026-11-09", "cenario": "x"}).status_code == 404
    for it in (9, 2001, "x"):
        assert cliente.get("/api/previsao-probabilistica", params={"iteracoes": it}).status_code == 422
    assert cliente.get("/api/painel", params={"lote": "l1"}).status_code == 404


def test_api_leituras_concorrentes_durante_troca_de_simulacao(projeto, ids):
    """6 threads leem /api/painel enquanto a simulação é ligada e desligada 3 vezes. Toda resposta é 200
    e o término simulado lido é sempre um dos dois valores possíveis (com ou sem a simulação)."""
    app = criar_app(projeto)
    principal = TestClient(app, raise_server_exceptions=False)
    ind = principal.get("/api/cenarios/independente").json()
    corpo = {"ajustes": [{"atividade_id": ids["andamento"], "equipes": 5}]}
    com = principal.post("/api/simulacao", json=corpo).json()["comparacao"]["termino_alvo"]
    principal.delete("/api/simulacao")
    vistos, erros = set(), []

    def leitor():
        c = TestClient(app, raise_server_exceptions=False)
        for _ in range(3):
            r = c.get("/api/painel")
            if r.status_code != 200:
                erros.append(r.status_code)
            else:
                vistos.add(r.json()["terminos"]["simulado"])

    ts = [threading.Thread(target=leitor) for _ in range(6)]
    for t in ts:
        t.start()
    for _ in range(3):
        principal.post("/api/simulacao", json=corpo)
        principal.delete("/api/simulacao")
    for t in ts:
        t.join()
    assert not erros
    assert vistos <= {ind["termino"], com}


@pytest.mark.parametrize("ajuste", [{"produtividade": 0.0001}, {"produtividade": 1e308, "equipes": 20}])
def test_api_ajuste_extremo_e_recusado_sem_envenenar_o_estado(cliente, ids, ajuste):
    """Produtividade 0,0001 un/dia (duração de milhões de dias) ou 1e308 × 20 equipes (infinito):
    esperado 422 com mensagem, e o painel continua respondendo 200 sem simulação ativa."""
    r = cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": ids["aberta"], **ajuste}]})
    painel = cliente.get("/api/painel")
    assert painel.status_code == 200 and painel.json()["simulacao_ativa"] is False
    assert r.status_code == 422


def test_api_estado4d_com_data_vazia_e_422(cliente):
    """Data vazia é data inválida: 422, como para 'hoje' ou '2026-02-30'."""
    assert cliente.get("/api/estado4d", params={"data": ""}).status_code == 422
