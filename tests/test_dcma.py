"""DCMA 14 pontos: redes pequenas com violação conhecida (à mão), teste do caminho crítico
executado no motor, as duas obras e o cronograma importado (MSPDI exportado)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from infra4d.calendario import Calendario
from infra4d.cenarios import Projeto, executar
from infra4d.dcma import avaliar, avaliar_cenario, avaliar_importado
from infra4d.importadores import exportar_mspdi, importar_mspdi
from infra4d.motor import AtividadeCPM as A, Relacao as R
import infra4d.rotas_dcma as rotas_dcma

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = {"ferrovia": RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json",
         "rodovia": RAIZ / "examples" / "synthetic" / "rodovia_ficticia.json"}
CAL = {"C": Calendario("C", "seg-sex")}
INI = date(2026, 3, 2).toordinal()  # segunda


def d(txt):
    return date.fromisoformat(txt).toordinal()


def T(i, dur, **kw):
    return A(i, dur, "C", **kw)


def ponto(saida, n):
    return next(p for p in saida["pontos"] if p["numero"] == n)


def base():
    """M0 → A(3) → B(5) → C(4) → MF. Rede limpa."""
    ativs = [A("M0", 0, "C", tipo="marco_inicio"), T("A", 3), T("B", 5), T("C", 4), A("MF", 0, "C", tipo="marco_termino")]
    rels = [R("M0", "A"), R("A", "B"), R("B", "C"), R("C", "MF")]
    return ativs, rels


def test_rede_limpa_passa_em_tudo_que_se_aplica():
    ativs, rels = base()
    s = avaliar(ativs, rels, CAL, INI)
    assert len(s["pontos"]) == 14 and [p["numero"] for p in s["pontos"]] == list(range(1, 15))
    for n in (1, 2, 3, 4, 5, 6, 7, 8, 12):
        assert ponto(s, n)["aprovado"] is True, ponto(s, n)
    assert s["populacao"] == 3  # marcos fora
    for n in (9, 10, 11, 13, 14):  # sem data de status, recursos, linha de base, prazo
        assert ponto(s, n)["aprovado"] is None and ponto(s, n)["nota"]


# ------------------------------------------------------------------ 1 a 5
def test_1_logica():
    ativs, rels = base()
    ativs.append(T("D", 2))
    rels.append(R("A", "D"))  # D sem sucessora
    p = ponto(avaliar(ativs, rels, CAL, INI), 1)
    assert p["valor"] == 25.0 and p["aprovado"] is False and p["violadoras"] == ["D"]
    assert p["detalhe"]["sem_sucessora"] == ["D"] and p["detalhe"]["sem_predecessora"] == []


def test_2_leads_e_3_lags():
    ativs, rels = base()
    rels[2] = R("B", "C", "FS", -1)
    s = avaliar(ativs, rels, CAL, INI)
    assert ponto(s, 2)["valor"] == 25.0 and ponto(s, 2)["aprovado"] is False
    assert ponto(s, 2)["violadoras"] == ["B->C FS-1"]
    assert ponto(s, 3)["aprovado"] is True
    rels[2] = R("B", "C", "FS", 2)
    s = avaliar(ativs, rels, CAL, INI)
    assert ponto(s, 3)["valor"] == 25.0 and ponto(s, 3)["violadoras"] == ["B->C FS+2"]
    assert ponto(s, 2)["aprovado"] is True


@pytest.mark.parametrize("n_ss,aprovado", [(1, True), (2, False)])
def test_4_tipos_de_relacao_limite_90(n_ss, aprovado):
    ativs = [T(f"X{i}", 1) for i in range(11)]
    rels = [R(f"X{i}", f"X{i + 1}", "SS" if i < n_ss else "FS") for i in range(10)]
    p = ponto(avaliar(ativs, rels, CAL, INI), 4)
    assert p["valor"] == 100.0 * (10 - n_ss) / 10 and p["aprovado"] is aprovado
    assert p["detalhe"]["SS"] == n_ss and len(p["violadoras"]) == n_ss


def test_5_so_restricao_rigida_conta():
    ativs, rels = base()
    ativs[2].restricao_inicio = d("2026-03-20")  # SNET: branda
    s = avaliar(ativs, rels, CAL, INI)
    assert ponto(s, 5)["aprovado"] is True and ponto(s, 5)["detalhe"]["snet_brandas"] == ["B"]
    ativs[3].restricao_termino = d("2026-06-30")  # FNLT: rígida
    p = ponto(avaliar(ativs, rels, CAL, INI), 5)
    assert p["violadoras"] == ["C"] and p["aprovado"] is False


# ------------------------------------------------------------------ 6 a 8
def test_6_folga_alta():
    ativs, rels = base()
    ativs += [T("Y", 60), T("X", 1)]
    rels += [R("M0", "Y"), R("Y", "MF"), R("M0", "X"), R("X", "MF")]
    p = ponto(avaliar(ativs, rels, CAL, INI), 6)
    # Y (60 d) fixa o término; X (1 d) tem 59 de folga; A, B, C: 60 − 12 = 48 > 44
    assert sorted(p["violadoras"]) == ["A", "B", "C", "X"] and p["aprovado"] is False


def test_7_folga_negativa_por_fnlt():
    ativs, rels = base()
    ativs[1].restricao_termino = d("2026-03-03")  # A (02–04/03) precisa acabar em 03/03: folga −1
    s = avaliar(ativs, rels, CAL, INI)
    p = ponto(s, 7)
    assert p["aprovado"] is False and "A" in p["violadoras"]
    assert ponto(s, 5)["violadoras"] == ["A"]


@pytest.mark.parametrize("dur,viola", [(44, False), (45, True)])
def test_8_duracao_alta(dur, viola):
    ativs, rels = base()
    ativs[2].duracao = dur
    p = ponto(avaliar(ativs, rels, CAL, INI), 8)
    assert (p["violadoras"] == ["B"]) is viola and p["aprovado"] is (not viola)


# ------------------------------------------------------------------ 9 a 14
def test_9_data_real_depois_da_data_de_status_e_avaliada_sem_quebrar():
    ativs, rels = base()
    ativs[0].status, ativs[0].inicio_real, ativs[0].termino_real = "concluida", INI, INI
    ativs[1].status, ativs[1].inicio_real, ativs[1].termino_real = "concluida", INI, d("2026-03-06")
    s = avaliar(ativs, rels, CAL, INI, data_status=d("2026-03-05"))  # término real 06/03 ≥ status 05/03
    p = ponto(s, 9)
    assert p["aprovado"] is False and p["valor"] == 1 and p["violadoras"][0].startswith("A: término real")
    assert s["erro_motor"] and ponto(s, 6)["valor"] is None and "não calculado" in ponto(s, 12)["nota"]
    ok = avaliar(ativs, rels, CAL, INI, data_status=d("2026-03-09"))
    assert ponto(ok, 9)["aprovado"] is True and ok["erro_motor"] is None


def test_10_recursos():
    ativs, rels = base()
    s = avaliar(ativs, rels, CAL, INI, recursos={"A": 1, "B": 2})
    p = ponto(s, 10)
    assert p["violadoras"] == ["C"] and p["aprovado"] is None  # informativo: DCMA não fixa limite
    assert "não se aplica" in ponto(avaliar(ativs, rels, CAL, INI), 10)["nota"]


def test_11_tarefas_perdidas_e_14_bei():
    ativs, rels = base()
    ds = d("2026-03-11")
    for a in ativs[:2]:  # M0 e A concluídos no prazo
        a.status, a.inicio_real = "concluida", INI
    ativs[0].termino_real, ativs[1].termino_real = INI, d("2026-03-04")
    ativs[2].status, ativs[2].inicio_real = "em_andamento", d("2026-03-05")
    lb = {"A": (INI, d("2026-03-04")), "B": (d("2026-03-05"), d("2026-03-10")), "C": (d("2026-03-11"), d("2026-03-16"))}
    s = avaliar(ativs, rels, CAL, INI, data_status=ds, linha_base=lb)
    p11, p14 = ponto(s, 11), ponto(s, 14)
    # devidas antes de 11/03: A (04/03) e B (10/03); B não concluída
    assert p11["valor"] == 50.0 and p11["violadoras"] == ["B"] and p11["aprovado"] is False
    assert p14["valor"] == 0.5 and p14["violadoras"] == ["B"] and p14["aprovado"] is False
    ativs[2].status, ativs[2].termino_real = "concluida", d("2026-03-10")
    s = avaliar(ativs, rels, CAL, INI, data_status=ds, linha_base=lb)
    assert ponto(s, 11)["valor"] == 0 and ponto(s, 14)["valor"] == 1.0 and ponto(s, 14)["aprovado"] is True


def test_12_caminho_critico_executado_no_motor():
    ativs, rels = base()
    s = avaliar(ativs, rels, CAL, INI, atraso_teste=7)
    p = ponto(s, 12)
    assert p["valor"] == 7 and p["aprovado"] is True
    det = p["detalhe"]
    assert det["termino_antes"] == "2026-03-17"  # 12 dias úteis a partir de 02/03
    assert det["termino_depois"] == "2026-03-26"  # +7 dias úteis
    assert det["atividade_testada"] == "A"


def test_12_falha_quando_a_atividade_so_dirige_pelo_inicio():
    """A dirige B só por SS: atrasar a DURAÇÃO de A não move o término (o teste reprova)."""
    ativs = [T("A", 3), T("B", 20)]  # A + 10 = 13 dias, ainda dentro dos 20 de B
    rels = [R("A", "B", "SS", 0)]
    p = ponto(avaliar(ativs, rels, CAL, INI, atividade_teste="A"), 12)
    assert p["valor"] == 0 and p["aprovado"] is False and p["violadoras"] == ["A"]
    # sem escolha explícita, o teste prefere a tarefa que dirige pelo término (B) e aprova
    assert ponto(avaliar(ativs, rels, CAL, INI), 12)["aprovado"] is True


@pytest.mark.parametrize("prazo,cpli,aprovado", [("2026-03-17", 1.0, True), ("2026-03-10", 7 / 12, False),
                                                 ("2026-03-31", 22 / 12, True)])
def test_13_cpli(prazo, cpli, aprovado):
    ativs, rels = base()
    p = ponto(avaliar(ativs, rels, CAL, INI, termino_contratual=d(prazo)), 13)
    assert p["valor"] == pytest.approx(cpli, abs=1e-4) and p["aprovado"] is aprovado
    assert p["detalhe"]["cpl"] == 12


# ------------------------------------------------------------------ obras reais (sintéticas)
@pytest.fixture(scope="module")
def projetos():
    return {k: Projeto.carregar(p) for k, p in OBRAS.items()}


@pytest.mark.parametrize("obra", list(OBRAS))
def test_obras_independente(projetos, obra):
    p = projetos[obra]
    s = avaliar_cenario(p, "independente")
    ind = executar(p, "independente")
    assert s["termino_calculado"] == ind["termino"]
    assert sum(ponto(s, 4)["detalhe"].values()) == s["n_relacoes_vivas"]
    p12 = ponto(s, 12)
    assert p12["aprovado"] is True and p12["detalhe"]["termino_depois"] > p12["detalhe"]["termino_antes"]
    for n in (11, 13, 14):
        assert ponto(s, n)["valor"] is not None  # linha de base, prazo e status existem nas obras
    # BEI pela definição: concluídas ÷ devidas
    lb_devidas = [a for a in p.dados["atividades"] if a.get("tipo", "tarefa") == "tarefa"
                  and a.get("termino_lb") and date.fromisoformat(a["termino_lb"]).toordinal() < p.data_status]
    concl = [a for a in p.dados["atividades"] if a.get("tipo", "tarefa") == "tarefa" and a.get("status") == "concluida"]
    assert ponto(s, 14)["valor"] == pytest.approx(len(concl) / len(lb_devidas), abs=1e-4)  # saída com 4 casas
    lb = avaliar_cenario(p, "linha_base")
    assert ponto(lb, 13)["valor"] == pytest.approx(1.0)  # linha de base termina no próprio prazo
    assert ponto(lb, 9)["aprovado"] is None


@pytest.mark.parametrize("obra", list(OBRAS))
def test_mspdi_exportado_da_o_mesmo_resultado_nos_pontos_de_rede(projetos, obra):
    p = projetos[obra]
    proprio = avaliar_cenario(p, "independente")
    imp = avaliar_importado(importar_mspdi(exportar_mspdi(p, executar(p, "independente"))))
    for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 12):
        a, b = ponto(proprio, n), ponto(imp, n)
        assert (a["valor"], a["aprovado"], sorted(a["violadoras"])) == (b["valor"], b["aprovado"],
                                                                        sorted(b["violadoras"])), n
    for n in (10, 11, 13, 14):  # o arquivo não traz recursos, linha de base nem prazo
        assert ponto(imp, n)["aprovado"] is None and "não se aplica" in ponto(imp, n)["nota"]


# ------------------------------------------------------------------ rotas
@pytest.fixture
def cliente(projetos):
    class E:
        def __init__(self, p):
            self.projeto, self.ajustes = p, []

    est = {k: E(p) for k, p in projetos.items()}

    def obter(obra=None):
        obra = obra or "ferrovia"
        if obra not in est:
            raise HTTPException(404, "obra desconhecida")
        return est[obra]

    app = FastAPI()
    rotas_dcma.ligar(app, obter)
    return TestClient(app)


def test_rotas(cliente):
    for obra in OBRAS:
        r = cliente.get("/api/dcma", params={"obra": obra, "cenario": "construtora"})
        assert r.status_code == 200 and len(r.json()["pontos"]) == 14 and r.json()["cenario"] == "construtora"
    assert cliente.get("/api/dcma", params={"cenario": "x"}).status_code == 422
    assert cliente.get("/api/dcma", params={"obra": "zz"}).status_code == 404
    xer = (RAIZ / "examples" / "fixtures" / "p6_minimo.xer").read_bytes()
    r = cliente.post("/api/dcma/importado", content=xer, headers={"Content-Type": "text/plain"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["origem"].endswith("(xer)") and j["termino_calculado"] == "2026-04-29"
    assert ponto(j, 4)["detalhe"] == {"FS": 5, "SS": 1, "FF": 1, "SF": 0}  # 8 relações − MS0→A1010 (concluída)
    assert cliente.post("/api/dcma/importado", content=b"lixo",
                        headers={"Content-Type": "text/plain"}).status_code == 415
    assert cliente.post("/api/dcma/importado", params={"formato": "xer"}, content=b"ERMHDR\t1\n",
                        headers={"Content-Type": "text/plain"}).status_code == 422


# ------------------------------------------------- revisão r12 (regressões próprias)
@pytest.mark.parametrize("cal_ativ,cal_proj", [("C5", "C6"), ("C6", "C5")])
def test_12_julga_no_calendario_da_atividade(cal_ativ, cal_proj):
    cals = {"C5": Calendario("C5", "5 d", (0, 1, 2, 3, 4)), "C6": Calendario("C6", "6 d", (0, 1, 2, 3, 4, 5))}
    p = ponto(avaliar([A("X", 20, cal_ativ)], [], cals, INI, calendario_projeto=cal_proj), 12)
    assert p["valor"] == 10 and p["aprovado"] is True
    det = p["detalhe"]
    assert det["calendario_atividade"] == cal_ativ and det["atraso_calendario_atividade"] == 10
    assert det["atraso_calendario_projeto"] == (12 if cal_ativ == "C5" else 8)  # informativo


def test_12_usa_a_relacao_que_de_fato_dirige_no_par_ss_ff():
    ativs = [T("A", 10), T("B", 30)]
    rels = [R("A", "B", "SS", 2), R("A", "B", "FF", 0)]
    p = ponto(avaliar(ativs, rels, CAL, INI), 12)
    assert (p["detalhe"]["atividade_testada"], p["valor"], p["aprovado"]) == ("B", 10.0, True)
    # e o inverso: quando quem dirige é a FF, A dirige pelo término e é a testada
    ativs = [T("A", 10), T("B", 2)]
    p = ponto(avaliar(ativs, [R("A", "B", "SS", 2), R("A", "B", "FF", 0)], CAL, INI), 12)
    assert (p["detalhe"]["atividade_testada"], p["aprovado"]) == ("A", True)


def test_rota_declara_se_a_simulacao_do_usuario_foi_aplicada(cliente):
    r = cliente.get("/api/dcma", params={"cenario": "independente"}).json()
    assert r["simulacao_do_usuario"].startswith("não aplicada") and "independente" in r["simulacao_do_usuario"]
    s = cliente.get("/api/dcma", params={"cenario": "simulado"}).json()
    assert s["simulacao_do_usuario"].startswith("aplicada: 0 ajuste")
    xer = (RAIZ / "examples" / "fixtures" / "p6_minimo.xer").read_bytes()
    i = cliente.post("/api/dcma/importado", content=xer, headers={"Content-Type": "text/plain"}).json()
    assert i["simulacao_do_usuario"].startswith("não aplicada") and "importado" in i["simulacao_do_usuario"]
