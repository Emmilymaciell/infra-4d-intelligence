"""Adaptador Obrasgov.br → INFRA 4D: só a fixture FICTÍCIA, sem rede.

Valores esperados conferidos à mão contra examples/fixtures/obrasgov_sintetico.json.
"""

import copy
import json
from pathlib import Path

import pytest

from infra4d import adaptador_obrasgov as A

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "fixtures" / "obrasgov_sintetico.json"


@pytest.fixture()
def entrada():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture()
def saida(entrada):
    return A.converter(entrada)


def test_fixture_e_ficticia_e_no_formato_paginado(entrada):
    assert entrada["_infra4d_ficticio"] is True and "FICTÍCIA" in entrada["_aviso"]
    for r in A.RECURSOS:
        assert set(entrada[r]) == {"data", "total_pages", "total_items", "page_number", "page_size"}
        assert entrada[r]["total_items"] == len(entrada[r]["data"])


def test_obra_meta_e_marcos(saida):
    m, o = saida["meta"], saida["ferrovia"]
    assert m["ficticio"] is True and "FICTÍCIOS" in m["aviso"]
    assert (m["tipo_obra"], m["inicio_projeto"], m["termino_contratual"], m["data_status"]) == \
           ("rodovia", "2025-12-01", "2027-05-21", "2026-11-10")
    assert (o["id"], o["uf"], o["extensao_km"]) == ("99999.26-01", "XX", None)
    assert {x["id"]: x["data"] for x in saida["marcos"]} == {
        "M-INICIO-PREVISTO": "2025-12-01", "M-FIM-PREVISTO": "2027-05-21", "M-INICIO-EFETIVO": "2025-12-01"}


def test_avanco_fisico_lotes_e_rastreio(saida):
    assert [(x["data"], x["percentual"]) for x in saida["avanco_fisico"]] == \
           [("2026-03-31", 12.5), ("2026-07-31", 48.0), ("2026-11-09", 81.9)]
    assert saida["avanco_fisico"][2]["motivos"] == ["Motivo fictício"]
    assert [(l["id"], l["construtora"], l["contrato"]["valor_global"]) for l in saida["lotes"]] == \
           [("C501", "CONSÓRCIO FICTÍCIO PLANALTO", 80000000.0), ("C502", "CONSTRUTORA FICTÍCIA CERRADO", 85000000.0)]
    assert saida["financeiro"] == {"investimento_previsto": 250000000.0, "valor_global_contratos": 165000000.0}
    assert saida["rastreio"] == {"id_projeto_investimento": "99999.26-01", "execucoes": [1, 2, 3], "contratos": [501, 502]}
    assert saida["situacoes"][0]["situacao"] == "Paralisada" and saida["situacoes"][0]["data"] == "2026-02-10"
    assert len(saida["localizacao"]["municipios"]) == 2 and len(saida["localizacao"]["pins"]) == 2
    assert saida["avisos"] == []


def test_lacunas_declaradas_e_nada_inventado(saida):
    assert any("cronograma" in x for x in saida["lacunas"])
    assert not {"atividades", "relacoes", "medicoes", "calendarios"} & set(saida)


def test_sem_marca_sai_como_dado_real(entrada):
    del entrada["_infra4d_ficticio"]
    s = A.converter(entrada)
    assert s["meta"]["ficticio"] is False and "FICTÍCIO" not in s["meta"]["aviso"]
    entrada["_infra4d_ficticio"] = "true"           # texto não vale (ADR-0005)
    assert A.converter(entrada)["meta"]["ficticio"] is False


def test_avanco_que_diminui_gera_aviso(entrada):
    entrada["execucao_fisica"]["data"][2]["percentual_execucao_fisica"] = 40.0
    assert any("DIMINUI" in x for x in A.converter(entrada)["avisos"])


