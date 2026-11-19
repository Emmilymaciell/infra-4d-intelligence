"""Exportação para BI: CSV pt-BR com BOM, modelo estrela, anti CSV injection e pacote ZIP.

Nenhum CSV é gravado no repositório: tudo é lido da memória (bytes) ou da resposta HTTP.
"""

from __future__ import annotations

import copy
import csv
import io
import re
import sys
import zipfile

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from infra4d.cenarios import Projeto, executar
from infra4d.exportacao import (ErroExportacao, _fmt, montar_tabelas, neutralizar, pacote_zip, para_csv,
                                parametros_csv)
import infra4d.rotas_exportacao as rotas_exp

RAIZ = __import__("pathlib").Path(__file__).resolve().parents[1]
OBRAS = {"ferrovia": RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json",
         "rodovia": RAIZ / "examples" / "synthetic" / "rodovia_ficticia.json"}


class _Estado:
    def __init__(self, projeto):
        self.projeto = projeto
        self._c = {}

    def resultado(self, c):
        if c not in self._c:
            self._c[c] = executar(self.projeto, c)
        return self._c[c]


@pytest.fixture(scope="module")
def estados():
    return {k: _Estado(Projeto.carregar(p)) for k, p in OBRAS.items()}


@pytest.fixture(scope="module")
def tabelas(estados):
    return {k: montar_tabelas(e.projeto, k, e.resultado) for k, e in estados.items()}


def ler(conteudo: bytes, sep=";"):
    assert conteudo.startswith(b"\xef\xbb\xbf"), "CSV sem BOM"
    texto = conteudo.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto, newline=""), delimiter=sep))


def num(txt: str, decimal=","):
    return None if txt == "" else float(txt.replace(decimal, "."))


# ------------------------------------------------------------------ ida e volta
@pytest.mark.parametrize("obra", list(OBRAS))
def test_fato_cronograma_ida_e_volta_bate_com_o_motor(estados, tabelas, obra):
    tabs, _ = tabelas[obra]
    linhas = ler(para_csv(tabs["fato_cronograma"]))
    est = estados[obra]
    assert len(linhas) == 4 * len(est.projeto.dados["atividades"])
    for ln in linhas:
        a = est.resultado(ln["cenario"])["atividades"][ln["atividade_id"]]
        assert ln["obra_id"] == obra
        assert ln["inicio"] == a["inicio"] and ln["termino"] == a["termino"]
        assert ln["lf"] == (a["lf"] or "")
        assert int(ln["duracao"]) == a["duracao"]
        assert (ln["folga_total"] == "" and a["folga_total"] is None) or int(ln["folga_total"]) == a["folga_total"]
        assert ln["critica"] == ("1" if a["critica"] else "0")
        prod = (a.get("memoria") or {}).get("produtividade")
        assert (prod is None and ln["produtividade"] == "") or num(ln["produtividade"]) == pytest.approx(prod)


def test_fato_boletim_e_curva_s_ida_e_volta(estados, tabelas):
    tabs, _ = tabelas["ferrovia"]
    p = estados["ferrovia"].projeto
    bol = ler(para_csv(tabs["fato_boletim"]))
    assert len(bol) == len(p.dados["medicoes"])
    for ln, m in zip(bol, p.dados["medicoes"]):
        assert ln["atividade_id"] == m["atividade_id"] and ln["semana_inicio"] == m["semana_inicio"]
        assert num(ln["quantidade"]) == pytest.approx(m["quantidade"], abs=1e-6)
    curva = ler(para_csv(tabs["fato_curva_s"]))
    finais = {ln["cenario"]: num(ln["avanco_pct"]) for ln in curva}  # última data de cada cenário
    assert finais["linha_base"] == pytest.approx(100.0)
    assert set(finais) == {"linha_base", "construtora", "independente", "simulado"}


# ----------------------------------------------------------------- formatação
def test_bom_e_decimal_pt_br(tabelas):
    tabs, _ = tabelas["ferrovia"]
    bruto = para_csv(tabs["fato_boletim"])
    assert bruto[:3] == b"\xef\xbb\xbf"
    texto = bruto.decode("utf-8-sig")
    cab, primeira = texto.split("\r\n")[:2]
    assert cab.split(";")[:3] == ["obra_id", "atividade_id", "semana_inicio"]
    assert "11,504" in primeira.split(";")  # quantidade do 1º boletim (11.504) com vírgula decimal
    assert "." not in primeira.split(";")[3]
    # dim_obra: acento intacto (UTF-8) e booleano 1/0
    obra = ler(para_csv(tabs["dim_obra"]))[0]
    assert "Fictícia" in obra["nome"] and obra["ficticio"] == "1"


