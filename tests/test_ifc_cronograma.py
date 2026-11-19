"""Cronograma nativo IFC 4.3 (etapa 5): IfcWorkPlan/IfcWorkSchedule por cenário, IfcTask/IfcTaskTime,
IfcRelSequence + IfcLagTime, IfcWorkCalendar e IfcRelAssignsToProduct — e a IDA E VOLTA pelo motor.

Mesma lógica do teste MSPDI (tests/test_importadores_mspdi.py): o IFC é gravado em disco, relido, o
cronograma vira ``AtividadeCPM``/``Relacao``/``Calendario`` e ``motor.calcular`` tem de dar es/ef de TODAS
as atividades, término e caminho crítico iguais ao cálculo de referência (``montar_entrada`` + ``calcular``).

Validação: EXPRESS completo na ferrovia; só esquema na rodovia (decisão do orquestrador, por tempo:
a validação EXPRESS com 3 cenários leva ~26 s por obra).
"""

import copy
import json

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")
import ifcopenshell.util.element  # noqa: E402
import ifcopenshell.validate  # noqa: E402

from infra4d.calendario import iso  # noqa: E402
from infra4d.cenarios import DATASET_PADRAO, Ajuste, Projeto, executar, montar_entrada  # noqa: E402
from infra4d.ifc import PSET_VINCULO  # noqa: E402
from infra4d.ifc import cronograma as cron  # noqa: E402
from infra4d.ifc import exportar as exp  # noqa: E402
from infra4d.motor import calcular  # noqa: E402

OBRAS = ("ferrovia", "rodovia")
CENARIOS = ["linha_base", "construtora", "independente"]


def _projeto(obra):
    return Projeto.carregar(DATASET_PADRAO.parent / f"{obra}_ficticia.json")


def _elementos_por_atividade(f):
    out = {}
    for e in f.by_type("IfcElement"):
        ps = ifcopenshell.util.element.get_pset(e, PSET_VINCULO)
        if ps:
            out.setdefault(ps["AtividadeId"], []).append(e)
    return out


def _gravar_e_reabrir(projeto, tmp_path_factory, cenarios=CENARIOS, ajustes=None, nome="m.ifc"):
    f, _ = exp.construir(projeto.dados, incluir_4d=False, posicionamento="local")
    resumo = cron.adicionar(f, projeto, cenarios, _elementos_por_atividade(f), ajustes=ajustes)
    caminho = tmp_path_factory.mktemp("cron") / nome
    f.write(str(caminho))
    return ifcopenshell.open(str(caminho)), resumo


@pytest.fixture(scope="module", params=OBRAS)
def obra(request):
    return request.param


@pytest.fixture(scope="module")
def projeto(obra):
    return _projeto(obra)


@pytest.fixture(scope="module")
def modelo(projeto, tmp_path_factory):
    return _gravar_e_reabrir(projeto, tmp_path_factory)


def _referencia(projeto, cenario, ajustes=None):
    ref_a, ref_r, _ = montar_entrada(projeto, cenario, ajustes)
    ds = None if cenario == "linha_base" else projeto.data_status
    return ref_a, calcular(ref_a, ref_r, projeto.calendarios, projeto.inicio_projeto, data_status=ds)


def _recalcular(f, cenario):
    ativs, rels, cals, meta = cron.ler(f, cenario)
    return calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta["data_status"])


# ---------------------------------------------------------------------------------- ida e volta

@pytest.mark.parametrize("cenario", CENARIOS)
def test_ida_e_volta_reproduz_datas_termino_e_caminho_critico(projeto, modelo, cenario):
    f, _ = modelo
    res = _recalcular(f, cenario)
    ref_a, ref = _referencia(projeto, cenario)
    assert set(res.atividades) == set(ref.atividades)
    if cenario != "linha_base":
        assert [a for a in ref_a if a.status == "nao_iniciada"], "o cenário precisa ter atividades não iniciadas"
    for aid in ref.atividades:  # TODAS, inclusive em andamento e concluídas
        assert (res.atividades[aid].es, res.atividades[aid].ef) == (ref.atividades[aid].es, ref.atividades[aid].ef), aid
        assert res.atividades[aid].folga_total == ref.atividades[aid].folga_total, aid
    assert res.termino_projeto == ref.termino_projeto
    assert iso(res.termino_projeto_data) == executar(projeto, cenario)["termino"]
    assert sorted(res.caminho_critico) == sorted(ref.caminho_critico)


