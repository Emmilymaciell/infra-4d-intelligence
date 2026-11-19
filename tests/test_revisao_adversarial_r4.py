"""Revisão adversarial — rodada 4: FNLT, lógica retida, relatório HTML e isolamento entre obras.

Mesmo protocolo: esperado calculado à mão no docstring. Os 5 casos que nasceram como
``xfail(strict=True)`` (5 defeitos) foram corrigidos e viraram REGRESSÃO normal.

Calendários: c5 = seg–sex; c6 = seg–sáb; cF = seg–sex com feriados em 07, 08, 19,
20 e 21/01/2026. 2026-01-05 é segunda. Status de teste: qua 14/01.
"""

import copy
import random
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from infra4d.calendario import Calendario
from infra4d.cenarios import Projeto
from infra4d.motor import AtividadeCPM as A
from infra4d.motor import ErroRede, Relacao as R, calcular

SEG = date(2026, 1, 5).toordinal()
DS = date(2026, 1, 14).toordinal()
CALS = {
    "c5": Calendario("c5", "5 dias"),
    "c6": Calendario("c6", "6 dias", (0, 1, 2, 3, 4, 5)),
    "cF": Calendario("cF", "5 dias com feriados", (0, 1, 2, 3, 4), frozenset(
        {date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 19), date(2026, 1, 20), date(2026, 1, 21)})),
}


def o(s):
    return date.fromisoformat(s).toordinal()


def rodar(ativs, rels, **kw):
    res = calcular(ativs, rels, CALS, SEG, **kw)
    by = {a.id: a for a in ativs}
    return res, {k: v.como_dict(CALS[by[k].calendario], by[k]) for k, v in res.atividades.items()}


def termino_iso(res):
    return date.fromordinal(res.termino_projeto_data).isoformat()


def _clone(b, **kw):
    d = dict(b.__dict__)
    d.update(kw)
    return A(**d)


def _rede(rng, calendarios, com_progresso, com_fnlt):
    """Só TAREFAS com trabalho (instantes têm defeitos próprios, ver xfail)."""
    n = rng.randint(2, 5)
    ativs = []
    for i in range(n):
        c = rng.choice(calendarios)
        x = rng.random() if com_progresso else 1.0
        if x < 0.15:
            ativs.append(A(f"N{i}", 0, c, status="concluida", inicio_real=SEG, termino_real=SEG + rng.randint(0, 8)))
        elif x < 0.40:
            ativs.append(A(f"N{i}", rng.randint(1, 6), c, status="em_andamento", inicio_real=SEG + rng.randint(0, 8)))
        else:
            ativs.append(A(f"N{i}", rng.randint(1, 6), c))
        if com_fnlt and ativs[-1].status != "concluida" and rng.random() < 0.3:
            ativs[-1].restricao_termino = (DS if com_progresso else SEG) + rng.randint(0, 25)
    rels, vistos = [], set()
    for j in range(1, n):
        for i in rng.sample(range(j), min(j, rng.randint(1, 2))):
            t = rng.choice(["FS", "SS", "FF", "SF"])
            if (i, j, t) not in vistos:
                vistos.add((i, j, t))
                rels.append(R(f"N{i}", f"N{j}", t, rng.randint(-3, 4)))
    return ativs, rels


def _violadas(ativs, res):
    """Atividades cujo EF passa do FNLT, em tempo de trabalho do seu calendário."""
    return {a.id for a in ativs if a.restricao_termino is not None and a.status != "concluida"
            and CALS[a.calendario].dias_uteis_entre(a.restricao_termino + 1, res.atividades[a.id].ef) > 0}


def _com_folga_consumida(ativs, a, x, k):
    c = CALS[a.calendario]
    if a.status == "nao_iniciada":
        return [_clone(b, restricao_inicio=c.proximo_util(c.somar(x.es, k))) if b.id == a.id else b for b in ativs]
    return [_clone(b, duracao=b.duracao + k) if b.id == a.id else b for b in ativs]


