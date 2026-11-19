"""Sensibilidade do término (tornado): rede pequena calculada à mão e as duas obras fictícias."""

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.calendario import ordinal
from infra4d.cenarios import DATASET_PADRAO, Projeto
from infra4d.sensibilidade import ErroSensibilidade, tornado

OBRAS = {"ferrovia": DATASET_PADRAO, "rodovia": DATASET_PADRAO.parent / "rodovia_ficticia.json"}


def _rede(qtd_a=100.0, qtd_b=90.0, qtd_c=20.0):
    """Calendário corrido (7 dias): A, B e C em paralelo até o marco. Produtividade 10 un/dia, 1 equipe."""
    def t(aid, lote, serv, q):
        return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": lote, "servico_id": serv,
                "quantidade_total": q, "produtividade_planejada": 10.0, "equipes": 1, "calendario": "C",
                "status": "nao_iniciada"}
    ativs = [t("A", "L1", "X", qtd_a), t("B", "L2", "Y", qtd_b), t("C", "L1", "Z", qtd_c),
             {"id": "M", "nome": "fim", "tipo": "marco_termino", "calendario": "C", "status": "nao_iniciada"}]
    return Projeto({"meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "C"},
                    "lotes": [{"id": "L1"}, {"id": "L2"}],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                    "servicos": [], "atividades": ativs, "medicoes": [],
                    "relacoes": [{"predecessora": x, "sucessora": "M", "tipo": "FS", "lag": 0} for x in "ABC"]})


def _por_grupo(r):
    return {(g["lote_id"], g["servico_id"]): g for g in r["grupos"]}


def test_rede_a_mao_critico_folga_proxima_e_folga_grande():
    r = tornado(_rede(), p=0.2, equipes=1)
    assert r["termino_referencia"] == "2026-01-14"                 # A: 100/10 = 10 dias
    g = _por_grupo(r)
    a, b, c = g[("L1", "X")], g[("L2", "Y")], g[("L1", "Z")]
    # A: +20% → ceil(100/12)=9, mas B (9 dias) passa a determinar: −1; −20% → ceil(100/8)=13: +3
    assert (a["melhorar"]["delta_dias_uteis"], a["piorar"]["delta_dias_uteis"]) == (-1, 3)
    assert a["assimetrico"] and not a["efeito_zero"] and a["amplitude_dias_uteis"] == 4
    # B (folga 1): +20% → 8 dias, não antecipa; −20% → ceil(90/8)=12: +2
    assert (b["melhorar"]["delta_dias_uteis"], b["piorar"]["delta_dias_uteis"]) == (0, 2)
    assert b["assimetrico"]
    # C (folga 8): nada muda
    assert c["efeito_zero"] and c["amplitude_dias_uteis"] == 0 and not c["assimetrico"]
    # +1 equipe: A 5 dias (B determina: −1); B não antecipa; C nada
    assert [x["equipes"]["delta_dias_uteis"] for x in (a, b, c)] == [-1, 0, 0]
    assert [(x["lote_id"], x["servico_id"]) for x in r["grupos"]] == [("L1", "X"), ("L2", "Y"), ("L1", "Z")]
    assert r["execucoes_motor"] == 1 + 3 * 3


def test_simetria_quando_so_um_caminho_determina():
    r = tornado(_rede(qtd_a=120.0), p=0.2)
    a = _por_grupo(r)[("L1", "X")]
    # 12 dias → ceil(120/12)=10 (−2) e ceil(120/8)=15 (+3): só a forma 1/(1±p), sem outro caminho
    assert (a["melhorar"]["delta_dias_uteis"], a["piorar"]["delta_dias_uteis"]) == (-2, 3)
    assert not a["assimetrico"]


def test_explicacao_vem_dos_numeros():
    g = _por_grupo(tornado(_rede(), p=0.2))
    a, c = g[("L1", "X")], g[("L1", "Z")]
    assert "caminho determinante" in a["explicacao"]
    assert "antecipa 1 dia útil" in a["explicacao"] and "atrasa 3 dias úteis" in a["explicacao"]
    assert "Assimétrico" in a["explicacao"] and "+1 equipe: antecipa 1 dia útil" in a["explicacao"]
    assert "fora do caminho crítico (menor folga total: 8 dias úteis)" in c["explicacao"]
    assert "A folga absorve ±20%" in c["explicacao"]


def test_p_zero_da_delta_zero_em_tudo():
    for projeto in (_rede(), Projeto.carregar(OBRAS["rodovia"])):
        r = tornado(projeto, p=0.0, equipes=0)
        assert r["grupos"] and all(g["efeito_zero"] for g in r["grupos"])
        assert all("equipes" not in g for g in r["grupos"])


@pytest.mark.parametrize("p, equipes", [(-0.1, 1), (1.0, 1), (0.1, -1), (0.1, 11), (0.1, 1.5), ("0.1", 1)])
def test_parametros_invalidos(p, equipes):
    with pytest.raises(ErroSensibilidade):
        tornado(_rede(), p=p, equipes=equipes)