@pytest.mark.parametrize("cenario", CENARIOS)
def test_datas_gravadas_iguais_as_da_api(projeto, modelo, cenario):
    f, _ = modelo
    gravado = cron.datas_gravadas(f, cenario)
    api = executar(projeto, cenario)["atividades"]
    assert set(gravado) == set(api)
    for aid, x in api.items():
        esperado = {k: x.get(k) for k in ("inicio", "termino", "es", "ef", "ls", "lf", "folga_total", "folga_livre")}
        esperado["critica"] = bool(x["critica"])
        assert gravado[aid] == esperado, aid


# ---------------------------------------------------------------------------------- estrutura

def test_estrutura_do_cronograma(projeto, modelo):
    f, resumo = modelo
    n = len(projeto.dados["atividades"])
    assert len(f.by_type("IfcWorkPlan")) == 1
    crons = {c.Identification: c for c in f.by_type("IfcWorkSchedule")}
    assert set(crons) == set(CENARIOS) and "simulado" not in crons  # simulado só com ajustes
    assert crons["linha_base"].PredefinedType == "BASELINE"
    assert crons["construtora"].PredefinedType == "PLANNED"
    assert (crons["independente"].PredefinedType, crons["independente"].ObjectType) == ("USERDEFINED", "INDEPENDENTE")
    assert len(f.by_type("IfcTask")) == n * len(CENARIOS) == resumo["tarefas"]
    assert len(f.by_type("IfcRelSequence")) == len(projeto.dados["relacoes"]) * len(CENARIOS)
    # UM IfcRelAssignsToProduct por peça, ligando a tarefa da atividade nos 3 cenários
    els = _elementos_por_atividade(f)
    for aid, lista in els.items():
        for e in lista:
            rels = [r for r in e.ReferencedBy if r.is_a("IfcRelAssignsToProduct")]
            assert len(rels) == 1
            assert sorted(t.Identification for t in rels[0].RelatedObjects) == [aid] * len(CENARIOS)
    assert len(f.by_type("IfcRelAssignsToProduct")) == sum(len(v) for v in els.values())


def test_calendarios_ida_e_volta_exata(projeto, modelo):
    f, _ = modelo
    _, _, cals, _ = cron.ler(f, "independente")
    for cid, c in cals.items():
        orig = projeto.calendarios[cid]
        assert tuple(sorted(c.dias_semana)) == tuple(sorted(orig.dias_semana)), cid
        assert c.nao_uteis == orig.nao_uteis, cid
    assert len(f.by_type("IfcWorkCalendar")) == len(projeto.calendarios)  # compartilhados pelos cenários


def test_validacao(obra, modelo):
    """Ferrovia: esquema + regras EXPRESS. Rodovia: só esquema (decisão declarada no topo)."""
    f, _ = modelo
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=(obra == "ferrovia"))
    assert log.statements == [], [str(s)[:200] for s in log.statements[:3]]


# ---------------------------------------------------------------------------------- detectores

def _tarefa(f, cenario, aid):
    c = next(x for x in f.by_type("IfcWorkSchedule") if x.Identification == cenario)
    return next(t for rel in c.Controls for t in rel.RelatedObjects if t.Identification == aid)


