"""5D FICTÍCIO: composições, orçamento, curva S financeira e EVM de custo.

Rede à mão (calendário seg–sex; 2026-01-05 é segunda; data de status seg 19/01):
- A  TER m³, L1: 1000 un, LB 05..09/01 (5 dias), executado 600 (boletim 05/01 -> entra em 12/01).
  custo direto 1,48 + 11,47 + 0 + 5,55 = 18,50; preço de venda 18,50 × 1,25 = 23,125.
  BAC 23.125; PV/dia 4.625 -> PV(19/01) = 23.125; EV = 600 × 23,125 = 13.875.
- B  LAS m³, L2: 200 un, LB 12..23/01 (10 dias), executado 50 (boletim 12/01 -> entra em 19/01).
  custo direto 13,2 + 36,3 + 82,5 + 33 = 165; preço 206,25. BAC 41.250; PV/dia 4.125;
  PV(19/01) = 5 dias = 20.625; EV = 50 × 206,25 = 10.312,5.
- S  SIN verba, L1: LB 19..23/01, não iniciada. custo direto 4.800.000; BAC 6.000.000; PV(19/01) = 0.
Fatores de custo fixados no teste: L1/TER 1,10 e L2/LAS 0,90 -> AC = 15.262,5 + 9.281,25 = 24.543,75.
Estas contas usam BDI EXPLÍCITO de 25% (``bdi=0.25``) para ficarem redondas; o BDI declarado da obra
(fórmula do TCU) e o reajuste fictício têm testes próprios no fim do arquivo.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from infra4d import orcamento as O
from infra4d.calendario import ordinal
from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO, Projeto
from ifc_opcional import requer_ifc

RODOVIA = DATASET_PADRAO.parent / "rodovia_ficticia.json"


def _dados(**mud):
    d = {
        "meta": {"aviso": "DADOS FICTÍCIOS", "ficticio": True, "tipo_obra": "ferrovia", "semente": 7,
                 "inicio_projeto": "2026-01-05",
                 "data_status": "2026-01-19", "calendario_obra": "C"},
        "lotes": [{"id": "L1"}, {"id": "L2"}],
        "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []}],
        "servicos": [], "relacoes": [],
        "atividades": [
            {"id": "A", "nome": "A", "tipo": "tarefa", "lote_id": "L1", "servico_id": "TER", "unidade": "m³",
             "quantidade_total": 1000.0, "produtividade_planejada": 200.0, "equipes": 1, "calendario": "C",
             "inicio_lb": "2026-01-05", "termino_lb": "2026-01-09", "status": "em_andamento",
             "quantidade_executada": 600.0},
            {"id": "B", "nome": "B", "tipo": "tarefa", "lote_id": "L2", "servico_id": "LAS", "unidade": "m³",
             "quantidade_total": 200.0, "produtividade_planejada": 20.0, "equipes": 1, "calendario": "C",
             "inicio_lb": "2026-01-12", "termino_lb": "2026-01-23", "status": "em_andamento",
             "quantidade_executada": 50.0},
            {"id": "S", "nome": "S", "tipo": "tarefa", "lote_id": "L1", "servico_id": "SIN", "duracao_fixa": 5,
             "calendario": "C", "inicio_lb": "2026-01-19", "termino_lb": "2026-01-23", "status": "nao_iniciada"},
            {"id": "M", "nome": "marco", "tipo": "marco_termino", "calendario": "C",
             "inicio_lb": "2026-01-23", "termino_lb": "2026-01-23"},
        ],
        "medicoes": [{"atividade_id": "A", "semana_inicio": "2026-01-05", "quantidade": 600.0, "equipes_dias": 5},
                     {"atividade_id": "B", "semana_inicio": "2026-01-12", "quantidade": 50.0, "equipes_dias": 5}],
    }
    for aid, campos in mud.items():
        next(a for a in d["atividades"] if a["id"] == aid).update(campos)
    return d


@pytest.fixture()
def fatores_fixos(monkeypatch):
    tab = {("L1", "TER"): 1.10, ("L2", "LAS"): 0.90, ("L1", "SIN"): 1.0}
    monkeypatch.setattr(O, "fator_custo", lambda semente, lote, serv: tab[(lote, serv)])


# =========================================================================== à mão
def test_orcamento_por_atividade_a_mao():
    linhas = {ln["atividade_id"]: ln for ln in O.orcar_atividades(Projeto(_dados()), bdi=0.25)}
    assert set(linhas) == {"A", "B", "S"}  # marco não é orçado
    assert linhas["A"]["preco_venda_unitario"] == pytest.approx(23.125)
    assert linhas["A"]["bac"] == pytest.approx(23125.0) and linhas["A"]["ev_na_data_status"] == pytest.approx(13875.0)
    assert linhas["A"]["custo_direto_orcado"] == pytest.approx(18500.0)
    assert linhas["B"]["bac"] == pytest.approx(41250.0) and linhas["B"]["ev_na_data_status"] == pytest.approx(10312.5)
    assert linhas["S"]["unidade"] == "vb" and linhas["S"]["bac"] == pytest.approx(6_000_000.0)
    assert linhas["S"]["ev_na_data_status"] == 0


def test_evm_conferido_a_mao(fatores_fixos):
    e = O.resumo(Projeto(_dados()), bdi=0.25)["evm"]
    bac, pv, ev, ac = 6_064_375.0, 43_750.0, 24_187.5, 24_543.75
    assert (e["bac"], e["pv"], e["ev"], e["ac"]) == (bac, pv, ev, ac)
    assert e["cv"] == -356.25 and e["sv"] == -19_562.5
    assert e["cpi"] == round(ev / ac, 4) == 0.9855
    assert e["spi"] == round(ev / pv, 4) == 0.5529
    assert e["eac"] == round(bac * ac / ev, 2)          # BAC ÷ CPI
    assert e["vac"] == round(bac - bac * ac / ev, 2)
    assert e["etc"] == round(bac * ac / ev - ac, 2)
    assert e["tcpi"] == round((bac - ev) / (bac - ac), 4)


def test_evm_por_lote_a_mao(fatores_fixos):
    r = O.resumo(Projeto(_dados()), bdi=0.25)
    lotes = {x["lote_id"]: x for x in r["por_lote"]}
    # L1: EV 13.875, AC 15.262,5 (×1,10), PV 23.125  |  L2: EV 10.312,5, AC 9.281,25 (×0,90), PV 20.625
    assert (lotes["L1"]["cpi"], lotes["L1"]["spi"]) == (round(1 / 1.1, 4), 0.6)
    assert (lotes["L2"]["cpi"], lotes["L2"]["spi"]) == (round(1 / 0.9, 4), 0.5)
    assert lotes["L1"]["bac"] + lotes["L2"]["bac"] == r["evm"]["bac"]
    assert O.resumo(Projeto(_dados()), bdi=0.25, lote="L2")["evm"]["ev"] == 10_312.5


def test_curva_s_a_mao(fatores_fixos):
    c = O.curva_s(Projeto(_dados()), bdi=0.25)
    pts = {p["data"]: p for p in c["pontos"]}
    assert list(pts) == ["2026-01-05", "2026-01-12", "2026-01-19", "2026-01-24"]  # 24 = fim da LB (23) + 1
    assert [pts[d]["pv"] for d in pts] == [0.0, 23_125.0, 43_750.0, 6_064_375.0]
    assert [pts[d]["ev"] for d in pts] == [0.0, 13_875.0, 24_187.5, None]   # EV só até a data de status
    assert [pts[d]["ac"] for d in pts] == [0.0, 15_262.5, 24_543.75, None]
    assert c["bac"] == 6_064_375.0


def test_verba_em_andamento_usa_percentual():
    d = _dados(S={"status": "em_andamento", "percentual_executado": 40.0, "inicio_real": "2026-01-12"})
    s = next(x for x in O.orcar_atividades(Projeto(d), bdi=0.25) if x["atividade_id"] == "S")
    assert s["ev_na_data_status"] == pytest.approx(2_400_000.0)
    assert O.resumo(Projeto(d), bdi=0.25)["evm"]["ev"] == pytest.approx(24_187.5 + 2_400_000.0)


def test_unidade_divergente_e_erro():
    with pytest.raises(O.ErroOrcamento, match=r"A: unidade da atividade 'm²'"):
        O.orcar_atividades(Projeto(_dados(A={"unidade": "m²"})))
    with pytest.raises(O.ErroOrcamento, match="sem composição"):
        O.orcar_atividades(Projeto(_dados(B={"servico_id": "XYZ"})))


@pytest.mark.parametrize("meta", [{"ficticio": False}, {"ficticio": "true"}, {"aviso": "DADOS FICTÍCIOS"}])
def test_ac_sintetico_so_com_marca_booleana(meta):
    d = _dados()
    d["meta"] = {k: v for k, v in d["meta"].items() if k != "ficticio"} | meta
    for fn in (O.resumo, O.curva_s):
        with pytest.raises(O.ErroOrcamento, match="meta.ficticio"):
            fn(Projeto(d))
    assert O.orcar_atividades(Projeto(d))  # o orçamento (BAC) não inventa custo real: segue disponível


def test_fator_de_custo_deterministico_e_na_faixa():
    f = O.fator_custo(7, "L1", "TER")
    assert f == O.fator_custo(7, "L1", "TER") and O.FAIXA_FATOR_CUSTO[0] <= f <= O.FAIXA_FATOR_CUSTO[1]
    assert len({O.fator_custo(7, l, s) for l in ("L1", "L2") for s in ("TER", "LAS", "SUB")}) > 1


def test_composicoes_sao_ficticias_e_decompostas():
    for tipo in ("ferrovia", "rodovia"):
        for c in O.tabela(tipo):
            assert c["codigo"].startswith("FIC-") and c["ficticio"] is True
            assert set(c["custo_direto"]) == {"mao_de_obra", "equipamento", "material", "transporte"}
            assert c["custo_direto_unitario"] == pytest.approx(sum(c["custo_direto"].values()), abs=0.01)
            assert c["preco_venda_unitario"] == pytest.approx(c["custo_direto_unitario"] * (1 + O.bdi_da_obra(tipo)), abs=0.01)
    with pytest.raises(O.ErroOrcamento):
        O.tabela("hidrovia")


def test_classificacao_ifc_pelo_exportador():
    pytest.importorskip("ifcopenshell")
    r = O.classificacao_ifc("ferrovia", "IfcCourse", "BALLASTBED")
    assert r["IfcClassificationReference"]["Identification"] == "FIC-FER-LAS-001" and r["unidade"] == "m³"
    assert (r["qto"], r["quantidade"], r["fator_para_unidade"]) == ("INFRA4D_Quantidade", "QuantidadeContratual", 1.0)
    # os 3 pontos que divergiam no mapa manual antigo (achado do agente de IFC)
    assert O.classificacao_ifc("rodovia", "IfcEarthworksCut")["servico_id"] == "SUP"
    assert O.classificacao_ifc("rodovia", "IfcPavement", "FLEXIBLE")["servico_id"] == "CBU"
    assert O.classificacao_ifc("rodovia", "IfcCourse", "USERDEFINED", "PRIMECOAT")["servico_id"] == "IMP"
    cbu = O.classificacao_ifc("rodovia", "IfcPavement", "FLEXIBLE")
    assert cbu["unidade"] == "t" and cbu["fator_para_unidade"] == pytest.approx(0.001)   # kg no modelo -> t
    amb = O.classificacao_ifc("rodovia", "IfcCourse", "PAVEMENT")                      # SBB e BGS
    assert amb["ambiguo"] is True and sorted(amb["candidatos"]) == ["FIC-ROD-BGS-001", "FIC-ROD-SBB-001"]
    assert O.classificacao_ifc("ferrovia", "IfcCourse", "PAVEMENT") is None
    assert O.classificacao_ifc("ferrovia", "IfcWall") is None


@pytest.mark.parametrize("tipo, arquivo", [("ferrovia", DATASET_PADRAO), ("rodovia", RODOVIA)])
def test_mapa_do_orcamento_coincide_com_o_exportador_por_servico(tipo, arquivo):
    """Para cada serviço da obra: (classe, PredefinedType, ObjectType) do mapa == ``exportar.classe_ifc``."""
    pytest.importorskip("ifcopenshell")
    from infra4d.ifc import exportar as exp
    mapa = {m["servico_id"]: m for m in O.mapa_ifc(tipo)}
    servicos = {a["servico_id"] for a in Projeto.carregar(arquivo).dados["atividades"] if a.get("servico_id")}
    assert servicos <= set(mapa), servicos - set(mapa)
    for s in servicos:
        m = mapa[s]
        if exp.estilo_conhecido(tipo, s) is None:
            assert m["sem_elemento"] and m["classe_ifc"] is None, s
        else:
            assert (m["classe_ifc"], m["predefined_type"], m["object_type"]) == exp.classe_ifc(tipo, s), s


@pytest.mark.parametrize("arquivo", [DATASET_PADRAO, RODOVIA], ids=["ferrovia", "rodovia"])
def test_ifc_exportado_classifica_cada_elemento_como_o_mapa(arquivo):
    """No IFC REAL exportado: cada elemento classificado (IfcClassificationReference = código FIC-…) tem a
    classe/PredefinedType/ObjectType que o mapa do orçamento atribui ao serviço daquele código."""
    pytest.importorskip("ifcopenshell")
    from infra4d.ifc import exportar as exp
    dados = Projeto.carregar(arquivo).dados
    tipo = O.tipo_obra(Projeto.carregar(arquivo))
    f, _info = exp.construir(dados, incluir_4d=False)
    por_codigo = {m["codigo"]: m for m in O.mapa_ifc(tipo)}
    n = 0
    for rel in f.by_type("IfcRelAssociatesClassification"):
        ref = rel.RelatingClassification
        if not ref.is_a("IfcClassificationReference"):
            continue   # classificação do projeto (não é composição)
        m = por_codigo[ref.Identification]
        for el in rel.RelatedObjects:
            obtido = (el.is_a(), getattr(el, "PredefinedType", None), getattr(el, "ObjectType", None))
            esperado = (m["classe_ifc"], m["predefined_type"],
                        m["object_type"] if m["predefined_type"] == "USERDEFINED" else obtido[2])
            assert obtido == esperado, (m["servico_id"], obtido, esperado)
            n += 1
    assert n > 500


def test_mapa_indisponivel_sem_exportador(monkeypatch, cliente):
    def falha():
        raise O.MapaIfcIndisponivel("mapa IFC indisponível: teste")
    monkeypatch.setattr(O, "_exportador", falha)
    j = cliente.get("/api/orcamento/composicoes").json()
    assert j["mapa_ifc"] == [] and "indisponível" in j["mapa_ifc_nota"] and j["composicoes"]
    assert cliente.get("/api/orcamento/classificacao-ifc", params={"classe": "IfcCourse"}).status_code == 503


# =========================================================================== obras do repo
@pytest.fixture(scope="module", params=[DATASET_PADRAO, RODOVIA], ids=["ferrovia", "rodovia"])
def obra(request):
    return Projeto.carregar(request.param)


def test_obra_orca_tudo_e_ev_bate_com_executado(obra):
    linhas = O.orcar_atividades(obra)
    tarefas = [a for a in obra.dados["atividades"] if a.get("servico_id") and a.get("tipo") == "tarefa"]
    assert len(linhas) == len(tarefas)
    r = O.resumo(obra)
    assert r["ficticio"] and "FICTÍCIO" in r["aviso"]
    assert r["evm"]["ev"] == pytest.approx(sum(ln["ev_na_data_status"] for ln in linhas), abs=0.01)
    assert sum(x["bac"] for x in r["por_lote"]) == pytest.approx(r["evm"]["bac"], abs=0.05)
    for x in r["por_lote"] + [r["evm"]]:
        assert O.FAIXA_FATOR_CUSTO[0] - 1e-3 <= x["ac"] / x["ev"] <= O.FAIXA_FATOR_CUSTO[1] + 1e-3
        assert x["eac"] == pytest.approx(x["bac"] / x["cpi"], rel=1e-3)


def test_obra_curva_s_monotonica_e_fecha(obra):
    c = O.curva_s(obra)
    for k in ("pv", "ev", "ac"):
        serie = [p[k] for p in c["pontos"] if p[k] is not None]
        assert serie and all(a <= b + 1e-6 for a, b in zip(serie, serie[1:])), k
    assert c["pontos"][-1]["pv"] == pytest.approx(c["bac"], abs=0.05)
    ds = obra.dados["meta"]["data_status"]
    no_status = next(p for p in c["pontos"] if p["data"] == ds)
    assert no_status["ev"] == pytest.approx(O.resumo(obra)["evm"]["ev"], abs=0.05)
    assert all(p["ev"] is None for p in c["pontos"] if p["data"] > ds)


# =========================================================================== API
@pytest.fixture(scope="module")
def cliente():
    return TestClient(criar_app(fontes={"ferrovia": Projeto.carregar(DATASET_PADRAO),
                                        "rodovia": Projeto.carregar(RODOVIA)}))


@pytest.mark.parametrize("obra_id", ["ferrovia", "rodovia"])
def test_api_rotas(cliente, obra_id):
    assert "rotas_orcamento" in cliente.app.state.rotas_ligadas
    for rota in ("composicoes", "resumo", "curva-s-financeira"):
        r = cliente.get(f"/api/orcamento/{rota}", params={"obra": obra_id})
        assert r.status_code == 200 and "FICTÍCIO" in r.json()["aviso"] and r.json()["ficticio"] is True, rota
    comp = cliente.get("/api/orcamento/composicoes", params={"obra": obra_id}).json()
    assert comp["tipo_obra"] == obra_id and all(c["codigo"].startswith("FIC-") for c in comp["composicoes"])
    lote = cliente.get("/api/orcamento/resumo", params={"obra": obra_id, "lote": "L2"}).json()
    assert lote["lote"] == "L2" and lote["por_lote"] == []


def test_api_erros(cliente):
    assert cliente.get("/api/orcamento/resumo", params={"lote": "L9"}).status_code == 404
    assert cliente.get("/api/orcamento/resumo", params={"obra": "zz"}).status_code == 404
    assert cliente.get("/api/orcamento/curva-s-financeira", params={"passo_dias": 0}).status_code == 422


@requer_ifc
def test_api_classificacao_ifc(cliente):
    assert cliente.get("/api/orcamento/classificacao-ifc", params={"classe": "IfcWall"}).status_code == 404
    r = cliente.get("/api/orcamento/classificacao-ifc", params={"classe": "IfcCourse", "predefined_type": "BALLASTBED"})
    assert r.status_code == 200 and r.json()["IfcClassificationReference"]["Identification"] == "FIC-FER-LAS-001"


# =========================================================================== revisão r9
def test_ev_ancorado_no_executado_mesmo_com_boletins_divergentes(fatores_fixos):
    # A executou 600, mas o boletim diz 300: o EV continua 600 × 23,125 = 13.875 e sai um aviso;
    # a curva distribui a âncora pelo perfil dos boletins (tudo na fronteira 12/01).
    d = _dados()
    d["medicoes"][0]["quantidade"] = 300.0
    r = O.resumo(Projeto(d), bdi=0.25)
    assert r["evm"]["ev"] == 24_187.5 and sum(x["ev"] for x in r["por_servico"]) == 24_187.5
    assert any("A: boletins somam 300" in x for x in r["avisos"])
    pts = {p["data"]: p for p in O.curva_s(Projeto(d), bdi=0.25)["pontos"]}
    assert pts["2026-01-12"]["ev"] == 13_875.0 and pts["2026-01-19"]["ev"] == 24_187.5
    # sem boletim e sem início real: a âncora entra inteira na data de status
    d["medicoes"] = [m for m in d["medicoes"] if m["atividade_id"] != "A"]
    pts = {p["data"]: p for p in O.curva_s(Projeto(d), bdi=0.25)["pontos"]}
    assert pts["2026-01-12"]["ev"] == 0.0 and pts["2026-01-19"]["ev"] == 24_187.5
    assert O.resumo(Projeto(_dados()))["avisos"] == []


@pytest.mark.parametrize("mud, trecho", [
    ({"inicio_lb": None}, "linha de base ausente"),
    ({"termino_lb": "09/01/2026"}, "linha de base ausente"),
    ({"inicio_lb": "2026-01-09", "termino_lb": "2026-01-05"}, "invertida"),
    ({"inicio_lb": "2026-01-10", "termino_lb": "2026-01-11"}, "sem dia útil"),   # sábado e domingo
    ({"quantidade_total": -1000.0}, "quantidade negativa"),
    ({"quantidade_executada": -1.0}, "quantidade negativa"),
])
def test_linha_de_base_e_quantidade_invalidas_sao_recusadas(mud, trecho):
    with pytest.raises(O.ErroOrcamento, match=f"A: .*{trecho}"):
        O.orcar_atividades(Projeto(_dados(A=mud)))


def test_preco_exibido_com_4_casas_igual_ao_do_calculo():
    ter = next(c for c in O.tabela("ferrovia") if c["servico_id"] == "TER")
    esperado = round(18.5 * (1 + O.bdi_da_obra("ferrovia")), 4)
    assert ter["preco_venda_unitario"] == esperado == round(O.preco_venda(O.COMPOSICOES["ferrovia"]["TER"]), 4)
    assert next(c for c in O.tabela("ferrovia", bdi=0.25) if c["servico_id"] == "TER")["preco_venda_unitario"] == 23.125


# =========================================================================== BDI declarado e reajuste (R11)
def test_bdi_pela_formula_do_tcu_confere_com_planilha_publica():
    # Planilha do CJF (R11 §1): AC 4%, S+G 0,8%, R 1,27%, DF 1,23%, L 7,40%, I 9,15% -> "BDI CALCULADO 26,93%"
    cjf = {"AC": 0.04, "SG": 0.008, "R": 0.0127, "DF": 0.0123, "L": 0.074, "I": 0.0915}
    assert round(100 * O.bdi_tcu(cjf), 2) == 26.93
    # ferrovia: (1+0,055+0,005+0,013) × 1,010 × 1,075 / (1 − 0,0565) − 1 = 1,16500975 / 0,9435 − 1
    assert O.bdi_da_obra("ferrovia") == pytest.approx(1.073 * 1.01 * 1.075 / 0.9435 - 1, abs=1e-12)
    assert round(O.bdi_da_obra("ferrovia"), 6) == 0.234775 and round(O.bdi_da_obra("rodovia"), 6) == 0.222159
    for tipo in ("ferrovia", "rodovia"):   # dentro da faixa do acórdão para rodovias e ferrovias
        assert O.FAIXA_BDI_TCU["q1"] <= O.bdi_da_obra(tipo) <= O.FAIXA_BDI_TCU["q3"]
    with pytest.raises(O.ErroOrcamento):
        O.bdi_da_obra("hidrovia")


def test_preco_padrao_usa_o_bdi_da_obra_e_bdi_explicito_substitui():
    ter = O.COMPOSICOES["ferrovia"]["TER"]
    assert O.preco_venda(ter) == pytest.approx(18.5 * (1 + O.bdi_da_obra("ferrovia")), abs=1e-6)
    assert O.preco_venda(ter, 0.25) == 23.125
    r = O.resumo(Projeto(_dados()))
    assert r["bdi"] == round(O.bdi_da_obra("ferrovia"), 6) and "TCU" in r["bdi_nota"]


def test_indice_e_fator_de_reajuste_a_mao():
    # TERRAPLENAGEM 0,45%/mês fictício. Data-base 01/01/2026.
    base = date(2026, 1, 1)
    assert O.indice_sintetico("TERRAPLENAGEM", 0) == 100.0
    assert O.indice_sintetico("TERRAPLENAGEM", 12) == pytest.approx(100 * 1.0045 ** 12)
    assert O.fator_reajuste("ferrovia", "TER", base, date(2026, 12, 31)) == 1.0                  # 1º ano
    assert O.fator_reajuste("ferrovia", "TER", base, date(2027, 1, 1)) == pytest.approx(1.0045 ** 12)
    assert O.fator_reajuste("ferrovia", "TER", base, date(2027, 12, 31)) == pytest.approx(1.0045 ** 12)  # anualidade
    assert O.fator_reajuste("ferrovia", "TER", base, date(2028, 1, 2)) == pytest.approx(1.0045 ** 24)
    assert O.fator_reajuste("rodovia", "CBU", base, date(2027, 3, 1)) == pytest.approx(1.006 ** 12)  # PAVIMENTACAO
    with pytest.raises(O.ErroOrcamento):
        O.fator_reajuste("ferrovia", "XYZ", base, date(2027, 1, 1))


def _dados_reajuste():
    # Data-base 01/01/2026. A (TER) executada em dez/2026 (1º ano: sem reajuste); B (TER, L2) em jan/2027
    # (2º ano: × 1,0045^12). Seg–sex; data de status seg 18/01/2027. BDI explícito 25% -> 23,125 R$/m³.
    def t(aid, lote, ini, fim, sem):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": lote, "servico_id": "TER", "unidade": "m³",
                "quantidade_total": 100.0, "produtividade_planejada": 20.0, "equipes": 1, "calendario": "C",
                "inicio_lb": ini, "termino_lb": fim, "status": "concluida", "quantidade_executada": 100.0,
                "inicio_real": ini, "termino_real": fim, "_sem": sem}
    a, b = t("A", "L1", "2026-12-07", "2026-12-11", "2026-12-07"), t("B", "L2", "2027-01-04", "2027-01-08", "2027-01-04")
    return {"meta": {"aviso": "FICTÍCIO", "ficticio": True, "tipo_obra": "ferrovia", "semente": 7,
                     "inicio_projeto": "2026-12-07",
                     "data_status": "2027-01-18", "calendario_obra": "C", "data_base_orcamento": "2026-01-01"},
            "lotes": [{"id": "L1"}, {"id": "L2"}],
            "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []}],
            "servicos": [], "relacoes": [],
            "atividades": [{k: v for k, v in x.items() if k != "_sem"} for x in (a, b)],
            "medicoes": [{"atividade_id": x["id"], "semana_inicio": x["_sem"], "quantidade": 100.0, "equipes_dias": 5}
                         for x in (a, b)]}


def test_ev_pv_ac_com_e_sem_reajuste_a_mao(monkeypatch):
    monkeypatch.setattr(O, "fator_custo", lambda semente, lote, serv: {"L1": 1.10, "L2": 0.90}[lote])
    r = O.resumo(Projeto(_dados_reajuste()), bdi=0.25)
    f12 = 1.0045 ** 12
    sem, com = r["evm"], r["reajuste"]["evm_com_reajuste"]
    # sem reajuste: BAC = PV = EV = 2 × 100 × 23,125 = 4.625; AC = 2.312,5 × 1,10 + 2.312,5 × 0,90 = 4.625
    assert (sem["bac"], sem["pv"], sem["ev"], sem["ac"]) == (4625.0, 4625.0, 4625.0, 4625.0)
    # com reajuste: só B (jan/2027) × f12
    assert com["ev"] == round(2312.5 + 2312.5 * f12, 2) and com["pv"] == com["ev"] and com["bac"] == com["ev"]
    assert com["ac"] == round(2312.5 * 1.10 + 2312.5 * f12 * 0.90, 2)
    assert r["reajuste"]["reajuste_ev_ate_data_status"] == round(2312.5 * (f12 - 1), 2)   # R = V (Ii − I0)/I0
    assert r["reajuste"]["data_base"] == "2026-01-01" and "FICTÍCIOS" in r["reajuste"]["aviso"]
    c = O.curva_s(Projeto(_dados_reajuste()), bdi=0.25)
    ult = next(p for p in c["pontos"] if p["data"] == "2027-01-18")
    assert (ult["ev"], ult["ev_reajustado"]) == (4625.0, com["ev"]) and c["bac_reajustado"] == com["bac"]


def test_obras_reajuste_coerente_com_a_data_base():
    fer = O.resumo(Projeto.carregar(DATASET_PADRAO))
    rod = O.resumo(Projeto.carregar(RODOVIA))
    # ferrovia: início 03/11/2025 -> aniversário 01/11/2026 < status 09/11/2026: há reajuste no EV
    assert fer["reajuste"]["data_base"] == "2025-11-01" and fer["reajuste"]["reajuste_ev_ate_data_status"] > 0
    # rodovia: início 01/12/2025 -> aniversário 01/12/2026 > status: EV sem reajuste; o PV futuro tem
    assert rod["reajuste"]["reajuste_ev_ate_data_status"] == 0
    assert rod["reajuste"]["evm_com_reajuste"]["bac"] > rod["evm"]["bac"]


def test_bdi_declarado_com_fonte_e_marca_e_sem_deducao_por_texto():
    for tipo, d in O.BDI_DECLARADO.items():
        assert d["ficticio"] is True and "Acórdão 2622/2013" in d["fonte"]
    comp = dict(O.COMPOSICOES["ferrovia"]["TER"])
    comp.pop("tipo_obra")   # mesmo com código FIC-FER-…, sem tipo declarado não há BDI implícito
    with pytest.raises(O.ErroOrcamento, match="bdi= explícito"):
        O.preco_venda(comp)
    assert O.preco_venda(comp, 0.25) == 23.125
    assert O.resumo(Projeto(_dados()))["bdi_declarado"]["ficticio"] is True


# =========================================================================== uma só regra de "semana terminada"
@pytest.mark.parametrize("lote", [None, "L2"])
def test_ev_do_orcamento_igual_ao_realizado_da_curva_s_financeira(lote):
    """Para todo t <= data de status: EV(t) do orcamento = realizado(t) da curva S financeira × BAC/100.
    Exato (±0,01 R$) pelos eventos da curva_s; e pela saída pública (percentual com 4 casas: tolerância de
    arredondamento = BAC × 0,00005/100)."""
    from infra4d import curva_s as CS
    from infra4d.cenarios import executar
    P = Projeto.carregar(DATASET_PADRAO)
    oc = O.curva_s(P, lote=lote)
    w = CS.pesos(P, "financeira", lote)
    bac = sum(w.values())
    real = CS._acumulador(CS.eventos_realizado(P, w))
    res = {c: executar(P, c) for c in ("linha_base", "construtora", "independente")}
    pub = {p["data"]: p["realizado"] for p in CS.curva_s(P, res, "financeira", lote=lote)["pontos"]}
    assert bac == pytest.approx(oc["bac"], abs=0.01)
    n = 0
    for p in oc["pontos"]:
        if p["ev"] is None:
            continue
        assert p["ev"] == pytest.approx(real(ordinal(p["data"])), abs=0.01), p["data"]
        if p["data"] in pub:
            assert p["ev"] == pytest.approx(pub[p["data"]] * bac / 100, abs=bac * 0.00005 / 100 + 0.01), p["data"]
            n += 1
    assert n > 10


def test_resumo_e_curva_declaram_que_nao_usam_a_simulacao(cliente):
    for rota in ("resumo", "curva-s-financeira"):
        antes = cliente.get(f"/api/orcamento/{rota}").json()
        assert antes["simulacao_do_usuario"].startswith("não aplicada:")
        r = cliente.post("/api/simulacao", json={"ajustes": [{"atividade_id": "L3-S04-TER", "produtividade": 800}]})
        assert r.status_code == 200
        depois = cliente.get(f"/api/orcamento/{rota}").json()
        cliente.delete("/api/simulacao")
        assert depois == antes, rota


def test_openapi_das_rotas_do_orcamento(cliente):
    sp = cliente.app.openapi()
    for rota in ("composicoes", "resumo", "curva-s-financeira", "classificacao-ifc"):
        op = sp["paths"][f"/api/orcamento/{rota}"]["get"]
        assert (op.get("description") or "").strip(), rota
        assert "404" in op["responses"] and op["responses"]["404"]["description"] != "Validation Error", rota


# =========================================================================== revisão r17
@pytest.mark.parametrize("base, antes, no_dia", [
    (date(2025, 11, 15), date(2026, 11, 14), date(2026, 11, 15)),   # dia 15: 01–14/11/2026 ainda no 1º ano
    (date(2025, 1, 31), date(2026, 1, 30), date(2026, 1, 31)),
    (date(2024, 2, 29), date(2025, 2, 28), date(2025, 3, 1)),       # 29/02 sem correspondência: dia imediato
])
def test_anualidade_pela_data_inteira(base, antes, no_dia):
    # TER 0,45%/mês: 1º ano 1,0; do aniversário em diante 1,0045^12.
    assert O.fator_reajuste("ferrovia", "TER", base, date(antes.year, antes.month, 1)) == 1.0
    assert O.fator_reajuste("ferrovia", "TER", base, antes) == 1.0
    assert O.fator_reajuste("ferrovia", "TER", base, no_dia) == pytest.approx(1.0045 ** 12)
    assert O.anos_completos(base, base) == 0 and O.anos_completos(base, date(base.year - 1, 6, 1)) == 0


@pytest.mark.parametrize("valor", ["2025-13-01", "abc", 20251101, "2025-11-01T00:00:00", "20251101",
                                   "2025-02-30", True, ["2025-11-01"]])
def test_data_base_invalida_e_erro_de_orcamento_e_422(valor):
    d = _dados_reajuste()
    d["meta"]["data_base_orcamento"] = valor
    P = Projeto(d)
    with pytest.raises(O.ErroOrcamento, match="data_base_orcamento"):
        O.data_base(P)
    c = TestClient(criar_app(fontes={"x": P}))
    for rota in ("resumo", "curva-s-financeira"):
        r = c.get(f"/api/orcamento/{rota}", params={"obra": "x"})
        assert r.status_code == 422 and "data_base_orcamento" in r.json()["detail"], (rota, r.text)


def test_composicoes_de_tipo_sem_composicao_e_422_como_o_resumo():
    d = Projeto.carregar(RODOVIA).dados
    d["meta"]["tipo_obra"] = "metro"
    c = TestClient(criar_app(fontes={"x": Projeto(d)}))
    for rota in ("composicoes", "resumo", "curva-s-financeira"):
        r = c.get(f"/api/orcamento/{rota}", params={"obra": "x"})
        assert r.status_code == 422 and "metro" in r.json()["detail"], (rota, r.status_code)


def test_nota_descreve_o_bdi_usado():
    P = Projeto(_dados())
    declarado = O.resumo(P)["bdi_nota"]
    assert "23.48%" in declarado and "INFORMADO" not in declarado
    r = O.resumo(P, bdi=0.25)
    assert r["bdi"] == 0.25 and "INFORMADO" in r["bdi_nota"] and "25.00%" in r["bdi_nota"]
    assert "23.48%" in r["bdi_nota"]          # cita o declarado só como contraste, identificado
    assert O.resumo(P, bdi=0)["bdi_nota"].count("0.00%") == 1


@pytest.mark.parametrize("bdi", [float("nan"), float("inf"), float("-inf"), -0.01, True, False, "0.25", None])
def test_bdi_explicito_invalido_e_recusado(bdi):
    P = Projeto(_dados())
    comp = O.COMPOSICOES["ferrovia"]["TER"]
    if bdi is None:   # None = "use o declarado": é o caminho válido, não erro
        assert O.preco_venda(comp, None) == O.preco_venda(comp)
        return
    for chamada in (lambda: O.preco_venda(comp, bdi), lambda: O.tabela("ferrovia", bdi),
                    lambda: O.orcar_atividades(P, bdi), lambda: O.resumo(P, bdi=bdi),
                    lambda: O.curva_s(P, bdi=bdi)):
        with pytest.raises(O.ErroOrcamento, match="bdi inválido"):
            chamada()
    assert O.validar_bdi(0) == 0.0 and O.validar_bdi(1) == 1.0   # int válido vira float


@pytest.mark.parametrize("valor", ["ausente", None, "", "  ", 1, True])
def test_obra_sem_tipo_obra_e_erro_nunca_ferrovia_por_padrao(valor):
    d = _dados()
    if valor == "ausente":
        del d["meta"]["tipo_obra"]
    else:
        d["meta"]["tipo_obra"] = valor
    P = Projeto(d)
    for chamada in (lambda: O.tipo_obra(P), lambda: O.orcar_atividades(P, 0.25), lambda: O.resumo(P),
                    lambda: O.curva_s(P)):
        with pytest.raises(O.ErroOrcamento, match="meta.tipo_obra"):
            chamada()
    c = TestClient(criar_app(fontes={"x": P}))
    for rota in ("composicoes", "resumo", "curva-s-financeira"):
        r = c.get(f"/api/orcamento/{rota}", params={"obra": "x"})
        assert r.status_code == 422 and "tipo_obra" in r.json()["detail"], (rota, r.status_code)


@pytest.mark.parametrize("valor", ["ausente", None, "", 1, "metro"])
def test_classificacao_ifc_com_tipo_invalido_e_422(valor):
    """r21: a rota chamava O.tipo_obra fora do _executar e respondia 500."""
    d = _dados()
    if valor == "ausente":
        del d["meta"]["tipo_obra"]
    else:
        d["meta"]["tipo_obra"] = valor
    c = TestClient(criar_app(fontes={"x": Projeto(d)}))
    r = c.get("/api/orcamento/classificacao-ifc", params={"obra": "x", "classe": "IfcCourse",
                                                          "predefined_type": "BALLASTBED"})
    assert r.status_code == 422 and "tipo_obra" in r.json()["detail"], (r.status_code, r.text)


def test_classificacao_ifc_sem_exportador_continua_503(monkeypatch, cliente):
    def indisponivel(*a, **k):
        raise O.MapaIfcIndisponivel("exportador IFC indisponível (teste)")
    monkeypatch.setattr(O, "classificacao_ifc", indisponivel)
    r = cliente.get("/api/orcamento/classificacao-ifc", params={"classe": "IfcCourse"})
    assert r.status_code == 503 and "indisponível" in r.json()["detail"]
