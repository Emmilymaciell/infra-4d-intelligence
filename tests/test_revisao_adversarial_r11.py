"""Revisão adversarial — rodada 11: recuperacao.py, sensibilidade.py e exportacao.py (+ rotas).

Mesmo protocolo: esperado calculado à mão ou por conferência independente (aplicar o plano no cenário
simulado; refazer a simulação do grupo; reler o CSV); defeito confirmado fica
``xfail(strict=True, reason="DEFEITO: ...")``.
"""

import copy
import csv
import io
import random
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import exportacao as X
from infra4d.calendario import iso, ordinal
from infra4d.cenarios import Ajuste, Projeto, executar
from infra4d.recuperacao import recuperar
from infra4d.sensibilidade import LIMIAR_ASSIMETRIA, tornado

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")


@pytest.fixture(scope="module")
def obras():
    return {o: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json") for o in OBRAS}


@pytest.fixture(scope="module")
def cliente(obras):
    from infra4d.api import criar_app
    return TestClient(criar_app(fontes=dict(obras)), raise_server_exceptions=False)


# =============================================================================
# 1. recuperação
# =============================================================================
def _rede_aleatoria(rng: random.Random) -> Projeto:
    """3 a 8 atividades por quantidade (calendários de 5 e 6 dias, 1–2 equipes), relações FS/SS/FF/SF com
    lag −2..3 (cadeias paralelas que trocam de determinante e atividades reversas aparecem), todas
    ligadas a um marco final M. Data de status = início; nada executado."""
    n = rng.randint(3, 8)
    ativs = []
    for i in range(n):
        qt = round(rng.uniform(50, 400), rng.choice([0, 3]))
        ativs.append({"id": f"N{i}", "nome": f"N{i}", "tipo": "tarefa", "calendario": rng.choice(["c5", "c6"]),
                      "lote_id": "L1", "servico_id": rng.choice(["TER", "DRE"]), "unidade": "m3",
                      "quantidade_total": qt, "produtividade_planejada": rng.choice([10.0, 7.0, 13.0]),
                      "equipes": rng.randint(1, 2), "status": "nao_iniciada"})
    ativs.append({"id": "M", "nome": "M", "tipo": "marco_termino", "calendario": "c5", "status": "nao_iniciada"})
    rels, vistos = [], set()
    for j in range(1, n):
        for i in rng.sample(range(j), min(j, rng.randint(1, 2))):
            if (i, j) not in vistos:
                vistos.add((i, j))
                rels.append({"predecessora": f"N{i}", "sucessora": f"N{j}",
                             "tipo": rng.choice(["FS", "FS", "SS", "FF", "SF"]), "lag": rng.randint(-2, 3)})
    rels += [{"predecessora": f"N{i}", "sucessora": "M", "tipo": "FS", "lag": 0} for i in range(n)]
    return Projeto({
        "meta": {"inicio_projeto": "2026-01-05", "data_status": "2026-01-05", "calendario_obra": "c5",
                 "aviso": "FICTÍCIO", "ficticio": True},
        "calendarios": [{"id": "c5", "nome": "c5", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []},
                        {"id": "c6", "nome": "c6", "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": []}],
        "atividades": ativs, "relacoes": rels, "medicoes": [], "lotes": [{"id": "L1"}], "servicos": []})


def _termino_com_plano(projeto, plano, alongar=None):
    """Término do cenário simulado aplicando o plano (opcionalmente com UMA frente 1 dia mais longa)."""
    aj = [Ajuste(atividade_id=p["id"], produtividade=p["quantidade_remanescente"] / (
        p["equipes_atuais"] * (p["duracao_necessaria"] + (1 if p["id"] == alongar else 0)))) for p in plano]
    return ordinal(executar(projeto, "simulado", aj)["termino"])


def test_plano_de_recuperacao_cumpre_o_prazo_ou_declara_inviabilidade():
    """150 redes aleatórias (semente fixa), prazo 1 a 20 dias corridos antes do término atual.
    Conferência INDEPENDENTE (aplicando os ajustes de produtividade no cenário simulado):
    (a) se a resposta diz que cumpre, o término simulado é <= prazo;
    (b) se diz que não cumpre, a viabilidade é 'inviavel' e, de fato, nem com TODAS as frentes a 2 × a
        produtividade medida (o fator máximo) o prazo é atingido — nenhum 'falso inviável';
    (c) a alternativa por equipes inteiras, quando existe, também cumpre."""
    rng = random.Random(8)
    for _ in range(150):
        p = _rede_aleatoria(rng)
        ind = executar(p, "independente")
        prazo = iso(ordinal(ind["termino"]) - rng.randint(1, 20))
        r = recuperar(p, prazo=prazo)
        if r["cumpre_prazo"]:
            assert r["plano"] and _termino_com_plano(p, r["plano"]) <= ordinal(prazo), (prazo, r["plano"])
            assert r["verificacao"]["produtividade"]["cumpre"] is True
            assert r["verificacao"]["equipes"]["cumpre"] in (True, None)
            assert r["plano_tipo"] == "minimo_que_cumpre"
        else:
            assert (r["viabilidade"], r["plano_tipo"]) == ("inviavel", "melhor_esforco_sem_cumprir") and r["motivo"]
            tudo = [Ajuste(atividade_id=a["id"], produtividade=2.0 * ind["atividades"][a["id"]]["memoria"]["produtividade"])
                    for a in p.dados["atividades"] if a.get("quantidade_total")]
            assert ordinal(executar(p, "simulado", tudo)["termino"]) > ordinal(prazo), "falso inviável"


@pytest.mark.parametrize("obra", OBRAS)
def test_recuperacao_nas_obras_e_casos_de_borda(obras, obra):
    """Prazo padrão (término da linha de base): a resposta é coerente com a própria verificação — se
    cumpre, o término alcançado <= prazo; se não, 'inviavel'. Prazo folgado (2039): 'no_prazo', plano vazio.
    Prazo igual à data de status e prazo em 2019 (antes do horizonte): 'inviavel', sem exceção.
    Marco já concluído (M-OS) no próprio prazo: 'no_prazo'; com prazo anterior ao real: 'inviavel'.
    Marco inexistente ou id de tarefa: ValueError."""
    p = obras[obra]
    r = recuperar(p)
    assert r["cumpre_prazo"] == (r["termino_alcancado"] <= r["prazo"])
    assert (r["viabilidade"] == "inviavel") == (not r["cumpre_prazo"])
    if r["cumpre_prazo"]:
        assert _termino_com_plano(p, r["plano"]) <= ordinal(r["prazo"])
    folgado = recuperar(p, prazo="2039-01-01")
    assert (folgado["viabilidade"], folgado["plano"], folgado["plano_tipo"]) == ("no_prazo", [], "nenhum")
    for prazo in (p.dados["meta"]["data_status"], "2019-01-01"):
        x = recuperar(p, prazo=prazo)
        assert (x["cumpre_prazo"], x["viabilidade"]) == (False, "inviavel")
    assert recuperar(p, marco="M-OS")["viabilidade"] == "no_prazo"
    assert recuperar(p, marco="M-OS", prazo="2020-06-01")["viabilidade"] == "inviavel"
    for marco in ("ZZ", next(a["id"] for a in p.dados["atividades"] if a.get("tipo", "tarefa") == "tarefa")):
        with pytest.raises(ValueError):
            recuperar(p, marco=marco)


def test_rota_de_recuperacao(cliente):
    """GET /api/recuperacao: prazo ilegível e marco inexistente -> 422; obra desconhecida -> 404;
    folga_max fora de 0..365 -> 422; a resposta repetida (cache) é idêntica à primeira."""
    assert cliente.get("/api/recuperacao", params={"prazo": "ontem"}).status_code == 422
    assert cliente.get("/api/recuperacao", params={"marco": "ZZ"}).status_code == 422
    assert cliente.get("/api/recuperacao", params={"obra": "zz"}).status_code == 404
    assert cliente.get("/api/recuperacao", params={"folga_max": -1}).status_code == 422
    a = cliente.get("/api/recuperacao", params={"obra": "rodovia"})
    assert a.status_code == 200 and a.json() == cliente.get("/api/recuperacao", params={"obra": "rodovia"}).json()


# (rodada 11: a relaxação final fazia UMA passada e o plano 'minimo_que_cumpre' podia ser relaxado em 1 dia —
# rede 56 da semente 8. Corrigido: a relaxação repete até estabilizar. Hoje é regressão.)
def test_plano_minimo_nao_pode_ser_relaxado_em_um_dia():
    """Mesmas 150 redes: quando o plano cumpre, alongar em 1 dia a duração necessária de QUALQUER frente
    do plano (as demais como no plano) tem de estourar o prazo — é o que 'mínimo' quer dizer."""
    rng = random.Random(8)
    relaxaveis = []
    for n in range(150):
        p = _rede_aleatoria(rng)
        prazo = iso(ordinal(executar(p, "independente")["termino"]) - rng.randint(1, 20))
        r = recuperar(p, prazo=prazo)
        if r["cumpre_prazo"]:
            relaxaveis += [(n + 1, x["id"]) for x in r["plano"]
                           if _termino_com_plano(p, r["plano"], alongar=x["id"]) <= ordinal(prazo)]
    assert relaxaveis == []


# =============================================================================
# 2. sensibilidade
# =============================================================================
@pytest.mark.parametrize("obra", OBRAS)
def test_tornado_bate_com_a_simulacao_e_classifica_pela_regra(cliente, obras, obra):
    """p = 0 (sem variação): Δ = 0 em todos os grupos. Com p = 10 % e +1 equipe, pela API:
    - os 3 grupos de maior amplitude: refazendo a simulação do grupo por POST /api/simulacao (produtividade
      do independente × 1,1 e × 0,9 em cada atividade pendente do grupo; equipes + 1), o Δ em dias corridos
      é exatamente o do tornado;
    - em TODOS os grupos as marcas seguem a regra declarada: amplitude = Δpiorar − Δmelhorar;
      efeito_zero ⇔ os dois Δ nulos; reverso ⇔ piorar antecipa ou melhorar atrasa;
      assimétrico ⇔ não reverso, Δpiorar > 0 e |Δmelhorar| < 0,5 × Δpiorar; ordenação por amplitude decrescente."""
    p = obras[obra]
    assert all(g["melhorar"]["delta_dias_corridos"] == g["piorar"]["delta_dias_corridos"] == 0
               for g in tornado(p, 0.0, 0)["grupos"])
    q = {"obra": obra}
    t = cliente.get("/api/sensibilidade", params={**q, "p": 0.1, "equipes": 1}).json()
    ind = cliente.get("/api/cenarios/independente", params=q).json()
    grupos = t["grupos"]
    assert [g["amplitude_dias_uteis"] for g in grupos] == sorted((g["amplitude_dias_uteis"] for g in grupos), reverse=True)
    for g in grupos:
        dm, dp = g["melhorar"]["delta_dias_uteis"], g["piorar"]["delta_dias_uteis"]
        assert g["amplitude_dias_uteis"] == dp - dm
        zero = dm == dp == g["melhorar"]["delta_dias_corridos"] == g["piorar"]["delta_dias_corridos"] == 0
        assert g["efeito_zero"] == zero and g["reverso"] == (dp < 0 or dm > 0)
        assert g["assimetrico"] == ((not g["reverso"]) and dp > 0 and abs(dm) < LIMIAR_ASSIMETRIA * dp)
    try:
        for g in grupos[:3]:
            mem = {i: ind["atividades"][i]["memoria"] for i in g["atividades"]}
            for chave, ajustes in (
                    ("melhorar", [{"atividade_id": i, "produtividade": m["produtividade"] * 1.1} for i, m in mem.items()]),
                    ("piorar", [{"atividade_id": i, "produtividade": m["produtividade"] * 0.9} for i, m in mem.items()]),
                    ("equipes", [{"atividade_id": i, "equipes": m["equipes"] + 1} for i, m in mem.items()])):
                r = cliente.post("/api/simulacao", params=q, json={"ajustes": ajustes})
                assert r.status_code == 200, r.text[:200]
                c = r.json()["comparacao"]
                assert (c["termino_alvo"], c["delta_dias_corridos"]) == \
                       (g[chave]["termino"], g[chave]["delta_dias_corridos"]), (g["lote_id"], g["servico_id"], chave)
    finally:
        cliente.delete("/api/simulacao", params=q)


def test_cache_do_tornado_e_por_obra_e_parametros(obras):
    """Segunda chamada igual: ``cache`` True e mesmos grupos. Outros parâmetros ou outra obra: ``cache``
    False. Uma obra NOVA com outros dados (cópia com um boletim alterado), servida por outro app:
    ``cache`` False — o cache é por identidade do dicionário de dados, não por id da obra."""
    from infra4d.api import criar_app
    c = TestClient(criar_app(fontes={"ferrovia": obras["ferrovia"]}), raise_server_exceptions=False)
    a = c.get("/api/sensibilidade", params={"p": 0.2, "equipes": 0}).json()
    b = c.get("/api/sensibilidade", params={"p": 0.2, "equipes": 0}).json()
    assert b["cache"] is True and b["grupos"] == a["grupos"]
    assert c.get("/api/sensibilidade", params={"p": 0.21, "equipes": 0}).json()["cache"] is False
    d = copy.deepcopy(obras["ferrovia"].dados)
    d["medicoes"][-1]["quantidade"] *= 0.5
    c2 = TestClient(criar_app(fontes={"ferrovia": Projeto(d)}), raise_server_exceptions=False)
    assert c2.get("/api/sensibilidade", params={"p": 0.2, "equipes": 0}).json()["cache"] is False
    for ruim in ({"p": 1}, {"p": -0.1}, {"p": "x"}, {"equipes": 11}, {"equipes": -1}):
        assert c.get("/api/sensibilidade", params=ruim).status_code == 422, ruim


# Regressão: defeito da rodada 11, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: p alto aceito pela rota (p < 1) faz a duração passar do horizonte do calendário "
#   "(2040): tornado() deixa escapar ErroCalendario e a rota, que só converte ErroSensibilidade, "
#   "responde 500. Com p = 0,99 a produtividade cai a 1 % e as durações multiplicam por 100")
def test_sensibilidade_com_p_alto_nao_responde_500(cliente):
    """GET /api/sensibilidade?p=0.99: ou 200 (grupo marcado como 'além do horizonte'), ou 422 com mensagem.
    Nunca 500 (era o que respondia na rodada 11)."""
    r = cliente.get("/api/sensibilidade", params={"p": 0.99, "equipes": 0})
    assert r.status_code in (200, 422), r.status_code


# =============================================================================
# 3. exportação
# =============================================================================
PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")
CARGAS = ["=cmd|' /C calc'!A0", "+1+1", "-2+3", "@SUM(1+1)", "\t=1+1", "\r=1+1", '=HYPERLINK("http://x";"y")',
          "=1;2", '"=1+1"', "-", "+"]


def _ler_zip(conteudo: bytes, sep=";"):
    z = zipfile.ZipFile(io.BytesIO(conteudo))
    tabelas = {}
    for nome in z.namelist():
        if nome.endswith(".csv"):
            bruto = z.read(nome)
            assert bruto.startswith(b"\xef\xbb\xbf"), nome
            linhas = list(csv.reader(io.StringIO(bruto.decode("utf-8-sig"), newline=""), delimiter=sep))
            tabelas[nome[:-4]] = (linhas[0], linhas[1:])
    return z.namelist(), tabelas


def _num(txt):
    return float(txt.replace(",", "."))


def test_fmt_numerico_sem_milhar_sem_notacao_cientifica_e_reversivel():
    """Decimal ',': 1234567,891 (sem separador de milhar); −5; 1e-7 -> 0,0000001; 1e16 por extenso;
    0,1 + 0,2 -> 0,3; 1/3 com 9 casas; NaN/inf -> vazio; texto não numérico em coluna numérica sai
    NEUTRALIZADO. Em nenhum caso há 'e'/'E' na saída, e trocar ',' por '.' devolve o número (±1e-9)."""
    casos = {1234567.891: "1234567,891", -5: "-5", 1e-7: "0,0000001", 1e16: "10000000000000000",
             0.1 + 0.2: "0,3", 1 / 3: "0,333333333", 0: "0", 2.50: "2,5"}
    for v, esperado in casos.items():
        txt = X._fmt(v, "decimal", ",")
        assert txt == esperado and "e" not in txt.lower()
        assert _num(txt) == pytest.approx(v, abs=1e-9)
    assert X._fmt(float("nan"), "decimal", ",") == X._fmt(float("inf"), "inteiro", ",") == ""
    assert X._fmt("=1+1", "decimal", ",") == "'=1+1" and X._fmt("-1+cmd", "inteiro", ",") == "'-1+cmd"
    assert X._fmt(7, "inteiro", ",") == "7" and X._fmt(True, "booleano", ",") == "1" and X._fmt(None, "texto", ",") == ""
    with pytest.raises(X.ErroExportacao):
        X.parametros_csv(",", ",")


def test_injecao_de_formula_e_neutralizada_em_todo_campo_de_texto(obras):
    """Obra com cargas de fórmula (=, +, -, @, TAB e CR na frente; HYPERLINK; carga com ';' e com aspas) em
    TODOS os textos livres: nome da obra, premissas, nome/construtora dos lotes, nome/disciplina/unidade dos
    serviços, nome/disciplina/unidade das atividades e origem dos boletins. Lendo o pacote ZIP pela API
    (separador ';'): em toda coluna de tipo texto ou data, nenhuma célula começa com = + - @ TAB CR; as
    cargas aparecem inteiras com o apóstrofo na frente ('=cmd…), inclusive a que contém ';' (campo entre
    aspas, sem quebrar colunas); colunas numéricas só começam com '-' quando são número."""
    from infra4d.api import criar_app
    d = copy.deepcopy(obras["ferrovia"].dados)
    k = iter(range(10 ** 9))

    def carga():
        return CARGAS[next(k) % len(CARGAS)]

    d["ferrovia"]["nome"], d["meta"]["versao_premissas"] = carga(), carga()
    for x in d["lotes"]:
        x["nome"], x["construtora"] = carga(), carga()
    for x in d["servicos"]:
        x["nome"], x["disciplina"], x["unidade"] = carga(), carga(), carga()
    for x in d["atividades"]:
        x["nome"], x["disciplina"] = carga(), carga()
        if x.get("unidade"):
            x["unidade"] = carga()
    for x in d["medicoes"]:
        x["origem"] = carga()
    c = TestClient(criar_app(fontes={"ferrovia": Projeto(d)}), raise_server_exceptions=False)
    r = c.get("/api/exportar/pacote.zip")
    assert r.status_code == 200, r.text[:300]
    _, tabelas = _ler_zip(r.content)
    tipos = {t["nome"]: {col["nome"]: col["tipo"] for col in t["colunas"]} for t in c.get("/api/exportar/tabelas").json()["tabelas"]}
    vistas = set()
    for nome, (cab, linhas) in tabelas.items():
        assert cab == list(tipos[nome]), nome
        for linha in linhas:
            assert len(linha) == len(cab), (nome, linha[:3])
            for col, cel in zip(cab, linha):
                if tipos[nome][col] in ("texto", "data"):
                    assert not cel.startswith(PERIGOSOS), (nome, col, cel)
                    if cel[:1] == "'" and cel[1:] in CARGAS:
                        vistas.add(cel[1:])
                elif cel.startswith(PERIGOSOS):
                    assert cel.startswith("-") and _num(cel) < 0, (nome, col, cel)
    assert vistas == {x for x in CARGAS if x.startswith(PERIGOSOS)}
    assert any(l[cab.index("nome")] == '"=1+1"' for cab, ls in [tabelas["dim_atividade"]] for l in ls)


@pytest.mark.parametrize("obra", OBRAS)
def test_pacote_zip_tem_nomes_seguros_chaves_integras_e_numeros_reversiveis(cliente, obras, obra):
    """ZIP: só nomes simples ([a-z_]+.csv, LEIAME.txt, aviso.txt), sem barra nem '..'.
    Estrela: atividade_id de fato_cronograma, fato_boletim e fato_marcos existe em dim_atividade; lote_id,
    segmento_id e servico_id de dim_atividade, dim_segmento, fato_conflitos e fato_recursos existem nas
    dimensões (vazio = sem valor); obra_id é o mesmo em toda linha; chaves primárias sem repetição.
    Números: quantidade_total de dim_atividade e quantidade/equipes_dias de fato_boletim, relidos com
    decimal ',', são os do dataset (±1e-9); fato_cronograma tem 4 cenários × nº de atividades.
    Separador/decimal: tab + ponto funciona; iguais -> 422; tabela inexistente -> 404."""
    q = {"obra": obra}
    r = cliente.get("/api/exportar/pacote.zip", params=q)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    nomes, t = _ler_zip(r.content)
    assert all(re.fullmatch(r"[a-z_]+\.csv|LEIAME\.txt|aviso\.txt", n) for n in nomes) and "aviso.txt" in nomes

    def col(tab, nome):
        cab, linhas = t[tab]
        return [l[cab.index(nome)] for l in linhas]

    ativ, lotes, segs, servs = (set(col(*x)) for x in (("dim_atividade", "atividade_id"), ("dim_lote", "lote_id"),
                                                      ("dim_segmento", "segmento_id"), ("dim_servico", "servico_id")))
    for tab, c in (("fato_cronograma", "atividade_id"), ("fato_boletim", "atividade_id"), ("fato_marcos", "marco_id")):
        assert set(col(tab, c)) <= ativ, tab
    for tab in ("dim_atividade", "dim_segmento", "fato_conflitos", "fato_recursos", "fato_marcos"):
        cab = t[tab][0]
        if "lote_id" in cab:
            assert set(col(tab, "lote_id")) - {""} <= lotes, tab
        if "segmento_id" in cab:
            assert set(col(tab, "segmento_id")) - {""} <= segs, tab
        if "servico_id" in cab:
            assert set(col(tab, "servico_id")) - {""} <= servs, tab
    assert {v for tab in t for v in col(tab, "obra_id")} == {obra}
    assert len(col("dim_atividade", "atividade_id")) == len(ativ)
    pk = list(zip(col("fato_cronograma", "atividade_id"), col("fato_cronograma", "cenario")))
    assert len(pk) == len(set(pk)) == 4 * len(ativ)

    dados = obras[obra].dados
    por_id = {a["id"]: a for a in dados["atividades"]}
    for aid, txt in zip(col("dim_atividade", "atividade_id"), col("dim_atividade", "quantidade_total")):
        esperado = por_id[aid].get("quantidade_total")
        assert (txt == "") == (esperado in (None, "")) and (txt == "" or _num(txt) == pytest.approx(esperado, abs=1e-9))
    for m, qt, ed in zip(dados["medicoes"], col("fato_boletim", "quantidade"), col("fato_boletim", "equipes_dias")):
        assert _num(qt) == pytest.approx(m["quantidade"], abs=1e-9) and _num(ed) == pytest.approx(m["equipes_dias"])
        assert "e" not in qt.lower() and "." not in qt

    tsv = cliente.get("/api/exportar/dim_lote.csv", params={**q, "sep": "tab", "decimal": "."})
    assert tsv.status_code == 200 and tsv.content.startswith(b"\xef\xbb\xbf") and b"\t" in tsv.content
    assert cliente.get("/api/exportar/dim_lote.csv", params={**q, "sep": ",", "decimal": ","}).status_code == 422
    assert cliente.get("/api/exportar/nao_existe.csv", params=q).status_code == 404
    assert cliente.get("/api/exportar/pacote.zip", params={"obra": "zz"}).status_code == 404


# Regressão: defeito da rodada 11, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: boletim de atividade inexistente (órfão) é ignorado nos cálculos, mas vai para "
#   "fato_boletim com um atividade_id que não existe em dim_atividade: chave estrangeira quebrada no "
#   "modelo estrela, sem nota no LEIAME")
def test_boletim_orfao_nao_quebra_a_chave_estrangeira(obras):
    """Dataset com um boletim de 'ATIVIDADE-QUE-NAO-EXISTE': todo atividade_id de fato_boletim tem de
    existir em dim_atividade (o órfão fica fora, ou entra em tabela/nota à parte)."""
    d = copy.deepcopy(obras["rodovia"].dados)
    d["medicoes"].append({"atividade_id": "ATIVIDADE-QUE-NAO-EXISTE", "semana_inicio": "2026-10-05",
                          "quantidade": 10.0, "equipes_dias": 5, "origem": "SINTÉTICA"})
    p = Projeto(d)
    res = {c: executar(p, c) for c in X.CENARIOS_EXPORTADOS}
    tabelas, _ = X.montar_tabelas(p, "rodovia", lambda c: res[c])
    dim = {l["atividade_id"] for l in tabelas["dim_atividade"].linhas}
    assert {l["atividade_id"] for l in tabelas["fato_boletim"].linhas} <= dim


# Regressão: defeito da rodada 11, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: coluna do tipo 'inteiro' passa por float(): inteiro acima de 2^53 sai ALTERADO "
#   "(12345678901234567890 -> 12345678901234567168), sem aviso")
def test_inteiro_grande_sai_exato():
    """Um inteiro tem de sair dígito por dígito (str(int)), qualquer que seja o tamanho."""
    assert X._fmt(12345678901234567890, "inteiro", ",") == "12345678901234567890"


# Regressão: defeito da rodada 11, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: o nome do arquivo no Content-Disposition usa meta.tipo_obra cru quando ?obra= é "
#   "omitido; um tipo_obra com aspas injeta um segundo parâmetro filename no cabeçalho "
#   "(filename=\"infra4d-x\"; filename=\"evil.bat-bi.zip\")")
# Desde o P8 (tipo de obra sem padrão silencioso): meta.tipo_obra malicioso nem chega ao nome do arquivo — é
#   recusado com 422. O caminho que ainda leva texto do usuário ao cabeçalho é o id da obra (?obra=).
def test_nome_do_arquivo_no_cabecalho_e_higienizado(obras):
    """(a) meta.tipo_obra = 'x\"; filename=\"evil.bat': a exportação responde 422, com 'tipo' no detail, e
    sem cabeçalho Content-Disposition. (b) Obra cujo ID é 'x\"; filename=\"evil.bat', pedida por ?obra=: 200,
    e o cabeçalho tem um único filename, só com letras, dígitos, '-', '_' e '.'."""
    from infra4d.api import criar_app
    malicioso = 'x"; filename="evil.bat'
    d = copy.deepcopy(obras["ferrovia"].dados)
    d["meta"]["tipo_obra"] = malicioso
    c = TestClient(criar_app(fontes={"ferrovia": Projeto(d)}), raise_server_exceptions=False)
    r = c.get("/api/exportar/pacote.zip")
    assert r.status_code == 422 and "tipo" in str(r.json()["detail"]) and "content-disposition" not in r.headers
    c = TestClient(criar_app(fontes={malicioso: obras["ferrovia"]}), raise_server_exceptions=False)
    r = c.get("/api/exportar/pacote.zip", params={"obra": malicioso})
    assert r.status_code == 200
    cab = r.headers["content-disposition"]
    assert re.fullmatch(r'attachment; filename="[A-Za-z0-9._-]+"', cab), cab
    assert cab.count("filename") == 2 and cab.count('"') == 2   # "attachment; filename=" + o texto higienizado
