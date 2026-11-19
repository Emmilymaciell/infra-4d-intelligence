"""Revisão adversarial — rodada 13: clima.py (cenários climáticos) e rotas_clima.py.

Mesmo protocolo: esperado calculado à mão ou por conferência independente (conjuntos de datas refeitos
aqui); defeito confirmado fica ``xfail(strict=True, reason="DEFEITO: ...")``.
"""

import copy
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import clima as C
from infra4d.cenarios import Projeto, executar

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")


@pytest.fixture(scope="module")
def obras():
    return {x: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{x}_ficticia.json") for x in OBRAS}


def _datas(lista):
    return {date.fromisoformat(x) for x in lista}


def _cal(projeto, cid):
    return next(c for c in projeto.dados["calendarios"] if c["id"] == cid)


def _feriados(projeto):
    return _datas(_cal(projeto, projeto.dados["meta"]["calendario_obra"])["nao_uteis"])


# =============================================================================
# 1. O que resiste
# =============================================================================
def _rede(rng: random.Random) -> Projeto:
    """3–8 tarefas (3 a 25 dias) em calendários cS (sensível, 6 dias, ~25 dias de chuva nos 120 dias
    seguintes), c5 e c6 (obra, 2 feriados), relações FS/SS/FF/SF com lag −2..3. Status = início."""
    n = rng.randint(3, 8)
    ativs = [{"id": f"N{i}", "nome": f"N{i}", "tipo": "tarefa", "calendario": rng.choice(["cS", "cS", "c5", "c6"]),
              "lote_id": "L1", "duracao_fixa": rng.randint(3, 25), "status": "nao_iniciada"} for i in range(n)]
    rels, vistos = [], set()
    for j in range(1, n):
        for i in rng.sample(range(j), min(j, rng.randint(1, 2))):
            if (i, j) not in vistos:
                vistos.add((i, j))
                rels.append({"predecessora": f"N{i}", "sucessora": f"N{j}",
                             "tipo": rng.choice(["FS", "FS", "SS", "FF", "SF"]), "lag": rng.randint(-2, 3)})
    chuva = {(date(2026, 1, 5) + timedelta(days=rng.randint(1, 120))).isoformat() for _ in range(25)}
    fer = ["2026-02-16", "2026-04-03"]
    return Projeto({
        "meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "c6",
                 "aviso": "FICTÍCIO", "ficticio": True},
        "calendarios": [{"id": "c5", "nome": "c5", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []},
                        {"id": "c6", "nome": "c6", "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": fer},
                        {"id": "cS", "nome": "cS", "sensivel_chuva": True, "dias_semana": [0, 1, 2, 3, 4, 5],
                         "nao_uteis": sorted(chuva | set(fer))}],
        "atividades": ativs, "relacoes": rels, "medicoes": [], "lotes": [{"id": "L1"}], "servicos": []})


def test_chuvoso_nunca_antecipa_e_seco_nunca_atrasa_em_redes_aleatorias():
    """300 redes aleatórias com calendários mistos (semente fixa), intensidade 20 %, 50 % ou 100 %:
    o cenário chuvoso (só acrescenta dias perdidos) tem Δ término >= 0 e o seco (só devolve) tem Δ <= 0.
    (O motor admite atividade 'reversa'; nestas redes ela não inverteu o sinal em nenhum caso.)"""
    rng = random.Random(3)
    for _ in range(300):
        p = _rede(rng)
        r = C.cenarios_climaticos(p, rng.choice([0.2, 0.5, 1.0]), 0)
        deltas = {c["tipo"]: c["delta_dias_corridos"] for c in r["cenarios"]}
        assert deltas["chuvoso"] >= 0 and deltas["seco"] <= 0, (deltas, p.dados["atividades"], p.dados["relacoes"])


