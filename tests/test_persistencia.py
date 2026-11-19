"""Persistência (SQLite) e histórico sintético da previsão."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from infra4d.calendario import ordinal
from infra4d.cenarios import Ajuste, Projeto, executar
from infra4d.persistencia import (BANCO_PADRAO, Banco, ErroPersistencia, datas_mensais, evolucao_previsao,
                                  hash_dados, projeto_na_data, reabrir_e_conferir, salvar_cenario_nomeado)
import infra4d.rotas_persistencia as rotas_hist

RAIZ = Path(__file__).resolve().parents[1]
OBRAS = {"ferrovia": RAIZ / "examples" / "synthetic" / "ferrovia_ficticia.json",
         "rodovia": RAIZ / "examples" / "synthetic" / "rodovia_ficticia.json"}
AJUSTE_TER_L3 = {"servico_id": "TER", "lote_id": "L3", "equipes": 3}


@pytest.fixture(scope="module")
def projetos():
    return {k: Projeto.carregar(p) for k, p in OBRAS.items()}


@pytest.fixture(scope="module")
def evolucoes(projetos):
    return {k: evolucao_previsao(p) for k, p in projetos.items()}


@pytest.fixture
def banco(tmp_path):
    return Banco(tmp_path / "teste.sqlite")


def _json(v):
    return json.loads(json.dumps(v, ensure_ascii=False, sort_keys=True))


# --------------------------------------------------------------- vem primeiro
def test_primeira_escrita_num_banco_novo_nao_trava(tmp_path):
    """Regressão: a 1ª escrita cria o esquema dentro do lock de escrita; com Lock não reentrante
    o processo TRAVAVA (visto ao rodar a suíte). Roda numa thread com prazo para virar falha, não trava."""
    b = Banco(tmp_path / "novo.sqlite")
    feito = []
    t = threading.Thread(target=lambda: feito.append(b.auditar("x", "o", "q", {}, {})), daemon=True)
    t.start()
    t.join(timeout=20)
    assert not t.is_alive(), "primeira escrita travou (lock não reentrante?)"
    assert feito == [1]


# ------------------------------------------------------------ cenários nomeados
def test_cenario_nomeado_ida_e_volta_identica(banco, projetos):
    p = projetos["ferrovia"]
    ajustes = [Ajuste.de_dict(AJUSTE_TER_L3)]
    salvo = salvar_cenario_nomeado(banco, p, "ferrovia", "3 equipes de terraplenagem no L3", ajustes, quem="fiscal A")
    esperado = executar(p, "simulado", ajustes)
    assert salvo["termino"] == esperado["termino"]
    assert salvo["termino"] != executar(p, "independente")["termino"], "o ajuste precisa mudar o término"

    lista = banco.listar_cenarios("ferrovia")
    assert [(c["id"], c["nome"], c["termino"], c["quem"]) for c in lista] == \
           [(salvo["id"], "3 equipes de terraplenagem no L3", esperado["termino"], "fiscal A")]
    assert lista[0]["ajustes"] == [Ajuste.de_dict(AJUSTE_TER_L3).__dict__]
    assert lista[0]["hash_dados"] == hash_dados(p)

    reaberto = reabrir_e_conferir(banco, p, salvo["id"])
    assert reaberto["resultado"] == _json({k: v for k, v in esperado.items() if not k.startswith("_")})
    assert reaberto["conferencia"]["reproduz_identico"] is True
    assert reaberto["conferencia"]["dados_da_obra_iguais"] is True
    # reabre de OUTRA instância (outro processo, mesmo arquivo)
    assert Banco(banco.caminho).obter_cenario(salvo["id"])["resultado"] == reaberto["resultado"]
    assert banco.listar_cenarios("rodovia") == []


def test_reabrir_com_dados_alterados_avisa(banco, projetos):
    p = projetos["ferrovia"]
    salvo = salvar_cenario_nomeado(banco, p, "ferrovia", "base", [Ajuste.de_dict(AJUSTE_TER_L3)])
    dados = json.loads(json.dumps(p.dados))
    for a in dados["atividades"]:
        if a.get("servico_id") == "TER" and a.get("lote_id") == "L3" and a.get("quantidade_total"):
            a["quantidade_total"] *= 3
    outro = Projeto(dados)
    conf = reabrir_e_conferir(banco, outro, salvo["id"])["conferencia"]
    assert conf["dados_da_obra_iguais"] is False
    assert conf["reproduz_identico"] is False
    assert "mudaram" in conf["nota"]


def test_nome_duplicado_e_id_inexistente(banco, projetos):
    p = projetos["ferrovia"]
    salvar_cenario_nomeado(banco, p, "ferrovia", "X", [])
    with pytest.raises(ErroPersistencia, match="já existe"):
        salvar_cenario_nomeado(banco, p, "ferrovia", "X", [])
    salvar_cenario_nomeado(banco, p, "rodovia-mesmo-nome-outra-obra", "X", [])  # nome é único POR obra
    with pytest.raises(ErroPersistencia, match="inexistente"):
        banco.obter_cenario(999)
    with pytest.raises(ErroPersistencia, match="obrigatório"):
        banco.salvar_cenario("ferrovia", "  ", [], {}, "h")


# -------------------------------------------------------- snapshots e auditoria
def test_snapshots_e_auditoria(banco):
    r1 = {"data_status": "2026-10-01", "termino": "2027-09-01", "cadeia_determinante": ["A", "B"]}
    r2 = {"data_status": "2026-11-01", "termino": "2027-09-10", "cadeia_determinante": ["A", "C"]}
    banco.gravar_snapshot("ferrovia", "independente", r2, 70.5, "h1")
    banco.gravar_snapshot("ferrovia", "independente", r1, 64.0, "h1")
    banco.gravar_snapshot("ferrovia", "independente", {**r1, "termino": "2027-09-02"}, 64.0, "h1")  # substitui
    s = banco.listar_snapshots("ferrovia")
    assert [(x["data_status"], x["termino"], x["cadeia_determinante"]) for x in s] == \
           [("2026-10-01", "2027-09-02", ["A", "B"]), ("2026-11-01", "2027-09-10", ["A", "C"])]
    assert banco.listar_snapshots("rodovia") == []

    banco.auditar("acao_1", "ferrovia", "fiscal B", {"x": 1}, {"ok": True})
    banco.auditar("acao_2", "ferrovia", None, {}, {})
    banco.auditar("acao_3", "rodovia", "fiscal C", {}, {})
    aud = banco.listar_auditoria("ferrovia")
    assert [a["acao"] for a in aud] == ["acao_2", "acao_1"]  # mais recente primeiro
    assert aud[1]["quem"] == "fiscal B" and aud[1]["parametros"] == {"x": 1}
    assert "sem autenticação" in aud[0]["quem"]
    assert all(a["quando"] for a in aud)
    assert len(banco.listar_auditoria()) == 3


def test_concorrencia_simples_duas_instancias_no_mesmo_arquivo(tmp_path):
    caminho = tmp_path / "conc.sqlite"
    bancos = [Banco(caminho), Banco(caminho)]
    erros, ids = [], []
    lock = threading.Lock()

    def trabalhar(n):
        b = bancos[n % 2]
        try:
            for i in range(10):
                id_ = b.salvar_cenario("ferrovia", f"t{n}-{i}", [], {"termino": "2027-01-01"}, "h")
                b.auditar("salvar_cenario", "ferrovia", f"t{n}", {"i": i}, {"id": id_})
                b.gravar_snapshot("ferrovia", f"c{n}", {"data_status": f"2026-01-{i + 1:02d}", "termino": "x"}, 1.0, "h")
                with lock:
                    ids.append(id_)
        except Exception as e:  # noqa: BLE001
            erros.append(e)

    threads = [threading.Thread(target=trabalhar, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert erros == []
    assert len(ids) == 80 and len(set(ids)) == 80
    assert len(Banco(caminho).listar_cenarios("ferrovia")) == 80
    assert len(Banco(caminho).listar_auditoria("ferrovia", limite=1000)) == 80
    assert len(Banco(caminho).listar_snapshots("ferrovia")) == 80


def test_banco_padrao_fica_fora_do_git():
    assert BANCO_PADRAO == RAIZ / "output" / "infra4d.sqlite"
    if shutil.which("git") is None:
        pytest.skip("git ausente")
    dentro = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=RAIZ, capture_output=True, text=True)
    if dentro.returncode != 0 or dentro.stdout.strip() != "true":
        pytest.skip("diretório não é repositório Git (ex.: git archive): check-ignore não se aplica")
    r = subprocess.run(["git", "check-ignore", "-q", "output/infra4d.sqlite"], cwd=RAIZ)
    assert r.returncode == 0, "output/infra4d.sqlite precisa estar ignorado pelo .gitignore"


# ------------------------------------------------------------ histórico sintético
@pytest.mark.parametrize("obra", list(OBRAS))
def test_ancora_truncar_na_data_atual_nao_muda_nada(projetos, evolucoes, obra):
    p = projetos[obra]
    assert projeto_na_data(p, p.data_status).dados == p.dados
    ultimo = evolucoes[obra]["pontos"][-1]
    assert ultimo["data_status"] == p.dados["meta"]["data_status"]
    assert ultimo["termino_independente"] == executar(p, "independente")["termino"]
    assert ultimo["termino_construtora"] == executar(p, "construtora")["termino"]
    assert ultimo["termino_linha_base"] == p.dados["meta"]["termino_linha_base"]


@pytest.mark.parametrize("obra", list(OBRAS))
def test_serie_monotona(projetos, evolucoes, obra):
    p = projetos[obra]
    pts = evolucoes[obra]["pontos"]
    assert len(pts) >= 10
    datas = [ordinal(x["data_status"]) for x in pts]
    assert datas == sorted(datas) and len(set(datas)) == len(datas)
    assert datas == datas_mensais(p)
    for a, b in zip(pts, pts[1:]):
        assert b["avanco_real_pct"] >= a["avanco_real_pct"]
        assert b["avanco_previsto_lb_pct"] >= a["avanco_previsto_lb_pct"]
        assert b["n_boletins"] >= a["n_boletins"]
        assert b["escorregamento_independente_dias"] == \
            ordinal(b["termino_independente"]) - ordinal(a["termino_independente"])
    for x in pts:
        assert ordinal(x["termino_independente"]) >= ordinal(x["data_status"])
        assert ordinal(x["termino_construtora"]) >= ordinal(x["data_status"])
        assert x["diferenca_dias_corridos"] == ordinal(x["termino_independente"]) - ordinal(x["termino_construtora"])
    assert evolucoes[obra]["simplificacoes"] and evolucoes[obra]["narrativa"]


def test_truncagem_no_passado(projetos):
    p = projetos["ferrovia"]
    h0 = hash_dados(p)
    t = ordinal("2026-05-01")
    pt = projeto_na_data(p, t)
    assert hash_dados(p) == h0, "o dataset original não pode ser alterado"
    assert pt.data_status == t
    assert all(ordinal(m["semana_inicio"]) < t for m in pt.dados["medicoes"])
    soma = {}
    for m in pt.dados["medicoes"]:
        soma[m["atividade_id"]] = soma.get(m["atividade_id"], 0) + m["quantidade"]
    orig = {a["id"]: a for a in p.dados["atividades"]}
    vistos = set()
    for a in pt.dados["atividades"]:
        o = orig[a["id"]]
        ini, fim = ordinal(o.get("inicio_real")), ordinal(o.get("termino_real"))
        if ini is None or ini >= t:
            assert a["status"] == "nao_iniciada" and "inicio_real" not in a
        elif fim is not None and fim < t:
            assert a["status"] == "concluida" and a == o
        else:
            assert a["status"] == "em_andamento" and "termino_real" not in a
            vistos.add("em_andamento")
            if a.get("quantidade_total"):
                assert a["quantidade_executada"] == pytest.approx(min(a["quantidade_total"], soma.get(a["id"], 0)))
    assert "em_andamento" in vistos
    # nenhuma concluída no passado que hoje não esteja concluída
    with pytest.raises(ValueError, match="futuro"):
        projeto_na_data(p, p.data_status + 1)


def test_status_so_avanca_ao_longo_dos_meses(projetos):
    p = projetos["rodovia"]
    ordem = {"nao_iniciada": 0, "em_andamento": 1, "concluida": 2}
    anterior = None
    for t in datas_mensais(p):
        st = {a["id"]: ordem[a["status"]] for a in projeto_na_data(p, t).dados["atividades"]}
        if anterior:
            assert all(st[k] >= anterior[k] for k in st)
        anterior = st


# --------------------------------------------------------------------- rotas
class _Estado:
    def __init__(self, projeto):
        self.projeto = projeto
        self._c = {}

    def resultado(self, c):
        if c not in self._c:
            self._c[c] = executar(self.projeto, c)
        return self._c[c]


@pytest.fixture
def cliente(projetos, tmp_path):
    estados = {k: _Estado(p) for k, p in projetos.items()}

    def obter_estado(obra=None):
        obra = obra or "ferrovia"
        if obra not in estados:
            raise HTTPException(404, f"obra desconhecida: {obra}")
        return estados[obra]

    app = FastAPI()
    rotas_hist.ligar(app, obter_estado, Banco(tmp_path / "api.sqlite"))
    return TestClient(app)


def test_rotas_cenarios_salvos(cliente, projetos):
    r = cliente.post("/api/historico/cenarios-salvos", params={"obra": "ferrovia"},
                     json={"nome": "reforço L3", "ajustes": [AJUSTE_TER_L3], "quem": "fiscal A"})
    assert r.status_code == 200, r.text
    id_ = r.json()["id"]
    assert r.json()["termino"] == executar(projetos["ferrovia"], "simulado", [Ajuste.de_dict(AJUSTE_TER_L3)])["termino"]
    assert cliente.post("/api/historico/cenarios-salvos", params={"obra": "ferrovia"},
                        json={"nome": "reforço L3", "ajustes": []}).status_code == 409
    assert cliente.post("/api/historico/cenarios-salvos", json={"nome": "x", "ajustes": [{"equipes": 0}]}
                        ).status_code == 422
    assert cliente.post("/api/historico/cenarios-salvos", json={"ajustes": []}).status_code == 422
    lista = cliente.get("/api/historico/cenarios-salvos", params={"obra": "ferrovia"}).json()
    assert [c["nome"] for c in lista["cenarios"]] == ["reforço L3"]
    assert cliente.get("/api/historico/cenarios-salvos", params={"obra": "rodovia"}).json()["cenarios"] == []
    det = cliente.get(f"/api/historico/cenarios-salvos/{id_}", params={"obra": "ferrovia"}).json()
    assert det["conferencia"]["reproduz_identico"] is True
    assert det["resultado"]["termino"] == r.json()["termino"]
    assert cliente.get(f"/api/historico/cenarios-salvos/{id_}", params={"obra": "rodovia"}).status_code == 404
    assert cliente.get("/api/historico/cenarios-salvos/999").status_code == 404
    assert cliente.get("/api/historico/cenarios-salvos", params={"obra": "nenhuma"}).status_code == 404
    aud = cliente.get("/api/historico/auditoria", params={"obra": "ferrovia"}).json()["registros"]
    assert [(a["acao"], a["quem"]) for a in aud] == [("salvar_cenario", "fiscal A")]


def test_rotas_evolucao_e_snapshots(cliente, projetos, evolucoes):
    e = cliente.get("/api/historico/evolucao", params={"obra": "rodovia"}).json()
    assert e["obra"] == "rodovia"
    assert e["pontos"] == _json(evolucoes["rodovia"]["pontos"])
    assert e["snapshots_registrados"] == []
    s = cliente.post("/api/historico/snapshots", params={"obra": "rodovia", "quem": "fiscal C"})
    assert s.status_code == 200
    e2 = cliente.get("/api/historico/evolucao", params={"obra": "rodovia"}).json()
    snaps = {x["cenario"]: x for x in e2["snapshots_registrados"]}
    assert snaps["independente"]["termino"] == e["pontos"][-1]["termino_independente"]
    assert snaps["construtora"]["termino"] == e["pontos"][-1]["termino_construtora"]
    assert snaps["independente"]["avanco"] == e["pontos"][-1]["avanco_real_pct"]
    aud = cliente.get("/api/historico/auditoria", params={"obra": "rodovia"}).json()["registros"]
    assert aud[0]["acao"] == "registrar_snapshot" and aud[0]["quem"] == "fiscal C"


def test_rotas_sem_ligar_respondem_503():
    app = FastAPI()
    app.include_router(rotas_hist.router)
    assert TestClient(app).get("/api/historico/auditoria").status_code == 503


def test_boletim_cortado_pela_data_e_rateado_pelos_dias_trabalhados(projetos):
    """Regressão r10: boletim de L1-S03-TER da semana de 04/09/2026 com status em 07/09 não pode trazer
    equipes·dia nem produção dos dias depois de 07/09."""
    p = projetos["ferrovia"]
    t = ordinal("2026-09-07")
    orig = [m for m in p.dados["medicoes"] if m["atividade_id"] == "L1-S03-TER" and m["semana_inicio"] == "2026-09-04"]
    assert len(orig) == 1 and orig[0]["equipes_dias"] == 10
    a = p.atividades["L1-S03-TER"]
    cal, eqs = p.calendarios[a["calendario"]], int(a.get("equipes") or 1)
    s = ordinal("2026-09-04")
    uteis, d = [], s
    while len(uteis) < orig[0]["equipes_dias"] // eqs:
        if cal.eh_util(d):
            uteis.append(d)
        d += 1
    k = sum(1 for x in uteis if x < t)
    assert 0 < k < len(uteis)
    cortado = [m for m in projeto_na_data(p, t).dados["medicoes"]
               if m["atividade_id"] == "L1-S03-TER" and m["semana_inicio"] == "2026-09-04"]
    assert len(cortado) == 1
    assert cortado[0]["equipes_dias"] == k * eqs
    assert cortado[0]["quantidade"] == pytest.approx(orig[0]["quantidade"] * k / len(uteis))
    assert cortado[0]["rateado_ate"] == "2026-09-07"
    assert "rateado_ate" not in orig[0], "o dataset original não pode ser alterado"
