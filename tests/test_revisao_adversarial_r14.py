"""Revisão adversarial — rodada 14: porta de entrada de dado real.
``importar_medicoes.py`` + ``rotas_medicoes.py`` (CSV de medições) e ``adaptador_obrasgov.py``.

Mesmo protocolo: esperado calculado à mão no docstring; defeito confirmado fica
``xfail(strict=True, reason="DEFEITO: ...")``.

Linha-modelo dos CSV deste arquivo (obra fictícia 'ferrovia', data de status 09/11/2026):
    L3-S03-TER;2026-11-05;;<quantidade>;<equipes_dias>;;;0;lancado;;x
"""

import copy
import csv
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import adaptador_obrasgov as OG
from infra4d import importar_medicoes as M
from infra4d.cenarios import Projeto

RAIZ = Path(__file__).resolve().parents[1]
CAB = ("atividade_id;data;semana_inicio;quantidade;equipes_dias;km_ini_exec;km_fim_exec;horas_chuva;estado;"
       "ref_memoria_calculo;observacao")
LINHA = "L3-S03-TER;2026-11-05;;{q};{e};;;0;lancado;;x"


def linha(q="100", e="1", data="2026-11-05", ativ="L3-S03-TER", obs="x"):
    return LINHA.format(q=q, e=e).replace("2026-11-05", data).replace("L3-S03-TER", ativ).replace(";x", ";" + obs)


def arq(linhas, meta="#ficticio=true\n", cab=CAB):
    return meta + cab + "\n" + "\n".join(linhas) + "\n"