@pytest.mark.parametrize("obra", OBRAS)
def test_calendarios_alternativos_ancora_feriados_e_intensidade_zero(obras, obra):
    """Para cada calendário sensível das obras e cada cenário (chuvoso/seco 50 %, deslocado ±6 semanas):
    - ÂNCORA exata: o conjunto de não úteis com data <= data de status é idêntico ao original;
    - nenhum feriado da obra (nem outro não útil que não seja chuva) é removido; nenhuma data repetida;
    - chuvoso só ACRESCENTA (novo ⊇ original) e seco só REMOVE dias de chuva (novo ⊆ original, e o que saiu
      era chuva futura); as contagens do resumo batem com a diferença dos conjuntos;
    - intensidade 0 devolve exatamente o calendário original."""
    p = obras[obra]
    ds = date.fromordinal(p.data_status)
    fer = _feriados(p)
    sens = C.calendarios_sensiveis(p)
    assert sens and p.dados["meta"]["calendario_obra"] not in sens
    for cid in sens:
        c = _cal(p, cid)
        atuais, chuva = _datas(c["nao_uteis"]), C._dias_chuva(p, cid)
        assert chuva == {d for d in atuais if d not in fer and d.weekday() in set(c["dias_semana"])}
        for tipo, kw in (("chuvoso", dict(intensidade=0.5)), ("seco", dict(intensidade=0.5)),
                         ("deslocado", dict(deslocamento_semanas=6)), ("deslocado", dict(deslocamento_semanas=-6))):
            lista, resumo = C.calendario_alternativo(p, cid, tipo, **kw)
            novos = _datas(lista)
            assert len(lista) == len(novos) and lista == sorted(lista)
            assert {d for d in novos if d <= ds} == {d for d in atuais if d <= ds}, (cid, tipo)
            assert (atuais - chuva) <= novos, (cid, tipo)
            if tipo == "chuvoso":
                assert novos >= atuais and resumo["dias_perdidos_acrescentados"] == len(novos - atuais) > 0
                assert all(d > ds and d.weekday() in set(c["dias_semana"]) for d in novos - atuais)
            if tipo == "seco":
                assert novos <= atuais and (atuais - novos) <= {d for d in chuva if d > ds}
                assert resumo["dias_devolvidos"] == len(atuais - novos) > 0
        for tipo in ("chuvoso", "seco"):
            assert _datas(C.calendario_alternativo(p, cid, tipo, intensidade=0.0)[0]) == atuais


@pytest.mark.parametrize("obra", OBRAS)
def test_cenarios_nas_obras_sinal_ancora_do_resultado_e_dataset_intacto(obras, obra):
    """Intensidades 0, 10 %, 50 % e 100 % com deslocamento de 4 semanas:
    - intensidade 0: chuvoso e seco têm Δ = 0 e o mesmo término do independente;
    - chuvoso Δ >= 0, seco Δ <= 0, e o efeito não diminui quando a intensidade cresce;
    - o dataset (JSON canônico dos dados) é idêntico antes e depois, e o cenário independente recalculado
      depois dá o mesmo resultado de antes (nada ficou em cache no Projeto);
    - âncora no RESULTADO: recalculando com o calendário chuvoso 50 %, toda atividade concluída mantém
      início e término, e toda atividade em andamento mantém o início."""
    p = obras[obra]
    antes = hashlib.sha256(json.dumps(p.dados, sort_keys=True).encode()).hexdigest()
    base = executar(p, "independente")
    chuvoso, seco = [], []
    for x in (0.0, 0.1, 0.5, 1.0):
        r = C.cenarios_climaticos(p, x, 4)
        d = {c["tipo"]: c for c in r["cenarios"]}
        assert set(d) == {"chuvoso", "seco", "deslocado"} and r["termino_independente"] == base["termino"]
        chuvoso.append(d["chuvoso"]["delta_dias_corridos"])
        seco.append(d["seco"]["delta_dias_corridos"])
        if x == 0.0:
            assert d["chuvoso"]["termino"] == d["seco"]["termino"] == base["termino"]
    assert chuvoso[0] == seco[0] == 0
    assert chuvoso == sorted(chuvoso) and seco == sorted(seco, reverse=True)
    assert hashlib.sha256(json.dumps(p.dados, sort_keys=True).encode()).hexdigest() == antes
    assert executar(p, "independente") == base
    cals = {cid: C.calendario_alternativo(p, cid, "chuvoso", intensidade=0.5)[0] for cid in C.calendarios_sensiveis(p)}
    alt = executar(C._projeto_com(p, cals), "independente")
    for aid, a in base["atividades"].items():
        b = alt["atividades"][aid]
        if a["status"] == "concluida":
            assert (b["inicio"], b["termino"]) == (a["inicio"], a["termino"]), aid
        elif a["status"] == "em_andamento":
            assert b["inicio"] == a["inicio"], aid


