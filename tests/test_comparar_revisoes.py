"""Comparação de revisões de cronograma: casos mínimos à mão por tipo de mudança, atribuição por
efeito isolado + resíduo de interação, alertas, as duas obras (cenários e MSPDI/XER) e a rota."""

from __future__ import annotations

import base64
import copy
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from infra4d.calendario import Calendario
from infra4d.cenarios import Projeto, executar
from infra4d.comparar_revisoes import Versao, comparar_revisoes, versao_do_cenario, versao_importada
from infra4d.importadores import exportar_mspdi, importar_mspdi, importar_xer
from infra4d.importadores.xer_exportar import exportar_xer
from infra4d.motor import AtividadeCPM as A, Relacao as R
import infra4d.rotas_revisoes as rotas_rev

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = {o: RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json" for o in ("ferrovia", "rodovia")}
INI = date(2026, 3, 2).toordinal()  # segunda
CAL = Calendario("C", "seg-sex")


def d(t):
    return date.fromisoformat(t).toordinal()


def base() -> Versao:
    """M0 → A(3) → B(5) → C(4) → MF e A → D(2) → MF. Término 17/03/2026 (A 02–04, B 05–11, C 12–17)."""
    ativs = [A("M0", 0, "C", tipo="marco_inicio"), A("A", 3, "C"), A("B", 5, "C"), A("C", 4, "C"), A("D", 2, "C"),
             A("MF", 0, "C", tipo="marco_termino")]
    rels = [R("M0", "A"), R("A", "B"), R("B", "C"), R("C", "MF"), R("A", "D"), R("D", "MF")]
    return Versao(ativs, rels, {"C": CAL}, INI, None, rotulo="A")


def com(f) -> Versao:
    v = base().copia()
    v.rotulo = "B"
    f(v)
    return v


def ativ(v, i):
    return next(x for x in v.atividades if x.id == i)


def rel(v, p, s):
    return next(x for x in v.relacoes if (x.predecessora, x.sucessora) == (p, s))


def _set(obj, **kw):
    for k, val in kw.items():
        setattr(obj, k, val)


# (nome, alteração, tipo da mudança, Δ esperado em dias corridos, calculado à mão)
CASOS = [
    ("duração B 5→8", lambda v: _set(ativ(v, "B"), duracao=8), "atividade_modificada", 3),       # 17/03 → 20/03
    ("adiciona X(4) entre B e C", lambda v: (v.atividades.append(A("X", 4, "C")),
                                             v.relacoes.remove(rel(v, "B", "C")),
                                             v.relacoes.extend([R("B", "X"), R("X", "C")])),
     None, 6),                                                                                    # 17/03 + 4 d.u. = 23/03
    ("remove D (não crítica)", lambda v: (v.atividades.remove(ativ(v, "D")),
                                          v.relacoes.remove(rel(v, "A", "D")), v.relacoes.remove(rel(v, "D", "MF"))),
     "atividade_removida", 0),
    ("lag B→C 0→+2", lambda v: _set(rel(v, "B", "C"), lag=2), "relacao_alterada", 2),            # 19/03
    ("tipo B→C FS→SS", lambda v: _set(rel(v, "B", "C"), tipo="SS"), "relacao_alterada", -6),     # C 05–10/03; B segue até 11/03
    ("SNET em C 23/03", lambda v: _set(ativ(v, "C"), restricao_inicio=d("2026-03-23")), "atividade_modificada", 9),
    ("FNLT em C (não move o término)", lambda v: _set(ativ(v, "C"), restricao_termino=d("2026-03-31")),
     "atividade_modificada", 0),
    ("feriado em 10/03", lambda v: v.calendarios.update(C=Calendario("C", "seg-sex", nao_uteis={date(2026, 3, 10)})),
     "calendario", 1),
    # D termina 06/03 (sex); +5 d.u. = 09–13/03; C 16–19/03 → +2
    ("relação nova D→C FS+5", lambda v: v.relacoes.append(R("D", "C", "FS", 5)), "relacao_adicionada", 2),
]


@pytest.mark.parametrize("nome,alterar,tipo,delta", CASOS, ids=[c[0] for c in CASOS])
def test_mudanca_unica_a_mao(nome, alterar, tipo, delta):
    r = comparar_revisoes(base(), com(alterar))
    assert r["termino_a"] == "2026-03-17"
    assert r["delta_dias_corridos"] == delta, r["termino_b"]
    assert r["reconstrucao"]["confere_com_b"] is True
    if tipo:  # uma unidade só: efeito isolado = Δ e nenhum resíduo
        assert r["por_tipo"] == {tipo: 1}, r["por_tipo"]
        assert r["mudancas"][0]["efeito_isolado_dias"] == delta
        assert r["atribuicao"]["residuo_interacao"] == 0


def test_atividade_adicionada_leva_as_suas_relacoes():
    r = comparar_revisoes(base(), com(CASOS[1][1]))
    assert r["por_tipo"] == {"atividade_adicionada": 1, "relacao_removida": 1}
    add = next(m for m in r["mudancas"] if m["tipo"] == "atividade_adicionada")
    assert sorted(add["detalhe"]["relacoes"]) == ["B->X FS+0", "X->C FS+0"]
    rem = next(m for m in r["mudancas"] if m["tipo"] == "relacao_removida")
    # sozinha, X entra entre B e C (B→C ainda existe, mas X→C dirige): +6 (23/03)
    assert add["efeito_isolado_dias"] == 6
    # sozinha, a remoção de B→C solta C (começa em 02/03) e B passa a fechar o projeto em 11/03: −6
    assert rem["efeito_isolado_dias"] == -6
    # juntas valem +6: o resíduo de interação (+6) é declarado, não distribuído
    assert r["atribuicao"] == {**r["atribuicao"], "soma_efeitos_isolados": 0, "residuo_interacao": 6}


def test_status_e_data_de_status():
    """A concluída em 02–03/03 (1 dia antes) e data de status 04/03: B 04–10, C 11–16 → término 16/03 (−1)."""
    def alterar(v):
        _set(ativ(v, "M0"), status="concluida", inicio_real=INI, termino_real=INI)
        _set(ativ(v, "A"), status="concluida", inicio_real=INI, termino_real=d("2026-03-03"), duracao=0)
        v.data_status = d("2026-03-04")
    r = comparar_revisoes(base(), com(alterar), agrupar_progresso_=False)
    assert r["delta_dias_corridos"] == -1 and r["reconstrucao"]["confere_com_b"]
    assert r["por_tipo"] == {"atividade_modificada": 2, "data_status": 1}
    g = comparar_revisoes(base(), com(alterar))  # padrão: agrupado
    assert g["por_tipo"] == {"progresso": 1} and g["mudancas"][0]["efeito_isolado_dias"] == -1
    assert g["atribuicao"]["residuo_interacao"] == 0
    att = r["atribuicao"]
    assert att["soma_efeitos_isolados"] + att["residuo_interacao"] == -1


def test_interacao_entre_caminhos_paralelos():
    """Dois caminhos críticos iguais (P1 e P2, 5 d.u.): encurtar só um não muda o término (o outro dirige);
    os dois juntos antecipam 2 d.u. Efeitos isolados 0 + 0; o Δ inteiro é RESÍDUO de interação."""
    def v0():
        return Versao([A("P1", 5, "C"), A("P2", 5, "C"), A("F", 0, "C", tipo="marco_termino")],
                      [R("P1", "F"), R("P2", "F")], {"C": CAL}, INI, rotulo="A")
    vb = v0()
    ativ(vb, "P1").duracao = 3
    ativ(vb, "P2").duracao = 3
    r = comparar_revisoes(v0(), vb)
    assert r["delta_dias_corridos"] == -2  # 06/03 → 04/03
    assert [m["efeito_isolado_dias"] for m in r["mudancas"]] == [0, 0]
    assert r["atribuicao"] == {**r["atribuicao"], "soma_efeitos_isolados": 0, "residuo_interacao": -2}


def test_efeito_isolado_incalculavel_e_declarado():
    """Relação nova que fecha um ciclo sozinha (só é válida junto com a remoção de outra)."""
    def alterar(v):
        v.relacoes.remove(rel(v, "A", "B"))
        v.relacoes.append(R("B", "A"))
        ativ(v, "M0")  # noqa
        v.relacoes.remove(rel(v, "M0", "A"))
        v.relacoes.append(R("M0", "B"))
    r = comparar_revisoes(base(), com(alterar))
    assert r["reconstrucao"]["confere_com_b"] is True
    sem = r["atribuicao"]["sem_efeito_calculavel"]
    assert sem and all(m["erro_isolado"] for m in r["mudancas"] if m["id"] in sem)


# ------------------------------------------------------------------ alertas
@pytest.mark.parametrize("alterar,tipo", [
    (lambda v: _set(rel(v, "B", "C"), lag=-1), "lag_negativo_novo"),
    (lambda v: _set(ativ(v, "C"), restricao_inicio=d("2026-03-23")), "restricao_nova_no_caminho_critico"),
    (lambda v: _set(ativ(v, "B"), duracao=3), "duracao_critica_encurtada_sem_progresso"),
    (lambda v: v.relacoes.remove(rel(v, "B", "C")), "relacao_critica_removida"),
])
def test_alertas(alterar, tipo):
    r = comparar_revisoes(base(), com(alterar))
    assert [a["tipo"] for a in r["alertas"]] == [tipo]


def test_sem_alerta_quando_a_mudanca_e_legitima():
    # encurtar D (não crítica) ou encurtar B JÁ em andamento não são alertas
    assert comparar_revisoes(base(), com(lambda v: _set(ativ(v, "D"), duracao=1)))["alertas"] == []
    assert comparar_revisoes(base(), com(lambda v: _set(rel(v, "B", "C"), lag=1)))["alertas"] == []


# ------------------------------------------------------------------ obras
@pytest.fixture(scope="module")
def projetos():
    return {o: Projeto.carregar(p) for o, p in OBRAS.items()}


@pytest.mark.parametrize("obra", list(OBRAS))
@pytest.mark.parametrize("a,b", [("linha_base", "construtora"), ("construtora", "independente")])
def test_obras_reconstrucao_e_soma(projetos, obra, a, b):
    p = projetos[obra]
    r = comparar_revisoes(versao_do_cenario(p, a), versao_do_cenario(p, b))
    assert r["termino_a"] == executar(p, a)["termino"] and r["termino_b"] == executar(p, b)["termino"]
    assert r["reconstrucao"]["confere_com_b"] is True
    att = r["atribuicao"]
    soma = sum(m["efeito_isolado_dias"] for m in r["mudancas"] if m["efeito_isolado_dias"] is not None)
    assert att["soma_efeitos_isolados"] == soma
    assert soma + att["residuo_interacao"] == r["delta_dias_corridos"]
    assert r["custo"]["execucoes_do_motor"] == r["n_mudancas"] + 3
    assert r["custo"]["segundos"] > 0


@pytest.mark.parametrize("obra", list(OBRAS))
def test_versoes_importadas_dao_a_mesma_comparacao(projetos, obra):
    p = projetos[obra]
    lb, co = executar(p, "linha_base"), executar(p, "construtora")
    va = versao_importada(importar_mspdi(exportar_mspdi(p, lb)), "LB")
    vb = versao_importada(importar_xer(exportar_xer(p, co).encode()), "construtora")
    via_arquivo = comparar_revisoes(va, vb)
    direto = comparar_revisoes(versao_do_cenario(p, "linha_base"), versao_do_cenario(p, "construtora"))
    assert (via_arquivo["termino_a"], via_arquivo["termino_b"]) == (direto["termino_a"], direto["termino_b"])
    ids = lambda r: {m["id"]: m["efeito_isolado_dias"] for m in r["mudancas"] if not m["id"].startswith("cal:")}
    assert ids(via_arquivo) == ids(direto)


# ------------------------------------------------------------------ rota
@pytest.fixture
def cliente(projetos):
    class E:
        def __init__(self, p):
            self.projeto, self.ajustes = p, []

    est = {o: E(p) for o, p in projetos.items()}

    def obter(obra=None):
        obra = obra or "ferrovia"
        if obra not in est:
            raise HTTPException(404, "obra desconhecida")
        return est[obra]

    app = FastAPI()
    rotas_rev.ligar(app, obter)
    return TestClient(app)


def test_rota_get_e_post(cliente, projetos):
    r = cliente.get("/api/revisoes/comparar", params={"obra": "rodovia"})
    assert r.status_code == 200 and r.json()["reconstrucao"]["confere_com_b"]
    assert cliente.get("/api/revisoes/comparar", params={"a": "x"}).status_code == 422
    assert cliente.get("/api/revisoes/comparar", params={"obra": "zz"}).status_code == 404
    p = projetos["ferrovia"]
    corpo = {"a": {"conteudo": exportar_mspdi(p, executar(p, "linha_base"))},
             "b": {"conteudo_base64": base64.b64encode(exportar_xer(p, executar(p, "construtora")).encode()).decode()}}
    r2 = cliente.post("/api/revisoes/comparar", json=corpo)
    assert r2.status_code == 200, r2.text
    assert r2.json()["termino_b"] == executar(p, "construtora")["termino"]
    misto = cliente.post("/api/revisoes/comparar", json={"a": {"cenario": "construtora"},
                                                         "b": {"conteudo": corpo["a"]["conteudo"]}})
    assert misto.status_code == 200 and misto.json()["termino_b"] == executar(p, "linha_base")["termino"]
    assert cliente.post("/api/revisoes/comparar", content=b"nao json").status_code == 422
    assert cliente.post("/api/revisoes/comparar", json={"a": {}}).status_code == 422
    assert cliente.post("/api/revisoes/comparar", json={"a": {"conteudo": "lixo"}, "b": {"cenario": "linha_base"}}
                        ).status_code == 415
    assert cliente.post("/api/revisoes/comparar", json={"a": {"conteudo_base64": "@@"}, "b": {"cenario": "linha_base"}}
                        ).status_code == 422
    assert cliente.post("/api/revisoes/comparar", json={"a": {"conteudo": "<Project"}, "b": {"cenario": "linha_base"}}
                        ).status_code == 422


def test_duas_atividades_adicionadas_ligadas_entre_si():
    """X e Y novas, B → X → Y → C: a relação X→Y pertence a uma das duas e entra quando ambas existem."""
    def alterar(v):
        v.atividades += [A("X", 2, "C"), A("Y", 3, "C")]
        v.relacoes += [R("B", "X"), R("X", "Y"), R("Y", "C")]
    r = comparar_revisoes(base(), com(alterar))
    assert r["delta_dias_corridos"] == 7  # +5 d.u.: C 19–24/03
    assert r["reconstrucao"]["confere_com_b"] is True
    rels = sorted(x for m in r["mudancas"] if m["tipo"] == "atividade_adicionada" for x in m["detalhe"]["relacoes"])
    assert rels == ["B->X FS+0", "X->Y FS+0", "Y->C FS+0"]


def test_encurtar_critica_ja_em_andamento_nao_e_alerta():
    """B em andamento com remanescente menor que a duração original: há progresso medido, não é alerta."""
    def alterar(v):
        _set(ativ(v, "M0"), status="concluida", inicio_real=INI, termino_real=INI)
        _set(ativ(v, "A"), status="concluida", inicio_real=INI, termino_real=d("2026-03-04"), duracao=0)
        _set(ativ(v, "B"), status="em_andamento", inicio_real=d("2026-03-05"), duracao=2)
        v.data_status = d("2026-03-09")
    r = comparar_revisoes(base(), com(alterar))
    assert not [a for a in r["alertas"] if a["tipo"] == "duracao_critica_encurtada_sem_progresso"]


@pytest.mark.parametrize("obra", list(OBRAS))
def test_modo_agrupado_e_detalhado_reconstroem_e_somam(projetos, obra):
    p = projetos[obra]
    va, vb = versao_do_cenario(p, "linha_base"), versao_do_cenario(p, "construtora")
    det = comparar_revisoes(va, vb, agrupar_progresso_=False)
    agr = comparar_revisoes(va, vb)
    for r in (det, agr):
        assert r["reconstrucao"]["confere_com_b"] is True
        assert r["atribuicao"]["soma_efeitos_isolados"] + r["atribuicao"]["residuo_interacao"] == r["delta_dias_corridos"]
    assert (det["modo"], agr["modo"]) == ("detalhado", "agrupado")
    grupo = next(m for m in agr["mudancas"] if m["id"] == "grupo:progresso")
    membros = set(grupo["detalhe"]["membros"])
    assert "param:data_status" in membros
    assert {m["id"] for m in det["mudancas"]} == membros | {m["id"] for m in agr["mudancas"] if m["id"] != "grupo:progresso"}
    # o pacote "data de status + progresso" tem efeito do tamanho do Δ, não +279 com resíduo −318
    assert abs(agr["atribuicao"]["residuo_interacao"]) < abs(det["atribuicao"]["residuo_interacao"])
    assert agr["n_mudancas"] < det["n_mudancas"]


def test_construtora_x_independente_nao_tem_grupo(projetos):
    p = projetos["ferrovia"]
    r = comparar_revisoes(versao_do_cenario(p, "construtora"), versao_do_cenario(p, "independente"))
    assert "progresso" not in r["por_tipo"]  # só durações mudaram: nada a agrupar

# ------------------------------------------------------------------ revisão r16 (regressões próprias)
@pytest.mark.parametrize("alterar,tipo", [
    (lambda v: (_set(rel(v, "B", "C"), lag=-1)), None),  # A tem lag 0: é lead NOVO (outro alerta)
    (lambda v: v.calendarios.update(S=Calendario("S", "seg-sab", (0, 1, 2, 3, 4, 5))) or _set(ativ(v, "B"), calendario="S"),
     "calendario_trocado_em_atividade_critica"),
])
def test_alertas_novos_r16(alterar, tipo):
    r = comparar_revisoes(base(), com(alterar))
    if tipo:
        assert tipo in [a["tipo"] for a in r["alertas"]]


def test_lead_aumentado_e_lag_reduzido_em_relacao_critica():
    def a_com(lag):
        v = base()
        rel(v, "B", "C").lag = lag
        return v
    r = comparar_revisoes(a_com(-1), (lambda v: (_set(rel(v, "B", "C"), lag=-3), v)[1])(a_com(-1)))
    assert [a["tipo"] for a in r["alertas"]] == ["lead_aumentado"]
    r = comparar_revisoes(a_com(4), (lambda v: (_set(rel(v, "B", "C"), lag=1), v)[1])(a_com(4)))
    assert [a["tipo"] for a in r["alertas"]] == ["lag_reduzido_em_relacao_critica"]


def test_duracao_encurtada_por_medicao_nao_e_alerta_e_texto_nao_afirma():
    v_manual = com(lambda v: _set(ativ(v, "B"), duracao=3))
    r = comparar_revisoes(base(), v_manual)
    msg = [a["mensagem"] for a in r["alertas"] if a["tipo"] == "duracao_critica_encurtada_sem_progresso"][0]
    assert "sem medição que justifique" not in msg and "confira" in msg
    v_medida = com(lambda v: _set(ativ(v, "B"), duracao=3))
    v_medida.duracao_por_medicao = True  # B veio do cenário independente: duração por produtividade medida
    assert not [a for a in comparar_revisoes(base(), v_medida)["alertas"]
                if a["tipo"] == "duracao_critica_encurtada_sem_progresso"]


def test_independente_em_duas_datas_sem_alerta_alto(projetos):
    from infra4d.tendencia import fotografia
    p = projetos["ferrovia"]
    a = versao_do_cenario(Projeto(fotografia(p.dados, p.data_status - 140)), "independente")
    r = comparar_revisoes(a, versao_do_cenario(p, "independente"))
    assert [x for x in r["alertas"] if x["gravidade"] == "alta"] == []


def test_teto_de_efeitos_isolados():
    from infra4d.comparar_revisoes import ErroComparacao
    vb = com(lambda v: (_set(ativ(v, "B"), duracao=8), _set(ativ(v, "C"), duracao=6)))
    with pytest.raises(ErroComparacao, match="teto"):
        comparar_revisoes(base(), vb, max_efeitos=1)
    assert comparar_revisoes(base(), vb, efeitos_isolados=False, max_efeitos=1)["atribuicao"] is None


@pytest.mark.parametrize("valor", ['"false"', '"0"', "0", "null", '"não"'])
def test_post_so_aceita_booleano_json(cliente, valor):
    lados = '"a":{"cenario":"linha_base"},"b":{"cenario":"construtora"}'
    for chave in ("efeitos_isolados", "agrupar_progresso"):
        r = cliente.post("/api/revisoes/comparar", content=("{" + lados + f',"{chave}":{valor}}}').encode())
        assert r.status_code == 422 and chave in r.json()["detail"]
    ok = cliente.post("/api/revisoes/comparar", content=("{" + lados + ',"efeitos_isolados":false}').encode())
    assert ok.status_code == 200 and ok.json()["atribuicao"] is None