def test_mutantes_mudam_o_resultado(projeto, modelo):
    """O recálculo depende do que está no IFC: mudar lag, apagar relação e tirar dia não útil é visto."""
    f0, _ = modelo
    _, ref = _referencia(projeto, "independente")
    ref_es = {k: (v.es, v.ef) for k, v in ref.atividades.items()}

    # 1) lag maior numa relação cujo sucessor ainda não começou
    f = ifcopenshell.file.from_string(f0.to_string())
    ids = {t.id() for rel in next(c for c in f.by_type("IfcWorkSchedule") if c.Identification == "independente").Controls
           for t in rel.RelatedObjects}
    rs = next(r for r in f.by_type("IfcRelSequence") if r.RelatingProcess.id() in ids
              and r.RelatedProcess.Status == "nao_iniciada" and r.RelatedProcess.ObjectType == "tarefa")
    rs.TimeLag = f.create_entity("IfcLagTime", LagValue=f.create_entity("IfcDuration", "P400D"), DurationType="WORKTIME")
    assert _recalcular(f, "independente").termino_projeto > ref.termino_projeto

    # 2) relações apagadas: TODAS as que chegam numa atividade crítica não iniciada (com pares SS+FF,
    #    apagar só uma pode não mudar nada — a primeira versão deste mutante não mudou e foi corrigida)
    f = ifcopenshell.file.from_string(f0.to_string())
    criticas = set(ref.caminho_critico)
    alvo = next(r.RelatedProcess for r in f.by_type("IfcRelSequence") if r.RelatingProcess.id() in ids
                and r.RelatedProcess.Identification in criticas and r.RelatedProcess.Status == "nao_iniciada")
    for r in [r for r in f.by_type("IfcRelSequence") if r.RelatedProcess == alvo]:
        f.remove(r)
    res = _recalcular(f, "independente")
    assert res.atividades[alvo.Identification].es < ref.atividades[alvo.Identification].es

    # 3) faixa de dias não úteis FUTURA removida de um calendário
    f = ifcopenshell.file.from_string(f0.to_string())
    ds = projeto.data_status
    wc, wt = next((wc, wt) for wc in f.by_type("IfcWorkCalendar") for wt in (wc.ExceptionTimes or ())
                  if __import__("datetime").date.fromisoformat(wt.StartDate).toordinal() > ds + 30)
    wc.ExceptionTimes = [x for x in wc.ExceptionTimes if x != wt]
    _, _, cals, _ = cron.ler(f, "independente")
    assert cals[wc.Identification].nao_uteis != projeto.calendarios[wc.Identification].nao_uteis


def test_duracao_fora_da_convencao_e_recusada(modelo):
    f0, _ = modelo
    f = ifcopenshell.file.from_string(f0.to_string())
    t = next(t for t in f.by_type("IfcTask") if t.TaskTime.ScheduleDuration)
    t.TaskTime.ScheduleDuration = "PT8H"
    with pytest.raises(cron.ErroCronograma):
        for c in CENARIOS:
            cron.ler(f, c)
    with pytest.raises(cron.ErroCronograma):
        cron.ler(f0, "cenario-que-nao-existe")


# ---------------------------------------------------------------------------------- simulado e negativos

def test_simulado_so_com_ajustes(tmp_path_factory):
    p = _projeto("ferrovia")
    f, resumo = _gravar_e_reabrir(p, tmp_path_factory, cenarios=CENARIOS + ["simulado"], nome="sem_aj.ifc")
    assert "simulado" not in resumo["cenarios"] and "simulado" not in cron.cenarios_no_arquivo(f)
    res_ind = executar(p, "independente")
    alvo = next(aid for aid, x in res_ind["atividades"].items()
                if x["critica"] and x["status"] == "nao_iniciada" and p.atividades[aid].get("produtividade_planejada"))
    aj = [Ajuste(atividade_id=alvo, produtividade=p.atividades[alvo]["produtividade_planejada"] * 0.5)]
    f, resumo = _gravar_e_reabrir(p, tmp_path_factory, cenarios=["independente", "simulado"], ajustes=aj, nome="aj.ifc")
    c = next(x for x in f.by_type("IfcWorkSchedule") if x.Identification == "simulado")
    assert (c.PredefinedType, c.ObjectType) == ("USERDEFINED", "SIMULADO")
    res = _recalcular(f, "simulado")
    _, ref = _referencia(p, "simulado", aj)
    assert {k: (v.es, v.ef) for k, v in res.atividades.items()} == {k: (v.es, v.ef) for k, v in ref.atividades.items()}
    assert iso(res.termino_projeto_data) == executar(p, "simulado", aj)["termino"] != res_ind["termino"]