@pytest.mark.parametrize("obra", OBRAS)
def test_deslocamento_move_o_padrao_inteiro_menos_colisoes_e_ancora(obras, obra):
    """Deslocado N semanas (−8, −1, +1, +8): os dias de chuva futuros do calendário alternativo são
    EXATAMENTE {d + 7·N : d é dia de chuva e d + 7·N > data de status} menos os que caem em não útil que
    não é chuva (feriado) — refeito aqui de forma independente. Consequência (declarar, não é erro de
    conta): o NÚMERO de dias de chuva do remanescente NÃO é preservado — muda pelo corte na data de status
    e pelas colisões com feriado."""
    p = obras[obra]
    ds = date.fromordinal(p.data_status)
    for cid in C.calendarios_sensiveis(p):
        atuais, chuva = _datas(_cal(p, cid)["nao_uteis"]), C._dias_chuva(p, cid)
        fixos = atuais - chuva
        for n in (-8, -1, 1, 8):
            novos = _datas(C.calendario_alternativo(p, cid, "deslocado", deslocamento_semanas=n)[0])
            esperado = {d + timedelta(days=7 * n) for d in chuva if d + timedelta(days=7 * n) > ds}
            assert {d for d in novos if d > ds} - fixos == esperado - fixos, (cid, n)
            assert all(d.weekday() == (d - timedelta(days=7 * n)).weekday() for d in esperado)


def test_calendario_sensivel_sem_chuva_e_marca_que_vence_o_nome():
    """Calendário marcado sensível cujos não úteis são só os feriados da obra: nenhum dia de chuva, os três
    cenários devolvem o calendário original e Δ = 0. Marca ``sensivel_chuva: false`` vence o nome
    ('dias de chuva'); marca true vale mesmo com nome neutro; o calendário da obra nunca é sensível."""
    fer = ["2026-02-16", "2026-04-03"]
    dados = {
        "meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "obra",
                 "aviso": "FICTÍCIO", "ficticio": True},
        "calendarios": [{"id": "obra", "nome": "obra com dias de chuva", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": fer},
                        {"id": "s", "nome": "neutro", "sensivel_chuva": True, "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": fer},
                        {"id": "n", "nome": "dias de chuva", "sensivel_chuva": False, "dias_semana": [0, 1, 2, 3, 4],
                         "nao_uteis": fer + ["2026-03-10"]}],
        "atividades": [{"id": "A", "nome": "A", "tipo": "tarefa", "calendario": "s", "duracao_fixa": 60,
                        "status": "nao_iniciada"}],
        "relacoes": [], "medicoes": [], "lotes": [], "servicos": []}
    p = Projeto(dados)
    assert C.calendarios_sensiveis(p) == ["s"]
    for tipo, kw in (("chuvoso", dict(intensidade=1.0)), ("seco", dict(intensidade=1.0)),
                     ("deslocado", dict(deslocamento_semanas=5))):
        lista, resumo = C.calendario_alternativo(p, "s", tipo, **kw)
        assert lista == sorted(fer) and resumo["dias_chuva_futuros_base"] == 0
    r = C.cenarios_climaticos(p, 1.0, 5)
    assert [c["delta_dias_corridos"] for c in r["cenarios"]] == [0, 0, 0]


def test_rota_de_clima_parametros_extremos_e_cache(obras):
    """GET /api/clima: intensidade −0,1, 1,1, 'nan' e texto -> 422; deslocamento ±27 e fracionário -> 422;
    obra desconhecida -> 404; extremos válidos (0 e 1; −26 e +26) -> 200; sem deslocamento vêm 2 cenários,
    com deslocamento 3; a segunda chamada igual devolve a mesma resposta."""
    from infra4d.api import criar_app
    c = TestClient(criar_app(fontes=dict(obras)), raise_server_exceptions=False)
    for ruim in ({"intensidade": -0.1}, {"intensidade": 1.1}, {"intensidade": "nan"}, {"intensidade": "x"},
                 {"deslocamento_semanas": 27}, {"deslocamento_semanas": -27}, {"deslocamento_semanas": 1.5}):
        assert c.get("/api/clima", params=ruim).status_code == 422, ruim
    assert c.get("/api/clima", params={"obra": "zz"}).status_code == 404
    a = c.get("/api/clima", params={"obra": "rodovia", "intensidade": 0, "deslocamento_semanas": -26})
    b = c.get("/api/clima", params={"obra": "rodovia", "intensidade": 1, "deslocamento_semanas": 26})
    assert a.status_code == b.status_code == 200
    assert len(a.json()["cenarios"]) == 3 and len(c.get("/api/clima").json()["cenarios"]) == 2
    assert c.get("/api/clima", params={"obra": "rodovia", "intensidade": 1, "deslocamento_semanas": 26}).json() == b.json()


