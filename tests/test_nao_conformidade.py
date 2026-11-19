"""Não conformidade (NC) como entidade da fiscalização (missão §3.5): ``nao_conformidade.py`` e
``GET /api/fiscalizacao/nao-conformidades``.

Rede à mão (seg–sex; data de status seg 19/01/2026):
- A  TER L1 km 0–2, 1000 m³, executado 400 em 5 equipe·dia (80/dia) → restam 600/80 = 7,5 → 8 dias:
  19/01 a 28/01. Caminho mais longo até M → CRÍTICA (folga 0).
- B  DRE L2 km 3–4, 1 dia em 19/01 → folga 7 (termina 7 dias úteis antes de A).
- C  SIN L1 km 5–6, concluída em 05/01.
NCs (prazo × data de status 19/01):
- NC-1 em A, aberta, alta, prazo 12/01 → VENCIDA há 7 dias corridos; A crítica → ALERTA; risco nível alto.
- NC-2 em B, em tratamento, média, prazo 30/01 → no prazo; B não crítica → sem alerta.
- NC-3 em C, encerrada em 06/01, prazo 07/01 → encerrada não vence nem alerta.
- NC-4 em B, aberta, baixa, prazo 16/01 → VENCIDA há 3 dias; sem alerta; risco nível baixo.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import nao_conformidade as NC
from infra4d.api import criar_app
from infra4d.cenarios import DATASET_PADRAO, Projeto, executar

ROTA = "/api/fiscalizacao/nao-conformidades"
SHA = "a" * 64


def _t(aid, lote, serv, qtd, prod, ini, fim, status, exe=0.0, km=(0, 1), **kw):
    return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": lote, "servico_id": serv, "unidade": "m³",
            "quantidade_total": qtd, "produtividade_planejada": prod, "equipes": 1, "calendario": "C",
            "inicio_lb": ini, "termino_lb": fim, "status": status, "quantidade_executada": exe,
            "km_ini": km[0], "km_fim": km[1], **kw}


def _ncs():
    return [
        {"id": "NC-1", "atividade_id": "A", "elemento_id": "A-E01", "km": 1.5, "data_abertura": "2026-01-06",
         "descricao": "grau de compactação abaixo do especificado", "gravidade": "alta", "prazo": "2026-01-12",
         "situacao": "aberta", "evidencias": [{"ref": "laudo/ensaio-17", "sha256": SHA}]},
        {"id": "NC-2", "atividade_id": "B", "data_abertura": "2026-01-15", "descricao": "bueiro desalinhado",
         "gravidade": "media", "prazo": "2026-01-30", "situacao": "em_tratamento"},
        {"id": "NC-3", "atividade_id": "C", "data_abertura": "2026-01-05", "descricao": "placa faltando",
         "gravidade": "baixa", "prazo": "2026-01-07", "situacao": "encerrada", "data_encerramento": "2026-01-06"},
        {"id": "NC-4", "atividade_id": "B", "km": 3.0, "data_abertura": "2026-01-12", "descricao": "entulho na vala",
         "gravidade": "baixa", "prazo": "2026-01-16", "situacao": "aberta"},
    ]


def _dados(ncs=None):
    d = {"meta": {"aviso": "DADOS FICTÍCIOS de teste", "ficticio": True, "tipo_obra": "ferrovia", "semente": 7,
                  "inicio_projeto": "2026-01-05", "data_status": "2026-01-19", "calendario_obra": "C"},
         "lotes": [{"id": "L1"}, {"id": "L2"}],
         "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []}],
         "servicos": [],
         "atividades": [
             _t("A", "L1", "TER", 1000.0, 100.0, "2026-01-05", "2026-01-16", "em_andamento", 400.0, (0, 2),
                inicio_real="2026-01-05"),
             _t("B", "L2", "DRE", 10.0, 10.0, "2026-01-19", "2026-01-19", "nao_iniciada", 0.0, (3, 4)),
             _t("C", "L1", "SIN", 10.0, 10.0, "2026-01-05", "2026-01-05", "concluida", 10.0, (5, 6),
                inicio_real="2026-01-05", termino_real="2026-01-05"),
             {"id": "M", "nome": "fim", "tipo": "marco_termino", "calendario": "C",
              "inicio_lb": "2026-01-16", "termino_lb": "2026-01-16"}],
         "relacoes": [{"predecessora": x, "sucessora": "M", "tipo": "FS", "lag": 0} for x in "ABC"],
         "medicoes": [{"atividade_id": "A", "semana_inicio": "2026-01-05", "quantidade": 400.0, "equipes_dias": 5},
                      {"atividade_id": "C", "semana_inicio": "2026-01-05", "quantidade": 10.0, "equipes_dias": 1}]}
    if ncs is not None:
        d["nao_conformidades"] = ncs
    return d


def _cliente(d) -> TestClient:
    return TestClient(criar_app(fontes={"x": Projeto(d)}))


# ------------------------------------------------------------------ rede e avaliação à mão
def test_premissas_da_rede_a_mao():
    r = executar(Projeto(_dados()), "independente")["atividades"]
    assert (r["A"]["critica"], r["A"]["folga_total"], r["A"]["termino"]) == (True, 0, "2026-01-28")
    assert (r["B"]["critica"], r["B"]["folga_total"]) == (False, 7)
    assert r["C"]["status"] == "concluida"


def test_vencidas_alertas_e_dias_a_mao():
    P = Projeto(_dados(_ncs()))
    rel = NC.relatorio(P, executar(P, "independente"))
    assert rel["n"] == 4
    assert [(n["id"], n["dias_vencida"]) for n in rel["vencidas"]] == [("NC-1", 7), ("NC-4", 3)]
    assert [a["nc_id"] for a in rel["alertas"]] == ["NC-1"]
    por_id = {n["id"]: n for n in rel["nao_conformidades"]}
    assert (por_id["NC-2"]["vencida"], por_id["NC-2"]["alerta"]) == (False, False)
    assert (por_id["NC-3"]["vencida"], por_id["NC-3"]["alerta"], por_id["NC-3"]["dias_vencida"]) == (False, False, 0)


@pytest.mark.parametrize("situacao, alerta", [("aberta", True), ("em_tratamento", True), ("encerrada", False)])
def test_alerta_em_atividade_critica_so_se_nao_encerrada(situacao, alerta):
    nc = {"id": "NC-X", "atividade_id": "A", "data_abertura": "2026-01-10", "descricao": "x", "gravidade": "baixa",
          "prazo": "2026-02-10", "situacao": situacao}
    if situacao == "encerrada":
        nc["data_encerramento"] = "2026-01-15"
    P = Projeto(_dados([nc]))
    assert bool(NC.relatorio(P, executar(P, "independente"))["alertas"]) is alerta


def test_nc_em_atividade_concluida_nao_e_alerta_mesmo_aberta():
    nc = {"id": "NC-C", "atividade_id": "C", "data_abertura": "2026-01-05", "descricao": "x", "gravidade": "alta",
          "prazo": "2026-01-30", "situacao": "aberta"}
    P = Projeto(_dados([nc]))
    assert NC.relatorio(P, executar(P, "independente"))["alertas"] == []


# ------------------------------------------------------------------ dataset sem NCs
@pytest.mark.parametrize("ncs", [None, []])
def test_dataset_sem_ncs_funciona(ncs):
    P = Projeto(_dados(ncs))
    assert NC.carregar(P) == []
    r = _cliente(_dados(ncs)).get(ROTA, params={"obra": "x"})
    assert r.status_code == 200
    j = r.json()
    assert (j["n"], j["nao_conformidades"], j["vencidas"], j["alertas"]) == (0, [], [], [])


def test_obras_publicadas_sem_ncs_respondem_vazio():
    c = TestClient(criar_app())
    for obra in ("ferrovia", "rodovia"):
        r = c.get(ROTA, params={"obra": obra})
        assert r.status_code == 200 and r.json()["n"] == 0, (obra, r.text)


# ------------------------------------------------------------------ fonte para o registro de riscos
def test_fonte_riscos_no_formato_das_fontes_e_evidencia_reconsultavel():
    from infra4d.riscos_prazo import extrair   # só leitura: mesmo extrator que o registro usa
    d = _dados(_ncs())
    P = Projeto(d)
    sinais = NC.fonte_riscos(P, executar(P, "independente"), "x")
    assert [s["atividades"] for s in sinais] == [["A"], ["B"]]
    chaves = {"chave", "fonte", "atividades", "nivel", "delta", "prob", "titulo", "texto", "evidencias"}
    assert all(set(s) == chaves and s["fonte"] == "nao_conformidade" for s in sinais)
    assert [s["chave"] for s in sinais] == [("frente", "L1", "TER"), ("frente", "L2", "DRE")]
    assert [s["nivel"] for s in sinais] == ["alto", "baixo"]
    c = _cliente(d)
    for s in sinais:
        ev = s["evidencias"][0]
        j = c.get(ev["rota"], params=ev["params"]).json()
        assert extrair(j, ev["caminho"]) == ev["valor"]
    assert [s["evidencias"][0]["valor"] for s in sinais] == [7, 3]


def test_fonte_riscos_sem_ncs_e_vazia():
    P = Projeto(_dados())
    assert NC.fonte_riscos(P, executar(P, "independente"), "x") == []


# ------------------------------------------------------------------ validação
def _mexe(i, **campos):
    ncs = _ncs()
    ncs[i] = {**ncs[i], **campos}
    return ncs


INVALIDOS = [
    (lambda: _ncs() + [_ncs()[0]], "id repetido"),
    (lambda: _mexe(0, id=""), "id ausente"),
    (lambda: _mexe(0, atividade_id="ZZ"), "atividade_id inexistente"),
    (lambda: _mexe(0, elemento_id="B-E01"), "elemento_id"),
    (lambda: _mexe(0, elemento_id="curto"), "elemento_id"),
    (lambda: _mexe(0, km=9.0), "fora do trecho"),
    (lambda: _mexe(0, km=float("nan")), "km deve ser número finito"),
    (lambda: _mexe(0, km=True), "km deve ser número finito"),
    (lambda: _mexe(0, descricao="  "), "descricao"),
    (lambda: _mexe(0, gravidade="critica"), "gravidade"),
    (lambda: _mexe(0, situacao="fechada"), "situacao"),
    (lambda: _mexe(0, prazo="2026-01-05"), "prazo 2026-01-05 antes da abertura"),
    (lambda: _mexe(0, data_abertura="2026-02-01", prazo="2026-02-10"), "depois da data de status"),
    (lambda: _mexe(0, data_abertura="2026-13-01"), "data_abertura"),
    (lambda: _mexe(0, prazo=20260112), "prazo deve ser texto"),
    (lambda: _mexe(2, data_encerramento=None), "data_encerramento deve ser texto"),
    (lambda: _mexe(2, data_encerramento="2026-01-04"), "antes da abertura"),
    (lambda: _mexe(0, data_encerramento="2026-01-10"), "só existe em NC encerrada"),
    (lambda: _mexe(0, evidencias=[{"ref": "f.jpg", "base64": "AAAA"}]), "nenhum conteúdo/foto"),
    (lambda: _mexe(0, evidencias=[{"ref": "f.jpg", "foto": "x"}]), "nenhum conteúdo/foto"),
    (lambda: _mexe(0, evidencias=[{"ref": "f", "sha256": "A" * 64}]), "sha256 inválido"),
    (lambda: _mexe(0, evidencias=[{"sha256": SHA}]), "sem ref"),
    (lambda: _mexe(0, evidencias="laudo"), "evidencias deve ser lista"),
    (lambda: _mexe(0, ficticio="sim"), "ficticio deve ser booleano"),
    (lambda: _mexe(0, responsavel="fulano"), "campo(s) desconhecido(s)"),
    (lambda: {"NC-1": {}}, "deve ser lista"),
    (lambda: ["texto"], "não é objeto"),
]


@pytest.mark.parametrize("fabrica, trecho", INVALIDOS, ids=[t for _, t in INVALIDOS])
def test_cadastro_invalido_e_recusado_e_422(fabrica, trecho):
    d = _dados(fabrica())
    with pytest.raises(NC.ErroNaoConformidade, match=None) as e:
        NC.carregar(Projeto(d))
    assert trecho in str(e.value), str(e.value)
    r = _cliente(d).get(ROTA, params={"obra": "x"})
    assert r.status_code == 422 and trecho in r.json()["detail"]


def test_todos_os_erros_sao_listados_de_uma_vez():
    ncs = _mexe(0, gravidade="x", situacao="y")
    _, erros = NC.validar(Projeto(_dados()), ncs)
    assert any("gravidade" in e for e in erros) and any("situacao" in e for e in erros)


@pytest.mark.parametrize("el", ["A-E01", "A-E7", "0aB_$" + "x" * 17])
def test_elemento_por_convencao_ou_globalid_e_aceito(el):
    assert NC.carregar(Projeto(_dados(_mexe(0, elemento_id=el))))[0]["elemento_id"] == el


# ------------------------------------------------------------------ rota: filtros e erros
def test_rota_filtros_lote_e_situacao():
    c = _cliente(_dados(_ncs()))
    j = c.get(ROTA, params={"obra": "x", "lote": "L2"}).json()
    assert sorted(n["id"] for n in j["nao_conformidades"]) == ["NC-2", "NC-4"]
    j = c.get(ROTA, params={"obra": "x", "situacao": "aberta"}).json()
    assert sorted(n["id"] for n in j["nao_conformidades"]) == ["NC-1", "NC-4"]


def test_rota_erros_404_e_422():
    c = _cliente(_dados(_ncs()))
    assert c.get(ROTA, params={"obra": "zz"}).status_code == 404
    assert c.get(ROTA, params={"obra": "x", "lote": "L9"}).status_code == 404
    r = c.get(ROTA, params={"obra": "x", "situacao": "fechada"})
    assert r.status_code == 422 and "situacao" in r.json()["detail"]


def test_openapi_documenta_404_e_422_e_tem_docstring():
    op = TestClient(criar_app()).get("/openapi.json").json()["paths"][ROTA]["get"]
    assert {"404", "422"} <= set(op["responses"]) and op.get("description")


# ------------------------------------------------------------------ exemplos sintéticos (ADR-0005)
def test_exemplos_so_em_obra_ficticia_e_marcados():
    P = Projeto.carregar(DATASET_PADRAO)
    ex = NC.exemplos_ficticios(P, executar(P, "independente"))
    assert [n["id"] for n in ex] == ["NC-FIC-001", "NC-FIC-002", "NC-FIC-003"]
    assert all(n["ficticio"] is True and n["origem"] == NC.ORIGEM_EXEMPLO and n["evidencias"] == [] for n in ex)
    assert NC.validar(P, ex)[1] == []                       # os exemplos passam na mesma validação
    j = TestClient(criar_app()).get(ROTA, params={"obra": "ferrovia", "exemplos": "true"}).json()
    assert j["fonte_das_ncs"] == "exemplos sintéticos"
    assert [v["id"] for v in j["vencidas"]] == ["NC-FIC-001"] and [a["nc_id"] for a in j["alertas"]] == ["NC-FIC-001"]


@pytest.mark.parametrize("marca", [False, "true", None])
def test_exemplos_em_obra_sem_a_marca_booleana_sao_recusados_409(marca):
    d = copy.deepcopy(json.loads(Path(DATASET_PADRAO).read_text(encoding="utf-8")))
    if marca is None:
        d["meta"].pop("ficticio")
    else:
        d["meta"]["ficticio"] = marca
    P = Projeto(d)
    with pytest.raises(NC.ExemploEmObraReal):
        NC.exemplos_ficticios(P, executar(P, "independente"))
    c = TestClient(criar_app(fontes={"x": P}))
    assert c.get(ROTA, params={"obra": "x", "exemplos": "true"}).status_code == 409
    assert c.get(ROTA, params={"obra": "x"}).status_code == 200   # sem exemplos: lista declarada (vazia)
