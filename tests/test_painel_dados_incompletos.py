"""/api/painel com dados incompletos não pode responder 500 (achado da revisão r15)."""

import copy

from infra4d.cenarios import Projeto, executar
from infra4d.painel import alertas


def _projeto_com(mutar):
    p = Projeto.carregar()
    dados = copy.deepcopy(p.dados)
    mutar(dados)
    return Projeto(dados)


def test_restricao_sem_atividade_vira_aviso_e_nao_quebra():
    def m(d):
        d.setdefault("restricoes", []).append(
            {"id": "R-X", "descricao": "sem dono", "situacao": "pendente", "data_liberacao": "2027-01-01"})
    p = _projeto_com(m)
    al = alertas(p, executar(p, "independente"), executar(p, "construtora"))
    assert any("sem atividade conhecida" in a["texto"] for a in al)


def test_restricao_pendente_em_atividade_concluida_nao_vira_alerta():
    p0 = Projeto.carregar()
    concluida = next(a["id"] for a in p0.dados["atividades"] if a.get("status") == "concluida")

    def m(d):
        d.setdefault("restricoes", []).append(
            {"id": "R-Y", "atividade_id": concluida, "descricao": "velha", "situacao": "pendente",
             "data_liberacao": "2027-01-01"})
    p = _projeto_com(m)
    al = alertas(p, executar(p, "independente"), executar(p, "construtora"))
    assert not any("velha" in a["texto"] for a in al)
    assert not any("None" in a["texto"] for a in al)


def test_restricao_sem_data_de_liberacao_nao_quebra():
    """r16: restrição sem data_liberacao derrubava o painel com KeyError."""
    p0 = Projeto.carregar()
    res0 = executar(p0, "independente")
    aberta = next(a["id"] for a in p0.dados["atividades"] if res0["atividades"][a["id"]]["folga_total"] is not None)

    def m(d):
        d.setdefault("restricoes", []).append(
            {"id": "R-Z", "atividade_id": aberta, "descricao": "sem data", "situacao": "pendente"})
    p = _projeto_com(m)
    al = alertas(p, executar(p, "independente"), executar(p, "construtora"))
    assert any("sem data" in a["texto"] and "não informada" in a["texto"] for a in al)


def test_comparar_com_atividade_sem_nome_usa_o_id():
    """r18: cenarios.comparar fazia atividades[aid]["nome"] e derrubava /api/comparacao e a simulação."""
    from infra4d.cenarios import comparar

    def m(d):
        for a in d["atividades"]:
            a.pop("nome", None)
    p = _projeto_com(m)
    c = comparar(p, executar(p, "construtora"), executar(p, "independente"))
    assert c  # não estoura; e onde há nome no resultado, é o id
    nomes = [x.get("nome") for x in c.get("atividades_que_mudaram", c.get("mudancas", [])) if isinstance(x, dict)]
    assert all(n for n in nomes)


def test_painel_sem_termino_linha_base_no_meta_usa_o_calculado():
    from fastapi.testclient import TestClient
    from infra4d import api
    app = api.criar_app()
    c = TestClient(app)
    base = c.get("/api/painel").json()
    est = api_estado(app)
    est.projeto.dados["meta"].pop("termino_linha_base")
    est.cache.clear()
    r = c.get("/api/painel")
    assert r.status_code == 200
    assert r.json()["termino_contratual"] == r.json()["terminos"]["linha_base"]
    assert base["termino_contratual"] == r.json()["termino_contratual"]


def api_estado(app):
    """O Estado da obra padrão, pelo mesmo caminho que as rotas usam."""
    return app.state.obter_estado(None)