def test_separador_e_decimal_configuraveis(tabelas):
    tabs, _ = tabelas["ferrovia"]
    us = ler(para_csv(tabs["fato_boletim"], sep=",", decimal="."), sep=",")
    assert us[0]["quantidade"] == "11.504"
    br_ponto = ler(para_csv(tabs["fato_boletim"], sep=";", decimal="."), sep=";")
    assert br_ponto[0]["quantidade"] == "11.504"
    tab = ler(para_csv(tabs["fato_boletim"], sep="tab"), sep="\t")
    assert tab[0]["quantidade"] == "11,504"
    for sep, dec in ((",", ","), (".", ","), (";", ";"), (";", "x")):
        with pytest.raises(ErroExportacao):
            parametros_csv(sep, dec)


@pytest.mark.parametrize("valor,tipo,esperado", [
    (1.0, "decimal", "1"), (0.1, "decimal", "0,1"), (1234567.891, "decimal", "1234567,891"),
    (1e-7, "decimal", "0,0000001"), (-3, "inteiro", "-3"), (-2.5, "decimal", "-2,5"),
    (float("nan"), "decimal", ""), (None, "texto", ""), (True, "booleano", "1"), (False, "booleano", "0"),
    ("2026-11-09", "data", "2026-11-09"), ("abc", "inteiro", "abc"), ("=1+1", "decimal", "'=1+1"),
])
def test_formatacao_de_celulas(valor, tipo, esperado):
    assert _fmt(valor, tipo, ",") == esperado


# --------------------------------------------------------------- CSV injection
@pytest.mark.parametrize("perigoso", ["=HYPERLINK(\"http://x\",\"clique\")", "+1+1", "-2+3", "@SUM(A1)",
                                      "\tTAB", "\rCR"])
def test_injecao_de_formula_e_neutralizada(estados, perigoso):
    dados = copy.deepcopy(estados["ferrovia"].projeto.dados)
    dados["atividades"][1]["nome"] = perigoso
    dados["lotes"][0]["construtora"] = perigoso
    p = Projeto(dados)
    tabs, _ = montar_tabelas(p, "ferrovia", lambda c: executar(p, c))
    ativ = {ln["atividade_id"]: ln for ln in ler(para_csv(tabs["dim_atividade"]))}
    assert ativ[dados["atividades"][1]["id"]]["nome"] == "'" + perigoso
    assert ler(para_csv(tabs["dim_lote"]))[0]["construtora"] == "'" + perigoso
    # nenhuma célula de texto do arquivo começa com caractere de fórmula
    for t in tabs.values():
        tipos = {c.nome: c.tipo for c in t.colunas}
        for ln in ler(para_csv(t)):
            for k, v in ln.items():
                if tipos[k] in ("texto", "data"):
                    assert not v.startswith(("=", "+", "-", "@", "\t", "\r")), (t.nome, k, v)


def test_numero_negativo_nao_e_neutralizado():
    assert neutralizar("-3") == "'-3"  # como TEXTO seria neutralizado...
    assert _fmt(-3, "inteiro", ",") == "-3"  # ...mas coluna numérica sai como número


# ---------------------------------------------------- chave estrangeira (estrela)
@pytest.mark.parametrize("obra", list(OBRAS))
def test_chaves_estrangeiras_integras(tabelas, obra):
    tabs, notas = tabelas[obra]
    ids = {
        "atividade": {ln["atividade_id"] for ln in ler(para_csv(tabs["dim_atividade"]))},
        "lote": {ln["lote_id"] for ln in ler(para_csv(tabs["dim_lote"]))},
        "segmento": {ln["segmento_id"] for ln in ler(para_csv(tabs["dim_segmento"]))},
        "servico": {ln["servico_id"] for ln in ler(para_csv(tabs["dim_servico"]))},
        "obra": {ln["obra_id"] for ln in ler(para_csv(tabs["dim_obra"]))},
    }
    assert ids["obra"] == {obra}
    refs = {"atividade_id": "atividade", "atividade_antecessora": "atividade", "atividade_sucessora": "atividade",
            "marco_id": "atividade", "lote_id": "lote", "segmento_id": "segmento", "servico_id": "servico",
            "servico_antecessor": "servico", "servico_sucessor": "servico", "obra_id": "obra"}
    checadas = set()
    for nome, t in tabs.items():
        if nome == "dim_obra":
            continue
        for ln in ler(para_csv(t)):
            for col, dim in refs.items():
                if col in ln and ln[col] != "" and not (nome.startswith("dim_") and col == f"{dim}_id"
                                                        and nome == f"dim_{dim}"):
                    assert ln[col] in ids[dim], (nome, col, ln[col])
                    checadas.add((nome, col))
    assert ("fato_cronograma", "atividade_id") in checadas and ("fato_boletim", "atividade_id") in checadas
    assert ("dim_atividade", "lote_id") in checadas and ("fato_marcos", "marco_id") in checadas
    if "fato_recursos" in tabs:
        assert ("fato_recursos", "servico_id") in checadas


