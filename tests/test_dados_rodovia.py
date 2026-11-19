"""Base sintética da RODOVIA fictícia: determinística, coerente e consumível sem alteração do motor."""

import json
from collections import defaultdict

import pytest

from infra4d import painel
from infra4d.cenarios import Ajuste, Projeto, executar
from infra4d.calendario import ordinal
from infra4d.dados_sinteticos_rodovia import DATASET_RODOVIA, gerar

CHAVES_TOPO = {"meta", "ferrovia", "lotes", "segmentos", "servicos", "calendarios", "atividades",
               "relacoes", "restricoes", "oaes", "medicoes", "alinhamento"}


@pytest.fixture(scope="module")
def dados():
    return json.loads(DATASET_RODOVIA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def projeto(dados):
    return Projeto(dados)


@pytest.fixture(scope="module")
def resultados(projeto):
    return {c: executar(projeto, c) for c in ("linha_base", "construtora", "independente")}


def test_arquivo_versionado_e_identico_ao_gerador(dados):
    assert gerar() == dados, "rode: python -m infra4d.dados_sinteticos_rodovia"


def test_mesmo_esquema_da_ferrovia_e_tipo_declarado(dados):
    assert set(dados) == CHAVES_TOPO
    assert dados["meta"]["tipo_obra"] == "rodovia"
    assert dados["ferrovia"]["extensao_km"] == 48.0
    assert len(dados["alinhamento"]["pontos"]) == 481
    assert dados["alinhamento"]["pontos"][-1][0] == 48.0


def test_dados_marcados_como_ficticios(dados):
    assert dados["meta"]["ficticio"] is True          # marca booleana, não texto (revisão r6)
    assert "FICTÍCIOS" in dados["meta"]["aviso"]
    assert dados["medicoes"]
    assert all(m["origem"].startswith("SINTÉTICA") for m in dados["medicoes"])


def test_hierarquia_de_ids_consistente(dados):
    lotes = {l["id"] for l in dados["lotes"]}
    segs = {s["id"]: s for s in dados["segmentos"]}
    ids = {a["id"] for a in dados["atividades"]}
    assert len(ids) == len(dados["atividades"])
    assert all(s["lote_id"] in lotes for s in segs.values())
    for a in dados["atividades"]:
        if a.get("segmento_id"):
            assert segs[a["segmento_id"]]["lote_id"] == a["lote_id"]
            if a.get("servico_id") and not a["servico_id"].startswith("OAE"):
                assert a["id"] == f"{a['segmento_id']}-{a['servico_id']}"
    for r in dados["relacoes"]:
        assert r["predecessora"] in ids and r["sucessora"] in ids
    assert all(m["atividade_id"] in ids for m in dados["medicoes"])


def test_executado_e_a_soma_dos_boletins(dados):
    soma = defaultdict(float)
    for m in dados["medicoes"]:
        soma[m["atividade_id"]] += m["quantidade"]
    for a in dados["atividades"]:
        if a.get("quantidade_total") and a["status"] != "nao_iniciada":
            assert a["quantidade_executada"] == pytest.approx(soma[a["id"]], abs=0.01)
            assert a["quantidade_executada"] <= a["quantidade_total"] + 1e-6
            if a["status"] == "concluida":
                assert a["quantidade_executada"] == pytest.approx(a["quantidade_total"], abs=0.01)


def test_status_coerente_com_data_de_status(dados):
    ds = dados["meta"]["data_status"]
    assert {a["status"] for a in dados["atividades"]} == {"concluida", "em_andamento", "nao_iniciada"}
    for a in dados["atividades"]:
        if a["status"] == "concluida":
            assert a["termino_real"] < ds
        if a["status"] != "nao_iniciada":
            assert a["inicio_real"] < ds
        else:
            assert "inicio_real" not in a
    for m in dados["medicoes"]:
        assert m["semana_inicio"] < ds


def test_calendario_de_pavimentacao_mais_restritivo(dados):
    cal = {c["id"]: set(c["nao_uteis"]) for c in dados["calendarios"]}
    assert cal["CAL-TERRA"] < cal["CAL-PAV"], "imprimação/CBUQ param em toda chuva e mais"
    for a in dados["atividades"]:
        if a.get("servico_id") in ("IMP", "CBU"):
            assert a["calendario"] == "CAL-PAV"


def test_cenarios_em_ordem_plausivel(resultados):
    t = {c: r["termino"] for c, r in resultados.items()}
    assert t["linha_base"] <= t["construtora"] < t["independente"]


def test_narrativa_cbuq_critico_e_abaixo_do_planejado(projeto, resultados):
    ind = resultados["independente"]
    assert any(aid.endswith("-CBU") for aid in ind["cadeia_determinante"])
    altos = {a["atividade_id"] for a in painel.alertas(projeto, ind, resultados["construtora"])
             if a["nivel"] == "alto" and a["atividade_id"]}
    assert any(aid.startswith("L2-") and aid.endswith("-CBU") for aid in altos)


def test_painel_roda(projeto, resultados):
    ds = projeto.data_status
    av_real = painel.avanco(projeto, resultados["independente"], ds)
    av_lb = painel.avanco(projeto, resultados["linha_base"], ds)
    assert 0 < av_real < av_lb < 1
    assert painel.alertas(projeto, resultados["independente"], resultados["construtora"])
    cs = painel.curva_s(projeto, resultados, passo_dias=28)
    assert len(cs["datas"]) > 10
    for serie in cs["series"].values():
        assert serie == sorted(serie) and serie[-1] == pytest.approx(100.0)


def _quantidade_pendente(projeto, r, a_id):
    a = projeto.atividades[a_id]
    return a.get("quantidade_total") and r["status"] != "concluida" and r["memoria"].get("regra") == "quantidade"


def test_ajuste_em_atividade_critica_move_o_termino(projeto, resultados):
    ind = resultados["independente"]
    alvo = next(aid for aid in ind["cadeia_determinante"]
                if aid.endswith("-CBU") and _quantidade_pendente(projeto, ind["atividades"][aid], aid))
    prod = ind["atividades"][alvo]["memoria"]["produtividade"]
    sim = executar(projeto, "simulado", [Ajuste(produtividade=prod * 0.5, atividade_id=alvo)])
    assert ordinal(sim["termino"]) > ordinal(ind["termino"])
    sim2 = executar(projeto, "simulado", [Ajuste(produtividade=prod * 2, atividade_id=alvo)])
    assert ordinal(sim2["termino"]) < ordinal(ind["termino"])


def test_ajuste_em_atividade_com_folga_nao_move(projeto, resultados):
    ind = resultados["independente"]
    alvo = next(aid for aid, r in ind["atividades"].items()
                if aid.endswith("-DEF") and _quantidade_pendente(projeto, r, aid) and r["folga_total"] >= 30)
    r = ind["atividades"][alvo]
    # -20% de produtividade: alongamento muito menor que a folga
    sim = executar(projeto, "simulado", [Ajuste(produtividade=r["memoria"]["produtividade"] * 0.8, atividade_id=alvo)])
    assert sim["atividades"][alvo]["duracao"] > r["duracao"]
    assert sim["atividades"][alvo]["duracao"] - r["duracao"] < r["folga_total"]
    assert sim["termino"] == ind["termino"]


# ------------------------------------------------------------------ cadastro de serviços (as duas obras)
@pytest.mark.parametrize("arquivo", [DATASET_RODOVIA, DATASET_RODOVIA.parent / "ferrovia_ficticia.json"],
                         ids=["rodovia", "ferrovia"])
def test_todo_servico_de_atividade_esta_cadastrado(arquivo):
    d = json.loads(arquivo.read_text(encoding="utf-8"))
    serv = {s["id"]: s for s in d["servicos"]}
    assert len(serv) == len(d["servicos"]), "id de serviço repetido"
    usados = {a["servico_id"] for a in d["atividades"] if a.get("servico_id")}
    assert usados <= set(serv), f"sem cadastro: {sorted(usados - set(serv))}"
    for a in d["atividades"]:
        s = serv.get(a.get("servico_id"))
        if not s:
            continue
        assert s["disciplina"] and s["nome"] and s["unidade"] and s["equipamentos"]
        if "duracao_fixa" in a:            # SIN / LIB: duração fixa, sem produtividade
            assert s["produtividade_planejada"] is None and s["duracao_fixa_dias"] == a["duracao_fixa"]
        else:                              # a produtividade cadastrada é a que a atividade usa
            assert a["produtividade_planejada"] == s["produtividade_planejada"]
            assert a["unidade"] == s["unidade"]


@pytest.mark.parametrize("arquivo", [DATASET_RODOVIA, DATASET_RODOVIA.parent / "ferrovia_ficticia.json"],
                         ids=["rodovia", "ferrovia"])
def test_todo_calendario_declara_sensivel_chuva_booleano(arquivo):
    d = json.loads(arquivo.read_text(encoding="utf-8"))
    marca = {c["id"]: c.get("sensivel_chuva") for c in d["calendarios"]}
    assert all(v is True or v is False for v in marca.values()), marca
    esperado = {"CAL-TERRA"} | ({"CAL-PAV"} if d["meta"].get("tipo_obra") == "rodovia" else set())
    assert {k for k, v in marca.items() if v} == esperado


@pytest.mark.parametrize("arquivo, tipo", [(DATASET_RODOVIA, "rodovia"),
                                           (DATASET_RODOVIA.parent / "ferrovia_ficticia.json", "ferrovia")])
def test_tipo_obra_declarado_explicitamente(arquivo, tipo):
    """Nenhum consumidor deve depender de "ausência = ferrovia": as duas obras declaram meta.tipo_obra."""
    assert json.loads(arquivo.read_text(encoding="utf-8"))["meta"]["tipo_obra"] == tipo


# ------------------------------------------------------------------ P9: gabarito fora do dataset publicado
import importlib  # noqa: E402

GERADORES = {"ferrovia": "infra4d.dados_sinteticos", "rodovia": "infra4d.dados_sinteticos_rodovia"}


@pytest.mark.parametrize("obra", list(GERADORES))
def test_dataset_publicado_nao_contem_o_gabarito(obra):
    texto = (DATASET_RODOVIA.parent / f"{obra}_ficticia.json").read_text(encoding="utf-8")
    assert "fatores_desempenho" not in texto and "termino_realidade_simulada\"" not in texto
    meta = json.loads(texto)["meta"]
    assert "fatores_desempenho_simulados" not in meta and "gabarito" in meta["gabarito"]


@pytest.mark.parametrize("obra", list(GERADORES))
def test_gabarito_publicado_e_o_do_gerador_e_marcado_ficticio(obra):
    mod = importlib.import_module(GERADORES[obra])
    pub = json.loads(mod.GABARITO.read_text(encoding="utf-8"))
    meta = json.loads((DATASET_RODOVIA.parent / f"{obra}_ficticia.json").read_text(encoding="utf-8"))["meta"]
    assert pub == mod.gabarito(meta["semente"])
    assert pub["ficticio"] is True and "FICTÍCIO" in pub["aviso"]
    assert (pub["semente"], pub["gerador"], pub["obra"]) == (meta["semente"], meta["gerador"], obra)
    assert pub["termino_realidade_simulada"] == mod.realidade_simulada(meta["semente"])
    assert pub["fatores_desempenho_simulados"] and all(v > 0 for v in pub["fatores_desempenho_simulados"].values())


def test_acessor_unico_confere_marca_gerador_semente_e_arquivo(tmp_path, monkeypatch):
    from infra4d.sintetico_comum import ErroGabarito, gabarito
    mod = importlib.import_module(GERADORES["rodovia"])
    dados = json.loads(DATASET_RODOVIA.read_text(encoding="utf-8"))
    assert gabarito(dados) == json.loads(mod.GABARITO.read_text(encoding="utf-8"))
    for campo, valor, msg in (("ficticio", False, "ficticio"), ("gerador", "outro.py", "gerador desconhecido"),
                              ("semente", "x", "semente inválida")):
        d = {**dados, "meta": {**dados["meta"], campo: valor}}
        with pytest.raises(ErroGabarito, match=msg):
            gabarito(d)
    # arquivo adulterado (CÓPIA em tmp_path; o publicado não é tocado) -> recusado
    copia = tmp_path / "rodovia_gabarito.json"
    g = json.loads(mod.GABARITO.read_text(encoding="utf-8"))
    g["fatores_desempenho_simulados"] = {k: 1.0 for k in g["fatores_desempenho_simulados"]}
    copia.write_text(json.dumps(g), encoding="utf-8")
    monkeypatch.setattr(mod, "GABARITO", copia)
    with pytest.raises(ErroGabarito, match="não confere"):
        gabarito(dados)
    # mundo em memória (outra semente): o arquivo não se aplica; vale o recalculado pelo gerador
    outro = {**dados, "meta": {**dados["meta"], "semente": dados["meta"]["semente"] + 1}}
    assert gabarito(outro) == mod.gabarito(dados["meta"]["semente"] + 1)