# =============================================================================
# 1. FNLT ("término não depois de")
# =============================================================================
def test_fnlt_casos_basicos():
    """A(5) seg5–sex9 (EF sáb10), B(8) seg5–qua14 (EF qui15) = término.
    FNLT de A em ter 13/01 (folgado): LF = qua14 -> folga = seg12, ter13 = 2 (sem FNLT seria 3).
    FNLT em qua 07/01 (apertado): LF = qui8 -> folga = −(qui8, sex9) = −2; ES/EF não mudam.
    FNLT em sáb 10/01 com A sozinha: LF ajustado = sáb10 = EF -> folga 0."""
    _, r = rodar([A("A", 5, "c5", restricao_termino=o("2026-01-13")), A("B", 8, "c5")], [])
    assert r["A"]["folga_total"] == 2 and r["B"]["folga_total"] == 0
    _, r = rodar([A("A", 5, "c5", restricao_termino=o("2026-01-07")), A("B", 8, "c5")], [])
    assert (r["A"]["inicio"], r["A"]["termino"], r["A"]["folga_total"]) == ("2026-01-05", "2026-01-09", -2)
    _, r = rodar([A("A", 5, "c5", restricao_termino=o("2026-01-10"))], [])
    assert r["A"]["folga_total"] == 0


@pytest.mark.parametrize("com_progresso", [False, True])
def test_propriedades_do_fnlt_em_redes_de_tarefas(com_progresso):
    """500 redes aleatórias de TAREFAS (c5/c6/cF, FS/SS/FF/SF, lag -3..4; sobrepor), ~30 % das
    atividades com FNLT. Por definição:
    (a) FNLT nunca altera ES/EF; (b) nunca aumenta a folga total;
    (c) toda atividade cujo EF passa do próprio FNLT tem folga negativa, e só há folga negativa
        se alguma atividade viola o seu FNLT;
    (d) consumir uma folga total positiva não move o término nem cria violação nova de FNLT."""
    ds = DS if com_progresso else None
    rng = random.Random(9)
    for _ in range(500):
        ativs, rels = _rede(rng, ["c5", "c6", "cF"], com_progresso, True)
        res = calcular(ativs, rels, CALS, SEG, data_status=ds)
        sem = calcular([_clone(a, restricao_termino=None) for a in ativs], rels, CALS, SEG, data_status=ds)
        ra, r0, ctx = res.atividades, sem.atividades, (ativs, rels)
        abertas = [a for a in ativs if a.status != "concluida"]
        assert all((ra[a.id].es, ra[a.id].ef) == (r0[a.id].es, r0[a.id].ef) for a in ativs), ctx
        assert all(ra[a.id].folga_total <= r0[a.id].folga_total for a in abertas), ctx
        violadas = _violadas(ativs, res)
        negativas = {a.id for a in abertas if ra[a.id].folga_total < 0}
        assert violadas <= negativas and (violadas or not negativas), ctx
        for a in abertas:
            x = ra[a.id]
            if x.folga_total > 0:
                mod = _com_folga_consumida(ativs, a, x, x.folga_total)
                r2 = calcular(mod, rels, CALS, SEG, data_status=ds)
                assert r2.termino_projeto == res.termino_projeto, (a.id, ctx)
                assert _violadas(mod, r2) <= violadas, (a.id, ctx)


def test_fnlt_no_marco_final_da_obra_gera_folga_negativa():
    """A(5) seg5–sex9 -> M (marco de término, o fim da obra) com FNLT qua 07/01.
    M ocorre no fim de sex 09/01; prazo é o fim de qua 07/01: folga = −(qui8, sex9) = −2 em M e em A.
    O motor devolve 0 nos dois (é o caso de uso principal de marco contratual)."""
    _, r = rodar([A("A", 5, "c5"), A("M", 0, "c5", tipo="marco_termino", restricao_termino=o("2026-01-07"))],
                 [R("A", "M")])
    assert r["M"]["termino"] == "2026-01-09"
    assert (r["M"]["folga_total"], r["A"]["folga_total"]) == (-2, -2)


