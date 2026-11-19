"""Cenários climáticos: calendários alternativos para o remanescente, com valores calculados à mão.

Rede pequena: data de status = início = qua 31/12/2025. Calendário da obra CO (todos os dias da semana)
com feriados 21 a 31/01/2026. Calendário sensível CT ("terra + chuva"): os mesmos feriados + chuva nos
dias PARES de 02 a 20/01/2026 (10 dias) + chuva PASSADA em 30/12/2025. A: 15 dias em CT. B: 3 dias em CO.

Base: A trabalha 31/12, os ímpares 01..19/01 (10) e 01..04/02 (feriados 21–31/01) => término 04/02/2026.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infra4d import rotas_clima
from infra4d.cenarios import DATASET_PADRAO, Projeto, executar
from infra4d.clima import calendario_alternativo, calendarios_sensiveis, cenarios_climaticos

RODOVIA = DATASET_PADRAO.parent / "rodovia_ficticia.json"
TODOS = [0, 1, 2, 3, 4, 5, 6]
FERIADOS = [f"2026-01-{d:02d}" for d in range(21, 32)]
CHUVA = [f"2026-01-{d:02d}" for d in range(2, 21, 2)]


def _proj():
    def t(aid, d, cal):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": "L1", "servico_id": aid, "duracao_fixa": d,
                "calendario": cal, "status": "nao_iniciada"}
    return Projeto({
        "meta": {"inicio_projeto": "2025-12-31", "data_status": "2025-12-31", "calendario_obra": "CO"},
        "lotes": [{"id": "L1"}], "servicos": [], "medicoes": [], "relacoes": [],
        "calendarios": [{"id": "CO", "nome": "obra", "dias_semana": TODOS, "nao_uteis": FERIADOS},
                        {"id": "CT", "nome": "terra", "sensivel_chuva": True, "dias_semana": TODOS,
                         "nao_uteis": FERIADOS + CHUVA + ["2025-12-30"]},
                        {"id": "CX", "nome": "via", "dias_semana": TODOS, "nao_uteis": FERIADOS}],
        "atividades": [t("A", 15, "CT"), t("B", 3, "CO")],
    })


def _termino_com(P, cid, nao_uteis):
    from infra4d.clima import _projeto_com
    return executar(_projeto_com(P, {cid: nao_uteis}), "independente")["termino"]


def test_so_calendarios_sensiveis_pela_marca_booleana():
    P = _proj()
    assert calendarios_sensiveis(P) == ["CT"]
    P.dados["calendarios"][2]["nome"] = "via (para com chuva)"  # o nome NÃO conta (r13)
    assert calendarios_sensiveis(P) == ["CT"]
    P.dados["calendarios"][2]["sensivel_chuva"] = True
    assert calendarios_sensiveis(P) == ["CT", "CX"]
    P.dados["calendarios"][1]["sensivel_chuva"] = False
    assert calendarios_sensiveis(P) == ["CX"]
    P.dados["calendarios"][1]["sensivel_chuva"] = "true"  # texto: recusado, não ignorado
    with pytest.raises(ValueError, match="booleano"):
        calendarios_sensiveis(P)


def test_base_e_seco_total():
    P = _proj()
    assert executar(P, "independente")["termino"] == "2026-02-04"
    # seco −100 %: devolve os 10 dias de chuva de janeiro => 31/12 + 01..14/01 = 15 dias => 14/01
    nu, rsm = calendario_alternativo(P, "CT", "seco", intensidade=1.0)
    assert set(nu) == set(FERIADOS) | {"2025-12-30"}
    # dezembro (só 30/12, 1 dia contra 10 de janeiro: não passa de 10 %) não é mês chuvoso
    assert rsm["dias_devolvidos"] == 10 and rsm["meses_chuvosos"] == [1]
    assert _termino_com(P, "CT", nu) == "2026-01-14"


def test_seco_parcial_termino_exato():
    # −50 %: devolve 5 dos 10 dias de chuva. A precisa de 31/12 + 14 úteis em janeiro (antes dos feriados de
    # 21/01). O término é o 14º dia de 01..20/01 que não é chuva restante — conta direta sobre o sorteio.
    P = _proj()
    nu, rsm = calendario_alternativo(P, "CT", "seco", intensidade=0.5)
    assert rsm["dias_devolvidos"] == 5
    restantes = {int(x[-2:]) for x in nu if x.startswith("2026-01-") and x in CHUVA}
    assert len(restantes) == 5
    dia_14 = [d for d in range(1, 21) if d not in restantes][13]
    assert _termino_com(P, "CT", nu) == f"2026-01-{dia_14:02d}"


def test_chuvoso_total_perde_janeiro_inteiro():
    # +100 %: 10 dias novos entre os úteis de janeiro posteriores ao status — exatamente os 10 ímpares
    # 01..19 (o resto é chuva ou feriado). Janeiro inteiro perdido: 31/12 + 01..14/02 => término 14/02.
    P = _proj()
    nu, rsm = calendario_alternativo(P, "CT", "chuvoso", intensidade=1.0)
    assert rsm["dias_perdidos_acrescentados"] == 10
    assert set(nu) - (set(FERIADOS) | set(CHUVA) | {"2025-12-30"}) == {f"2026-01-{d:02d}" for d in range(1, 20, 2)}
    assert _termino_com(P, "CT", nu) == "2026-02-14"


@pytest.mark.parametrize("semanas,termino", [(1, "2026-01-20"), (-1, "2026-02-01"), (0, "2026-02-04")])
def test_estacao_deslocada(semanas, termino):
    # +1 semana: chuva nos pares 02..20 vai para 09..27 (ímpares); 30/12 fica (passado; dezembro não é mês
    #   chuvoso). Úteis: 31/12, 01–08 (8), 10, 12, …, 20 (6) = 15 => término 20/01.
    # −1 semana: pares 08..20 vão para 01, 03, …, 13 (02, 04, 06 caem antes do status: descartados; a chuva
    #   de 30/12 fica, âncora). Úteis: 31/12, 02, 04, …, 12 (6), 14..20 (7) = 14 => 15º em 01/02.
    P = _proj()
    nu, _ = calendario_alternativo(P, "CT", "deslocado", deslocamento_semanas=semanas)
    assert "2025-12-30" in nu  # passado intocado
    assert _termino_com(P, "CT", nu) == termino


def test_ancora_passado_intocado_e_monotonia_no_dataset():
    for arquivo in (DATASET_PADRAO, RODOVIA):
        P = Projeto.carregar(arquivo)
        ds = date.fromordinal(P.data_status)
        for cid in calendarios_sensiveis(P):
            c = next(x for x in P.dados["calendarios"] if x["id"] == cid)
            orig = set(c["nao_uteis"])
            passado = {x for x in orig if date.fromisoformat(x) <= ds}
            for tipo, kw in (("chuvoso", {"intensidade": 0.5}), ("seco", {"intensidade": 0.5}),
                             ("deslocado", {"deslocamento_semanas": 3})):
                nu, _ = calendario_alternativo(P, cid, tipo, **kw)
                nu = set(nu)
                assert {x for x in nu if date.fromisoformat(x) <= ds} == passado, (arquivo.name, cid, tipo)
                if tipo == "chuvoso":
                    assert nu >= orig  # só acrescenta
                if tipo == "seco":
                    assert nu <= orig  # só remove
                    obra = next(x for x in P.dados["calendarios"] if x["id"] == P.dados["meta"]["calendario_obra"])
                    assert set(obra["nao_uteis"]) & orig <= nu  # feriado nunca é removido


@pytest.mark.parametrize("arquivo", [DATASET_PADRAO, RODOVIA])
def test_obras_chuvoso_nunca_antecipa_seco_nunca_atrasa(arquivo):
    P = Projeto.carregar(arquivo)
    r = cenarios_climaticos(P, intensidade=0.3, deslocamento_semanas=2)
    sens = r["calendarios_sensiveis"]
    assert sens and P.dados["meta"]["calendario_obra"] not in sens
    c = {x["tipo"]: x for x in r["cenarios"]}
    assert c["chuvoso"]["delta_dias_corridos"] >= 0
    assert c["seco"]["delta_dias_corridos"] <= 0
    assert c["chuvoso"]["termino"] >= r["termino_independente"] >= c["seco"]["termino"]
    for x in r["cenarios"]:
        assert x["explicacao"] and x["termino"] in x["explicacao"]
        assert set(x["criticas_em_calendario_sensivel"]) <= set(P.atividades)
    # o dataset não foi alterado
    assert executar(P, "independente")["termino"] == r["termino_independente"]
    # determinístico por semente
    assert cenarios_climaticos(P, intensidade=0.3, deslocamento_semanas=2) == r


def test_parametros_invalidos():
    P = _proj()
    with pytest.raises(ValueError):
        cenarios_climaticos(P, intensidade=1.5)
    with pytest.raises(ValueError):
        cenarios_climaticos(P, deslocamento_semanas=40)
    with pytest.raises(ValueError):
        calendario_alternativo(P, "CT", "granizo")


def test_rota_clima():
    P = _proj()

    class Est:
        projeto = P

    def obter_estado(obra):
        if obra not in (None, "x"):
            from fastapi import HTTPException
            raise HTTPException(404, "obra desconhecida")
        return Est

    vazio = FastAPI()
    vazio.include_router(rotas_clima.router)
    assert TestClient(vazio).get("/api/clima").status_code == 503
    app = FastAPI()
    rotas_clima.ligar(app, obter_estado)
    c = TestClient(app)
    j = c.get("/api/clima", params={"obra": "x", "intensidade": 1.0, "deslocamento_semanas": 1}).json()
    t = {x["tipo"]: x["termino"] for x in j["cenarios"]}
    assert t == {"chuvoso": "2026-02-14", "seco": "2026-01-14", "deslocado": "2026-01-20"}
    assert j["termino_independente"] == "2026-02-04"
    assert c.get("/api/clima", params={"intensidade": 2}).status_code == 422
    assert c.get("/api/clima", params={"deslocamento_semanas": 99}).status_code == 422
    assert c.get("/api/clima", params={"obra": "marte"}).status_code == 404


def test_chuvoso_parcial_conta_exata_e_status_no_meio_do_mes():
    # +50 %: exatamente round(0,5 × 10) = 5 dias novos, todos ímpares de 01..19/01 e nunca antes do status.
    P = _proj()
    nu, rsm = calendario_alternativo(P, "CT", "chuvoso", intensidade=0.5)
    novos = set(nu) - (set(FERIADOS) | set(CHUVA) | {"2025-12-30"})
    assert rsm["dias_perdidos_acrescentados"] == 5 and len(novos) == 5
    # status em 10/01: chuva FUTURA de janeiro = 12, 14, 16, 18, 20 (5 dias) => +100 % acrescenta 5 dias,
    # sorteados só entre 11..19/01 ímpares (11, 13, 15, 17, 19 — exatamente 5): nada em 01..10.
    P.dados["meta"]["data_status"] = "2026-01-10"
    P2 = Projeto(P.dados)
    nu, rsm = calendario_alternativo(P2, "CT", "chuvoso", intensidade=1.0)
    novos = set(nu) - (set(FERIADOS) | set(CHUVA) | {"2025-12-30"})
    assert novos == {f"2026-01-{d}" for d in (11, 13, 15, 17, 19)} and rsm["dias_perdidos_acrescentados"] == 5


def test_deslocamento_conjunto_exato_e_sinal():
    P = _proj()
    base = set(FERIADOS)
    mais, _ = calendario_alternativo(P, "CT", "deslocado", deslocamento_semanas=1)
    menos, _ = calendario_alternativo(P, "CT", "deslocado", deslocamento_semanas=-1)
    # +1: pares 02..20 + 7 = ímpares 09..27; 30/12 continua (passado; dezembro não é mês chuvoso)
    assert set(mais) - base == {"2025-12-30"} | {f"2026-01-{d:02d}" for d in range(9, 20, 2)}
    # −1: pares 08..20 − 7 = ímpares 01..13 (02, 04, 06 − 7 caem antes do status); 30/12 − 7 é passado: some
    assert set(menos) - base == {"2025-12-30"} | {f"2026-01-{d:02d}" for d in range(1, 14, 2)}


def test_calendario_da_obra_nunca_e_sensivel_mesmo_com_chuva_no_nome():
    P = _proj()
    P.dados["calendarios"][0]["sensivel_chuva"] = True
    assert calendarios_sensiveis(P) == ["CT"]


def test_meio_para_cima_e_feriado_local_em_mes_seco():
    # status em 10/01: chuva futura 12, 14, 16, 18, 20 (5 dias) => 50 % = floor(2,5 + 0,5) = 3 (round() daria 2)
    P = _proj()
    P.dados["meta"]["data_status"] = "2026-01-10"
    P2 = Projeto(P.dados)
    assert calendario_alternativo(P2, "CT", "chuvoso", intensidade=0.5)[1]["dias_perdidos_acrescentados"] == 3
    assert calendario_alternativo(P2, "CT", "seco", intensidade=0.5)[1]["dias_devolvidos"] == 3
    # feriado local do CT em 15/06/2026 (junho: 1 dia contra 10 de janeiro, abaixo de 10 %) não é chuva
    P = _proj()
    P.dados["calendarios"][1]["nao_uteis"].append("2026-06-15")
    P3 = Projeto(P.dados)
    for tipo, kw in (("seco", {"intensidade": 1.0}), ("deslocado", {"deslocamento_semanas": 2})):
        assert "2026-06-15" in calendario_alternativo(P3, "CT", tipo, **kw)[0]


def test_calendario_nao_sensivel_nunca_muda():
    # CX (via, sem marca) com uma parada própria em 07/01: nenhum cenário mexe nele
    P = _proj()
    P.dados["calendarios"][2]["nao_uteis"] = FERIADOS + ["2026-01-07", "2026-01-09"]
    P2 = Projeto(P.dados)
    for tipo, kw in (("seco", {"intensidade": 1.0}), ("chuvoso", {"intensidade": 1.0}),
                     ("deslocado", {"deslocamento_semanas": 2})):
        nu, rsm = calendario_alternativo(P2, "CX", tipo, **kw)
        assert set(nu) == set(FERIADOS) | {"2026-01-07", "2026-01-09"}
        assert rsm["dias_perdidos_acrescentados"] == rsm["dias_devolvidos"] == 0
