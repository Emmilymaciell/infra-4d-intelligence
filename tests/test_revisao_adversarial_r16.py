"""Revisão adversarial — rodada 16: ``aceleracao.py`` (/api/aceleracao), ``comparar_revisoes.py``
(/api/revisoes/comparar), ``backtest.py`` (/api/backtest) e ``tendencia.py`` (/api/tendencia).

Alvo nº 1: vazamento de dado futuro na fotografia de uma data passada ``d``. A conferência é
contrafactual e independente de ``tendencia.fotografia``: monta-se um dataset em que NADA posterior a
``d`` aconteceu (e o que estava em curso tem valores arbitrários) e exige-se a MESMA fotografia.

Cada teste traz no docstring o resultado esperado calculado à mão ou por conferência independente.
Defeito confirmado fica ``xfail(strict=True, reason="DEFEITO: ...")``.
"""

import copy
import random
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d.aceleracao import acelerar
from infra4d.backtest import backtest
from infra4d.calendario import Calendario, ErroCalendario, iso, ordinal
from infra4d.cenarios import Ajuste, Projeto, executar
from infra4d.comparar_revisoes import Versao, comparar_revisoes, versao_do_cenario
from infra4d.motor import AtividadeCPM as A
from infra4d.motor import ErroRede
from infra4d.motor import Relacao as R
from infra4d.persistencia import projeto_na_data
from infra4d.tendencia import fotografia, tendencia

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")
CENARIOS = ("construtora", "independente")


def _defeito(motivo):
    return pytest.mark.xfail(strict=True, reason="DEFEITO: " + motivo)


