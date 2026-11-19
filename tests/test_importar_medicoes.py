"""Importação de medições por CSV (só dado SINTÉTICO): validação por linha, injeção, limites,
fictício × real, simulação em memória e Δ término."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import infra4d.importar_medicoes as im
from infra4d.cenarios import Projeto, executar
from infra4d.importar_medicoes import ErroArquivo, aplicar_em_memoria, importar
import infra4d.rotas_medicoes as rotas_med

RAIZ = Path(__file__).resolve().parents[1]
FIX = RAIZ / "examples" / "fixtures"
DATASET = RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json"
CAB = "atividade_id;data;semana_inicio;quantidade;equipes_dias;km_ini_exec;km_fim_exec;horas_chuva;estado;ref_memoria_calculo;observacao"


@pytest.fixture(scope="module")
def projeto():
    return Projeto.carregar(DATASET)


def ler(nome):
    return (FIX / nome).read_bytes()


def csv_de(linhas, meta=("#ficticio=true",), cab=CAB):
    return ("\r\n".join([*meta, cab, *linhas]) + "\r\n").encode("utf-8-sig")


def h(dados):
    return hashlib.sha256(json.dumps(dados, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------------ arquivo válido
def test_fixture_valida_e_aprovada_e_aplicada_so_em_memoria(projeto):
    antes = h(projeto.dados)
    r = importar(projeto, ler("medicoes_validas.csv"), "medicoes_validas.csv")
    assert r["aprovado"] is True and r["aceitas"] == 4 and r["rejeitadas"] == []
    assert (r["separador"], r["decimal"], r["ficticio"]) == (";", ",", True)
    novas = [(m["atividade_id"], m["semana_inicio"], m["quantidade"], m["equipes_dias"], m["tipo"])
             for m in r["medicoes_novas"]]
    assert novas == [("L3-S03-TER", "2026-11-07", 6000.0, 2.0, "diario"),  # "6.000,0": milhar + vírgula
                     ("L3-S03-TER", "2026-11-05", 5800.0, 2.0, "diario"),
                     ("L1-S03-LAS", "2026-11-07", 1200.5, 2.0, "boletim"),
                     ("L1-S03-SOL", "2026-11-06", 3.5, 1.0, "diario")]
    assert r["por_estado"] == {"conferido_fiscal": 2, "aprovado": 1, "lancado": 1}
    novo = r["_projeto"]
    assert h(projeto.dados) == antes, "o projeto original não pode ser alterado"
    assert len(novo.dados["medicoes"]) == len(projeto.dados["medicoes"]) + 4
    a = novo.atividades
    assert a["L3-S03-TER"]["quantidade_executada"] == pytest.approx(
        projeto.atividades["L3-S03-TER"]["quantidade_executada"] + 11800)
    assert (a["L1-S03-SOL"]["status"], a["L1-S03-SOL"]["inicio_real"]) == ("em_andamento", "2026-11-06")
    assert any("janela do boletim existente" in x["mensagem"] for x in r["avisos"])


def test_ida_e_volta_csv_gerado_com_csv_writer(projeto):
    """Gera o CSV com csv.writer (pt-BR e en-US) e reimporta: os valores voltam iguais."""
    regs = [("L2-S04-DRE", "2026-11-05", 12.25, 1.0), ("L2-S04-TER", "2026-11-04", 4321.5, 2.0)]
    for sep, dec in ((";", ","), (",", ".")):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=sep, lineterminator="\r\n")
        buf.write("#ficticio=true\r\n")
        w.writerow(["atividade_id", "data", "quantidade", "equipes_dias", "estado"])
        for aid, d, q, e in regs:
            w.writerow([aid, d, f"{q}".replace(".", dec), f"{e:g}", "lancado"])
        r = importar(projeto, buf.getvalue().encode("utf-8-sig"))
        assert r["aprovado"], r["rejeitadas"]
        assert [(m["atividade_id"], m["semana_inicio"], m["quantidade"], m["equipes_dias"])
                for m in r["medicoes_novas"]] == list(regs)


def test_delta_termino_coerente_com_calculo_direto(projeto):
    r = importar(projeto, ler("medicoes_validas.csv"))
    direto = copy.deepcopy(projeto.dados)
    for m in r["medicoes_novas"]:
        direto["medicoes"].append({k: m[k] for k in ("atividade_id", "semana_inicio", "quantidade", "equipes_dias",
                                                     "origem")})
    ativ = {a["id"]: a for a in direto["atividades"]}
    ativ["L3-S03-TER"]["quantidade_executada"] += 11800
    ativ["L1-S03-LAS"]["quantidade_executada"] += 1200.5
    ativ["L1-S03-SOL"].update(quantidade_executada=3.5, status="em_andamento", inicio_real="2026-11-06")
    esperado = executar(Projeto(direto), "independente")
    obtido = executar(r["_projeto"], "independente")
    assert obtido["termino"] == esperado["termino"]
    antes = executar(projeto, "independente")
    # L3-S03-TER é crítica: produção extra a 2.900–3.000 m³/eq·dia (média medida ~1.872) antecipa o término
    assert "L3-S03-TER" in antes["cadeia_determinante"]
    assert obtido["termino"] < antes["termino"]


# ------------------------------------------------------------------ rejeições
ESPERADO_ERROS = {
    4: ("atividade_id", "frente"), 5: ("data", "data"), 6: ("data", "data_status"), 7: ("data", "na_data_status"),
    8: ("quantidade", "nao_negativo"), 9: ("equipes_dias", "producao_sem_equipe"),
    10: ("km_ini_exec", "km_no_trecho"), 11: ("estado", "estado"),
    12: ("ref_memoria_calculo", "aprovado_exige_memoria"), 13: ("horas_chuva", "chuva"),
    14: ("semana_inicio", "duplicado"), 15: ("atividade_id", "frente"), 16: ("quantidade", "numero"),
    17: ("quantidade", "numero"), 18: ("data", "formato"), 19: ("data", "data"),
}


def test_cada_regra_de_rejeicao_por_linha_e_coluna(projeto):
    r = importar(projeto, ler("medicoes_com_erros.csv"))
    rej = {x["linha"]: x["erros"] for x in r["rejeitadas"]}
    assert set(rej) == set(ESPERADO_ERROS)
    for linha, (campo, regra) in ESPERADO_ERROS.items():
        assert (campo, regra) in {(e["campo"], e["regra"]) for e in rej[linha]}, (linha, rej[linha])
        assert len({(e["campo"], e["regra"]) for e in rej[linha]}) == len(rej[linha]), "erro repetido"
    assert r["aceitas"] == 1 and r["aprovado"] is False and "tudo ou nada" in r["motivo"]
    assert "_projeto" not in r


def test_duplicado_dentro_do_arquivo(projeto):
    r = importar(projeto, csv_de(["L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;", "L2-S04-DRE;2026-11-05;;2;1;;;0;lancado;;"]))
    assert r["rejeitadas"][0]["linha"] == 4 and r["rejeitadas"][0]["erros"][0]["regra"] == "duplicado"


# ------------------------------------------------------------------ injeção
def test_injecao_de_formula_nunca_e_avaliada(projeto):
    r = importar(projeto, ler("medicoes_injecao.csv"))
    rej = {x["linha"]: x for x in r["rejeitadas"]}
    assert set(rej) == {4, 5, 6, 7}
    assert rej[4]["atividade_id"].startswith("=HYPERLINK(")  # texto literal no relatório
    for linha, campo in ((5, "quantidade"), (6, "quantidade"), (7, "equipes_dias")):
        assert [(e["campo"], e["regra"]) for e in rej[linha]["erros"]] == [(campo, "numero")]
        assert "fórmula" in rej[linha]["erros"][0]["mensagem"]
    textos = [a["mensagem"] for a in r["avisos"] if "TEXTO literal" in a["mensagem"]]
    assert len(textos) == 3  # '=' na atividade, '@' e '=' na observação
    assert r["aceitas"] == 2 and r["aprovado"] is False


@pytest.mark.parametrize("celula", ["+1000", "=2*3000", "@SUM(A1)", "-1+3", "1e3", "1_000", "∞", "nan", "inf"])
def test_numero_suspeito_e_recusado(celula):
    assert isinstance(im._numero(celula, ","), str)


@pytest.mark.parametrize("celula,valor", [("1.234,5", 1234.5), ("12,25", 12.25), ("-3", -3.0), ("7", 7.0),
                                          ("1.000.000", 1000000.0), (" 2,5 ", 2.5), ("", None)])
def test_numero_pt_br_aceito(celula, valor):
    assert im._numero(celula, ",") == valor


# ------------------------------------------------------------------ arquivo recusado
def test_ficticio_x_real(projeto):
    with pytest.raises(ErroArquivo, match="ficticio=true"):
        importar(projeto, csv_de(["L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;"], meta=()))
    real = copy.deepcopy(projeto.dados)
    real["meta"]["ficticio"] = False
    with pytest.raises(ErroArquivo, match="obra real"):
        importar(Projeto(real), csv_de(["L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;"]))
    # obra real exige a marca EXPLÍCITA '#ficticio=false' (ADR-0005): sem marca é recusado
    with pytest.raises(ErroArquivo, match="ficticio=false"):
        importar(Projeto(real), csv_de(["L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;"], meta=()))
    ok = importar(Projeto(real), csv_de(["L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;"], meta=("#ficticio=false",)))
    assert ok["aprovado"] and ok["ficticio"] is False


def test_encoding_errado_e_erro_claro(projeto):
    dados = ("#ficticio=true\r\n" + CAB + "\r\nL2-S04-DRE;2026-11-05;;1;1;;;0;lançado;;ação\r\n").encode("cp1252")
    with pytest.raises(ErroArquivo, match="UTF-8"):
        importar(projeto, dados)


def test_limites(projeto, monkeypatch):
    linha = "L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;"
    monkeypatch.setattr(im, "MAX_LINHAS", 3)
    with pytest.raises(ErroArquivo, match="linhas"):
        importar(projeto, csv_de([linha.replace("11-05", f"11-0{i}") for i in range(1, 6)]))
    monkeypatch.setattr(im, "MAX_BYTES", 100)
    with pytest.raises(ErroArquivo, match="limite"):
        importar(projeto, csv_de([linha]))
    monkeypatch.undo()
    r = importar(projeto, csv_de(["L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;" + "x" * (im.MAX_CELULA + 1)]))
    assert r["rejeitadas"][0]["erros"][0]["regra"] == "tamanho"


@pytest.mark.parametrize("cab,msg", [("atividade_id;data;quantidade", "equipes_dias"),
                                     ("atividade_id;quantidade;equipes_dias", "data ou semana_inicio"),
                                     ("atividade_id;data;data;quantidade;equipes_dias", "repetida"),
                                     ("sem separador", "separador")])
def test_cabecalho_invalido(projeto, cab, msg):
    with pytest.raises(ErroArquivo, match=msg):
        importar(projeto, csv_de([], cab=cab))


def test_linha_com_colunas_a_mais(projeto):
    r = importar(projeto, csv_de(["L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;obs;EXTRA"]))
    assert r["rejeitadas"][0]["erros"][0]["regra"] == "formato"


# ------------------------------------------------------------------ rota
@pytest.fixture
def cliente(projeto):
    class E:
        def __init__(self, p):
            self.projeto, self._c = p, {}

        def resultado(self, c):
            if c not in self._c:
                self._c[c] = executar(self.projeto, c)
            return self._c[c]

    est = E(projeto)

    def obter(obra=None):
        if obra not in (None, "ferrovia"):
            raise HTTPException(404, "obra desconhecida")
        return est

    app = FastAPI()
    rotas_med.ligar(app, obter)
    return TestClient(app)


def test_rota_relatorio_e_simulacao(cliente, projeto):
    arquivo_antes = DATASET.read_bytes()
    url = "/api/medicoes/importar"
    r = cliente.post(url, content=ler("medicoes_validas.csv"), headers={"Content-Type": "text/csv"})
    assert r.status_code == 200 and r.json()["aprovado"] and r.json()["aplicado"] is False
    assert "_projeto" not in r.json() and "simulacao" not in r.json()
    s = cliente.post(url, params={"aplicar": True, "obra": "ferrovia"}, content=ler("medicoes_validas.csv"),
                     headers={"Content-Type": "text/csv"}).json()
    sim = s["simulacao"]
    assert s["aplicado"] is True and sim["persistido"] is False
    assert sim["termino_antes"] == executar(projeto, "independente")["termino"]
    assert sim["termino_depois"] < sim["termino_antes"] and sim["delta_dias_corridos"] < 0
    assert sim["comparacao"]["termino_alvo"] == sim["termino_depois"]
    assert any(m["id"] == "L3-S03-TER" for m in sim["comparacao"]["duracoes_alteradas"])
    # nada persistido: arquivo do dataset e estado da API intactos
    assert DATASET.read_bytes() == arquivo_antes
    s2 = cliente.post(url, params={"aplicar": True}, content=ler("medicoes_validas.csv"),
                      headers={"Content-Type": "text/csv"}).json()
    assert s2["simulacao"]["termino_antes"] == sim["termino_antes"]
    e = cliente.post(url, params={"aplicar": True}, content=ler("medicoes_com_erros.csv"),
                     headers={"Content-Type": "text/csv"}).json()
    assert e["aplicado"] is False and e["simulacao"] is None and len(e["rejeitadas"]) == 16


def test_rota_erros(cliente):
    url = "/api/medicoes/importar"
    assert cliente.post(url, content="ação".encode("cp1252"), headers={"Content-Type": "text/csv"}).status_code == 422
    assert cliente.post(url, content=b"  ", headers={"Content-Type": "text/csv"}).status_code == 400
    assert cliente.post(url, params={"obra": "zz"}, content=b"x", headers={"Content-Type": "text/csv"}).status_code == 404
    assert cliente.post(url, content=b"--a\r\n", headers={"Content-Type": "multipart/form-data; boundary=a"}
                        ).status_code == 415
    assert cliente.post(url, content=b"x" * (im.MAX_BYTES + 1), headers={"Content-Type": "text/csv"}).status_code == 413


def test_aplicar_em_memoria_limita_ao_total(projeto):
    total = projeto.atividades["L2-S03-LAS"]["quantidade_total"]
    novo, efeitos = aplicar_em_memoria(projeto, [{"atividade_id": "L2-S03-LAS", "semana_inicio": "2026-11-05",
                                                  "quantidade": 99999.0, "equipes_dias": 1.0, "origem": "t"}])
    assert novo.atividades["L2-S03-LAS"]["quantidade_executada"] == total
    assert any("limitado ao total" in e for e in efeitos)


# ------------------------------------------------------------------ r14: marca, CSV estrito, dígitos, avisos
L = "L2-S04-DRE;2026-11-05;;1;1;;;0;lancado;;"


@pytest.mark.parametrize("meta,trecho", [
    (("#ficticio=true", "#ficticio=true"), "repetida"),
    (("#ficticio=true", "#ficticio=false"), "repetida"),
    (("#ficticio: true",), "ficticio"),
    (("#fictício=true",), "ficticio"),
    (("#Ficticio=true",), "ficticio"),
    (("#ficticio=true # gerado",), "true ou false"),
    (("#ficticio=True",), "true ou false"),
    (("#ficticio=sim",), "true ou false"),
    (("#ficticio=\"true\"",), "true ou false"),
    (("#ficticio=",), "true ou false"),
])
def test_marca_ficticio_estrita(projeto, meta, trecho):
    with pytest.raises(ErroArquivo, match=trecho):
        importar(projeto, csv_de([L], meta=meta))


def test_marca_ficticio_aceita_espacos_em_volta(projeto):
    assert importar(projeto, csv_de([L], meta=("  #ficticio=true  ",)))["aprovado"]


def test_aspas_nao_fechadas_e_quebra_de_linha_na_celula(projeto):
    with pytest.raises(ErroArquivo, match="CSV malformado|quebra de linha"):
        importar(projeto, csv_de([L + '"sem fechar', L.replace("11-05", "11-04")]))
    with pytest.raises(ErroArquivo, match="quebra de linha"):
        importar(projeto, csv_de([L + '"linha 1\r\nlinha 2"']))
    with pytest.raises(ErroArquivo, match=r"U\+2028"):
        importar(projeto, csv_de([L + "obs\u2028mais"]))


def test_limite_global_do_csv_intocado(projeto):
    antes = csv.field_size_limit()
    importar(projeto, csv_de([L]))
    assert csv.field_size_limit() == antes


@pytest.mark.parametrize("celula", ["١٢٣", "۱۲", "１２３", "1٫5"])
def test_digitos_nao_ascii_recusados(celula):
    for dec in (",", "."):
        msg = im._numero(celula, dec)
        assert isinstance(msg, str) and "0-9" in msg


def test_aviso_de_milhar_ambiguo(projeto):
    r = importar(projeto, csv_de(["L2-S04-DRE;2026-11-05;;1.234;1;;;0;lancado;;"]))
    assert any("1.234" in a["mensagem"] and "1234" in a["mensagem"] for a in r["avisos"])
    r = importar(projeto, csv_de(["L2-S04-DRE;2026-11-05;;1.234,5;1;;;0;lancado;;"]))
    assert not any("1.234" in a["mensagem"] for a in r["avisos"])


def test_bom_duplicado_e_erro_claro(projeto):
    with pytest.raises(ErroArquivo, match="BOM"):
        importar(projeto, "\ufeff".encode() + csv_de([L]))


def test_lixo_depois_de_aspas_e_bom_duplo_em_texto(projeto):
    # CSV estrito: texto depois de fechar aspas na mesma célula é erro (o leitor solto juntaria 'obsx')
    with pytest.raises(ErroArquivo, match="CSV malformado"):
        importar(projeto, csv_de([L + '"obs"x']))
    texto = csv_de([L]).decode("utf-8-sig")
    assert importar(projeto, "\ufeff" + texto)["aprovado"]  # um BOM em texto: tolerado
    with pytest.raises(ErroArquivo, match="BOM"):
        importar(projeto, "\ufeff\ufeff" + texto)
