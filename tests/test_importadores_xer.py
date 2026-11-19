"""Importador Primavera P6 XER (parser próprio): fixture escrita à mão e casos de borda.

Compatibilidade com o P6 real NÃO é alegada: a fixture é sintética, escrita à
mão conforme a descrição pública do formato (%T/%F/%R).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infra4d.calendario import iso
from infra4d.importadores import ErroImportacao, importar_xer
from infra4d.importadores import rotas
from infra4d.importadores.comum import Avisos
from infra4d.importadores.xer import ler_clndr_data, ler_tabelas
from infra4d.motor import calcular

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "fixtures" / "p6_minimo.xer"


def _calc(dados):
    ativs, rels, cals, meta = dados
    res = calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta["data_status"])
    por_id = {a.id: a for a in ativs}
    datas = {aid: (iso(r.data_inicio(cals[por_id[aid].calendario], por_id[aid])),
                   iso(r.data_termino(cals[por_id[aid].calendario], por_id[aid])))
             for aid, r in res.atividades.items()}
    return res, datas


# Calendário seg–sex 8 h, feriado 21/04/2026 (terça, serial 46133). Início 06/04, data de dados 15/04/2026.
#   MS0   marco de início concluído em 06/04
#   A1010 concluída 06–08/04
#   A1020 em andamento desde 09/04, remanescente 24 h = 3 d a partir da data de dados: 15, 16, 17/04
#   A1030 6 d FS A1020: 20, [21 feriado], 22, 23, 24, 27, 28/04          → término 28/04
#   A1040 4 d SS A1030 +16 h (2 d): 2 dias úteis a partir de 20 (20, 22) → início 23; 23, 24, 27, 28/04
#   A1050 3 d FF A1040 +8 h (1 d): A1040 termina 28 → A1050 termina 29; início 27/04
#   A1060 2 d FS A1010, CS_MSOA 27/04: restrição vence → 27, 28/04; folga total 1 (MS9 em 29)
#   MS9   marco de término FS A1050, FS A1060 → 29/04/2026 = término do projeto
ESPERADO_XER = {
    "MS0": ("2026-04-06", "2026-04-06"),
    "A1010": ("2026-04-06", "2026-04-08"),
    "A1020": ("2026-04-09", "2026-04-17"),
    "A1030": ("2026-04-20", "2026-04-28"),
    "A1040": ("2026-04-23", "2026-04-28"),
    "A1050": ("2026-04-27", "2026-04-29"),
    "A1060": ("2026-04-27", "2026-04-28"),
    "MS9": ("2026-04-29", "2026-04-29"),
}


def test_fixture_xer_escrita_a_mao_bate_com_o_calculo_manual():
    dados = importar_xer(FIXTURE.read_bytes())
    ativs, rels, cals, meta = dados
    por_id = {a.id: a for a in ativs}
    assert len(ativs) == 8 and len(rels) == 8 and len(cals) == 1
    assert meta["inicio_projeto"] == date(2026, 4, 6).toordinal()
    assert meta["data_status"] == date(2026, 4, 15).toordinal()
    assert meta["avisos"] == []
    cal = cals["Seg-Sex 8h com feriado"]
    assert cal.dias_semana == (0, 1, 2, 3, 4)
    assert cal.nao_uteis == frozenset({date(2026, 4, 21)})
    assert (por_id["MS0"].tipo, por_id["MS9"].tipo) == ("marco_inicio", "marco_termino")
    assert [(a.status, a.duracao) for a in (por_id["A1010"], por_id["A1020"], por_id["A1030"])] == \
           [("concluida", 0), ("em_andamento", 3), ("nao_iniciada", 6)]
    assert por_id["A1060"].restricao_inicio == date(2026, 4, 27).toordinal()
    assert {(r.predecessora, r.sucessora, r.tipo, r.lag) for r in rels} >= {
        ("A1030", "A1040", "SS", 2), ("A1040", "A1050", "FF", 1)}

    res, datas = _calc(dados)
    assert datas == ESPERADO_XER
    assert iso(res.termino_projeto_data) == "2026-04-29"
    assert res.atividades["A1060"].folga_total == 1
    assert res.cadeia_determinante == ["A1020", "A1030", "A1040", "A1050", "MS9"]


def test_fixture_xer_sem_feriado_muda_o_resultado():
    """Detector: se a exceção do calendário não fosse lida, A1030 terminaria em 27/04."""
    texto = FIXTURE.read_text(encoding="utf-8").replace("(0||0(d|46133)())", "")
    res, datas = _calc(importar_xer(texto))
    assert datas["A1030"] == ("2026-04-20", "2026-04-27")
    assert iso(res.termino_projeto_data) == "2026-04-28"


def test_tabelas_xer_brutas():
    t = ler_tabelas(FIXTURE.read_text(encoding="utf-8"))
    assert set(t) == {"PROJECT", "CALENDAR", "TASK", "TASKPRED"}
    assert t["TASK"][2]["task_code"] == "A1020" and t["TASK"][2]["status_code"] == "TK_Active"
    assert t["TASKPRED"][3]["pred_type"] == "PR_SS" and t["TASKPRED"][3]["lag_hr_cnt"] == "16"


def test_clndr_data_com_separadores_de_controle_e_excecao_util():
    bruto = ("(0||CalendarData()(\x7f(0||DaysOfWeek()(\x7f(0||1()())(0||2()((0||0(s|07:00|f|16:00)())))"
             "(0||3()())(0||4()())(0||5()())(0||6()())(0||7()((0||0(s|08:00|f|12:00)())))))\r\n"
             "(0||Exceptions()((0||0(d|46133)())(0||1(d|46140)((0||0(s|08:00|f|12:00)())))))))")
    av = Avisos()
    semana, nao = ler_clndr_data(bruto, av, "teste")
    assert semana == (0, 5)  # segunda e sábado
    assert nao == {date(2026, 4, 21)}
    assert any("com horário" in x for x in av.lista())


def test_clndr_data_ilegivel_cai_no_padrao_com_aviso():
    av = Avisos()
    assert ler_clndr_data("(0||CalendarData()((0||Days", av, "x") == (None, set())
    assert av.lista()


def _xer(tarefas, preds, cstr=("", "")):
    T = "\t"
    linhas = ["ERMHDR\t19.12", "%T\tPROJECT", "%F\tproj_id\tplan_start_date\tlast_recalc_date\tclndr_id",
              "%R\t1\t2026-04-06 08:00\t\t9", "%T\tCALENDAR", "%F\tclndr_id\tclndr_name\tday_hr_cnt\tclndr_data",
              "%R\t9\tPadrao\t8\t", "%T\tTASK",
              "%F\ttask_id\tproj_id\tclndr_id\ttask_code\ttask_type\tstatus_code\ttarget_drtn_hr_cnt\tcstr_type\tcstr_date"]
    for tid, cod, tipo, h in tarefas:
        c = cstr if cod == "B" else ("", "")
        linhas.append("%R" + T + T.join([tid, "1", "9", cod, tipo, "TK_NotStart", h, c[0], c[1]]))
    linhas += ["%T\tTASKPRED", "%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt"]
    for i, (s, p, tp, lag) in enumerate(preds):
        linhas.append("%R" + T + T.join([str(i), s, p, tp, lag]))
    return "\n".join(linhas + ["%E"])


def test_loe_ignorado_restricao_mso_e_horas_fracionarias():
    txt = _xer([("1", "A", "TT_Task", "12"), ("2", "B", "TT_Task", "8"), ("3", "L", "TT_LOE", "40")],
               [("2", "1", "PR_FS", "4"), ("3", "1", "PR_SS", "0")], cstr=("CS_MSO", "2026-04-10 08:00"))
    ativs, rels, cals, meta = importar_xer(txt)
    por_id = {a.id: a for a in ativs}
    assert set(por_id) == {"A", "B"}
    assert por_id["A"].duracao == 2  # 12 h ÷ 8 = 1,5 → 2
    assert por_id["B"].restricao_inicio == date(2026, 4, 10).toordinal()
    assert [(r.predecessora, r.sucessora, r.tipo, r.lag) for r in rels] == [("A", "B", "FS", 0)]  # 4 h → 0 d
    assert cals["Padrao"].dias_semana == (0, 1, 2, 3, 4)  # clndr_data vazio → padrão
    texto = " | ".join(meta["avisos"])
    assert "LOE" in texto and "CS_MSO" in texto and "arredondado" in texto


def test_pred_type_desconhecido_e_arquivo_nao_xer():
    with pytest.raises(ErroImportacao, match="pred_type"):
        importar_xer(_xer([("1", "A", "TT_Task", "8"), ("2", "B", "TT_Task", "8")], [("2", "1", "PR_XX", "0")]))
    with pytest.raises(ErroImportacao, match="ERMHDR"):
        importar_xer("isto não é XER")


def test_rota_importar_xer_pelo_corpo():
    app = FastAPI()
    rotas.ligar(app, lambda obra=None: None)  # importar não usa o estado da obra
    c = TestClient(app)
    r = c.post("/api/cronograma/importar", content=FIXTURE.read_bytes(), headers={"Content-Type": "text/plain"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["formato"] == "xer"
    assert (corpo["n_atividades"], corpo["n_relacoes"]) == (8, 8)
    assert corpo["termino_calculado"] == "2026-04-29"
    assert corpo["data_status"] == "2026-04-15"
    assert corpo["por_status"] == {"concluida": 2, "em_andamento": 1, "nao_iniciada": 5}
    assert any("clndr_data" in x for x in corpo["limitacoes"])
    # forçar o formato errado dá 422, não 500
    r = c.post("/api/cronograma/importar", params={"formato": "mspdi"}, content=FIXTURE.read_bytes(),
               headers={"Content-Type": "text/plain"})
    assert r.status_code == 422


# ------------------------------------------- robustez (rodada 5 da revisão adversarial)
def _trocar_coluna(campo_antigo, campo_novo, tabela="TASK"):
    linhas = FIXTURE.read_text(encoding="utf-8").split("\n")
    atual = None
    for i, ln in enumerate(linhas):
        p = ln.split("\t")
        if p[0] == "%T":
            atual = p[1].strip()
        elif p[0] == "%F" and atual == tabela:
            linhas[i] = "\t".join(campo_novo if c.strip() == campo_antigo else c for c in p)
    return "\n".join(linhas)


@pytest.mark.parametrize("tabela,coluna", [("TASK", "task_id"), ("TASK", "status_code"),
                                           ("TASKPRED", "pred_task_id"), ("PROJECT", "plan_start_date")])
def test_coluna_obrigatoria_ausente_recusa_citando_a_coluna(tabela, coluna):
    with pytest.raises(ErroImportacao, match=coluna):
        importar_xer(_trocar_coluna(coluna, "COLUNA_X", tabela))


def test_coluna_opcional_ausente_gera_aviso_que_cita_a_coluna():
    _, rels, _, meta = importar_xer(_trocar_coluna("lag_hr_cnt", "COLUNA_X", "TASKPRED"))
    assert any("lag_hr_cnt" in a for a in meta["avisos"])
    assert all(r.lag == 0 for r in rels)


@pytest.mark.parametrize("valor", ["nan", "inf", "-inf", "1e999"])
def test_numero_nao_finito_no_xer_e_erro_de_importacao(valor):
    texto = FIXTURE.read_text(encoding="utf-8").replace("\tPR_SS\t16", f"\tPR_SS\t{valor}", 1)
    assert texto != FIXTURE.read_text(encoding="utf-8")
    with pytest.raises(ErroImportacao, match="finito|limite"):
        importar_xer(texto)


def test_clndr_data_profundo_e_recusado_e_serial_absurdo_ignorado():
    av = Avisos()
    with pytest.raises(ErroImportacao, match="níveis"):
        ler_clndr_data("(0||a()(" * 3000, av, "x")
    semana, nao = ler_clndr_data("(0||CalendarData()((0||Exceptions()((0||0(d|99999999999)())(0||1(d|46133)())))))",
                                 av, "x")
    assert nao == {date(2026, 4, 21)}


def test_teto_de_calendarios_usados():
    from infra4d.importadores.comum import MAXIMO_CALENDARIOS
    n = MAXIMO_CALENDARIOS + 1
    T = "\t"
    linhas = ["ERMHDR\t19.12", "%T\tPROJECT", "%F\tproj_id\tplan_start_date", "%R\t1\t2026-04-06 08:00",
              "%T\tCALENDAR", "%F\tclndr_id\tclndr_name"] + [f"%R\t{i}\tC{i}" for i in range(n)]
    linhas += ["%T\tTASK", "%F\ttask_id\tproj_id\tclndr_id\ttask_code\tstatus_code\ttarget_drtn_hr_cnt"]
    linhas += ["%R" + T + T.join([str(i), "1", str(i), f"A{i}", "TK_NotStart", "8"]) for i in range(n)]
    with pytest.raises(ErroImportacao, match="calendários"):
        importar_xer("\n".join(linhas))


# ------------------------------------------------- exportação XER (ida e volta)
import copy as _copy
import re

from infra4d.cenarios import Projeto, executar, montar_entrada
from infra4d.importadores.xer import COLUNAS, ler_campos
from infra4d.importadores.xer_exportar import NAO_EXPORTADO, exportar_xer

_OBRAS = {o: Path(__file__).resolve().parents[1] / "examples" / "synthetic" / f"{o}_ficticia.json"
          for o in ("ferrovia", "rodovia")}


@pytest.fixture(scope="module")
def projetos_xer():
    return {o: Projeto.carregar(p) for o, p in _OBRAS.items()}


def _referencia(p, cen):
    ativs, rels, _ = montar_entrada(p, cen)
    ds = None if cen == "linha_base" else p.data_status
    return ativs, rels, calcular(ativs, rels, p.calendarios, p.inicio_projeto, data_status=ds)


@pytest.mark.parametrize("obra", list(_OBRAS))
@pytest.mark.parametrize("cen", ["independente", "construtora", "linha_base"])
def test_xer_exportado_ida_e_volta_exata(projetos_xer, obra, cen):
    p = projetos_xer[obra]
    texto = exportar_xer(p, executar(p, cen))
    ativs, rels, cals, meta = importar_xer(texto.encode("utf-8"))
    res = calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta["data_status"])
    ref_a, ref_r, ref = _referencia(p, cen)
    assert meta["avisos"] == []
    assert {k: (r.es, r.ef) for k, r in res.atividades.items()} == {k: (r.es, r.ef) for k, r in ref.atividades.items()}
    assert res.termino_projeto_data == ref.termino_projeto_data
    assert sorted(res.caminho_critico) == sorted(ref.caminho_critico)
    assert res.cadeia_determinante == ref.cadeia_determinante
    chave = lambda a: (a.duracao, a.tipo, a.status, a.inicio_real, a.termino_real, a.restricao_inicio,
                       a.restricao_termino, a.calendario)
    assert {a.id: chave(a) for a in ativs} == {a.id: chave(a) for a in ref_a}
    assert sorted((r.predecessora, r.sucessora, r.tipo, r.lag) for r in rels) == \
           sorted((r.predecessora, r.sucessora, r.tipo, r.lag) for r in ref_r)
    for cid, cal in cals.items():
        assert (cal.dias_semana, cal.nao_uteis) == (p.calendarios[cid].dias_semana, p.calendarios[cid].nao_uteis)
    assert meta["data_status"] == (None if cen == "linha_base" else p.data_status)


def test_xer_exportado_passa_na_validacao_de_colunas_da_r5(projetos_xer):
    p = projetos_xer["ferrovia"]
    campos = ler_campos(exportar_xer(p, executar(p, "independente")))
    for tabela, (obrig, opc) in COLUNAS.items():
        assert set(obrig) <= set(campos[tabela]), tabela
        assert set(opc) <= set(campos[tabela]), tabela  # nem aviso de coluna opcional


def test_xer_exporta_snet_e_fnlt_juntos_e_texto_sem_tab(projetos_xer):
    p = projetos_xer["rodovia"]
    dados = _copy.deepcopy(p.dados)
    nao_ini = [a for a in dados["atividades"] if a.get("status") == "nao_iniciada" and a.get("tipo", "tarefa") == "tarefa"]
    alvo = nao_ini[0]
    alvo["restricao_inicio"] = "2027-01-04"
    alvo["restricao_termino"] = "2027-02-26"
    alvo["nome"] = "Nome\tcom TAB\ne quebra"
    nao_ini[1]["restricao_termino"] = "2026-12-01"  # só FNLT (vai no 1º par)
    q = Projeto(dados)
    texto = exportar_xer(q, executar(q, "independente"))
    ativs, rels, cals, meta = importar_xer(texto)
    por = {a.id: a for a in ativs}
    assert por[alvo["id"]].restricao_inicio == date(2027, 1, 4).toordinal()
    assert por[alvo["id"]].restricao_termino == date(2027, 2, 26).toordinal()
    assert por[nao_ini[1]["id"]].restricao_termino == date(2026, 12, 1).toordinal()
    assert meta["nomes"][alvo["id"]] == "Nome com TAB e quebra"
    res = calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta["data_status"])
    _, _, ref = _referencia(q, "independente")
    assert {k: (r.es, r.ef, r.folga_total) for k, r in res.atividades.items()} == \
           {k: (r.es, r.ef, r.folga_total) for k, r in ref.atividades.items()}


def test_xer_declara_o_que_nao_exporta():
    assert any("recursos" in x for x in NAO_EXPORTADO) and any("WBS" in x for x in NAO_EXPORTADO)


def test_rota_exportar_xer_e_reimportar():
    from infra4d.api import criar_app
    c = TestClient(criar_app())
    for obra in ("ferrovia", "rodovia"):
        r = c.get("/api/cronograma/exportar/xer", params={"obra": obra, "cenario": "construtora"})
        assert r.status_code == 200 and r.content.startswith(b"ERMHDR")
        assert re.fullmatch(r'attachment; filename="[A-Za-z0-9._-]+"', r.headers["content-disposition"])
        imp = c.post("/api/cronograma/importar", content=r.content, headers={"Content-Type": "text/plain"}).json()
        assert imp["formato"] == "xer" and imp["avisos"] == []
        assert imp["termino_calculado"] == c.get("/api/cenarios/construtora", params={"obra": obra}).json()["termino"]
    assert c.get("/api/cronograma/exportar/xer", params={"cenario": "x"}).status_code == 422
    assert c.get("/api/cronograma/exportar/xer", params={"obra": "zz"}).status_code == 404
