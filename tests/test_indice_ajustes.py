"""Índice de ajustes da simulação: mesmo resultado da varredura antiga (ordem preservada)."""

from infra4d.cenarios import Ajuste, Projeto, executar


def _antigo(ajustes, a):
    """Oráculo: a varredura linear original (o último ajuste aplicável vence)."""
    return [aj for aj in ajustes if aj.aplica_a(a)]


def test_indice_reproduz_a_ordem_da_varredura_linear():
    from infra4d.cenarios import _IndiceAjustes
    p = Projeto.carregar()
    ajustes = [
        Ajuste(produtividade=1000.0, servico_id="TER", lote_id="L3"),
        Ajuste(produtividade=1500.0, atividade_id="L3-S04-TER"),
        Ajuste(equipes=3, servico_id="TER"),
        Ajuste(produtividade=1200.0, atividade_id="L3-S04-TER"),
        Ajuste(produtividade=50.0, servico_id="DRE", lote_id="L1"),
    ]
    idx = _IndiceAjustes(ajustes)
    for a in p.dados["atividades"]:
        assert idx.para(a) == _antigo(ajustes, a), a["id"]


def test_simulado_com_ajustes_sobrepostos_da_o_mesmo_termino_que_aplicar_em_ordem():
    """O último ajuste vence: produtividade 1200 (por atividade) depois de 1000 (por serviço/lote)."""
    p = Projeto.carregar()
    r1 = executar(p, "simulado", [Ajuste(produtividade=1000.0, servico_id="TER", lote_id="L3"),
                                  Ajuste(produtividade=1200.0, atividade_id="L3-S04-TER")])
    assert r1["atividades"]["L3-S04-TER"]["memoria"]["produtividade"] == 1200.0
    assert r1["atividades"]["L3-S03-TER"]["memoria"]["produtividade"] == 1000.0
    r2 = executar(p, "simulado", [Ajuste(produtividade=1200.0, atividade_id="L3-S04-TER"),
                                  Ajuste(produtividade=1000.0, servico_id="TER", lote_id="L3")])
    assert r2["atividades"]["L3-S04-TER"]["memoria"]["produtividade"] == 1000.0