@pytest.fixture(scope="module", params=list(OBRAS))
def obra(request):
    projeto = Projeto.carregar(OBRAS[request.param])
    return request.param, projeto, tornado(projeto)


def test_obras_tornado_ordenado_e_consistente(obra):
    nome, projeto, r = obra
    amps = [g["amplitude_dias_uteis"] for g in r["grupos"]]
    assert amps == sorted(amps, reverse=True) and amps[0] > 0
    assert r["execucoes_motor"] == 1 + 3 * len(r["grupos"])
    ref = ordinal(r["termino_referencia"])
    for g in r["grupos"]:
        for k in ("melhorar", "piorar", "equipes"):
            assert ordinal(g[k]["termino"]) - ref == g[k]["delta_dias_corridos"]
            assert (g[k]["delta_dias_uteis"] == 0) == (g[k]["delta_dias_corridos"] == 0)
            if abs(g[k]["delta_dias_corridos"]) >= 7:      # calendário da obra 6x1: úteis < corridos
                assert 0 < abs(g[k]["delta_dias_uteis"]) < abs(g[k]["delta_dias_corridos"])
        pendentes = [projeto.atividades[i] for i in g["atividades"]]
        assert all(a["status"] != "concluida" and a["quantidade_total"] for a in pendentes)
        assert g["efeito_zero"] == (g["amplitude_dias_uteis"] == 0 and g["melhorar"]["delta_dias_corridos"] == 0
                                    and g["piorar"]["delta_dias_corridos"] == 0)
    topo = r["grupos"][0]
    assert topo["no_caminho_determinante"]
    assert topo["servico_id"] == {"ferrovia": "TER", "rodovia": "CBU"}[nome]


def test_ferrovia_mostra_o_reverso_declarado():
    g = _por_grupo(tornado(Projeto.carregar(OBRAS["ferrovia"])))[("L3", "DOR")]
    assert g["reverso"] and g["piorar"]["delta_dias_uteis"] < 0 and "reverso" in g["explicacao"]


def test_api_com_cache_e_tempo():
    c = TestClient(criar_app(fontes={"rodovia": Projeto.carregar(OBRAS["rodovia"])}))
    assert "rotas_sensibilidade" in c.app.state.rotas_ligadas
    r1 = c.get("/api/sensibilidade", params={"obra": "rodovia", "p": 0.1, "equipes": 1}).json()
    r2 = c.get("/api/sensibilidade", params={"obra": "rodovia", "p": 0.1, "equipes": 1}).json()
    assert r1["cache"] is False and r2["cache"] is True and r1["grupos"] == r2["grupos"]
    assert r1["tempo_s"] > 0
    assert c.get("/api/sensibilidade", params={"obra": "rodovia", "p": 0.2}).json()["cache"] is False
    for params, codigo in (({"p": 1}, 422), ({"p": -0.1}, 422), ({"equipes": 11}, 422), ({"obra": "zz"}, 404)):
        assert c.get("/api/sensibilidade", params={"obra": "rodovia", **params}).status_code == codigo


# ------------------------------------------------------------------ revisão r11: horizonte do calendário
def test_grupo_que_passa_do_horizonte_fica_marcado_e_vai_ao_topo():
    """A: 50.000 un a 10/dia = 5.000 dias (até ~2039). −20% → 6.250 dias: passa de 2040 (horizonte)."""
    r = tornado(_rede(qtd_a=50000.0), p=0.2, equipes=1)
    topo = r["grupos"][0]
    assert (topo["lote_id"], topo["servico_id"]) == ("L1", "X")
    assert topo["fora_do_horizonte"] and topo["piorar"]["fora_do_horizonte"]
    assert topo["piorar"]["delta_dias_uteis"] is None and topo["amplitude_dias_uteis"] is None
    assert not (topo["efeito_zero"] or topo["reverso"] or topo["assimetrico"])
    assert topo["melhorar"]["delta_dias_uteis"] < 0          # melhorar continua calculado
    assert "horizonte do calendário" in topo["explicacao"]
    assert r["n_fora_do_horizonte"] == 1
    assert all(not g["fora_do_horizonte"] and g["amplitude_dias_uteis"] is not None for g in r["grupos"][1:])


def test_referencia_fora_do_horizonte_e_erro_de_sensibilidade():
    with pytest.raises(ErroSensibilidade, match="independente"):
        tornado(_rede(qtd_a=1e6), p=0.1)


def test_api_p_alto_responde_200_com_grupos_marcados():
    c = TestClient(criar_app(fontes={"ferrovia": Projeto.carregar(OBRAS["ferrovia"])}))
    j = c.get("/api/sensibilidade", params={"obra": "ferrovia", "p": 0.99, "equipes": 0})
    assert j.status_code == 200
    j = j.json()
    assert j["n_fora_do_horizonte"] > 0
    n = j["n_fora_do_horizonte"]
    assert all(g["fora_do_horizonte"] for g in j["grupos"][:n]) and not any(g["fora_do_horizonte"] for g in j["grupos"][n:])