def test_marco_de_termino_em_feriado_nao_gera_folga_negativa():
    """N0(4, c5) seg5–qui8 (EF sex9) --FS-2--> M (marco de término, cF; 07 e 08/01 feriados).
    Alvo = sex9 − 2 úteis de c5 = qua 07/01. Sem restrição alguma: folga total >= 0 em M e em N0.
    O motor devolve −1 nos dois."""
    _, r = rodar([A("N0", 4, "c5"), A("M", 0, "cF", tipo="marco_termino")], [R("N0", "M", "FS", -2)])
    assert r["M"]["folga_total"] >= 0 and r["N0"]["folga_total"] >= 0


# =============================================================================
# 2. Lógica retida
# =============================================================================
def test_retida_caso_basico_e_parametro_invalido():
    """Status qua14. P(5) não iniciada qua14..ter20 (EF qua21) --FS--> S em andamento, remanescente 2.
    Sobrepor: S = qua14–qui15; término ter 20/01. Retida: remanescente de S só depois de P:
    qua21–qui22; término qui 22/01, P e S críticas com folga 0.
    logica_progresso desconhecida -> ErroRede."""
    ativs = [A("P", 5, "c5"), A("S", 2, "c5", status="em_andamento", inicio_real=SEG)]
    rs, _ = rodar(ativs, [R("P", "S")], data_status=DS)
    rr, r = rodar(ativs, [R("P", "S")], data_status=DS, logica_progresso="retida")
    assert (termino_iso(rs), termino_iso(rr)) == ("2026-01-20", "2026-01-22")
    assert (r["P"]["folga_total"], r["S"]["folga_total"]) == (0, 0)
    assert "retida" in r["S"]["motivo_inicio"]
    with pytest.raises(ErroRede):
        rodar(ativs, [R("P", "S")], data_status=DS, logica_progresso="x")


def test_propriedades_da_logica_retida_em_calendario_unico():
    """600 redes aleatórias de TAREFAS em c5 com progresso (status qua14), sem FNLT. Por definição:
    (a) retida nunca antecipa: término e EF de cada atividade >= os de sobrepor;
    (b) FS/FF para sucessora em andamento são satisfeitas pelo REMANESCENTE;
    (c) folga total >= 0 e folga livre <= total;
    (d) consumir a folga total não move o término; não iniciada: folga+1 move."""
    c = CALS["c5"]
    rng = random.Random(9)
    for _ in range(600):
        ativs, rels = _rede(rng, ["c5"], True, False)
        res = calcular(ativs, rels, CALS, SEG, data_status=DS, logica_progresso="retida")
        sob = calcular(ativs, rels, CALS, SEG, data_status=DS)
        ra, by, ctx = res.atividades, {a.id: a for a in ativs}, (ativs, rels)
        assert res.termino_projeto >= sob.termino_projeto, ctx
        assert all(ra[i].ef >= sob.atividades[i].ef for i in ra), ctx
        for rel in rels:
            if by[rel.sucessora].status != "em_andamento" or rel.tipo not in ("FS", "FF"):
                continue
            p, s = ra[rel.predecessora], ra[rel.sucessora]
            alvo = c.somar(p.ef, rel.lag)
            if rel.tipo == "FS":
                assert s.inicio_restante >= alvo, (rel, ctx)
            else:
                assert s.ef - 1 >= c.ultimo_dia_util(alvo), (rel, ctx)
        for a in ativs:
            if a.status == "concluida":
                continue
            x = ra[a.id]
            assert 0 <= x.folga_livre <= x.folga_total, (a.id, ctx)

            def termino(k, a=a, x=x):
                mod = _com_folga_consumida(ativs, a, x, k) if k else ativs
                return calcular(mod, rels, CALS, SEG, data_status=DS, logica_progresso="retida").termino_projeto

            assert termino(x.folga_total) == res.termino_projeto, (a.id, ctx)
            if a.status == "nao_iniciada":
                assert termino(x.folga_total + 1) > res.termino_projeto, (a.id, ctx)