# ------------------------------------------------------------------- pacote ZIP
def test_pacote_zip_valido_com_dicionario_completo_e_aviso(estados, tabelas):
    tabs, notas = tabelas["ferrovia"]
    p = estados["ferrovia"].projeto
    z = zipfile.ZipFile(io.BytesIO(pacote_zip(tabs, notas, p)))
    assert z.testzip() is None
    nomes = set(z.namelist())
    assert {f"{t}.csv" for t in tabs} | {"LEIAME.txt", "aviso.txt"} == nomes
    assert {"dim_obra", "dim_lote", "dim_segmento", "dim_servico", "dim_atividade", "fato_cronograma",
            "fato_boletim", "fato_curva_s", "fato_marcos"} <= set(tabs)
    for t in tabs:
        assert z.read(f"{t}.csv") == para_csv(tabs[t])
    assert "FICTÍCIOS" in z.read("aviso.txt").decode("utf-8-sig")
    leia = z.read("LEIAME.txt").decode("utf-8-sig")
    # dicionário: cada coluna de cada CSV aparece na seção da sua tabela com tipo e origem
    secoes = dict(re.findall(r"\[(\w+)\.csv\][^\n]*\n((?:  [^\n]*\n)+)", leia))
    assert set(secoes) == set(tabs)
    for t in tabs:
        cab = z.read(f"{t}.csv").decode("utf-8-sig").split("\r\n")[0].split(";")
        documentadas = [ln.strip().split(" | ")[0] for ln in secoes[t].splitlines()]
        assert cab == documentadas, t
        assert all(len(ln.split(" | ")) == 4 and ln.split(" | ")[3].strip() for ln in secoes[t].splitlines())


def test_sem_aviso_quando_nao_ficticio(estados):
    dados = copy.deepcopy(estados["rodovia"].projeto.dados)
    dados["meta"]["ficticio"] = False
    p = Projeto(dados)
    tabs, notas = montar_tabelas(p, "rodovia", lambda c: executar(p, c))
    assert "aviso.txt" not in zipfile.ZipFile(io.BytesIO(pacote_zip(tabs, notas, p))).namelist()


def test_modulo_recursos_ausente_omite_os_fatos_opcionais(estados, monkeypatch):
    monkeypatch.setitem(sys.modules, "infra4d.recursos", None)  # import passa a falhar
    e = estados["ferrovia"]
    tabs, notas = montar_tabelas(e.projeto, "ferrovia", e.resultado)
    assert "fato_conflitos" not in tabs and "fato_recursos" not in tabs
    assert any("fato_recursos" in n for n in notas) and any("fato_conflitos" in n for n in notas)
    z = zipfile.ZipFile(io.BytesIO(pacote_zip(tabs, notas, e.projeto)))
    assert z.testzip() is None and "omitida" in z.read("LEIAME.txt").decode("utf-8-sig")


# --------------------------------------------------------------------- rotas
@pytest.fixture
def cliente(estados):
    def obter_estado(obra=None):
        obra = obra or "ferrovia"
        if obra not in estados:
            raise HTTPException(404, f"obra desconhecida: {obra}")
        return estados[obra]

    app = FastAPI()
    rotas_exp.ligar(app, obter_estado)
    return TestClient(app)


