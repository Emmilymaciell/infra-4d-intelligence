"""Boletim com produtividade implausível não pode virar 500 (achado da revisão r17, medido pela pesquisa-verificada).

Um boletim ínfimo (0,001 un em 500 equipe·dias) faz a produtividade medida ~2e-6, a duração explode e o motor
sai do horizonte do calendário. Isso é erro do dado: a API responde 422 com o motivo, em qualquer rota.
"""

from fastapi.testclient import TestClient

from infra4d import api


def _app_com_boletim_infimo():
    app = api.criar_app()
    est = app.state.obter_estado(None)
    dados = est.projeto.dados
    ativ = next(a for a in dados["atividades"]
                if a.get("status") == "em_andamento" and a.get("quantidade_total") and a.get("servico_id"))
    base = next(m for m in dados["medicoes"] if m["atividade_id"] == ativ["id"])
    # todos os boletins da atividade viram um só, ínfimo: produtividade medida ~2e-6
    dados["medicoes"] = [m for m in dados["medicoes"] if m["atividade_id"] != ativ["id"]]
    dados["medicoes"].append({**base, "quantidade": 0.001, "equipes_dias": 500})
    # o Projeto indexa na criação: recria para a mutação valer, e limpa o cache (contrato de ARQUITETURA §3)
    est.projeto = type(est.projeto)(dados)
    est.cache.clear()
    return app


def test_cenario_independente_com_boletim_infimo_responde_422_e_nao_500():
    c = TestClient(_app_com_boletim_infimo(), raise_server_exceptions=False)
    for rota in ("/api/cenarios/independente", "/api/painel"):
        r = c.get(rota)
        assert r.status_code == 422, (rota, r.status_code, r.text[:300])  # o dado de fato estoura o horizonte
        assert "horizonte" in r.json()["detail"]