def test_retida_com_calendarios_diferentes_nao_gera_folga_negativa():
    """Status qua14. N0(6, c5) não iniciada: qua14..qua21 (EF qui22) --FS+3--> N1 (c6) em andamento,
    remanescente 5. Lag em c5: qui22, sex23, seg26 -> alvo ter27. N1 (c6): ter27..sáb31 (EF dom 01/02).
    Caminho único: N0 crítica, folga 0. Na volta o motor recua 5 dias úteis de c5 (não de c6) a partir
    de 01/02 e chega a seg26 em vez de ter27: folga −1 em N0."""
    res, r = rodar([A("N0", 6, "c5"), A("N1", 5, "c6", status="em_andamento", inicio_real=o("2026-01-09"))],
                   [R("N0", "N1", "FS", 3)], data_status=DS, logica_progresso="retida")
    assert (r["N0"]["termino"], r["N1"]["termino"], termino_iso(res)) == ("2026-01-21", "2026-01-31", "2026-01-31")
    assert r["N0"]["folga_total"] == 0


def test_retida_igual_a_sobrepor_quando_as_predecessoras_ja_terminaram():
    """Status qua14. C concluída (05–12/01) --FS+3--> B em andamento desde ter 13/01, remanescente 2.
    Não há predecessora aberta. Pela regra declarada, retida = sobrepor: B = qua14–qui15.
    O motor, em retida, aplica o lag a partir do término real (13,14,15 -> sex16) e B termina seg 19/01.
    (Se a intenção for 'lag de concluída ainda vale', a docstring e a descrição do painel é que mudam.)"""
    ativs = [A("C", 0, "c5", status="concluida", inicio_real=SEG, termino_real=o("2026-01-12")),
             A("B", 2, "c5", status="em_andamento", inicio_real=o("2026-01-13"))]
    rs, _ = rodar(ativs, [R("C", "B", "FS", 3)], data_status=DS)
    rr, _ = rodar(ativs, [R("C", "B", "FS", 3)], data_status=DS, logica_progresso="retida")
    assert termino_iso(rs) == "2026-01-15"
    assert termino_iso(rr) == termino_iso(rs)


# =============================================================================
# 3. Relatório HTML e 4. isolamento entre obras (API)
# =============================================================================
XSS = '<script>alert(1)</script>"\'<img src=x onerror=1>'


@pytest.fixture(scope="module")
def cliente():
    from infra4d.api import criar_app
    return TestClient(criar_app(), raise_server_exceptions=False)