def test_lag_e_folga_negativos_vao_para_pset(tmp_path_factory):
    """O validador aceita até 'abc' em IfcDuration (aceite por omissão): negativo NÃO vai para IfcDuration."""
    p0 = _projeto("ferrovia")
    dados = copy.deepcopy(p0.dados)
    res = executar(p0, "independente")["atividades"]
    nao_ini = {a["id"] for a in dados["atividades"] if a.get("status") == "nao_iniciada" and a.get("tipo") == "tarefa"}
    rel = next(r for r in dados["relacoes"] if r["predecessora"] in nao_ini and r["sucessora"] in nao_ini)
    rel["lag"] = -3
    alvo = next(aid for aid in nao_ini if res[aid]["critica"])
    lim = __import__("datetime").date.fromisoformat(res[alvo]["termino"]) - __import__("datetime").timedelta(days=60)
    next(a for a in dados["atividades"] if a["id"] == alvo)["restricao_termino"] = lim.isoformat()
    p = Projeto(json.loads(json.dumps(dados)))
    f, resumo = _gravar_e_reabrir(p, tmp_path_factory, cenarios=["independente"], nome="neg.ifc")
    assert resumo["registros_negativos_em_pset"] >= 2
    for tt in f.by_type("IfcTaskTime"):
        for campo in ("TotalFloat", "FreeFloat", "ScheduleDuration", "RemainingTime"):
            assert not str(getattr(tt, campo) or "").startswith("-"), campo
    for lt in f.by_type("IfcLagTime"):
        assert not str(lt.LagValue.wrappedValue).startswith("-")
    gravado = cron.datas_gravadas(f, "independente")
    api = executar(p, "independente")["atividades"]
    assert gravado[alvo]["folga_total"] == api[alvo]["folga_total"] < 0
    res_i = _recalcular(f, "independente")
    _, ref = _referencia(p, "independente")
    assert {k: (v.es, v.ef, v.folga_total) for k, v in res_i.atividades.items()} == \
           {k: (v.es, v.ef, v.folga_total) for k, v in ref.atividades.items()}
    rels = cron.ler(f, "independente")[1]
    assert any(r.lag == -3 and r.predecessora == rel["predecessora"] and r.sucessora == rel["sucessora"] for r in rels)
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log)
    assert log.statements == []


# ---------------------------------------------------------------------------------- rotas

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def cliente_api():
    from infra4d.api import criar_app
    return TestClient(criar_app())


@pytest.mark.parametrize("cenario", CENARIOS)
def test_rota_exportar_e_recalcular_cronograma(cliente_api, obra, cenario):
    corpo = cliente_api.get("/api/ifc/exportar", params={"obra": obra}).content
    r = cliente_api.post("/api/ifc/cronograma", params={"obra": obra, "cenario": cenario}, content=corpo)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["cenarios_no_arquivo"] == CENARIOS
    assert v["confere_com_api"] is True and v["termino_calculado"] == v["termino_api"]
    assert v["n_atividades"] == len(_projeto(obra).dados["atividades"])


def test_rota_cronograma_erros(cliente_api):
    corpo = cliente_api.get("/api/ifc/exportar", params={"obra": "ferrovia"}).content
    r = cliente_api.post("/api/ifc/cronograma", params={"obra": "ferrovia", "cenario": "simulado"}, content=corpo)
    assert r.status_code == 422 and "simulado" in r.json()["detail"]  # sem ajustes, não há cronograma simulado
    assert cliente_api.post("/api/ifc/cronograma", content=b"").status_code == 400
    assert cliente_api.post("/api/ifc/cronograma", content=b"nada").status_code == 422


def test_rota_exportar_inclui_simulado_quando_ha_ajustes(cliente_api):
    p = _projeto("ferrovia")
    res = executar(p, "independente")["atividades"]
    alvo = next(aid for aid, x in res.items()
                if x["critica"] and x["status"] == "nao_iniciada" and p.atividades[aid].get("produtividade_planejada"))
    prod = p.atividades[alvo]["produtividade_planejada"] * 0.5
    r = cliente_api.post("/api/simulacao", params={"obra": "ferrovia"},
                         json={"ajustes": [{"atividade_id": alvo, "produtividade": prod}]})
    assert r.status_code == 200, r.text
    try:
        termino_sim = cliente_api.get("/api/cenarios/simulado", params={"obra": "ferrovia"}).json()["termino"]
        corpo = cliente_api.get("/api/ifc/exportar", params={"obra": "ferrovia"}).content
        r = cliente_api.post("/api/ifc/cronograma", params={"obra": "ferrovia", "cenario": "simulado"}, content=corpo)
        assert r.status_code == 200, r.text
        assert r.json()["cenarios_no_arquivo"] == CENARIOS + ["simulado"]
        assert r.json()["termino_calculado"] == termino_sim
    finally:
        cliente_api.delete("/api/simulacao", params={"obra": "ferrovia"})


# ---------------------------------------------------------------------------------- r17 e R13-3

def _reaberto(projeto, cenarios=("independente",)):
    f, _ = exp.construir(projeto.dados, incluir_4d=False, posicionamento="local")
    cron.adicionar(f, projeto, list(cenarios), {})
    return ifcopenshell.file.from_string(f.to_string())