def test_rotas_csv_e_pacote(cliente, estados):
    r = cliente.get("/api/exportar/fato_cronograma.csv", params={"obra": "rodovia"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    linhas = ler(r.content)
    ind = estados["rodovia"].resultado("independente")
    for ln in linhas:
        if ln["cenario"] == "independente":
            assert ln["termino"] == ind["atividades"][ln["atividade_id"]]["termino"]
    r2 = cliente.get("/api/exportar/dim_atividade.csv", params={"sep": ",", "decimal": "."})
    assert r2.status_code == 200 and ler(r2.content, sep=",")[0]["obra_id"] == "ferrovia"
    assert cliente.get("/api/exportar/nao_existe.csv").status_code == 404
    assert cliente.get("/api/exportar/dim_obra.csv", params={"obra": "zz"}).status_code == 404
    assert cliente.get("/api/exportar/dim_obra.csv", params={"sep": ",", "decimal": ","}).status_code == 422
    z = cliente.get("/api/exportar/pacote.zip", params={"obra": "rodovia"})
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(z.content)).testzip() is None
    lst = cliente.get("/api/exportar/tabelas").json()
    assert {t["nome"] for t in lst["tabelas"]} >= {"dim_obra", "fato_cronograma"}


def test_rotas_sem_ligar_503():
    app = FastAPI()
    app.include_router(rotas_exp.router)
    assert TestClient(app).get("/api/exportar/dim_obra.csv").status_code == 503


# ------------------------------------------------- revisão r11 (regressões próprias)
@pytest.mark.parametrize("perigoso", [" =cmd", "\n=cmd", "  +1", "\t-2", "＝cmd", "＋1", "－1", "＠x",
                                      " ＝cmd"])
def test_neutraliza_depois_de_espacos_e_largura_total(perigoso):
    assert neutralizar(perigoso) == "'" + perigoso
    assert _fmt(perigoso, "texto", ",") == "'" + perigoso


@pytest.mark.parametrize("seguro", ["abc", "a=b", "1-2", "", "   "])
def test_texto_comum_nao_e_neutralizado(seguro):
    assert neutralizar(seguro) == seguro


def test_inteiro_grande_e_texto_inteiro_saem_exatos():
    assert _fmt(12345678901234567890, "inteiro", ",") == "12345678901234567890"
    assert _fmt("-98765432109876543210", "inteiro", ",") == "-98765432109876543210"
    assert _fmt(True, "inteiro", ",") == "1"


def test_boletim_orfao_fica_fora_do_fato_e_vai_para_as_notas(estados):
    dados = copy.deepcopy(estados["rodovia"].projeto.dados)
    dados["medicoes"].append({"atividade_id": "NAO-EXISTE", "semana_inicio": "2026-10-05", "quantidade": 1.0,
                              "equipes_dias": 1, "origem": "SINTÉTICA"})
    p = Projeto(dados)
    tabs, notas = montar_tabelas(p, "rodovia", lambda c: executar(p, c))
    assert "NAO-EXISTE" not in {l["atividade_id"] for l in tabs["fato_boletim"].linhas}
    assert len(tabs["fato_boletim"].linhas) == len(dados["medicoes"]) - 1
    assert any("NAO-EXISTE" in n and "fato_boletim" in n for n in notas)
    assert "NAO-EXISTE" in zipfile.ZipFile(io.BytesIO(pacote_zip(tabs, notas, p))).read("LEIAME.txt").decode("utf-8-sig")


def test_nome_de_arquivo_higienizado_no_cabecalho(estados):
    from infra4d.exportacao import nome_seguro
    assert nome_seguro('x"; filename="evil.bat') == "x_filename_evil.bat"
    assert nome_seguro("") == "obra" and nome_seguro("../..") == "obra"
    e = estados["ferrovia"]
    app = FastAPI()
    rotas_exp.ligar(app, lambda obra=None: e)  # aceita qualquer id: o nome vem do ?obra= informado
    c = TestClient(app)
    for url in ("/api/exportar/pacote.zip", "/api/exportar/dim_obra.csv"):
        cab = c.get(url, params={"obra": 'x"; filename="evil.bat'}).headers["content-disposition"]
        assert re.fullmatch(r'attachment; filename="[A-Za-z0-9._-]+"', cab), cab
    # tipo de obra fora do declarado (P8): recusado com 422, nunca vira nome de arquivo nem "ferrovia"
    dados = copy.deepcopy(estados["ferrovia"].projeto.dados)
    dados["meta"]["tipo_obra"] = 'x"; filename="evil.bat'
    e2 = _Estado(Projeto(dados))
    app2 = FastAPI()
    rotas_exp.ligar(app2, lambda obra=None: e2)
    r2 = TestClient(app2).get("/api/exportar/pacote.zip")
    assert r2.status_code == 422 and "tipo de obra" in r2.json()["detail"]