def _br(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


@pytest.mark.parametrize("obra", ["ferrovia", "rodovia"])
def test_relatorio_traz_os_mesmos_numeros_do_painel(cliente, obra):
    """Para cada obra: avanço real do relatório = avanço do painel com 1 casa (vírgula decimal);
    términos de linha de base, construtora e independente = os do painel em dd/mm/aaaa; o relatório
    nomeia a obra pedida. No painel, a lógica retida nunca antecipa em relação a sobrepor."""
    p = cliente.get("/api/painel", params={"obra": obra}).json()
    h = cliente.get("/api/relatorio", params={"obra": obra})
    assert h.status_code == 200 and h.headers["content-type"].startswith("text/html")
    t = h.text
    assert re.findall(r"Avanço físico real</span><b>([^<]+)", t) == [f"{p['avanco_real']:.1f}%".replace(".", ",")]
    terminos = dict(re.findall(r"Término — ([^<]+)</span><b>([^<]+)", t))
    assert terminos["linha de base"] == _br(p["terminos"]["linha_base"])
    assert terminos["construtora"] == _br(p["terminos"]["construtora"])
    assert terminos["independente"] == _br(p["terminos"]["independente"])
    assert re.findall(r"obra <code>([^<]*)", t) == [obra]
    sl = p["sensibilidade_logica"]
    assert sl["sobrepor"] == p["terminos"]["independente"] and sl["retida"] >= sl["sobrepor"]


def test_relatorio_escapa_todo_texto_vindo_dos_dados(monkeypatch):
    """Nome da obra, aviso, premissas, gerador, nomes de atividade, unidades, descrições de restrição e
    até o ID da obra recebem a carga '<script>…<img onerror>'. No HTML não pode aparecer nenhuma tag
    viva: '<script>alert' e '<img src=x' ausentes, e a versão escapada presente."""
    from infra4d import relatorio
    from infra4d.api import criar_app
    # (o global `_obter_estado` deixou de existir: o router do relatório agora é criado por app)
    d = copy.deepcopy(Projeto.carregar().dados)
    for k in ("aviso", "versao_premissas", "gerador", "semente"):
        d["meta"][k] = XSS
    d["ferrovia"]["nome"] = XSS
    for a in d["atividades"]:
        a["nome"] = XSS + a["nome"]
        if a.get("unidade"):
            a["unidade"] = XSS
    for r in d.get("restricoes", []):
        r["descricao"] = XSS
    px = Projeto(d)
    c = TestClient(criar_app(fontes={"ferrovia": px, XSS: px}), raise_server_exceptions=False)
    for params in ({}, {"obra": XSS}):
        h = c.get("/api/relatorio", params=params)
        assert h.status_code == 200
        assert "<script>alert" not in h.text and "<img src=x" not in h.text
        assert "&lt;script&gt;alert(1)" in h.text
    nf = c.get("/api/relatorio", params={"obra": "<script>x</script>"})
    assert nf.status_code == 404 and nf.headers["content-type"].startswith("application/json")


def test_relatorio_de_um_app_nao_e_sequestrado_por_outro_app(monkeypatch):
    """app1 tem a obra 'ferrovia'; app2, criado depois, só tem a obra 'outra'.
    GET /api/relatorio?obra=ferrovia no app1 tem de responder 200, como o /api/painel do mesmo app.
    Responde 404 'obra desconhecida: ferrovia (disponíveis: outra)'."""
    from infra4d import relatorio
    from infra4d.api import criar_app
    # (o global `_obter_estado` deixou de existir: o router do relatório agora é criado por app)
    p = Projeto.carregar()
    c1 = TestClient(criar_app(fontes={"ferrovia": p}), raise_server_exceptions=False)
    TestClient(criar_app(fontes={"outra": p}), raise_server_exceptions=False)
    assert c1.get("/api/painel", params={"obra": "ferrovia"}).status_code == 200
    assert c1.get("/api/relatorio", params={"obra": "ferrovia"}).status_code == 200


def test_simulacao_de_uma_obra_nao_vaza_para_a_outra(cliente):
    """Simular na rodovia (produtividade ÷ 5 numa atividade aberta por quantidade) liga a simulação só lá:
    painel, GET simulação e relatório da ferrovia continuam sem simulação e com os mesmos términos.
    DELETE na ferrovia não desliga a da rodovia. Obra desconhecida -> 404 em todas as rotas."""
    antes = cliente.get("/api/painel", params={"obra": "ferrovia"}).json()["terminos"]
    ind = cliente.get("/api/cenarios/independente", params={"obra": "rodovia"}).json()
    aid = next(k for k, v in ind["atividades"].items()
               if v["status"] == "nao_iniciada" and v["memoria"].get("regra") == "quantidade")
    corpo = {"ajustes": [{"atividade_id": aid, "produtividade": ind["atividades"][aid]["memoria"]["produtividade"] / 5}]}
    try:
        assert cliente.post("/api/simulacao", params={"obra": "rodovia"}, json=corpo).status_code == 200
        ferrovia = cliente.get("/api/painel", params={"obra": "ferrovia"}).json()
        assert ferrovia["simulacao_ativa"] is False and ferrovia["terminos"] == antes
        assert cliente.get("/api/simulacao", params={"obra": "ferrovia"}).json()["ajustes"] == []
        assert "Simulação ativa" not in cliente.get("/api/relatorio", params={"obra": "ferrovia"}).text
        assert "Simulação ativa" in cliente.get("/api/relatorio", params={"obra": "rodovia"}).text
        cliente.delete("/api/simulacao", params={"obra": "ferrovia"})
        assert cliente.get("/api/painel", params={"obra": "rodovia"}).json()["simulacao_ativa"] is True
    finally:
        cliente.delete("/api/simulacao", params={"obra": "rodovia"})
    for rota in ("/api/painel", "/api/relatorio", "/api/simulacao", "/api/cenarios/independente", "/api/comparacao"):
        assert cliente.get(rota, params={"obra": "../ferrovia"}).status_code == 404, rota