@pytest.fixture(scope="module")
def ficticia():
    return Projeto.carregar(RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json")


@pytest.fixture(scope="module")
def real(ficticia):
    """A mesma obra SEM a marca de fictícia (meta.ficticio = false): faz o papel de obra real."""
    d = copy.deepcopy(ficticia.dados)
    d["meta"]["ficticio"] = False
    return Projeto(d)


@pytest.fixture(autouse=True)
def _limite_csv():
    """Restaura o limite global do módulo csv depois de cada teste (ver o defeito do limite, abaixo)."""
    antes = csv.field_size_limit()
    yield
    csv.field_size_limit(antes)


def resumo(projeto, conteudo):
    r = M.importar(projeto, conteudo)
    return r["aprovado"], r["aceitas"], [[e["regra"] for e in z["erros"]] for z in r["rejeitadas"]]


def _hash(projeto):
    return hashlib.sha256(json.dumps(projeto.dados, sort_keys=True).encode()).hexdigest()


# =============================================================================
# 1. importação de medições — o que resiste
# =============================================================================
@pytest.mark.parametrize("celula", ["1e3", "0x10", "1_000", "∞", "NaN", "+1", "--1", " =1", "\t=1", "＝1", "1.5",
                                    "1,2,3", "1.23.456", "'100", "100%", "1,5e2", "²", "9" * 400, "=2*3", "-1+3",
                                    "@SUM(A1)", "1/2"])
def test_fórmula_ou_numero_estranho_nunca_vira_quantidade(ficticia, celula):
    """Cada célula acima, na coluna quantidade de um arquivo com ';' e vírgula decimal, é RECUSADA com a
    regra 'numero' (notação científica, hexadecimal, sublinhado, infinito, NaN, sinal '+', duplo '−', '='
    com espaço ou TAB na frente, '＝' de largura total, ponto decimal ambíguo, fórmula, 400 dígitos = inf).
    Nada é avaliado e o arquivo não é aprovado."""
    aprovado, aceitas, erros = resumo(ficticia, arq([linha(q=celula)]))
    assert (aprovado, aceitas, erros) == (False, 0, [["numero"]])


def test_numeros_pt_br_validos_e_negativo(ficticia):
    """'12,5' -> 12,5; '1.234,5' -> 1234,5; '1 234,5' -> 1234,5; '0,0' -> 0. Com separador ',' o decimal é o
    ponto: '1000.5' -> 1000,5. Negativo ('-5') é número, e a regra de quantidade não negativa o recusa."""
    for celula, valor in (("12,5", 12.5), ("1.234,5", 1234.5), ("1 234,5", 1234.5), ("0,0", 0.0)):
        r = M.importar(ficticia, arq([linha(q=celula)]))
        assert r["aprovado"] and r["medicoes_novas"][0]["quantidade"] == valor, celula
    r = M.importar(ficticia, arq(["L3-S03-TER,2026-11-05,,1000.5,1,,,0,lancado,,x"], cab=CAB.replace(";", ",")))
    assert (r["separador"], r["decimal"], r["medicoes_novas"][0]["quantidade"]) == (",", ".", 1000.5)
    assert resumo(ficticia, arq([linha(q="-5")])) == (False, 0, [["nao_negativo"]])


def test_duplicidade_e_tudo_ou_nada(ficticia):
    """Mesma (atividade, data) duas vezes; a 2ª com espaços em volta da data; a 2ª como semana_inicio; o id
    com espaço no fim: 'duplicado'. Chave que já existe nos boletins da obra: 'duplicado'. Data na própria
    data de status: 'na_data_status'. Uma linha boa + uma ruim: NÃO aprovado, sem projeto em memória e com o
    motivo 'tudo ou nada'. (Data em outra grafia não entra: só AAAA-MM-DD é aceito.)"""
    for segunda in (linha(q="5"), linha(q="5", data=" 2026-11-05 "), "L3-S03-TER;;2026-11-05;5;1;;;0;lancado;;x",
                    linha(q="5", ativ="L3-S03-TER ")):
        assert resumo(ficticia, arq([linha(), segunda])) == (False, 1, [["duplicado"]])
    for grafia in ("20261105", "05/11/2026", "2026-W45-4", "2026-11-5"):
        assert resumo(ficticia, arq([linha(data=grafia)]))[2][0][0] == "data"
    ex = ficticia.dados["medicoes"][-1]
    assert resumo(ficticia, arq([f"{ex['atividade_id']};;{ex['semana_inicio']};5;1;;;0;lancado;;x"]))[2] == [["duplicado"]]
    assert resumo(ficticia, arq([linha(q="1", data="2026-11-09")]))[2] == [["na_data_status"]]
    r = M.importar(ficticia, arq([linha(), linha(q="abc", data="2026-11-04")]))
    assert (r["aprovado"], r["aceitas"], len(r["rejeitadas"]), "_projeto" in r) == (False, 1, 1, False)
    assert "tudo ou nada" in r["motivo"]


def test_arquivo_malformado_e_recusado_com_erro_claro(ficticia):
    """Latin-1 e UTF-16 -> 'não está em UTF-8'; BOM duplo, vazio, só metadados, coluna repetida, coluna
    obrigatória ausente, separador misturado no cabeçalho, linha com célula de 100 mil caracteres,
    50.001 linhas e 5 MB + 1 byte -> ErroArquivo (a rota responde 422). Célula de 1.001 caracteres e linha
    com colunas a mais: linha rejeitada ('tamanho' / 'formato'). CR, CRLF e NUL numa célula: aceitos.
    50.000 linhas (o limite) são processadas."""
    base = arq([linha()])
    recusados = [base.replace(";x", ";ç").encode("latin-1"), base.encode("utf-16"),
                 b"\xef\xbb\xbf\xef\xbb\xbf" + base.encode(), "", "#ficticio=true\n", arq([], cab=CAB + ";data"),
                 arq([], cab=CAB.replace("quantidade;", "")), arq([linha()], cab=CAB.replace(";", ",", 5)),
                 arq([linha(obs="y" * 100000)]), arq([linha(q="1")] * 50001),
                 ("#ficticio=true\n" + CAB + "\n" + "x" * (5 * 1024 * 1024)).encode()]
    for conteudo in recusados:
        with pytest.raises(M.ErroArquivo) as e:
            M.importar(ficticia, conteudo)
        assert str(e.value)
    assert resumo(ficticia, arq([linha(obs="y" * 1001)]))[2] == [["tamanho"]]
    assert resumo(ficticia, arq([linha() + ";a;b"]))[2] == [["formato"]]
    for ok in (base.replace("\n", "\r"), base.replace("\n", "\r\n"), arq([linha(obs="a\x00b")])):
        assert resumo(ficticia, ok) == (True, 1, [])
    r = M.importar(ficticia, arq([linha(q="1")] * 50000))
    assert (r["linhas"], r["aceitas"], len(r["rejeitadas"])) == (50000, 1, 49999)


@pytest.mark.parametrize("marca", ["#ficticio=true\n", "\n\n#ficticio=true\n"])
def test_marca_de_ficticio_reconhecida_separa_as_obras(ficticia, real, marca):
    """A marca exata '#ficticio=true' (também com linhas em branco antes) faz o arquivo entrar na obra
    fictícia e ser RECUSADO na obra real."""
    conteudo = arq([linha()], meta=marca)
    assert M.importar(ficticia, conteudo)["ficticio"] is True
    with pytest.raises(M.ErroArquivo, match="obra real"):
        M.importar(real, conteudo)


# Contrato desde a correção da rodada 14: a marca é EXATA. Na rodada 14 estas grafias valiam 'true' (e este
# arquivo as tratava como reconhecidas); a correção do bypass fictício × real as tornou erro do arquivo.
@pytest.mark.parametrize("marca", ["#ficticio=TRUE\n", "# ficticio = true\n", "#FICTICIO=Sim\n", "##ficticio=true\n",
                                   "#ficticio=false\n#ficticio=true\n", "#ficticio=0\n"])
def test_grafia_frouxa_da_marca_e_erro_nas_duas_obras(ficticia, real, marca):
    """Grafia que não é exatamente '#ficticio=true|false', ou marca repetida, é ERRO do arquivo tanto na obra
    fictícia quanto na real — nunca vale 'true' nem 'false'."""
    for obra in (ficticia, real):
        with pytest.raises(M.ErroArquivo, match="inválida|repetida"):
            M.importar(obra, arq([linha()], meta=marca))


def test_obra_ficticia_recusa_arquivo_sem_marca_e_marca_no_meio(ficticia):
    """Sem marca ou com '#ficticio=false': a obra fictícia recusa. '#ficticio=false' no MEIO do arquivo
    é linha de dados inválida: o arquivo inteiro não é aprovado."""
    for meta in ("", "#ficticio=false\n"):
        with pytest.raises(M.ErroArquivo, match="FICTÍCIA"):
            M.importar(ficticia, arq([linha()], meta=meta))
    assert resumo(ficticia, arq([linha(), "#ficticio=false", linha(q="5", data="2026-11-04")]))[0] is False


def test_aplicar_em_memoria_deixa_obra_dataset_e_api_intactos(ficticia):
    """Fixture válida (4 linhas). Direto: aprovado, 4 boletins a mais no projeto EM MEMÓRIA e o projeto
    original com o mesmo hash. Pela API com aplicar=true: 200, 'persistido' false, e DEPOIS disso o painel,
    o cenário independente e o nº de boletins de /api/projeto são idênticos aos de antes (o cache do Estado
    não foi tocado); o arquivo do dataset em disco tem o mesmo hash. Corpo vazio 400; multipart 415;
    5 MB + 1 -> 413; obra desconhecida 404; arquivo com erro e aplicar=true -> 200 com 'aplicado' false."""
    from infra4d.api import criar_app
    caminho = RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json"
    disco = hashlib.sha256(caminho.read_bytes()).hexdigest()
    valida = (RAIZ / "examples" / "fixtures" / "medicoes_validas.csv").read_bytes()
    h0 = _hash(ficticia)
    r = M.importar(ficticia, valida)
    assert r["aprovado"] and r["aceitas"] == 4
    assert len(r["_projeto"].dados["medicoes"]) == len(ficticia.dados["medicoes"]) + 4 and _hash(ficticia) == h0

    c = TestClient(criar_app(fontes={"ferrovia": ficticia}), raise_server_exceptions=False)
    antes = (c.get("/api/painel").json(), c.get("/api/cenarios/independente").json(),
             len(c.get("/api/projeto").json()["medicoes"]) if "medicoes" in c.get("/api/projeto").json() else None)

    def post(corpo, **p):
        return c.post("/api/medicoes/importar", params=p, content=corpo, headers={"Content-Type": "text/csv"})

    resp = post(valida, aplicar="true")
    assert resp.status_code == 200
    j = resp.json()
    assert j["aplicado"] is True and j["simulacao"]["persistido"] is False and "_projeto" not in j
    assert j["simulacao"]["termino_antes"] == antes[1]["termino"]
    depois = (c.get("/api/painel").json(), c.get("/api/cenarios/independente").json(),
              len(c.get("/api/projeto").json()["medicoes"]) if "medicoes" in c.get("/api/projeto").json() else None)
    assert depois == antes and _hash(ficticia) == h0
    assert hashlib.sha256(caminho.read_bytes()).hexdigest() == disco
    assert post(b"").status_code == 400
    assert c.post("/api/medicoes/importar", content=b"x", headers={"Content-Type": "multipart/form-data; boundary=x"}).status_code == 415
    assert post(b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert post(valida, obra="zz").status_code == 404
    ruim = post(arq([linha(q="abc")]).encode(), aplicar="true")
    assert ruim.status_code == 200 and ruim.json()["aplicado"] is False and ruim.json()["simulacao"] is None


# =============================================================================
# 1b. importação de medições — defeitos
# =============================================================================
# Regressão: defeito da rodada 14, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: a regra fictício × real é contornável. Numa obra REAL, o arquivo só é barrado se a marca "
#   "for lida como 'verdadeira'; qualquer grafia que o leitor NÃO reconhece vale 'não é fictício' e o "
#   "arquivo ENTRA: marca duplicada contraditória (vale a última), '#ficticio: true' (dois-pontos), "
#   "'#fictício=true' (acento), '#ficticio=true # comentário', '#ficticio=verdade', '#ficticio=\"true\"', "
#   "'#ficticio=on'. Dado sintético entra em obra real — o contrário do que o ADR-0005 quer")
@pytest.mark.parametrize("marca", ["#ficticio=true\n#ficticio=false\n", "#ficticio: true\n", "#fictício=true\n",
                                   "#ficticio=true # gerado pelo simulador\n", "#ficticio=verdade\n",
                                   '#ficticio="true"\n', "#ficticio=on\n"])
def test_obra_real_recusa_arquivo_que_se_declara_ficticio_em_qualquer_grafia(real, marca):
    """Cada cabeçalho acima traz uma declaração de fictício que um humano lê como 'sim' (ou é contraditória).
    Numa obra real o arquivo tem de ser recusado: a marca só pode ser exatamente true/false, uma vez; valor
    ou chave não reconhecidos e marca repetida são ERRO, não 'falso'. (Na rodada 14 todos eram aceitos e aprovados.)"""
    with pytest.raises(M.ErroArquivo):
        M.importar(real, arq([linha()], meta=marca))


# Regressão: defeito da rodada 14, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: aspas não fechadas não são erro — o leitor CSV (não estrito) engole as linhas seguintes "
#   "para dentro da célula e o arquivo é APROVADO com menos linhas do que tem: a medição da 2ª linha some "
#   "em silêncio dentro do texto de 'observacao'")
def test_aspas_nao_fechadas_nao_engolem_linhas(ficticia):
    """Duas medições; a 1ª tem a observação aberta com aspas e nunca fechada. Esperado: arquivo recusado
    (ErroArquivo) ou, no mínimo, não aprovado. Na rodada 14: aprovado com 1 linha aceita (a de 05/11); a de 04/11
    não aparece nem como aceita nem como rejeitada."""
    conteudo = arq([linha(obs='"sem fechar'), linha(q="5", data="2026-11-04")])
    try:
        r = M.importar(ficticia, conteudo)
    except M.ErroArquivo:
        return
    assert not r["aprovado"] or r["linhas"] == 2


# Regressão: defeito da rodada 14, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: `csv.field_size_limit(MAX_CELULA * 4)` altera o limite GLOBAL do módulo csv (de 131.072 "
#   "para 4.000) e nunca o restaura: depois de uma importação de medições, qualquer leitura de CSV no mesmo "
#   "processo com célula acima de 4.000 caracteres passa a falhar")
def test_importar_nao_altera_o_limite_global_do_csv(ficticia):
    """O limite de tamanho de campo do módulo csv tem de ser o mesmo antes e depois de importar."""
    antes = csv.field_size_limit()
    M.importar(ficticia, arq([linha()]))
    assert csv.field_size_limit() == antes


# Regressão: defeito da rodada 14, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: as expressões de número usam \\d, que casa dígitos Unicode: '١٢٣' (arábico-índico), "
#   "'۱۲' (persa) e '１２３' (largura total) entram como 123/12/123 sem aviso. Não é fórmula, mas é uma grafia que "
#   "nenhum relatório mostra como foi digitada e que o Excel pt-BR não trata como número")
@pytest.mark.parametrize("celula", ["١٢٣", "۱۲", "１２３"])
def test_digitos_nao_ascii_nao_viram_numero_em_silencio(ficticia, celula):
    """Quantidade escrita com dígitos não ASCII: recusada com a regra 'numero' (ou aceita COM aviso na
    linha). (Na rodada 14: aceita sem aviso.)"""
    r = M.importar(ficticia, arq([linha(q=celula)]))
    sobre_a_celula = [a for a in r["avisos"] if celula in a["mensagem"] or "dígito" in a["mensagem"].lower()]
    assert (not r["aprovado"]) or sobre_a_celula


# =============================================================================
# 2. adaptador Obrasgov
# =============================================================================
@pytest.fixture(scope="module")
def obrasgov():
    return json.loads((RAIZ / "examples" / "fixtures" / "obrasgov_sintetico.json").read_text(encoding="utf-8"))


def _pi(e):
    return e["projeto_investimento"]["data"][0]


def test_obrasgov_marca_booleana_nada_inventado_e_rastreio(obrasgov):
    """Marca: só ``_infra4d_ficticio: true`` (booleano) dá meta.ficticio True; 'true' em texto, 1 e ausente
    dão False e o aviso de dado público. Nada inventado: a saída não tem 'atividades', 'relacoes',
    'calendarios' nem 'medicoes'; lotes sem km; extensão None; e as lacunas dizem isso.
    Rastreio: cada lote, cada ponto de avanço e cada situação trazem o id de origem que está na entrada;
    cada marco traz o campo de origem e a data é a desse campo; meta.termino_contratual = dt_final_prevista."""
    r = OG.converter(obrasgov)
    assert r["meta"]["ficticio"] is True and "FICTÍCIOS" in r["meta"]["aviso"]
    for valor in ("true", 1, None):
        e = copy.deepcopy(obrasgov)
        if valor is None:
            e.pop("_infra4d_ficticio")
        else:
            e["_infra4d_ficticio"] = valor
        s = OG.converter(e)
        assert s["meta"]["ficticio"] is False and "FICTÍCIOS" not in s["meta"]["aviso"]
    assert not {"atividades", "relacoes", "calendarios", "medicoes"} & set(r)
    assert all(x["km_ini"] is None and x["km_fim"] is None for x in r["lotes"]) and r["ferrovia"]["extensao_km"] is None
    assert len(r["lacunas"]) == 3
    p = _pi(obrasgov)
    assert {x["id_origem"] for x in r["lotes"]} == {c["id_contrato"] for c in obrasgov["contrato"]["data"]}
    assert [x["id_origem"] for x in r["avanco_fisico"]] == r["rastreio"]["execucoes"]
    assert set(r["rastreio"]["execucoes"]) == {x["id_execucao_fisica"] for x in obrasgov["execucao_fisica"]["data"]}
    assert r["rastreio"]["id_projeto_investimento"] == p["id_projeto_investimento"] == r["ferrovia"]["id"]
    for m in r["marcos"]:
        assert p[m["campo_origem"]][:10] == m["data"]
    assert r["meta"]["termino_contratual"] == p["dt_final_prevista"][:10]
    por_id = {x["id_execucao_fisica"]: x for x in obrasgov["execucao_fisica"]["data"]}
    for x in r["avanco_fisico"]:
        assert x["percentual"] == por_id[x["id_origem"]]["percentual_execucao_fisica"]


def test_obrasgov_entrada_malformada_reconhecida_e_enorme(obrasgov):
    """Entrada que não é objeto ([], texto, None, número, {}), envelope em lista, 'data' que não é lista,
    2 projetos, id fora do formato, percentual em texto, data numérica, data ilegível, páginas faltando e
    registro de outro projeto -> ErroObrasgov. 100 mil execuções: convertidas sem erro."""
    for x in ([], "x", None, 5, {}):
        with pytest.raises(OG.ErroObrasgov):
            OG.converter(x)
    mutacoes = [
        lambda e: e.__setitem__("contrato", []), lambda e: e["contrato"].__setitem__("data", "x"),
        lambda e: e["projeto_investimento"]["data"].append(_pi(e)),
        lambda e: _pi(e).__setitem__("id_projeto_investimento", "1"),
        lambda e: e["execucao_fisica"]["data"][0].__setitem__("percentual_execucao_fisica", "50"),
        lambda e: e["execucao_fisica"]["data"][0].__setitem__("percentual_execucao_fisica", 101),
        lambda e: _pi(e).__setitem__("dt_final_prevista", 20270101),
        lambda e: _pi(e).__setitem__("dt_final_prevista", "Tarde demais"),
        lambda e: e["contrato"].__setitem__("total_items", 99),
        lambda e: e["contrato"]["data"][0].__setitem__("id_projeto_investimento", "99999.99-99"),
    ]
    for mut in mutacoes:
        e = copy.deepcopy(obrasgov)
        mut(e)
        with pytest.raises(OG.ErroObrasgov):
            OG.converter(e)
    e = copy.deepcopy(obrasgov)
    e["execucao_fisica"].pop("total_items", None)
    e["execucao_fisica"]["data"] = [dict(e["execucao_fisica"]["data"][0], id_execucao_fisica=i) for i in range(100000)]
    assert len(OG.converter(e)["avanco_fisico"]) == 100000


OBRASGOV_ESTOURA = {
    "eixos_tipos lista de texto": lambda e: _pi(e).__setitem__("eixos_tipos", ["rodovia"]),
    "executores lista de texto": lambda e: _pi(e).__setitem__("executores", ["DNIT"]),
    "pins lista de números": lambda e: _pi(e).__setitem__("pins", [1, 2]),
    "investimento previsto em texto": lambda e: _pi(e).__setitem__(
        "investimentos_previstos", [{"vl_investimento_previsto": "1.000,00"}]),
    "id de contrato texto e número": lambda e: (e["contrato"]["data"][0].__setitem__("id_contrato", "A1"),
                                                 e["contrato"]["data"].append(dict(e["contrato"]["data"][0], id_contrato=7))),
    "valor global em texto": lambda e: e["contrato"]["data"][0].__setitem__("valor_global_contrato", "R$ 10"),
    "motivos lista de texto": lambda e: e["execucao_fisica"]["data"][0].__setitem__("motivos", ["chuva"]),
}


# Regressão: defeito da rodada 14, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: campos aninhados fora do tipo esperado escapam como AttributeError/TypeError em vez de "
#   "ErroObrasgov: listas de texto onde se esperam objetos (eixos_tipos, executores, pins, motivos), valores "
#   "monetários em texto (soma) e ids de contrato de tipos misturados (ordenação). Quando houver rota, "
#   "isso vira 500")
@pytest.mark.parametrize("caso", sorted(OBRASGOV_ESTOURA))
def test_obrasgov_campo_aninhado_malformado_e_erro_do_adaptador(obrasgov, caso):
    """Cada mutação da fixture acima tem de ser recusada com ErroObrasgov (mensagem com o campo), ou
    convertida com aviso — nunca AttributeError/TypeError."""
    e = copy.deepcopy(obrasgov)
    OBRASGOV_ESTOURA[caso](e)
    try:
        r = OG.converter(e)
    except OG.ErroObrasgov:
        return
    assert r["avisos"]


# Regressão: defeito da rodada 14, já corrigido pelo dono do módulo (a marca xfail saiu). O que falhava:
#   reason="DEFEITO: valor monetário NaN/infinito passa sem validação (financeiro.valor_global_contratos = "
#   "NaN) e registro que não é objeto dentro de 'data' é DESCARTADO em silêncio, sem aviso — o adaptador "
#   "perde um contrato malformado sem dizer")
@pytest.mark.parametrize("caso", ["valor nan", "registro que não é objeto"])
def test_obrasgov_valor_nao_finito_e_registro_descartado_sao_sinalizados(obrasgov, caso):
    """(a) valor_global_contrato = NaN: ErroObrasgov ou aviso; nunca NaN no total.
    (b) um texto solto na lista de contratos: ErroObrasgov ou aviso dizendo que 1 registro foi ignorado."""
    e = copy.deepcopy(obrasgov)
    if caso == "valor nan":
        e["contrato"]["data"][0]["valor_global_contrato"] = float("nan")
    else:
        e["contrato"]["data"].append("lixo")
        e["contrato"].pop("total_items", None)
    try:
        r = OG.converter(e)
    except OG.ErroObrasgov:
        return
    total = r["financeiro"]["valor_global_contratos"]
    assert total == total and r["avisos"]