# =============================================================================
# 2. Defeitos
# =============================================================================
# Regressão: defeito da rodada 13, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: 'sensível pelo nome' é busca de SUBSTRING ('chuva', 'úmid', 'umid'): um calendário "
#   "chamado 'Administrativo (escritório: não para com chuva)' é tratado como sensível, e os não úteis "
#   "próprios dele (recesso de fim de ano), por não serem feriado da obra, viram 'dias de chuva' — o "
#   "cenário seco 100 % os devolve como dias úteis. Mesmo problema da marca por texto da rodada 6")
def test_calendario_cujo_nome_nega_a_chuva_nao_e_sensivel(obras):
    """Renomeando o CAL-ADM da ferrovia para 'Administrativo (escritório: não para com chuva)' e dando a ele
    3 dias de recesso (24/12, 31/12/2026 e 04/01/2027): ele NÃO é sensível à chuva e o recesso nunca é
    mexido. (Na rodada 13 ele entrava em `calendarios_sensiveis` e o seco 100 % removia os 3 dias.)"""
    d = copy.deepcopy(obras["ferrovia"].dados)
    adm = next(c for c in d["calendarios"] if c["id"] == "CAL-ADM")
    recesso = ["2026-12-24", "2026-12-31", "2027-01-04"]
    adm["nome"] = "Administrativo (escritório: não para com chuva)"
    adm["nao_uteis"] = adm["nao_uteis"] + recesso
    p = Projeto(d)
    assert "CAL-ADM" not in C.calendarios_sensiveis(p)
    assert set(recesso) <= set(C.calendario_alternativo(p, "CAL-ADM", "seco", intensidade=1.0)[0])


# Regressão: defeito da rodada 13, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: só os feriados do calendário da OBRA são protegidos. Um não útil próprio de um "
#   "calendário sensível (feriado local, parada programada) que não esteja no calendário da obra é "
#   "classificado como chuva: o seco 100 % o devolve e o deslocado o empurra N semanas")
@pytest.mark.parametrize("tipo,kw", [("seco", dict(intensidade=1.0)), ("deslocado", dict(deslocamento_semanas=3))])
def test_nao_util_proprio_de_calendario_sensivel_nao_e_tratado_como_chuva(obras, tipo, kw):
    """CAL-TERRA da ferrovia ganha um feriado local em 15/06/2027 (mês sem chuva no dataset: a estação é
    dez–mar), que não existe no calendário da obra. Em qualquer cenário climático esse dia continua não
    útil. (Na rodada 13 ele sumia no seco 100 % e ia para 06/07/2027 no deslocado de 3 semanas.)"""
    d = copy.deepcopy(obras["ferrovia"].dados)
    terra = next(c for c in d["calendarios"] if c["id"] == "CAL-TERRA")
    assert not any(x.startswith("2027-06") for x in terra["nao_uteis"])
    terra["nao_uteis"] = sorted(terra["nao_uteis"] + ["2027-06-15"])
    lista, _ = C.calendario_alternativo(Projeto(d), "CAL-TERRA", tipo, **kw)
    assert "2027-06-15" in lista


# Regressão: defeito da rodada 13, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: a quantidade de dias por mês usa round() do Python (arredonda meio para o PAR): "
#   "com 50 % de intensidade, um mês com 1 dia de chuva ganha 0, com 3 ganha 2 e com 5 ganha 2 — a regra "
#   "declarada 'round(X × chuva do mês)' não é monótona nem simétrica em meio dia")
def test_arredondamento_da_intensidade_e_meio_para_cima():
    """Calendário sensível com 1 dia de chuva em fev/2026, 3 em mar e 5 em abr; intensidade 50 %:
    meio dia arredonda para cima -> acrescenta 1 + 2 + 3 = 6 dias no chuvoso e devolve 6 no seco.
    (Na rodada 13: 0 + 2 + 2 = 4.)"""
    chuva = ["2026-02-10", "2026-03-10", "2026-03-11", "2026-03-12",
             "2026-04-06", "2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10"]
    p = Projeto({
        "meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "obra",
                 "aviso": "FICTÍCIO", "ficticio": True},
        "calendarios": [{"id": "obra", "nome": "obra", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []},
                        {"id": "s", "nome": "s", "sensivel_chuva": True, "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": chuva}],
        "atividades": [{"id": "A", "nome": "A", "tipo": "tarefa", "calendario": "s", "duracao_fixa": 10,
                        "status": "nao_iniciada"}],
        "relacoes": [], "medicoes": [], "lotes": [], "servicos": []})
    assert C.calendario_alternativo(p, "s", "chuvoso", intensidade=0.5)[1]["dias_perdidos_acrescentados"] == 6
    assert C.calendario_alternativo(p, "s", "seco", intensidade=0.5)[1]["dias_devolvidos"] == 6