@pytest.mark.parametrize("mexer, trecho", [
    (lambda e: e["execucao_fisica"]["data"][0].update(percentual_execucao_fisica=120), "percentual inválido"),
    (lambda e: e["execucao_fisica"]["data"][0].update(percentual_execucao_fisica=True), "percentual inválido"),
    (lambda e: e["execucao_fisica"]["data"][0].update(dt_final_execucao="31/03/2026"), "data inválida"),
    (lambda e: e["contrato"]["data"][0].update(id_projeto_investimento="11111.26-01"), "outro projeto"),
    (lambda e: e["projeto_investimento"]["data"][0].update(id_projeto_investimento="abc"), "formato"),
    (lambda e: (e["projeto_investimento"]["data"].clear(), e["projeto_investimento"].update(total_items=0)),
     "exatamente 1"),
    (lambda e: e["execucao_fisica"].update(total_items=200), "junte todas as páginas"),
    (lambda e: e.update(contrato=[1, 2]), "envelope paginado"),
])
def test_entrada_invalida_e_recusada(entrada, mexer, trecho):
    mexer(entrada)
    with pytest.raises(A.ErroObrasgov, match=trecho):
        A.converter(entrada)


def test_nao_acessa_a_rede():
    fonte = Path(A.__file__).read_text(encoding="utf-8")
    assert not any(m in fonte for m in ("urllib", "requests", "httpx", "http.client", "socket"))


def test_entrada_nao_e_alterada(entrada):
    antes = copy.deepcopy(entrada)
    A.converter(entrada)
    assert entrada == antes


# ---- r14, defeito 5: campo aninhado fora do tipo -> ErroObrasgov com o nome do campo (nunca AttributeError/TypeError)
def _pi(e):
    return e["projeto_investimento"]["data"][0]


@pytest.mark.parametrize("mexer, trecho", [
    (lambda e: _pi(e).update(eixos_tipos=["rodovia"]), "eixos_tipos"),
    (lambda e: _pi(e).update(executores="DNIT"), "executores"),
    (lambda e: _pi(e).update(pins=[1, 2]), "pins"),
    (lambda e: _pi(e).update(investimentos_previstos=[{"vl_investimento_previsto": "1.000,00"}]),
     "vl_investimento_previsto"),
    (lambda e: _pi(e).update(investimentos_previstos=[{"vl_investimento_previsto": True}]), "vl_investimento_previsto"),
    (lambda e: e["execucao_fisica"]["data"][0].update(motivos=["chuva"]), "motivos"),
    (lambda e: e["execucao_fisica"]["data"][0].update(indicativos=[None]), "indicativos"),
    (lambda e: e["contrato"]["data"][0].update(valor_global_contrato="R$ 10"), "valor_global_contrato"),
    (lambda e: e["contrato"]["data"][0].update(valor_acumulado_contrato=[1]), "valor_acumulado_contrato"),
    (lambda e: e["contrato"]["data"][0].update(id_contrato="A1"), "id_contrato"),
    (lambda e: e["contrato"]["data"][1].update(id_contrato=True), "id_contrato"),
    (lambda e: e["execucao_fisica"]["data"][0].update(id_execucao_fisica="x"), "id_execucao_fisica"),
])
def test_campo_aninhado_fora_do_tipo_e_recusado(entrada, mexer, trecho):
    mexer(entrada)
    with pytest.raises(A.ErroObrasgov, match=trecho):
        A.converter(entrada)


# ---- r14, defeito 6: valor não finito recusado; registro que não é objeto gera aviso (não some calado)
@pytest.mark.parametrize("valor", [float("nan"), float("inf"), float("-inf")])
def test_valor_monetario_nao_finito_e_recusado(entrada, valor):
    entrada["contrato"]["data"][0]["valor_global_contrato"] = valor
    with pytest.raises(A.ErroObrasgov, match="não finito"):
        A.converter(entrada)
    entrada["contrato"]["data"][0]["valor_global_contrato"] = 1.0
    _pi(entrada)["investimentos_previstos"] = [{"vl_investimento_previsto": valor}]
    with pytest.raises(A.ErroObrasgov, match="não finito"):
        A.converter(entrada)


def test_registro_que_nao_e_objeto_gera_aviso_com_a_contagem(entrada):
    entrada["contrato"]["data"] += ["lixo", 7]
    entrada["contrato"].pop("total_items")
    s = A.converter(entrada)
    assert [x["id"] for x in s["lotes"]] == ["C501", "C502"]
    assert s["financeiro"]["valor_global_contratos"] == 165000000.0
    assert s["avisos"] == ["contrato: 2 registro(s) ignorado(s) por não serem objetos JSON"]
