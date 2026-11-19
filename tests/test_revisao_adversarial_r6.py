"""Revisão adversarial — rodada 6: revisão cruzada de fiscalizacao.py e referencia_linear.py (+ rotas).

Mesmo protocolo: esperado calculado à mão no docstring; defeito confirmado fica
``xfail(strict=True, reason="DEFEITO: ...")``.
"""

import copy
import json
import math
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import fiscalizacao as F
from infra4d.cenarios import Projeto
from infra4d.referencia_linear import Eixo, ErroReferencia, Estaca, Estaqueamento, cobertura

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = ("ferrovia", "rodovia")


@pytest.fixture(scope="module")
def obras():
    return {o: Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{o}_ficticia.json") for o in OBRAS}


@pytest.fixture(scope="module")
def diarios(obras):
    return {o: F.gerar_diarios_sinteticos(p) for o, p in obras.items()}


@pytest.fixture(scope="module")
def base(obras, diarios):
    """Um diário sintético válido da ferrovia, com produção e km executado."""
    return next(r for r in diarios["ferrovia"] if r["quantidade"] > 0 and r.get("km_ini_exec") is not None)


@pytest.fixture(scope="module")
def cliente():
    from infra4d.api import criar_app
    return TestClient(criar_app(), raise_server_exceptions=False)


def regras(projeto, reg, **kw):
    r = F.validar(projeto, reg, **kw)
    return r["valido"], sorted({e["regra"] for e in r["erros"]})


# =============================================================================
# 1. fiscalização — o que resiste
# =============================================================================
@pytest.mark.parametrize("obra", OBRAS)
def test_diarios_sinteticos_sao_validos_conciliam_e_a_linha_real_e_coerente(obras, diarios, obra):
    """Nas duas obras fictícias: todo diário e todo boletim estendido gerado passa na própria validação;
    a conciliação diários × boletins tem 0 divergências e nenhum diário sem boletim; a linha real de cada
    frente tem datas estritamente crescentes, km monótono no sentido da atividade, dentro do trecho, não
    passa da data de status, e o km atual = km_ini + extensão × (executado ÷ total), com 1 m de tolerância."""
    p, ds = obras[obra], diarios[obra]
    assert all(F.validar(p, r)["valido"] for r in ds)
    assert all(F.validar(p, b)["valido"] for b in F.boletins_estendidos(p, ds))
    c = F.conciliar(p, ds)
    assert c["n_boletins"] > 0 and c["n_divergencias"] == 0 and c["diarios_sem_boletim"] == []
    frentes = F.linha_real(p, ds)["frentes"]
    assert frentes
    for f in frentes:
        a = p.atividades[f["atividade_id"]]
        s = 1 if a["km_fim"] >= a["km_ini"] else -1
        kms, datas = [x["km"] for x in f["pontos"]], [x["data"] for x in f["pontos"]]
        assert all(b > x for x, b in zip(datas, datas[1:])) and datas[-1] <= p.dados["meta"]["data_status"]
        assert all((b - x) * s >= -1e-9 for x, b in zip(kms, kms[1:]))
        lo, hi = sorted((a["km_ini"], a["km_fim"]))
        assert all(lo - 1e-6 <= k <= hi + 1e-6 for k in kms)
        feito = a["quantidade_total"] if a["status"] == "concluida" else a.get("quantidade_executada", 0)
        esperado = a["km_ini"] + (a["km_fim"] - a["km_ini"]) * min(1.0, feito / a["quantidade_total"])
        assert f["km_atual"] == pytest.approx(esperado, abs=1e-3), f["atividade_id"]


def test_validacao_recusa_o_que_deve(obras, base):
    """Partindo de um diário válido, cada alteração tem de produzir exatamente a regra indicada:
    data futura, antes do projeto, não texto; km fora do trecho, contra o sentido, só um dos dois;
    chuva 24,5 h, negativa, nula; produção sem equipe; equipe negativa; NaN e booleano em quantidade;
    aprovado sem memória (ou só espaços); estado desconhecido; sem origem; marco; lote errado."""
    p = obras["ferrovia"]
    a = p.atividades[base["atividade_id"]]
    assert regras(p, base) == (True, [])
    marco = next(x["id"] for x in p.dados["atividades"] if x.get("tipo", "tarefa") != "tarefa")
    casos = {
        "data_status": {"data": "2030-01-01"}, "data": {"data": "2020-01-01"},
        "km_no_trecho": {"km_fim_exec": max(a["km_ini"], a["km_fim"]) + 50},
        "km_sentido": {"km_ini_exec": base["km_fim_exec"], "km_fim_exec": base["km_ini_exec"]},
        "km": {"km_fim_exec": None}, "chuva": {"horas_chuva": 24.5},
        "producao_sem_equipe": {"equipes_dias": 0}, "nao_negativo": {"equipes_dias": -1},
        "numero": {"quantidade": float("nan")}, "aprovado_exige_memoria": {"estado": "aprovado"},
        "estado": {"estado": ["aprovado"]}, "origem": {"origem": ""}, "frente": {"lote_id": "L9"},
        "formato": {"ocorrencias": "chuva"}, "foto_hash": {"fotos": [{"ref": "a", "sha256": "zz"}]},
    }
    for regra, troca in casos.items():
        assert regras(p, {**base, **troca}) == (False, [regra]), regra
    assert regras(p, {**base, "data": 5}) == (False, ["data"])
    assert regras(p, {**base, "horas_chuva": -1}) == (False, ["chuva"])
    assert regras(p, {**base, "horas_chuva": None}) == (False, ["chuva"])
    assert regras(p, {**base, "quantidade": True}) == (False, ["numero"])
    assert regras(p, {**base, "estado": "aprovado", "ref_memoria_calculo": "   "}) == (False, ["aprovado_exige_memoria"])
    assert regras(p, {**base, "atividade_id": marco})[0] is False


def test_transicoes_de_estado(obras, base):
    """lancado -> conferido_fiscal -> aprovado; conferido_fiscal -> lancado (devolução). Pular etapa
    (lancado -> aprovado) e sair de aprovado (-> lancado, -> conferido_fiscal) são erro de transição."""
    p = obras["ferrovia"]

    def t(de, para):
        return regras(p, {**base, "estado": para, "ref_memoria_calculo": "MC-1"}, estado_anterior=de)

    for de, para in (("lancado", "conferido_fiscal"), ("conferido_fiscal", "aprovado"), ("conferido_fiscal", "lancado")):
        assert t(de, para) == (True, []), (de, para)
    for de, para in (("lancado", "aprovado"), ("aprovado", "lancado"), ("aprovado", "conferido_fiscal")):
        assert t(de, para) == (False, ["transicao"]), (de, para)
    assert t("xx", "lancado") == (False, ["estado"])


def test_conciliacao_aponta_quantidade_injetada(obras, diarios):
    """Somar 1 unidade a UM diário com produção gera exatamente 1 divergência, no boletim daquela janela."""
    for obra in OBRAS:
        ds = copy.deepcopy(diarios[obra])
        r = next(x for x in ds if x["quantidade"] > 0)
        r["quantidade"] += 1
        c = F.conciliar(obras[obra], ds)
        assert c["n_divergencias"] == 1
        assert c["divergencias"][0]["atividade_id"] == r["atividade_id"]
        assert c["divergencias"][0]["delta_quantidade"] == pytest.approx(1, abs=1e-6)


def test_rota_validar_resiste_a_json_estranho(cliente, base):
    """POST /api/fiscalizacao/validar: lista, número, null e texto -> 200 com valido=false (regra 'formato');
    corpo vazio e JSON quebrado -> 422; 100 mil colchetes aninhados e inteiro de 5000 dígitos -> 400;
    NaN, 1e999, chaves duplicadas, estado_anterior lista/objeto, 200 mil fotos -> 200, nunca 500."""
    def post(bruto):
        return cliente.post("/api/fiscalizacao/validar", content=bruto, headers={"Content-Type": "application/json"})

    for bruto in ("[1,2]", "5", "null", '"x"'):
        r = post(bruto)
        assert r.status_code == 200 and r.json()["valido"] is False and r.json()["erros"][0]["regra"] == "formato"
    assert post("").status_code == 422 and post("{").status_code == 422
    assert post("[" * 100000 + "]" * 100000).status_code == 400
    assert post('{"quantidade": ' + "9" * 5000 + "}").status_code == 400
    for bruto in ('{"quantidade": NaN}', '{"quantidade": 1e999}', '{"estado":"lancado","estado":"aprovado"}',
                  json.dumps({**base, "estado_anterior": ["x"]}), json.dumps({**base, "estado_anterior": {"a": 1}}),
                  json.dumps({**base, "atividade_id": {"a": 1}}), json.dumps({**base, "fotos": [{"ref": "a"}] * 200000})):
        assert post(bruto).status_code == 200, bruto[:60]
    assert post(json.dumps(base)).json()["valido"] is True


# =============================================================================
# 1b. fiscalização — defeitos
# =============================================================================
@pytest.mark.parametrize("aviso", [
    "DADOS REAIS — este arquivo NÃO é fictício",
    "Obra real. Não contém dado sintético.",
    "Medição real da Rodovia Fictícia Ltda",
])
def test_gerador_recusa_obra_cujo_aviso_nega_ser_ficticia(obras, aviso):
    """Com cada aviso acima (obra declarada REAL), gerar_diarios_sinteticos tem de levantar ErroFiscalizacao,
    como faz com aviso vazio. Sugestão do revisor, adotada no ADR-0005: marca explícita e booleana (meta.ficticio).

    Ajuste do orquestrador após a correção: uma obra declarada real NÃO tem `meta.ficticio: true`. O teste
    agora simula isso de três formas (marca ausente, False e o TEXTO "true") e ainda usa o aviso enganoso
    — a trava não pode ceder ao texto do aviso NEM a uma marca que não seja o booleano True."""
    for marca in ("ausente", False, "true"):
        d = dict(obras["ferrovia"].dados)
        meta = dict(d["meta"], aviso=aviso + " (DADOS INTEIRAMENTE FICTÍCIOS)")
        if marca == "ausente":
            meta.pop("ficticio", None)
        else:
            meta["ficticio"] = marca
        d["meta"] = meta
        with pytest.raises(F.ErroFiscalizacao):
            F.gerar_diarios_sinteticos(Projeto(d))


@pytest.mark.parametrize("campo", ["quantidade", "km_ini_exec", "horas_chuva"])
def test_validar_com_inteiro_gigante_devolve_erro_de_validacao(cliente, base, campo):
    """Diário válido com o campo trocado por um inteiro de 400 dígitos: esperado 200 com valido=false e um
    erro no campo (como acontece com 1e999 e NaN). Hoje: 500."""
    bruto = json.dumps({**base, campo: 0}).replace(f'"{campo}": 0', f'"{campo}": ' + "9" * 400)
    r = cliente.post("/api/fiscalizacao/validar", content=bruto, headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    assert r.json()["valido"] is False


@pytest.mark.parametrize("caso", ["data fora das janelas", "atividade sem boletim"])
def test_conciliacao_conta_producao_sem_boletim_como_divergencia(obras, diarios, caso):
    """Injeta UM diário com produção: (a) na data de status, depois da última janela de boletim da frente;
    (b) numa atividade por quantidade que não tem boletim. Nos dois casos há produção em diário sem boletim
    que a cubra: n_divergencias tem de ser >= 1. Hoje é 0 (e diarios_sem_boletim tem 1 item)."""
    p = obras["ferrovia"]
    ds = copy.deepcopy(diarios["ferrovia"])
    extra = dict(next(x for x in ds if x["quantidade"] > 0))
    if caso == "data fora das janelas":
        extra["data"] = p.dados["meta"]["data_status"]
    else:
        com_boletim = {m["atividade_id"] for m in p.dados["medicoes"]}
        extra["atividade_id"] = next(a["id"] for a in p.dados["atividades"]
                                     if a.get("quantidade_total") and a["id"] not in com_boletim)
    c = F.conciliar(p, ds + [extra])
    assert len(c["diarios_sem_boletim"]) == 1
    assert c["n_divergencias"] >= 1


@pytest.mark.parametrize("dias_chuva", [999, -1, "x"])
def test_boletim_com_dias_de_chuva_impossiveis_e_recusado(obras, base, dias_chuva):
    """Boletim de 1 dia (periodo_ini = periodo_fim). dias_chuva só pode ser inteiro de 0 a 1."""
    bol = {"tipo": "boletim", "atividade_id": base["atividade_id"], "periodo_ini": base["data"],
           "periodo_fim": base["data"], "quantidade": 1, "equipes_dias": 1, "estado": "lancado", "origem": "x",
           "dias_chuva": dias_chuva}
    assert F.validar(obras["ferrovia"], bol)["valido"] is False


@pytest.mark.parametrize("caso", ["atividade nao iniciada", "quantidade 100x o total"])
def test_validar_avisa_incoerencia_com_a_atividade(obras, base, caso):
    """(a) Diário com produção, datado antes da data de status, para atividade cujo status é 'nao_iniciada'
    e executado 0. (b) Um único dia com 100 vezes a quantidade total da atividade. Esperado: erro, ou ao
    menos um aviso além do aviso genérico de obra fictícia."""
    p = obras["ferrovia"]
    if caso == "atividade nao iniciada":
        a = next(x for x in p.dados["atividades"] if x["status"] == "nao_iniciada" and x.get("quantidade_total")
                 and "km_ini" in x)
        reg = {**base, "atividade_id": a["id"], "lote_id": a["lote_id"], "segmento_id": a.get("segmento_id"),
               "km_ini_exec": a["km_ini"], "km_fim_exec": a["km_ini"]}
    else:
        reg = {**base, "quantidade": p.atividades[base["atividade_id"]]["quantidade_total"] * 100}
    r = F.validar(p, reg)
    especificos = [x for x in r["avisos"] if "FICTÍCIA" not in x]
    assert (not r["valido"]) or especificos


@pytest.mark.parametrize("data", ["20260331", "2026-W14-2"])
def test_validar_so_aceita_data_no_formato_declarado(obras, base, data):
    """31/03/2026 escrito como '20260331' ou como semana ISO '2026-W14-2' (terça da semana 14) não está no
    formato AAAA-MM-DD: esperado erro de regra 'data'. Hoje o registro é válido."""
    assert regras(obras["ferrovia"], {**base, "data": data}) == (False, ["data"])


# =============================================================================
# 2. referência linear — o que resiste
# =============================================================================
def test_estaca_texto_e_limites():
    """'125+20,00' é inválida (fração em [0, 20)); '125+19,999' fecha em '126+00,00' (nunca N+20,00);
    ponto e vírgula decimais são aceitos; '-3+05,00' = −55 m; '1 234+5' e '12+5,5,5' são inválidas."""
    with pytest.raises(ErroReferencia):
        Estaca.de_texto("125+20,00")
    assert Estaca.de_texto("125+19,999").texto() == "126+00,00"
    assert Estaca.de_texto("125+19.5").texto() == Estaca.de_texto("125+19,5").texto() == "125+19,50"
    assert Estaca.de_texto("-3+05,00").metros == -55.0
    for ruim in ("1 234+5", "12+5,5,5", "12", "+5", "12+"):
        with pytest.raises(ErroReferencia):
            Estaca.de_texto(ruim)


def test_ida_e_volta_com_equacoes_que_recuam_e_avancam():
    """Equações: km 1 -> 40+00 (RECUA de 50+00), km 2 -> 150+00 (AVANÇA de 90+00), km 3 -> 120+10 (recua),
    km 3,5 -> 300+00 (avança). Para 20 mil km sorteados em [−0,5; 5]: km -> Estaca -> km é identidade
    (erro < 1e-12 km) e km -> texto + trecho -> km erra no máximo 5 mm (arredondamento ao cm).
    Casos à mão: 45+00 é ambígua (km 0,9 no trecho 0 e 1,1 no trecho 1); 100+00 cai no salto 90+00..150+00;
    40+00 com trecho 1 = km 1,0 e com trecho 0 = km 0,8."""
    e = Estaqueamento(0, [{"km": 1.0, "estaca": "40+00,00"}, {"km": 2.0, "estaca": "150+00,00"},
                          {"km": 3.0, "estaca": "120+10,00"}, {"km": 3.5, "estaca": "300+00,00"}])
    rng = random.Random(1)
    for _ in range(20000):
        km = rng.uniform(-0.5, 5)
        est = e.km_para_estaca(km)
        assert e.estaca_para_km(est) == pytest.approx(km, abs=1e-12)
        assert e.estaca_para_km(est.texto(), trecho=est.trecho) == pytest.approx(km, abs=5.1e-6)
    with pytest.raises(ErroReferencia, match="ambígua"):
        e.estaca_para_km("45+00,00")
    with pytest.raises(ErroReferencia, match="salto"):
        e.estaca_para_km("100+00,00")
    assert e.estaca_para_km("40+00,00", trecho=1) == pytest.approx(1.0)
    assert e.estaca_para_km("40+00,00", trecho=0) == pytest.approx(0.8)
    with pytest.raises(ErroReferencia):
        Estaqueamento(0, [{"km": 2, "estaca": "1+0"}, {"km": 1, "estaca": "1+0"}])


def test_eixo_recusa_pontos_repetidos_e_km_nao_crescente_e_projeta_em_curva_de_90_graus():
    """Pontos consecutivos iguais, km repetido, 1 ponto só e ponto sem y são ErroReferencia.
    Eixo em L: (0,0) -> (10,0) -> (10,10), curva à ESQUERDA no km 10. Ponto (10,5; −0,5), fora da curva,
    projeta no vértice (km 10), lado DIREITO, afastamento √0,5. Ponto (8; 1), dentro da curva, é esquerdo."""
    for pts in ([[0, 0, 0], [1, 0, 0]], [[0, 0, 0], [0, 1, 0]], [[0, 0, 0]], [[0, 0], [1, 1]]):
        with pytest.raises(ErroReferencia):
            Eixo(pts)
    e = Eixo([[0, 0, 0], [10, 10, 0], [20, 10, 10]])
    fora = e.localizar(10.5, -0.5)
    assert (fora["km"], fora["lado"]) == (10.0, "direito") and fora["afastamento_m"] == pytest.approx(math.sqrt(0.5))
    assert e.localizar(8, 1)["lado"] == "esquerdo"


def test_rotas_de_referencia_com_valores_extremos(cliente):
    """km nan/inf/−1/1e400 e x nan/inf -> 422 com mensagem; '12,5' (vírgula decimal) -> 422 do FastAPI;
    km e estaca juntos, ou nenhum -> 422; '125+20,00' -> 422; trecho inexistente -> 422; obra desconhecida
    -> 404; 250+00,00 = km 5 nas duas obras; coordenada 1e308 -> 200 (projeção no extremo, sem NaN)."""
    def g(rota, **p):
        return cliente.get(f"/api/referencia/{rota}", params=p)

    for p in ({"km": "nan"}, {"km": "inf"}, {"km": "-1"}, {"km": "1e400"}, {"km": "12,5"}, {"km": 5, "estaca": "1+0"}, {},
              {"estaca": "125+20,00"}, {"estaca": "250+00,00", "trecho": 3}, {"estaca": "250+00,00", "trecho": -1}):
        assert g("km", **p).status_code == 422, p
    for p in ({"x": "nan", "y": 0}, {"x": "inf", "y": 0}, {"x": "1,5", "y": 0}, {"x": 0}):
        assert g("ponto", **p).status_code == 422, p
    assert g("km", km=5, obra="x").status_code == 404
    for obra in OBRAS:
        assert g("km", estaca="250+00,00", obra=obra).json()["km"] == 5.0
    longe = g("ponto", x=1e308, y=1e308)
    assert longe.status_code == 200 and math.isfinite(longe.json()["distancia_m"])


# =============================================================================
# 2b. referência linear — defeitos
# =============================================================================
@pytest.mark.parametrize("digitos", [400, 5000])
def test_estaca_com_numero_gigante_e_erro_de_referencia(cliente, digitos):
    """GET /api/referencia/km?estaca=999…9+1: esperado 422 ('estaca inválida' ou fora do eixo). Hoje 500."""
    assert cliente.get("/api/referencia/km", params={"estaca": "9" * digitos + "+1"}).status_code == 422


@pytest.mark.parametrize("construir", [
    lambda: Eixo([[0, 0, 0], [1, float("nan"), 0], [2, 5, 5]]),
    lambda: Eixo([[0, 0, 0], [1, float("inf"), 0]]),
    lambda: Eixo([["a", 0, 0], [1, 1, 1]]),
    lambda: Estaqueamento(0, [{"km": "abc", "estaca": "1+0"}]),
    lambda: Estaqueamento(0, [(1, 2, 3)]),
])
def test_dados_de_eixo_invalidos_dao_erro_de_referencia(construir):
    """Cada construção acima usa dado de eixo inválido e tem de levantar ErroReferencia."""
    try:
        construir()
    except ErroReferencia:
        return
    pytest.fail("aceito sem ErroReferencia")


def test_lado_em_curva_fechada():
    """Eixo: (0,0) -> (10,0) -> (5,5): curva à ESQUERDA de 135° no km 10. O lado de fora de uma curva à
    esquerda é o DIREITO. O ponto (11; 0,5) está fora da curva, a √1,25 m do vértice: lado 'direito',
    afastamento +1,118. O motor devolve 'esquerdo', −1,118."""
    e = Eixo([[0, 0, 0], [10, 10, 0], [10 + math.sqrt(50), 5, 5]])
    assert e.localizar(12, 3)["lado"] == "direito"
    loc = e.localizar(11, 0.5)
    assert loc["km"] == 10.0 and loc["lado"] == "direito"
    assert loc["afastamento_m"] == pytest.approx(math.sqrt(1.25))


def test_cobertura_inclui_atividade_de_trecho_invertido():
    """Lote km 0–20. Atividade A executa do km 10 para o km 5; B do km 5 para o km 10. No km 7 as duas
    frentes cobrem o ponto: cobertura = [A, B]. Hoje só B."""
    d = {"lotes": [{"id": "L1", "km_ini": 0, "km_fim": 20}], "segmentos": [],
         "atividades": [{"id": "A", "km_ini": 10, "km_fim": 5}, {"id": "B", "km_ini": 5, "km_fim": 10}]}
    assert sorted(a["id"] for a in cobertura(d, 7)["atividades"]) == ["A", "B"]
