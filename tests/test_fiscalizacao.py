"""Fiscalização: diário de obra, boletim estendido, validação, conciliação, produtividade e linha real.

Os números esperados da rede pequena foram calculados À MÃO (comentados).
Calendários: 2026-01-05 é segunda-feira; obra 6x1 (seg–sáb).
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from infra4d import fiscalizacao as F
from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO, Projeto

RODOVIA = DATASET_PADRAO.parent / "rodovia_ficticia.json"
SEG_SAB = [0, 1, 2, 3, 4, 5]


# =========================================================================== rede à mão
# O  = calendário da obra, seg–sáb, sem feriados.
# T  = "Terra com chuva": seg–sáb, não útil em qua 07/01 (chuva).  => dias de chuva = {07/01}
# A  = terraplenagem, cal T, km 10 -> 12, 100 un, 2 equipes, EM ANDAMENTO.
#      boletim 05/01: 10 equipes·dia (5 dias: 05,06,08,09,10), 40 un  => 8 un/dia
#      boletim 12/01: 10 equipes·dia (5 dias: 12..16), 30 un           => 6 un/dia
#      data de status sáb 17/01.  executado 70 => km 10 + 2 × 0,70 = 11,4
# V  = via, cal O (não para com chuva), km 12 -> 10 (DECRESCENTE), 60 un, 1 equipe, CONCLUÍDA.
#      boletim 05/01: 6 dias (05..10), 36 un => 6/dia;  boletim 12/01: 4 dias (12..15), 24 un => 6/dia
def _dados(aviso="DADOS INTEIRAMENTE FICTÍCIOS — teste", ficticio=True):
    return {
        "meta": {"aviso": aviso, "ficticio": ficticio, "semente": 99, "inicio_projeto": "2026-01-05", "data_status": "2026-01-17",
                 "calendario_obra": "O"},
        "lotes": [{"id": "L1"}, {"id": "L2"}],
        "segmentos": [{"id": "S1", "lote_id": "L1", "km_ini": 10, "km_fim": 12}],
        "calendarios": [{"id": "O", "nome": "Obra 6x1", "dias_semana": SEG_SAB, "nao_uteis": []},
                        {"id": "T", "nome": "Terra com chuva", "dias_semana": SEG_SAB, "nao_uteis": ["2026-01-07"]}],
        "servicos": [],
        "atividades": [
            {"id": "A", "nome": "A", "tipo": "tarefa", "lote_id": "L1", "segmento_id": "S1", "servico_id": "TER",
             "km_ini": 10.0, "km_fim": 12.0, "unidade": "m³", "quantidade_total": 100.0,
             "produtividade_planejada": 4.0, "equipes": 2, "calendario": "T", "status": "em_andamento",
             "inicio_real": "2026-01-05", "quantidade_executada": 70.0},
            {"id": "V", "nome": "V", "tipo": "tarefa", "lote_id": "L1", "segmento_id": "S1", "servico_id": "VIA",
             "km_ini": 12.0, "km_fim": 10.0, "unidade": "m", "quantidade_total": 60.0,
             "produtividade_planejada": 6.0, "equipes": 1, "calendario": "O", "status": "concluida",
             "inicio_real": "2026-01-05", "termino_real": "2026-01-15", "quantidade_executada": 60.0},
            {"id": "M", "nome": "marco", "tipo": "marco_fim", "lote_id": "L1", "calendario": "O"},
        ],
        "relacoes": [],
        "medicoes": [
            {"atividade_id": "A", "semana_inicio": "2026-01-05", "quantidade": 40.0, "equipes_dias": 10, "origem": "SINT"},
            {"atividade_id": "A", "semana_inicio": "2026-01-12", "quantidade": 30.0, "equipes_dias": 10, "origem": "SINT"},
            {"atividade_id": "V", "semana_inicio": "2026-01-05", "quantidade": 36.0, "equipes_dias": 6, "origem": "SINT"},
            {"atividade_id": "V", "semana_inicio": "2026-01-12", "quantidade": 24.0, "equipes_dias": 4, "origem": "SINT"},
        ],
    }


@pytest.fixture()
def P():
    return Projeto(_dados())


@pytest.fixture()
def D(P):
    return F.gerar_diarios_sinteticos(P)


def _de(D, aid):
    return {r["data"]: r for r in D if r["atividade_id"] == aid}


def _ok(**extra):
    r = {"tipo": "diario", "data": "2026-01-09", "atividade_id": "A", "lote_id": "L1", "segmento_id": "S1",
         "km_ini_exec": 10.5, "km_fim_exec": 10.7, "quantidade": 10.0, "equipes_dias": 2, "horas_chuva": 0,
         "ocorrencias": [], "fotos": [{"ref": "campo/foto1.jpg", "sha256": "a" * 64, "lat": -15.8, "lon": -47.9}],
         "estado": "lancado", "ref_memoria_calculo": None, "origem": "teste manual"}
    r.update(extra)
    return r


def _regras(P, reg, anterior=None):
    return {e["regra"] for e in F.validar(P, reg, estado_anterior=anterior)["erros"]}


# =========================================================================== gerador (à mão)
def test_dias_de_chuva_vem_do_calendario_de_chuva(P):
    assert F.dias_de_chuva(P) == {F.ordinal("2026-01-07")}


def test_diario_da_frente_que_para_com_chuva(D):
    a = _de(D, "A")
    # 05..10 (6 registros: 5 trabalhados + 07 paralisado) e 12..16 (5): 11 registros
    assert sorted(a) == ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-10",
                         "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15", "2026-01-16"]
    assert [a[d]["quantidade"] for d in ("2026-01-05", "2026-01-12")] == [8.0, 6.0]
    par = a["2026-01-07"]
    assert par["quantidade"] == 0 and par["equipes_dias"] == 0 and 1 <= par["horas_chuva"] <= 10
    assert "Paralisação por chuva" in par["ocorrencias"][0]
    assert par["km_ini_exec"] == par["km_fim_exec"] == pytest.approx(10.32)  # 16 un após 2 dias
    assert a["2026-01-05"]["km_ini_exec"] == 10.0 and a["2026-01-05"]["km_fim_exec"] == pytest.approx(10.16)
    assert a["2026-01-16"]["km_fim_exec"] == pytest.approx(11.4)
    assert all(a[d]["horas_chuva"] == 0 for d in a if d != "2026-01-07")


def test_frente_que_nao_para_com_chuva_registra_a_chuva_e_produz(D):
    v = _de(D, "V")
    assert sorted(v) == ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-10",
                         "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15"]  # concluída: nada depois de 15
    assert v["2026-01-07"]["quantidade"] == 6.0 and v["2026-01-07"]["horas_chuva"] > 0
    assert "não paralisa" in v["2026-01-07"]["ocorrencias"][0]
    # mesma chuva no mesmo dia para as duas frentes (atributo do local, não da frente)
    assert v["2026-01-07"]["horas_chuva"] == _de(D, "A")["2026-01-07"]["horas_chuva"]
    # decrescente: 12 -> 10; após 1 dia (6 de 60) = 11,8; termina exatamente em 10
    assert v["2026-01-05"]["km_fim_exec"] == pytest.approx(11.8)
    assert v["2026-01-15"]["km_fim_exec"] == pytest.approx(10.0)


def test_gerador_deterministico_e_nao_altera_os_dados(P):
    antes = json.dumps(P.dados, sort_keys=True)
    assert F.gerar_diarios_sinteticos(P) == F.gerar_diarios_sinteticos(Projeto(_dados()))
    assert json.dumps(P.dados, sort_keys=True) == antes


def test_tudo_marcado_sintetico_e_sem_foto_inventada(P, D):
    assert all(r["sintetico"] is True and "SINTÉTICA" in r["origem"] and r["fotos"] == [] for r in D)
    B = F.boletins_estendidos(P, D)
    assert all(b["sintetico"] is True and "SINTÉTICA" in b["origem"] for b in B)


@pytest.mark.parametrize("aviso, marca", [
    ("Obra BR-000, contrato 123", False),
    ("DADOS INTEIRAMENTE FICTÍCIOS", None),      # texto diz fictício, mas falta a marca booleana
    ("DADOS INTEIRAMENTE FICTÍCIOS", "true"),    # texto, não booleano
    ("DADOS REAIS — este arquivo NÃO é fictício", False),
])
def test_gerador_recusa_obra_sem_marca_booleana(aviso, marca):
    real = Projeto(_dados(aviso=aviso, ficticio=marca))
    assert F.obra_ficticia(real) is False
    with pytest.raises(F.ErroFiscalizacao, match="meta.ficticio"):
        F.gerar_diarios_sinteticos(real)
    assert "FICTÍCIA" not in " ".join(F.validar(real, _ok())["avisos"])


def test_boletim_estendido_estados(P, D):
    B = {(b["atividade_id"], b["periodo_ini"]): b for b in F.boletins_estendidos(P, D)}
    # A em andamento: último boletim só conferido (sem memória); anterior aprovado com memória
    assert B[("A", "2026-01-12")]["estado"] == "conferido_fiscal" and B[("A", "2026-01-12")]["ref_memoria_calculo"] is None
    assert B[("A", "2026-01-05")]["estado"] == "aprovado" and B[("A", "2026-01-05")]["ref_memoria_calculo"]
    assert B[("A", "2026-01-05")]["quantidade"] == 40.0 and B[("A", "2026-01-05")]["dias_chuva"] == 1
    assert B[("V", "2026-01-12")]["estado"] == "aprovado"  # V concluída
    assert all(F.validar(P, b)["valido"] for b in B.values())


# =========================================================================== validação
def test_registro_correto_passa_com_aviso_de_obra_ficticia(P):
    r = F.validar(P, _ok())
    assert r["valido"] and r["erros"] == []
    assert any("FICTÍCIA" in a for a in r["avisos"])


@pytest.mark.parametrize("extra, regra", [
    ({"estado": "aprovado"}, "aprovado_exige_memoria"),
    ({"estado": "aprovado", "ref_memoria_calculo": "  "}, "aprovado_exige_memoria"),
    ({"km_fim_exec": 12.5}, "km_no_trecho"),
    ({"km_ini_exec": 9.9}, "km_no_trecho"),
    ({"km_ini_exec": 10.7, "km_fim_exec": 10.5}, "km_sentido"),
    ({"km_fim_exec": None}, "km"),
    ({"quantidade": 0, "equipes_dias": 0}, "km_sem_quantidade"),
    ({"quantidade": -1}, "nao_negativo"),
    ({"quantidade": "dez"}, "numero"),
    ({"equipes_dias": 0}, "producao_sem_equipe"),
    ({"horas_chuva": 24.5}, "chuva"),
    ({"horas_chuva": -1}, "chuva"),
    ({"data": "2026-01-18"}, "data_status"),
    ({"data": "18/01/2026"}, "data"),
    ({"data": "20260109"}, "data"),
    ({"data": "2026-W02-5"}, "data"),
    ({"quantidade": 10 ** 400}, "numero"),
    ({"km_fim_exec": 10 ** 400}, "km"),
    ({"horas_chuva": 10 ** 400}, "chuva"),
    ({"fotos": [{"ref": "x", "lat": 10 ** 400}]}, "foto_coord"),
    ({"fotos": [{"ref": "x"}] * (F.MAX_FOTOS + 1)}, "foto_limite"),
    ({"dias_chuva": 2}, "chuva"),
    ({"atividade_id": "X"}, "frente"),
    ({"atividade_id": "M"}, "frente"),
    ({"lote_id": "L2"}, "frente"),
    ({"estado": "pago"}, "estado"),
    ({"fotos": [{"arquivo": "x"}]}, "foto_ref"),
    ({"fotos": [{"ref": "x", "sha256": "123"}]}, "foto_hash"),
    ({"fotos": [{"ref": "x", "lat": 91}]}, "foto_coord"),
    ({"ocorrencias": "chuva"}, "formato"),
    ({"origem": ""}, "origem"),
])
def test_cada_regra_de_validacao(P, extra, regra):
    assert regra in _regras(P, _ok(**extra))


def test_km_respeita_sentido_decrescente(P):
    base = dict(atividade_id="V", km_ini_exec=11.8, km_fim_exec=11.6, quantidade=6, equipes_dias=1)
    assert F.validar(P, _ok(**base))["valido"]
    assert "km_sentido" in _regras(P, _ok(**{**base, "km_ini_exec": 11.6, "km_fim_exec": 11.8}))


@pytest.mark.parametrize("dc, valido", [(0, True), (5, True), (6, False), (-1, False), ("x", False),
                                        (True, False), (2.5, False)])
def test_dias_chuva_do_boletim(P, dc, valido):
    b = _ok(tipo="boletim", periodo_ini="2026-01-12", periodo_fim="2026-01-16", dias_chuva=dc)  # 5 dias
    b.pop("data")
    assert F.validar(P, b)["valido"] is valido


def _avisos(P, reg, **kw):
    return [x for x in F.validar(P, reg, **kw)["avisos"] if "FICTÍCIA" not in x]


def test_avisos_de_coerencia_com_a_frente(P):
    assert _avisos(P, _ok()) == []
    d = _dados()
    d["atividades"][0]["status"] = "nao_iniciada"
    assert any("nao_iniciada" in x for x in _avisos(Projeto(d), _ok()))
    assert any("maior que o total" in x for x in _avisos(P, _ok(quantidade=1000.0)))
    # qua 07/01 é chuva no calendário T da frente A: produção ali é suspeita (domingo 11/01 também)
    assert any("dia não útil" in x for x in _avisos(P, _ok(data="2026-01-07")))
    assert any("dia não útil" in x for x in _avisos(P, _ok(data="2026-01-11")))
    assert any("sem histórico" in x for x in _avisos(P, _ok(estado="aprovado", ref_memoria_calculo="MC")))
    assert _avisos(P, _ok(estado="aprovado", ref_memoria_calculo="MC"), estado_anterior="conferido_fiscal") == []
    assert all(F.validar(P, r)["valido"] for r in (_ok(quantidade=1000.0), _ok(data="2026-01-11")))  # só aviso


def test_validacao_de_boletim_periodo(P):
    b = _ok(tipo="boletim", periodo_ini="2026-01-12", periodo_fim="2026-01-10")
    b.pop("data")
    assert "data" in _regras(P, b)
    b.update(periodo_fim="2026-01-16", horas_chuva=30)  # 5 dias: até 120 h
    assert F.validar(P, b)["valido"]
    assert "chuva" in _regras(P, {**b, "horas_chuva": 121})


@pytest.mark.parametrize("de, para, valida", [
    ("lancado", "conferido_fiscal", True),
    ("conferido_fiscal", "aprovado", True),
    ("conferido_fiscal", "lancado", True),   # devolução
    ("lancado", "aprovado", False),          # pula a conferência
    ("aprovado", "lancado", False),          # aprovado é final
    ("aprovado", "conferido_fiscal", False),
])
def test_transicoes_de_estado(P, de, para, valida):
    assert F.transicao_valida(de, para) is valida
    reg = _ok(estado=para, ref_memoria_calculo="MC-1")
    assert ("transicao" in _regras(P, reg, anterior=de)) is (not valida)


def test_estado_anterior_desconhecido(P):
    assert "estado" in _regras(P, _ok(), anterior="rascunho")


def test_registro_que_nao_e_objeto(P):
    assert F.validar(P, [1, 2])["valido"] is False


# =========================================================================== conciliação
def test_conciliacao_dos_sinteticos_fecha(P, D):
    c = F.conciliar(P, D)
    assert c["n_boletins"] == 4 and c["n_divergencias"] == 0 and c["diarios_sem_boletim"] == [] and c["ok"]


def test_conciliacao_aponta_divergencia_feita_a_mao(P, D):
    D2 = copy.deepcopy(D)
    next(r for r in D2 if r["atividade_id"] == "A" and r["data"] == "2026-01-13")["quantidade"] += 1.0
    D2 = [r for r in D2 if not (r["atividade_id"] == "V" and r["data"] >= "2026-01-12")]  # some a 2ª semana de V
    D2.append({"atividade_id": "A", "data": "2026-01-03", "quantidade": 5.0, "equipes_dias": 2})
    c = F.conciliar(P, D2)
    # 2 boletins divergentes + 1 produção fora de qualquer boletim = 3 (r6: antes contava 2)
    assert (c["n_divergencias"], c["n_divergencias_de_boletim"], c["n_producao_sem_boletim"], c["ok"]) == (3, 2, 1, False)
    div = {(d["atividade_id"], d["semana_inicio"]): d for d in c["divergencias"]}
    assert set(div) == {("A", "2026-01-12"), ("V", "2026-01-12")}
    assert div[("A", "2026-01-12")]["delta_quantidade"] == pytest.approx(1.0)
    assert div[("A", "2026-01-12")]["delta_equipes_dias"] == 0
    assert div[("V", "2026-01-12")]["sem_diario"] and div[("V", "2026-01-12")]["delta_equipes_dias"] == -4
    assert c["diarios_sem_boletim"] == [{"atividade_id": "A", "data": "2026-01-03", "quantidade": 5.0,
                                         "equipes_dias": 2}]
    assert F.conciliar(P, D2, lote="L2")["n_boletins"] == 0


# =========================================================================== produtividade
def test_produtividade_trabalhada_x_calendario(P, D):
    linhas = {x["atividade_id"]: x for x in F.produtividade_trabalhada_x_calendario(P, D)["atividades"]}
    a = linhas["A"]
    # 70 un ÷ 20 equipes·dia = 3,5; dias úteis da obra 05..16 = 6 + 5 = 11 → 70 ÷ (11 × 2) = 3,1818
    assert a["prod_por_dia_trabalhado"] == 3.5 and a["prod_por_dia_util_obra"] == pytest.approx(3.1818)
    assert (a["dias_trabalhados"], a["dias_paralisados_chuva"], a["dias_uteis_obra_no_periodo"]) == (10, 1, 11)
    assert a["perda_por_paralisacao_pct"] == 9.1
    v = linhas["V"]  # não para com chuva: as duas medidas coincidem
    assert v["prod_por_dia_trabalhado"] == v["prod_por_dia_util_obra"] == 6.0 and v["perda_por_paralisacao_pct"] == 0


# =========================================================================== linha real
def test_linha_real_a_mao(P, D):
    fr = {f["atividade_id"]: f for f in F.linha_real(P, D)["frentes"]}
    pts = [(p["data"], round(p["km"], 6)) for p in fr["A"]["pontos"]]
    # fronteiras de dia; 07 (paralisado) não gera ponto: o segmento 07 -> 09 é a linha plana no km 10,32... e
    # o dia 08 leva de 10,32 a 10,48 (ponto em 09)
    assert pts == [("2026-01-05", 10.0), ("2026-01-06", 10.16), ("2026-01-07", 10.32), ("2026-01-09", 10.48),
                   ("2026-01-10", 10.64), ("2026-01-11", 10.8), ("2026-01-13", 10.92), ("2026-01-14", 11.04),
                   ("2026-01-15", 11.16), ("2026-01-16", 11.28), ("2026-01-17", 11.4)]
    assert fr["A"]["km_atual"] == pytest.approx(11.4) and fr["A"]["sentido"] == "crescente"
    # 1,4 km em 12 dias corridos (05 -> 17)
    assert fr["A"]["ritmo_medio_km_por_dia_corrido"] == pytest.approx(1.4 / 12, abs=1e-6)
    assert fr["V"]["sentido"] == "decrescente" and fr["V"]["pontos"][0]["km"] == 12.0
    assert fr["V"]["km_atual"] == pytest.approx(10.0)
    assert F.linha_real(P, D, lote="L2")["frentes"] == []


# =========================================================================== obras fictícias reais do repo
@pytest.fixture(scope="module", params=[DATASET_PADRAO, RODOVIA], ids=["ferrovia", "rodovia"])
def obra(request):
    P = Projeto.carregar(request.param)
    return P, F.gerar_diarios_sinteticos(P)


def test_obra_diarios_fecham_no_executado_e_no_km(obra):
    P, D = obra
    assert D and F.obra_ficticia(P)
    ds = P.dados["meta"]["data_status"]
    soma, ultimo = {}, {}
    for r in sorted(D, key=lambda r: r["data"]):
        assert r["data"] < ds and r["sintetico"] and r["fotos"] == []
        soma[r["atividade_id"]] = soma.get(r["atividade_id"], 0.0) + r["quantidade"]
        ultimo[r["atividade_id"]] = r
    for aid, q in soma.items():
        a = P.atividades[aid]
        assert q == pytest.approx(a["quantidade_executada"], abs=1e-6)
        esperado = a["km_ini"] + (a["km_fim"] - a["km_ini"]) * a["quantidade_executada"] / a["quantidade_total"]
        assert ultimo[aid]["km_fim_exec"] == pytest.approx(esperado, abs=1e-5)
        if a["status"] == "concluida":
            assert ultimo[aid]["km_fim_exec"] == pytest.approx(a["km_fim"], abs=1e-6)


def test_obra_conciliacao_zero_e_tudo_valido(obra):
    P, D = obra
    c = F.conciliar(P, D)
    assert c["n_boletins"] == len(P.dados["medicoes"]) and c["n_divergencias"] == 0
    invalidos = [(r["atividade_id"], r["data"], F.validar(P, r)["erros"]) for r in D if not F.validar(P, r)["valido"]]
    assert invalidos == []
    assert all(F.validar(P, b)["valido"] for b in F.boletins_estendidos(P, D))


def test_obra_chuva_derruba_produtividade_de_calendario(obra):
    P, D = obra
    linhas = F.produtividade_trabalhada_x_calendario(P, D)["atividades"]
    com_chuva = [x for x in linhas if x["dias_paralisados_chuva"] > 0]
    assert com_chuva, "a obra fictícia tem calendário de chuva: alguma frente deve parar"
    assert all(x["prod_por_dia_util_obra"] < x["prod_por_dia_trabalhado"] for x in com_chuva)


# =========================================================================== API
@pytest.fixture(scope="module")
def cliente():
    return TestClient(criar_app(fontes={"ferrovia": Projeto.carregar(DATASET_PADRAO),
                                        "rodovia": Projeto.carregar(RODOVIA)}))


def test_api_rotas_ligadas(cliente):
    assert "rotas_fiscalizacao" in cliente.app.state.rotas_ligadas


@pytest.mark.parametrize("obra_id", ["ferrovia", "rodovia"])
def test_api_envelope_sempre_diz_que_e_sintetico(cliente, obra_id):
    for rota in ("diario", "boletins", "conciliacao", "produtividade", "linha-real"):
        r = cliente.get(f"/api/fiscalizacao/{rota}", params={"obra": obra_id})
        assert r.status_code == 200, rota
        j = r.json()
        assert j["sintetico"] is True and "FICTÍCIOS" in j["aviso"] and "SINTÉTICA" in j["origem"], rota
    assert cliente.get("/api/fiscalizacao/conciliacao", params={"obra": obra_id}).json()["n_divergencias"] == 0


def test_api_diario_filtros(cliente):
    P = cliente.app.state.obras.estado("ferrovia").projeto
    aid = next(a["id"] for a in P.dados["atividades"] if a.get("status") == "em_andamento"
               and a.get("quantidade_total"))
    j = cliente.get("/api/fiscalizacao/diario", params={"atividade_id": aid, "de": "2026-10-01",
                                                         "ate": "2026-12-31"}).json()
    assert j["total"] > 0 and all(r["atividade_id"] == aid and "2026-10-01" <= r["data"] <= "2026-12-31"
                                  for r in j["diarios"])
    assert cliente.get("/api/fiscalizacao/diario", params={"limite": 3}).json()["truncado"] is True
    assert cliente.get("/api/fiscalizacao/diario", params={"atividade_id": "NAO-EXISTE"}).status_code == 404
    assert cliente.get("/api/fiscalizacao/diario", params={"de": "ontem"}).status_code == 422
    assert cliente.get("/api/fiscalizacao/diario", params={"de": "20261001"}).status_code == 422
    assert cliente.get("/api/fiscalizacao/linha-real", params={"lote": "L9"}).status_code == 404
    assert cliente.get("/api/fiscalizacao/diario", params={"obra": "nao-existe"}).status_code == 404


def test_api_linha_real_por_lote(cliente):
    j = cliente.get("/api/fiscalizacao/linha-real", params={"obra": "rodovia", "lote": "L1"}).json()
    assert j["frentes"] and all(f["lote_id"] == "L1" and len(f["pontos"]) >= 2 for f in j["frentes"])


def test_api_validar(cliente):
    P = cliente.app.state.obras.estado("ferrovia").projeto
    a = next(a for a in P.dados["atividades"] if a.get("status") == "concluida" and a.get("quantidade_total"))
    reg = {"data": a["inicio_real"], "atividade_id": a["id"], "km_ini_exec": a["km_ini"], "km_fim_exec": a["km_ini"],
           "quantidade": 0, "equipes_dias": 0, "horas_chuva": 3, "estado": "aprovado", "origem": "teste"}
    j = cliente.post("/api/fiscalizacao/validar", json=reg).json()
    assert j["valido"] is False and {e["regra"] for e in j["erros"]} == {"aprovado_exige_memoria"}
    reg.update(ref_memoria_calculo="MC-9", estado_anterior="lancado")
    j = cliente.post("/api/fiscalizacao/validar", json=reg).json()
    assert {e["regra"] for e in j["erros"]} == {"transicao"}
    reg["estado_anterior"] = "conferido_fiscal"
    j = cliente.post("/api/fiscalizacao/validar", json=reg).json()
    assert j["valido"] is True and any("FICTÍCIA" in x for x in j["avisos"])
    assert cliente.post("/api/fiscalizacao/validar", json=[1]).json()["valido"] is False