@pytest.fixture(scope="module")
def bases():
    return {o: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json") for o in OBRAS}


def _app(fontes):
    from infra4d.api import criar_app
    return TestClient(criar_app(fontes=fontes), raise_server_exceptions=False)


# =============================================================================
# 1. tendência / backtest — vazamento de dado futuro
# =============================================================================
def _mundo_sem_futuro(dados: dict, d: int, rng: random.Random) -> dict:
    """O dataset como seria se NADA posterior a ``d`` tivesse acontecido. Escrito sem olhar a regra da
    fotografia, só o enunciado 'o que se sabia em d':
    - boletim: fica só se a semana inteira já passou (início + 7 <= d) ou se a atividade terminou antes de d;
    - atividade que começou em d ou depois: não iniciada, sem datas reais, executado 0;
    - atividade em curso em d (começou antes, não terminou antes): sem término real, e os campos de
      progresso da data de status ATUAL (quantidade executada, percentual) trocados por valores ARBITRÁRIOS
      — se a fotografia os lesse, o resultado mudaria;
    - restrição com liberação posterior a d: pendente."""
    x = copy.deepcopy(dados)
    ativ = {a["id"]: a for a in dados["atividades"]}
    fica = []
    for m in x["medicoes"]:
        a = ativ[m["atividade_id"]]
        t = ordinal(a["termino_real"]) if a.get("termino_real") else None
        if ordinal(m["semana_inicio"]) + 7 <= d or (t is not None and t < d):
            fica.append(m)
    x["medicoes"] = fica
    for a in x["atividades"]:
        ini = ordinal(a["inicio_real"]) if a.get("inicio_real") else None
        fim = ordinal(a["termino_real"]) if a.get("termino_real") else None
        if ini is None or ini >= d:
            a.pop("inicio_real", None)
            a.pop("termino_real", None)
            a.pop("percentual_executado", None)
            a["status"] = "nao_iniciada"
            if "quantidade_executada" in a:
                a["quantidade_executada"] = 0.0
        elif fim is None or fim >= d:
            a.pop("termino_real", None)
            a["status"] = "em_andamento"
            if "quantidade_executada" in a:
                a["quantidade_executada"] = round(rng.random() * a["quantidade_total"], 3)
            if "duracao_fixa" in a:
                a["percentual_executado"] = round(rng.random() * 99, 1)
    for r in x.get("restricoes", []):
        if ordinal(r["data_liberacao"]) > d:
            r["situacao"] = "pendente"
    return x


@pytest.mark.parametrize("obra", OBRAS)
def test_fotografia_inteira_nao_depende_do_futuro(bases, obra):
    """20 datas sorteadas entre o início e a véspera da data de status. Para cada uma, a fotografia do
    dataset real e a do 'mundo sem futuro' têm de ser IGUAIS campo a campo (o dicionário inteiro: meta,
    atividades, boletins, restrições e todo o resto) — qualquer campo que entrasse sem filtro de data
    apareceria aqui. Em 4 das datas, também o resultado do motor atividade a atividade nos dois cenários."""
    dados = bases[obra].dados
    ds, ini = ordinal(dados["meta"]["data_status"]), ordinal(dados["meta"]["inicio_projeto"])
    rng = random.Random(16)
    for k in range(20):
        d = rng.randint(ini + 1, ds - 1)
        real, limpo = fotografia(dados, d), fotografia(_mundo_sem_futuro(dados, d, rng), d)
        assert real == limpo, iso(d)
        if k % 5 == 0:
            for c in CENARIOS:
                assert executar(Projeto(real), c)["atividades"] == executar(Projeto(limpo), c)["atividades"], (iso(d), c)


@pytest.mark.parametrize("obra", OBRAS)
def test_fotografia_da_fotografia(bases, obra):
    """Fotografar em d1 uma fotografia tirada em d2 (d1 <= d2) é o mesmo que fotografar o original em d1
    (fora o carimbo ``fotografia_de``): quem está em d2 não sabe mais sobre d1 do que quem está em hoje."""
    dados = bases[obra].dados
    ds, ini = ordinal(dados["meta"]["data_status"]), ordinal(dados["meta"]["inicio_projeto"])
    rng = random.Random(61)
    for _ in range(10):
        d1 = rng.randint(ini + 1, ds - 1)
        d2 = rng.randint(d1, ds - 1)
        direta, dupla = fotografia(dados, d1), fotografia(fotografia(dados, d2), d1)
        for f in (direta, dupla):
            f["meta"] = {k: v for k, v in f["meta"].items() if k != "fotografia_de"}
        assert direta == dupla, (iso(d1), iso(d2))


@pytest.mark.parametrize("obra", OBRAS)
def test_serie_e_erros_de_quem_esta_no_passado_sao_o_prefixo(bases, obra):
    """Obra Y = a obra X como era 16 semanas atrás (fotografia). Com passo de 28 dias (4 passos), a série
    MTA de Y tem de ser exatamente o começo da série de X — mesmas datas, mesmos términos — e os erros do
    backtest contra a realidade simulada (que não depende da data de status) idem. Se a série de X usasse
    qualquer informação posterior, os pontos antigos difeririam."""
    X = bases[obra]
    Y = Projeto(fotografia(X.dados, X.data_status - 112))
    tx, ty = tendencia(X, 28), tendencia(Y, 28)
    n = len(ty["datas_de_status"])
    assert n >= 3 and tx["datas_de_status"][:n] == ty["datas_de_status"]
    for mx, my in zip(tx["marcos"], ty["marcos"]):
        assert mx["id"] == my["id"] and mx["serie"][:n] == my["serie"]
    bx, by = backtest(X, 28), backtest(Y, 28)
    for mx, my in zip(bx["marcos"], by["marcos"]):
        rx, ry = mx["por_referencia"]["realidade_simulada"], my["por_referencia"]["realidade_simulada"]
        assert rx["referencia"] == ry["referencia"]
        for c in CENARIOS:
            assert rx["erro_dias"][c][:n] == ry["erro_dias"][c]


def _zero(bases) -> Projeto:
    """A ferrovia no dia do início do projeto (data de status == início): obra que ainda não começou."""
    P = bases["ferrovia"]
    return projeto_na_data(P, ordinal(P.dados["meta"]["inicio_projeto"]))


def test_tendencia_de_obra_no_dia_do_inicio_responde(bases):
    """Data de status == início do projeto: não há data passada. /api/tendencia responde 200 com série vazia."""
    r = _app({"zero": _zero(bases)}).get("/api/tendencia", params={"obra": "zero", "passo_dias": 28})
    assert r.status_code == 200 and r.json()["datas_de_status"] == []


# Regressão: defeito da rodada 16, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("backtest de obra cuja data de status é o próprio início do projeto: `datas_de_status` devolve lista "
#   "vazia e `linhas[-1]` estoura IndexError -> /api/backtest responde 500 (a /api/tendencia, com o mesmo "
#   "dado, responde 200 com série vazia). Correção: sem datas, devolver o resultado vazio declarado (ou 422)")
def test_backtest_de_obra_no_dia_do_inicio_nao_e_500(bases):
    """Mesma obra do teste acima: o backtest não tem o que medir, mas a rota não pode responder 500."""
    r = _app({"zero": _zero(bases)}).get("/api/backtest", params={"obra": "zero", "passo_dias": 28})
    assert r.status_code in (200, 422), r.status_code


# Regressão: defeito da rodada 16, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("backtest com marco de término que não existe na realidade simulada do gerador: `realidade_da_obra` só "
#   "confere as TAREFAS concluídas e declara a referência 'coerente'; depois `ordinal(real[m])` estoura "
#   "KeyError -> 500. Correção: marco ausente da realidade = referência indisponível (declarada), como já "
#   "é feito para dataset alterado")
def test_backtest_com_marco_fora_da_realidade_simulada_nao_estoura(bases):
    """Dataset da ferrovia com um marco de término a mais (M-NOVO, depois de M-L1-FIM). O gerador não conhece
    esse marco. Esperado: backtest devolve os 5 marcos; a referência 'realidade_simulada' fica indisponível
    ou cobre só os marcos conhecidos — nunca exceção."""
    d = copy.deepcopy(bases["ferrovia"].dados)
    d["atividades"].append({**copy.deepcopy(next(a for a in d["atividades"] if a["id"] == "M-L1-FIM")),
                            "id": "M-NOVO"})
    d["relacoes"].append({"predecessora": "M-L1-FIM", "sucessora": "M-NOVO", "tipo": "FS", "lag": 0})
    r = backtest(Projeto(d), 91)
    assert len(r["marcos"]) == 5


@pytest.mark.parametrize("rota", ["/api/tendencia", "/api/backtest"])
# Regressão: defeito da rodada 16, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("restrição sem `data_liberacao` (campo que o painel trata como opcional em outras rotas): "
#   "`fotografia` faz `ordinal(r['data_liberacao'])` e estoura KeyError -> 500 em /api/tendencia e "
#   "/api/backtest. Correção: restrição sem data continua com a situação que tem (ou vira aviso)")
def test_restricao_sem_data_de_liberacao_nao_e_500(bases, rota):
    """Uma restrição pendente sem data de liberação no dataset: as rotas respondem 200 (ou 422 com motivo)."""
    d = copy.deepcopy(bases["ferrovia"].dados)
    d["restricoes"].append({"id": "R-SEM-DATA", "descricao": "sem data", "atividade_id": "L3-S01-GRA",
                            "situacao": "pendente"})
    r = _app({"x": Projeto(d)}).get(rota, params={"obra": "x", "passo_dias": 91})
    assert r.status_code in (200, 422), r.status_code


# =============================================================================
# 2. aceleração
# =============================================================================
def _q(aid, qtd=100.0, eq=1):
    return {"id": aid, "nome": aid, "tipo": "tarefa", "lote_id": "L1", "servico_id": "TER", "quantidade_total": qtd,
            "produtividade_planejada": 10.0, "equipes": eq, "calendario": "C", "status": "nao_iniciada",
            "unidade": "m³"}


def _proj(ativs, rels=()):
    """Calendário corrido; início = data de status = 01/01/2026; sem boletins (vale a produtividade planejada,
    10 un/equipe·dia). Custo da equipe·dia passado à mão: TER = 100."""
    return Projeto({"meta": {"inicio_projeto": "2026-01-01", "data_status": "2026-01-01", "calendario_obra": "C",
                             "termino_linha_base": "2026-12-31", "ficticio": True, "aviso": "FICTÍCIO"},
                    "lotes": [{"id": "L1"}], "servicos": [], "medicoes": [],
                    "calendarios": [{"id": "C", "nome": "C", "dias_semana": [0, 1, 2, 3, 4, 5, 6], "nao_uteis": []}],
                    "atividades": list(ativs),
                    "relacoes": [{"predecessora": p, "sucessora": s, "tipo": "FS", "lag": 0} for p, s in rels]})


CUSTOS = {"TER": 100.0}


@pytest.mark.parametrize("obra", OBRAS)
def test_obras_mais_limite_nunca_piora_e_ajustes_conferem(bases, obra):
    """Nas duas obras, com limite de 1, 2, 3 e 20 equipes extras: o término inicial é o do cenário
    independente; o término alcançado nunca piora quando o limite cresce; a curva é estritamente
    decrescente no término e crescente no custo; e os ajustes finais, aplicados como simulação, dão o
    término prometido."""
    P = bases[obra]
    ind = executar(P, "independente")["termino"]
    anterior = None
    for lim in (1, 2, 3, 20):
        r = acelerar(P, limite_extra=lim)
        assert r["termino_inicial"] == ind
        ts = [ordinal(p["termino"]) for p in r["curva"]]
        cs = [p["custo_acumulado"] for p in r["curva"]]
        assert all(a > b for a, b in zip(ts, ts[1:])) and all(a < b for a, b in zip(cs, cs[1:]))
        sim = executar(P, "simulado", [Ajuste(**a) for a in r["ajustes_finais"]])["termino"]
        assert sim == r["termino_alcancado"] and r["verificacao"]["confere"] is True
        assert r["cumpre_prazo"] == (ordinal(r["termino_alcancado"]) <= ordinal(r["prazo"]))
        if anterior is not None:
            assert ordinal(r["termino_alcancado"]) <= anterior
        anterior = ordinal(r["termino_alcancado"])


# Regressão: defeito da rodada 16, já corrigido pelo dono do módulo (as marcas xfail saíram). O que falhava:
#   platô do arredondamento: candidata era só a atividade cuja duração caía com +1 equipe. A (100 un, 5 equipes)
#   dura ⌈100/50⌉ = 2 dias; com 6 a 9 equipes continua 2; com 10 dura 1. Como +1 não ganhava nada, A saía das
#   candidatas e o resultado era 'cumpre_prazo: false … limite de 5 equipe(s) extra(s)' — falso. Em série
#   (A → B, prazo 03/01) o guloso parava em 04/01; com A = 10 e B = 6 (⌈100/60⌉ = 2 dias) o término é 03/01.
@pytest.mark.parametrize("ativs,rels,prazo,ajuste_manual", [
    ([_q("A", eq=5)], [], "2026-01-01", {"A": 10}),
    ([_q("A", eq=5), _q("B")], [("A", "B")], "2026-01-03", {"A": 10, "B": 6})])
def test_prazo_alcancavel_dentro_do_limite_e_cumprido(ativs, rels, prazo, ajuste_manual):
    """Conferência independente: os ajustes manuais do parâmetro respeitam o limite (base + 5) e, aplicados
    como simulação pelo motor, cumprem o prazo. Logo ``acelerar`` com limite_extra=5 não pode responder
    que o prazo é inalcançável por falta de equipes."""
    P = _proj(ativs, rels)
    manual = executar(P, "simulado", [Ajuste(atividade_id=i, equipes=n) for i, n in ajuste_manual.items()])
    assert manual["termino"] == prazo
    r = acelerar(P, prazo=prazo, limite_extra=5, custos=CUSTOS)
    assert r["cumpre_prazo"] is True, (r["termino_alcancado"], r["motivo"])


# Regressão: defeito da rodada 16, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("custo adicional NEGATIVO: com muitas equipes de base o arredondamento da duração deixa mais de 10 "
#   "equipe·dias ociosos, e +1 equipe os elimina. 160 un, 15 equipes: 2 dias = 30 equipe·dias; 16 equipes: "
#   "1 dia = 16 equipe·dias; custo = 100 × ((16 − 30) + 10) = −400. A curva sai com custo acumulado "
#   "−400 (o módulo promete 'custo estritamente crescente') e acelerar passa a 'economizar'. Correção: "
#   "piso 0 nos equipe·dias ociosos (ou custo = mobilização + max(0, …)) e declarar")
def test_custo_de_acelerar_nunca_e_negativo():
    """À mão: A com 160 un a 10 un/equipe·dia. 15 equipes -> ⌈160/150⌉ = 2 dias (término 02/01); 16 equipes
    -> 1 dia (01/01). Trazer uma 16ª equipe custa, no mínimo, a mobilização dela (10 equipe·dias × 100 =
    1.000): o custo adicional do passo tem de ser > 0 e a curva crescente."""
    r = acelerar(_proj([_q("A", qtd=160.0, eq=15)]), prazo="2026-01-01", custos=CUSTOS)
    assert (r["termino_inicial"], r["termino_alcancado"]) == ("2026-01-02", "2026-01-01")
    assert r["custo_adicional_total"] > 0, r["curva"]


# Regressão: defeito da rodada 16, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("GET /api/aceleracao?prazo= (parâmetro vazio): `ordinal('')` devolve None sem erro e a comparação "
#   "`t_atual <= t_prazo` estoura TypeError -> 500. 'abc' e '2026-02-30' dão 422 corretamente. "
#   "Correção: prazo vazio = padrão (término da LB) ou 422")
def test_prazo_vazio_nao_e_500(bases):
    """``?prazo=`` é o que um formulário com o campo em branco envia. Esperado 200 (usa o padrão) ou 422."""
    c = _app({"ferrovia": bases["ferrovia"]})
    assert c.get("/api/aceleracao", params={"prazo": "abc"}).status_code == 422
    assert c.get("/api/aceleracao", params={"prazo": ""}).status_code in (200, 422)


# =============================================================================
# 3. comparação de revisões
# =============================================================================
INI = date(2026, 3, 2).toordinal()  # segunda-feira


def _rede(rng: random.Random, n: int) -> Versao:
    cals = {"C": Calendario("C", "seg-sex"), "S": Calendario("S", "seg-sab", nao_uteis={date(2026, 3, 10)})}
    ats, rels = [A("M0", 0, "C", tipo="marco_inicio")], []
    for i in range(n):
        ats.append(A(f"T{i:02d}", rng.randint(1, 9), rng.choice("CS")))
        for p in rng.sample(ats[:-1], k=min(len(ats) - 1, rng.randint(1, 2))):
            rels.append(R(p.id, ats[-1].id, rng.choice(["FS", "FS", "FS", "SS", "FF"]), rng.choice([0, 0, 0, 1, 2, -1])))
    ats.append(A("MF", 0, "C", tipo="marco_termino"))
    com_sucessora = {r.predecessora for r in rels}
    rels += [R(a.id, "MF") for a in ats[1:-1] if a.id not in com_sucessora]
    return Versao(ats, rels, cals, INI, None, rotulo="A")


def _mutar(rng: random.Random, v: Versao) -> Versao:
    b = v.copia()
    b.rotulo = "B"
    for _ in range(rng.randint(1, 5)):
        ts = [a for a in b.atividades if a.tipo == "tarefa"]
        op = rng.choice(["dur", "cal", "snet", "fnlt", "lag", "tipo_rel", "add_rel", "dup_rel", "rem_rel", "add_at",
                         "rem_at", "calendario", "novo_cal", "inicio"])
        try:
            if op == "dur":
                rng.choice(ts).duracao = rng.randint(1, 12)
            elif op == "cal":
                rng.choice(ts).calendario = rng.choice("CS")
            elif op == "snet":
                rng.choice(ts).restricao_inicio = INI + rng.randint(0, 40)
            elif op == "fnlt":
                rng.choice(ts).restricao_termino = INI + rng.randint(10, 60)
            elif op == "lag":
                rng.choice(b.relacoes).lag = rng.choice([-2, 0, 1, 3])
            elif op == "tipo_rel":
                rng.choice(b.relacoes).tipo = rng.choice(["FS", "SS", "FF", "SF"])
            elif op == "add_rel":
                i, j = sorted(rng.sample(range(len(ts)), 2))
                b.relacoes.append(R(ts[i].id, ts[j].id, rng.choice(["FS", "SS", "FF"]), rng.choice([0, 1])))
            elif op == "dup_rel":
                r = rng.choice(b.relacoes)
                b.relacoes.append(R(r.predecessora, r.sucessora, r.tipo, r.lag + rng.choice([1, 2, 3])))
            elif op == "rem_rel":
                b.relacoes.remove(rng.choice(b.relacoes))
            elif op == "add_at":
                nid = f"N{rng.randint(0, 99):02d}"
                if all(a.id != nid for a in b.atividades):
                    b.atividades.insert(-1, A(nid, rng.randint(1, 9), "C"))
                    b.relacoes += [R(rng.choice(ts).id, nid), R(nid, "MF")]
            elif op == "rem_at":
                x = rng.choice(ts)
                b.atividades.remove(x)
                b.relacoes = [r for r in b.relacoes if x.id not in (r.predecessora, r.sucessora)]
            elif op == "calendario":
                b.calendarios["C"] = Calendario("C", "seg-sex", nao_uteis={date(2026, 3, rng.randint(3, 27))})
            elif op == "novo_cal":
                b.calendarios["N"] = Calendario("N", "seg-dom")
                rng.choice(ts).calendario = "N"
            else:
                b.inicio_projeto = INI + rng.choice([-7, 7, 14])
        except (IndexError, ValueError):
            pass
    return b


def test_fuzz_inventario_completo_reconstroi_b():
    """400 pares (A, B) sorteados: B = A com 1 a 5 mutações de 14 tipos (duração, calendário, SNET, FNLT,
    lag, tipo de relação, relação nova/duplicada/removida, atividade nova/removida, definição de
    calendário, calendário novo, início do projeto). Para todo par em que as duas redes são válidas:
    A + todas as mudanças inventariadas dá o término de B (inventário completo); soma dos efeitos isolados
    + resíduo = Δ total; e Δ ≠ 0 nunca vem com zero mudanças."""
    rng = random.Random(1616)
    comparados = 0
    for caso in range(400):
        a = _rede(rng, rng.randint(3, 9))
        b = _mutar(rng, a)
        try:
            a.calcular(), b.calcular()
        except (ErroRede, ErroCalendario):
            continue
        r = comparar_revisoes(a, b)
        comparados += 1
        assert r["reconstrucao"]["confere_com_b"] is True, caso
        at = r["atribuicao"]
        assert at["soma_efeitos_isolados"] + at["residuo_interacao"] == r["delta_dias_corridos"], caso
        assert r["n_mudancas"] > 0 or r["delta_dias_corridos"] == 0, caso
    assert comparados > 250


@pytest.mark.parametrize("obra", OBRAS)
def test_duas_datas_de_status_da_mesma_obra_reconstroem(bases, obra):
    """A = cenário independente da obra 20 semanas atrás; B = hoje. Nos modos agrupado e detalhado a
    reconstrução confere com B e soma + resíduo = Δ; no agrupado nenhuma mudança fica sem efeito calculável."""
    P = bases[obra]
    a = versao_do_cenario(Projeto(fotografia(P.dados, P.data_status - 140)), "independente")
    b = versao_do_cenario(P, "independente")
    for agrupar in (True, False):
        r = comparar_revisoes(a, b, agrupar_progresso_=agrupar)
        assert r["reconstrucao"]["confere_com_b"] is True
        assert r["atribuicao"]["soma_efeitos_isolados"] + r["atribuicao"]["residuo_interacao"] == r["delta_dias_corridos"]
        if agrupar:
            assert r["atribuicao"]["sem_efeito_calculavel"] == []


# Regressão: defeito da rodada 16, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("alerta falso de manipulação: comparando o cenário INDEPENDENTE da mesma obra em duas datas de status "
#   "(mesmo dataset honesto, só mais boletins), sai 'duracao_critica_encurtada_sem_progresso', gravidade "
#   "ALTA, para L3-S04-GRA (13 → 12 d.u.) e L3-S04-TER (95 → 94), com o texto '(sem medição que "
#   "justifique)'. A duração caiu justamente por MEDIÇÃO: a produtividade medida da frente (boletins de "
#   "outros segmentos) subiu. Correção: não emitir esse alerta quando a versão é o cenário independente "
#   "(ou quando a frente tem boletins novos entre A e B), ou tirar a afirmação do texto")
def test_avanco_honesto_no_independente_nao_dispara_alerta_alto(bases):
    """Ferrovia, independente em (hoje − 20 semanas) × hoje: nenhuma lógica, restrição ou duração foi
    editada à mão — tudo o que muda vem dos boletins. Esperado: zero alertas de gravidade alta."""
    P = bases["ferrovia"]
    a = versao_do_cenario(Projeto(fotografia(P.dados, P.data_status - 140)), "independente")
    r = comparar_revisoes(a, versao_do_cenario(P, "independente"))
    assert [x["mensagem"] for x in r["alertas"] if x["gravidade"] == "alta"] == []


def test_rota_revisoes_entradas_ruins(bases):
    """GET com cenário inexistente 422; a == b dá Δ 0 e nenhuma mudança; POST com corpo que não é JSON,
    lista, lado que não é objeto, cenário inválido e XML truncado: todos 422; conteúdo vazio: 415."""
    c = _app({"ferrovia": bases["ferrovia"]})
    assert c.get("/api/revisoes/comparar", params={"a": "x"}).status_code == 422
    j = c.get("/api/revisoes/comparar", params={"a": "independente", "b": "independente"}).json()
    assert (j["delta_dias_corridos"], j["n_mudancas"], j["reconstrucao"]["confere_com_b"]) == (0, 0, True)
    for corpo in (b"\xff\xfe", b"[]", b'{"a":1,"b":2}', b'{"a":{"cenario":"x"},"b":{"cenario":"construtora"}}',
                  b'{"a":{"conteudo":"<x"},"b":{"cenario":"construtora"}}'):
        assert c.post("/api/revisoes/comparar", content=corpo).status_code == 422, corpo
    assert c.post("/api/revisoes/comparar", content=b'{"a":{"conteudo":""},"b":{"conteudo":""}}').status_code == 415


# Regressão: defeito da rodada 16, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   @_defeito("POST /api/revisoes/comparar: `bool(js.get('efeitos_isolados', True))` — o texto \"false\" (ou \"0\", "
#   "ou \"não\") vira True, e o cliente que pediu para NÃO calcular efeitos isolados paga uma execução do "
#   "motor por mudança. Idem `agrupar_progresso`. Correção: aceitar só booleano JSON (422 para o resto)")
def test_post_efeitos_isolados_como_texto_false_nao_vira_true(bases):
    """Com ``"efeitos_isolados": false`` (booleano) a resposta traz ``atribuicao: null``. Com o texto
    "false", ou a rota recusa (422) ou respeita o pedido — nunca calcula os efeitos como se fosse true."""
    c = _app({"ferrovia": bases["ferrovia"]})
    lados = '"a":{"cenario":"linha_base"},"b":{"cenario":"construtora"}'
    r = c.post("/api/revisoes/comparar", content=("{" + lados + ',"efeitos_isolados":false}').encode())
    assert r.status_code == 200 and r.json()["atribuicao"] is None
    r = c.post("/api/revisoes/comparar", content=("{" + lados + ',"efeitos_isolados":"false"}').encode())
    assert r.status_code == 422 or r.json()["atribuicao"] is None