QUEBRAS_TERCEIRO = {
    "SequenceType NOTDEFINED": (lambda f: setattr(f.by_type("IfcRelSequence")[0], "SequenceType", "NOTDEFINED"),
                                "SequenceType"),
    "SequenceType ausente": (lambda f: setattr(f.by_type("IfcRelSequence")[0], "SequenceType", None), "SequenceType"),
    "tarefa sem TaskTime": (lambda f: setattr(f.by_type("IfcTask")[0], "TaskTime", None), "IfcTaskTime"),
    "exceção sem StartDate": (lambda f: setattr(f.by_type("IfcWorkCalendar")[0].ExceptionTimes[0], "StartDate", None),
                              "StartDate"),
    "WEEKLY sem WeekdayComponent": (lambda f: setattr(f.by_type("IfcRecurrencePattern")[0], "WeekdayComponent", None),
                                    "WeekdayComponent"),
    "tarefa sem Identification": (lambda f: setattr(f.by_type("IfcTask")[0], "Identification", None), "Identification"),
    "cronograma sem StartTime": (lambda f: setattr(f.by_type("IfcWorkSchedule")[0], "StartTime", None), "StartTime"),
    "lag que não é IfcDuration": (lambda f: setattr(
        next(r for r in f.by_type("IfcRelSequence") if r.TimeLag), "TimeLag",
        f.create_entity("IfcLagTime", LagValue=f.create_entity("IfcRatioMeasure", 0.5), DurationType="WORKTIME")),
        "IfcDuration"),
}


@pytest.mark.parametrize("nome", sorted(QUEBRAS_TERCEIRO))
def test_ler_recusa_ifc_de_terceiro_incompleto_com_motivo(nome):
    """r17: atributo OPCIONAL do IFC ausente/fora do suportado → ErroCronograma com o motivo (rota: 422), nunca
    KeyError/TypeError/AttributeError (que viravam 500)."""
    f = _reaberto(_projeto("ferrovia"))
    quebra, palavra = QUEBRAS_TERCEIRO[nome]
    quebra(f)
    with pytest.raises(cron.ErroCronograma, match=palavra):
        cron.ler(f, "independente")


def test_lag_em_elapsedtime_vira_aviso_declarado():
    p = _projeto("ferrovia")
    f = _reaberto(p)
    rs = next(r for r in f.by_type("IfcRelSequence") if r.TimeLag)
    rs.TimeLag.DurationType = "ELAPSEDTIME"
    ativs, rels, cals, meta = cron.ler(f, "independente")
    assert any("ELAPSEDTIME" in a and rs.RelatingProcess.Identification in a for a in meta["avisos"])
    assert cron.ler(_reaberto(p), "independente")[3]["avisos"] == []  # arquivo nosso: sem aviso


def test_em_andamento_grava_schedule_duration_total_e_concluida_actual_duration(projeto, modelo):
    """R13-3: em andamento leva ScheduleDuration = dias úteis de início a término (além de RemainingTime);
    concluída leva ActualDuration = dias úteis entre início e término reais. A ida e volta continua exata
    (os testes de ida e volta acima rodam sobre este mesmo arquivo)."""
    f, _ = modelo
    api = executar(projeto, "independente")["atividades"]
    ativs = {a.id: a for a in montar_entrada(projeto, "independente")[0]}
    vistos = {"em_andamento": 0, "concluida": 0}
    from infra4d.calendario import ordinal
    for aid, tt in ((t.Identification, t.TaskTime) for rel in next(
            c for c in f.by_type("IfcWorkSchedule") if c.Identification == "independente").Controls
            for t in rel.RelatedObjects):
        a, cal = ativs[aid], projeto.calendarios[ativs[aid].calendario]
        if a.status == "em_andamento":
            total = cal.dias_uteis_entre(ordinal(api[aid]["inicio"]), ordinal(api[aid]["termino"]) + 1)
            assert (tt.ScheduleDuration, tt.RemainingTime) == (f"P{total}D", f"P{a.duracao}D"), aid
            assert total > a.duracao  # a total inclui o que já foi feito
            vistos["em_andamento"] += 1
        elif a.status == "concluida" and a.inicio_real and a.termino_real:
            real = cal.dias_uteis_entre(a.inicio_real, a.termino_real + 1)
            assert (tt.ScheduleDuration, tt.ActualDuration) == (f"P{a.duracao}D", f"P{real}D"), aid
            vistos["concluida"] += 1
        else:
            assert tt.ActualDuration is None
    assert vistos["em_andamento"] and vistos["concluida"]
