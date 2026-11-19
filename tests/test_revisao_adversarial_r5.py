"""Revisão adversarial — rodada 5: revisão cruzada de recursos.py e importadores/.

Mesmo protocolo: esperado calculado à mão no docstring; defeito confirmado fica
``xfail(strict=True, reason="DEFEITO: ...")``.

2026-01-05 é segunda. Calendários dos projetos sintéticos deste arquivo: c5 = seg–sex;
c6 = seg–sáb; cF = seg–sex com feriados em 19 e 20/01 e 16/02/2026.
"""

import random
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infra4d import recursos
from infra4d.calendario import iso
from infra4d.cenarios import Projeto, executar
from infra4d.importadores.comum import ErroImportacao
from infra4d.importadores.mspdi import exportar_mspdi, importar_mspdi
from infra4d.importadores.xer import importar_xer
from infra4d.motor import calcular

RAIZ = Path(__file__).resolve().parents[1]
MSPDI = (RAIZ / "examples" / "fixtures" / "mspdi_minimo.xml").read_text(encoding="utf-8")
XER = (RAIZ / "examples" / "fixtures" / "p6_minimo.xer").read_bytes().decode("utf-8").replace("\r\n", "\n")
CORPO_MSPDI = MSPDI.split("?>", 1)[1]


# ----------------------------------------------------------------------------- projetos sintéticos
def proj(ativs, rels=(), ds="2026-01-14"):
    return Projeto({
        "meta": {"inicio_projeto": "2026-01-05", "data_status": ds, "calendario_obra": "c5", "aviso": "FICTÍCIO"},
        "calendarios": [
            {"id": "c5", "nome": "c5", "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": []},
            {"id": "c6", "nome": "c6", "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": []},
            {"id": "cF", "nome": "cF", "dias_semana": [0, 1, 2, 3, 4],
             "nao_uteis": ["2026-01-19", "2026-01-20", "2026-02-16"]}],
        "atividades": list(ativs), "relacoes": list(rels), "medicoes": [], "servicos": [], "lotes": [{"id": "L1"}],
    })


def fx(i, dur, cal="c5", **k):
    d = {"id": i, "nome": i, "tipo": "tarefa", "calendario": cal, "duracao_fixa": dur, "status": "nao_iniciada",
         "lote_id": "L1"}
    d.update(k)
    return d


def marco(i, tipo, cal="c5"):
    return {"id": i, "nome": i, "tipo": tipo, "calendario": cal, "status": "nao_iniciada"}


def rel(p, s, t="FS", lag=0):
    return {"predecessora": p, "sucessora": s, "tipo": t, "lag": lag}


def frente(i, serv, km0, km1, dur, **k):
    return fx(i, dur, servico_id=serv, segmento_id="S1", km_ini=km0, km_fim=km1, **k)


# =============================================================================
# 1. recursos.py
# =============================================================================
def test_nivelamento_em_redes_aleatorias_preserva_relacoes_capacidade_e_snet():
    """250 projetos aleatórios (semente fixa): calendários c5/c6/cF misturados, marcos de início e
    término, tarefas de duração 0, em andamento, FS/SS/FF/SF com lag -2..3, recursos TER (cap. 2) e
    DRE (cap. 1) com 1–2 equipes. O nivelamento tem de: passar nas três provas próprias (relações,
    capacidade, SNET); nunca antecipar o término nem o ES de ninguém; e, numa conferência independente
    do uso diário, não deixar dia acima da capacidade que não seja carga fixa de atividade em andamento
    ou atividade maior que a capacidade (declaradas como irredutíveis)."""
    cap = {"L1/TER": 2, "L1/DRE": 1}
    rng = random.Random(3)
    for _ in range(250):
        n, ativs = rng.randint(3, 7), []
        for i in range(n):
            y, cal = rng.random(), rng.choice(["c5", "c6", "cF"])
            if y < 0.10:
                ativs.append(marco(f"N{i}", rng.choice(["marco_inicio", "marco_termino"]), cal))
            elif y < 0.18:
                ativs.append(fx(f"N{i}", 0, cal=cal, servico_id="TER"))
            elif y < 0.30:
                ativs.append(fx(f"N{i}", rng.randint(2, 8), cal=cal, servico_id=rng.choice(["TER", "DRE"]),
                                status="em_andamento", inicio_real=f"2026-01-0{rng.randint(5, 9)}",
                                percentual_executado=50, equipes=rng.randint(1, 2)))
            else:
                ativs.append(fx(f"N{i}", rng.randint(1, 6), cal=cal, servico_id=rng.choice(["TER", "DRE", None]),
                                equipes=rng.randint(1, 2)))
        rels, vistos = [], set()
        for j in range(1, n):
            for i in rng.sample(range(j), min(j, rng.randint(0, 2))):
                if (i, j) not in vistos:
                    vistos.add((i, j))
                    rels.append(rel(f"N{i}", f"N{j}", rng.choice(["FS", "SS", "FF", "SF"]), rng.randint(-2, 3)))
        p = proj(ativs, rels)
        r = executar(p, "construtora")
        nv = recursos.nivelar(p, r, capacidades=cap)
        ctx = (ativs, rels)
        assert nv["prova_relacoes"]["ok"] and nv["prova_capacidade"]["ok"] and nv["prova_snet"]["ok"], ctx
        assert nv["termino_nivelado"] >= nv["termino_cpm"], ctx
        niv = nv["_resultado"]
        assert all(v["es"] >= r["atividades"][k]["es"] for k, v in niv["atividades"].items()), ctx
        fixa = recursos.uso_diario([x for x in recursos.intervalos(p, r) if x["status"] == "em_andamento"])
        irred = {(x["recurso"], x["data"]) for x in nv["prova_capacidade"]["sobrecarga_irredutivel"]}
        grandes = nv["prova_capacidade"]["atividades_acima_da_capacidade"]
        for rec, serie in recursos.uso_diario(recursos.intervalos(p, niv)).items():
            for d, v in serie.items():
                if v > cap[rec] and not grandes:
                    assert fixa.get(rec, {}).get(d, 0) > 0 and (rec, iso(d)) in irred, (rec, iso(d), ctx)


def test_histograma_com_logica_retida_conta_so_o_remanescente():
    """Status qua 14/01. P(5) não iniciada: 14..20/01. S em andamento (50 % de 4 d -> remanescente 2),
    FS de P. Retida: o remanescente de S é 21 e 22/01. S consome equipe em exatamente 2 dias úteis
    (21/01 e 22/01). O histograma conta 7 (14 a 22/01)."""
    p = proj([fx("P", 5, servico_id="TER"),
              fx("S", 4, servico_id="DRE", status="em_andamento", inicio_real="2026-01-05", percentual_executado=50)],
             [rel("P", "S")])
    r = executar(p, "construtora", logica_progresso="retida")
    assert (r["atividades"]["S"]["duracao"], r["atividades"]["S"]["termino"]) == (2, "2026-01-22")
    s = next(x for x in recursos.intervalos(p, r) if x["id"] == "S")
    assert [iso(d) for d in s["dias"]] == ["2026-01-21", "2026-01-22"]


def test_balanco_frentes_paralelas_e_trechos_invertidos():
    """T (terraplenagem) e D (drenagem), 10 km em 10 dias úteis cada, D com SS+2 de T: D anda 2 dias
    atrás de T. Em dias corridos (regra declarada) a distância é ~2 km no primeiro dia comum e nunca
    fica abaixo de 1,5 km até T terminar -> nenhum conflito com buffer 1,5. O mesmo com os dois trechos
    invertidos (km 10 -> 0): o sentido é detectado e também não há conflito."""
    for k0, k1 in ((0, 10), (10, 0)):
        p = proj([frente("T", "TER", k0, k1, 10), frente("D", "DRE", k0, k1, 10)], [rel("T", "D", "SS", 2)],
                 ds="2026-01-05")
        cb = recursos.conflitos_balanco(p, executar(p, "construtora"), buffer_km=1.5)
        assert cb["pares"] == [["TER", "DRE"]] and cb["n_conflitos"] == 0


def test_balanco_detecta_sucessora_executada_antes_da_antecessora():
    """Mesmo segmento, km 0–10. Drenagem D (sucessora) de 05 a 09/01; terraplenagem T (antecessora) só
    começa em 19/01 (SNET). D percorre todo o trecho onde T ainda não passou: tem de haver ao menos um
    conflito (ultrapassagem). O módulo devolve 0."""
    p = proj([frente("T", "TER", 0, 10, 10, restricao_inicio="2026-01-19"), frente("D", "DRE", 0, 10, 5)],
             ds="2026-01-05")
    r = executar(p, "construtora")
    assert (r["atividades"]["D"]["termino"], r["atividades"]["T"]["inicio"]) == ("2026-01-09", "2026-01-19")
    assert recursos.conflitos_balanco(p, r, pares={("TER", "DRE")})["n_conflitos"] >= 1


def test_balanco_usa_o_executado_da_frente_em_andamento():
    """Status qua 14/01. T (antecessora) começou em 01/12/2025 e executou 10 % de 10 km: está no km 1,
    com 9 dias úteis de remanescente (1 km/dia, até 26/01). D (sucessora) começa em 14/01 e faz 10 km em
    9 dias (1,11 km/dia). Em 15/01: T no km 2, D no km 1,11 -> distância 0,89 km < buffer 1,0, e só
    diminui. O primeiro conflito tem de aparecer até 15/01. O módulo põe T no km ~7,7 em 14/01 (reta do
    início real ao EF) e só acusa conflito em 26/01."""
    p = proj([frente("T", "TER", 0, 10, 10, status="em_andamento", inicio_real="2025-12-01", percentual_executado=10),
              frente("D", "DRE", 0, 10, 9)])
    r = executar(p, "construtora")
    assert (r["atividades"]["T"]["duracao"], r["atividades"]["T"]["termino"]) == (9, "2026-01-26")
    cb = recursos.conflitos_balanco(p, r, pares={("TER", "DRE")}, buffer_km=1.0)
    assert cb["n_conflitos"] >= 1 and min(c["data"] for c in cb["conflitos"]) <= "2026-01-15"


# =============================================================================
# 2. importadores: ida e volta
# =============================================================================
def _ida_e_volta(p, res):
    ativs, rels, cals, meta = importar_mspdi(exportar_mspdi(p, res))
    out = calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta["data_status"])
    por_id = {a.id: a for a in ativs}
    difs = []
    for aid, esperado in res["atividades"].items():
        d = out.atividades[aid].como_dict(cals[por_id[aid].calendario], por_id[aid])
        difs += [(aid, k, esperado[k], d[k]) for k in ("inicio", "termino", "folga_total") if d[k] != esperado[k]]
    return iso(out.termino_projeto_data), difs


@pytest.mark.parametrize("obra", ["ferrovia", "rodovia"])
def test_ida_e_volta_mspdi_exata_nas_duas_obras(obra):
    """Exportar e reimportar linha de base, construtora e independente das duas obras fictícias
    (calendários de 5 e 6 dias, progresso real): mesmo término e, por atividade, mesmo início, término
    e folga total — zero diferenças."""
    p = Projeto.carregar(RAIZ / "examples" / "synthetic" / f"{obra}_ficticia.json")
    for cenario in ("linha_base", "construtora", "independente"):
        res = executar(p, cenario)
        assert _ida_e_volta(p, res) == (res["termino"], []), cenario


def test_ida_e_volta_mspdi_com_calendarios_mistos_marcos_progresso_e_lags_negativos():
    """Rede escrita para forçar os casos difíceis: concluída em sábado (c6), em andamento em c6, tarefa
    em calendário com feriados, SNET, marco de início, marco de término em cF, tarefa de duração 0,
    SS/FF/SF com lag negativo e positivo. Ida e volta nos cenários linha de base e construtora: mesmo
    término (27/01/2026 nos dois) e nenhuma diferença de início, término ou folga."""
    p = proj([fx("C", 5, status="concluida", inicio_real="2026-01-05", termino_real="2026-01-09"),
              fx("CS", 6, cal="c6", status="concluida", inicio_real="2026-01-05", termino_real="2026-01-10"),
              fx("A", 10, cal="c6", status="em_andamento", inicio_real="2026-01-10", percentual_executado=40),
              fx("B", 4, cal="cF"), fx("D", 3, cal="c6", restricao_inicio="2026-01-24"),
              marco("M0", "marco_inicio"), marco("MT", "marco_termino", "cF"), fx("Z", 0), fx("E", 7)],
             [rel("C", "A"), rel("A", "B", "SS", 2), rel("A", "B", "FF", -1), rel("B", "D", "SF", 3),
              rel("B", "MT", "FS", -2), rel("M0", "E"), rel("E", "MT", "FF", 1), rel("Z", "E", "SS", 1),
              rel("CS", "E", "FS", 3), rel("D", "MT")])
    for cenario in ("linha_base", "construtora"):
        res = executar(p, cenario)
        assert res["termino"] == "2026-01-27"
        assert _ida_e_volta(p, res) == ("2026-01-27", []), cenario


# =============================================================================
# 3. importadores: entrada malformada ou maliciosa
# =============================================================================
def col(tabela, campo, novo, linha=0, texto=XER):
    """Troca o valor de um campo numa linha %R de uma tabela do XER da fixture."""
    saida, atual, campos, k = [], None, None, -1
    for ln in texto.split("\n"):
        p = ln.split("\t")
        if p[0] == "%T":
            atual, k = p[1], -1
        elif p[0] == "%F" and atual == tabela:
            campos = p[1:]
        elif p[0] == "%R" and atual == tabela:
            k += 1
            if linha is None or k == linha:
                p += [""] * (len(campos) + 1 - len(p))
                p[1 + campos.index(campo)] = novo
                ln = "\t".join(p)
        saida.append(ln)
    return "\n".join(saida)


def excecao(de, ate):
    bloco = (f"<Exception><TimePeriod><FromDate>{de}T00:00:00</FromDate><ToDate>{ate}T23:59:00</ToDate>"
             f"</TimePeriod><DayWorking>0</DayWorking></Exception>")
    if "<Exceptions>" in MSPDI:
        return MSPDI.replace("<Exceptions>", "<Exceptions>" + bloco, 1)
    return MSPDI.replace("</Calendar>", "<Exceptions>" + bloco + "</Exceptions></Calendar>", 1)


def heranca_profunda(n=2000):
    cals = "".join(f"<Calendar><UID>{i}</UID><Name>C{i}</Name><BaseCalendarUID>{i + 1}</BaseCalendarUID></Calendar>"
                   for i in range(1000, 1000 + n))
    return re.sub(r"<CalendarUID>\d+</CalendarUID>", "<CalendarUID>1000</CalendarUID>",
                  MSPDI.replace("<Calendars>", "<Calendars>" + cals, 1))


ENTRADAS_RECUSADAS = {
    "mspdi vazio": ("mspdi", ""),
    "mspdi truncado": ("mspdi", MSPDI[:len(MSPDI) // 2]),
    "mspdi byte nulo": ("mspdi", MSPDI.replace("<Name>", "<Name>\x00", 1)),
    "mspdi doctype": ("mspdi", MSPDI.replace("?>", "?><!DOCTYPE Project>", 1)),
    "mspdi bomba de entidades utf-16": ("mspdi", (
        '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE Project [<!ENTITY a "aaaaaaaaaa">'
        + "".join(f'<!ENTITY {chr(98 + i)} "{("&" + chr(97 + i) + ";") * 10}">' for i in range(9)) + "]>"
        + CORPO_MSPDI.replace("<Name>", "<Name>&j;", 1)).encode("utf-16")),
    "mspdi data ilegível": ("mspdi", re.sub(r"<StartDate>[^<]*", "<StartDate>ontem", MSPDI, count=1)),
    "mspdi início em 1900": ("mspdi", re.sub(r"<StartDate>[^<]*", "<StartDate>1900-01-01T08:00:00", MSPDI, count=1)),
    "mspdi calendário sem dia útil": ("mspdi", MSPDI.replace("<DayWorking>1</DayWorking>", "<DayWorking>0</DayWorking>")),
    "mspdi minutos por dia negativos": ("mspdi", MSPDI.replace("<StartDate>", "<MinutesPerDay>-480</MinutesPerDay><StartDate>", 1)),
    "xer só cabeçalho": ("xer", "ERMHDR\t1\n"),
    "xer em utf-16": ("xer", XER.encode("utf-16")),
    "xer %R sem %F": ("xer", XER.replace("%F\ttask_id\tproj_id", "%X\ttask_id\tproj_id")),
    "xer número ilegível": ("xer", col("TASK", "remain_drtn_hr_cnt", "abc", 3)),
    "xer data ilegível": ("xer", col("PROJECT", "plan_start_date", "32/13/2026")),
    "xer data real impossível": ("xer", col("TASK", "act_start_date", "2026-02-30 08:00", 2)),
    "xer tipo de relação vazio": ("xer", col("TASKPRED", "pred_type", "")),
    "xer tab dentro de valor": ("xer", col("TASK", "task_name", '"a\tb"', 3)),
}


@pytest.mark.parametrize("nome", sorted(ENTRADAS_RECUSADAS))
def test_entrada_ruim_e_recusada_com_erro_claro(nome):
    """Cada entrada malformada da tabela acima tem de levantar ErroImportacao (que a rota traduz em 422),
    com mensagem não vazia — nunca outra exceção."""
    formato, dados = ENTRADAS_RECUSADAS[nome]
    with pytest.raises(ErroImportacao) as e:
        (importar_xer if formato == "xer" else importar_mspdi)(dados)
    assert str(e.value)


def test_xer_tolerancias_declaradas():
    """Entradas estranhas mas aceitáveis, cada uma com o efeito esperado: BOM + cp1252 (8 atividades);
    bytes inválidos em cp1252 no fim (8); clndr_data ilegível -> padrão segunda a sexta COM aviso;
    relação para atividade inexistente -> descartada COM aviso."""
    assert len(importar_xer(XER.replace("Mobilizacao", "Mobilização").encode("cp1252"))[0]) == 8
    assert len(importar_xer(XER.encode() + b"\x81\x8d")[0]) == 8
    _, _, _, meta = importar_xer(col("CALENDAR", "clndr_data", "(((("))
    assert any("ilegível" in a for a in meta["avisos"])
    _, rels, _, meta = importar_xer(col("TASKPRED", "pred_task_id", "999"))
    assert any("descartada" in a for a in meta["avisos"])


def test_excecao_de_calendario_fora_do_horizonte_e_tolerancia_declarada():
    """Ajuste do orquestrador após a correção (rodada 5): a exceção 9999-12-01..9999-12-31 antes estourava
    OverflowError. A correção RECORTA exceções ao horizonte dos calendários (2020–2040) antes de iterar;
    esta fica inteira fora dele, então é IGNORADA com aviso e a importação é aceita — tolerância declarada,
    não erro. Também não pode demorar (antes uma exceção 0001..9998 levava ~7 s)."""
    import time
    t0 = time.perf_counter()
    _, _, _, meta = importar_mspdi(excecao("9999-12-01", "9999-12-31"))
    assert time.perf_counter() - t0 < 2.0
    assert any("fora do horizonte" in a for a in meta["avisos"]), meta["avisos"]


ENTRADAS_QUE_ESTOURAM = {
    "mspdi encoding desconhecido": ("mspdi", re.sub(r'encoding="[^"]+"', 'encoding="utf-99"', MSPDI).encode()),
    "mspdi MinutesPerDay inf": ("mspdi", MSPDI.replace("<StartDate>", "<MinutesPerDay>inf</MinutesPerDay><StartDate>", 1)),
    "mspdi UID 1e999": ("mspdi", MSPDI.replace("<UID>1</UID>", "<UID>1e999</UID>", 1)),
    "mspdi duração com 400 dígitos": ("mspdi", re.sub(r"<Duration>PT\d+H", "<Duration>PT" + "9" * 400 + "H", MSPDI, count=1)),
    "mspdi herança de 2000 calendários": ("mspdi", heranca_profunda()),
    "xer remanescente nan": ("xer", col("TASK", "remain_drtn_hr_cnt", "nan", 3)),
    "xer remanescente inf": ("xer", col("TASK", "remain_drtn_hr_cnt", "inf", 3)),
    "xer lag nan": ("xer", col("TASKPRED", "lag_hr_cnt", "nan")),
    "xer clndr_data com 3000 níveis": ("xer", col("CALENDAR", "clndr_data", "(0||a()(" * 3000)),
}


@pytest.mark.parametrize("nome", sorted(ENTRADAS_QUE_ESTOURAM))
def test_entrada_ruim_que_hoje_estoura_deveria_ser_erro_de_importacao(nome):
    """Cada entrada tem de ser recusada com ErroImportacao (422). Hoje:
    encoding 'utf-99' -> LookupError; 'inf'/'1e999'/400 dígitos -> OverflowError (int(float('inf')));
    'nan' -> ValueError cru; exceção de calendário até 9999-12-31 -> OverflowError em date + 1 dia;
    2000 calendários herdados em cadeia e clndr_data com 3000 níveis -> RecursionError."""
    formato, dados = ENTRADAS_QUE_ESTOURAM[nome]
    with pytest.raises(ErroImportacao):
        (importar_xer if formato == "xer" else importar_mspdi)(dados)


@pytest.mark.parametrize("nome", ["mspdi MinutesPerDay inf", "xer remanescente nan", "xer clndr_data com 3000 níveis"])
def test_rota_importar_nunca_responde_500(nome):
    """POST /api/cronograma/importar com o arquivo no corpo: esperado 4xx com detalhe; hoje 500."""
    from infra4d.api import criar_app
    c = TestClient(criar_app(), raise_server_exceptions=False)
    formato, dados = ENTRADAS_QUE_ESTOURAM[nome]
    corpo = dados if isinstance(dados, bytes) else dados.encode("utf-8")
    r = c.post("/api/cronograma/importar", params={"formato": formato}, content=corpo,
               headers={"Content-Type": "application/octet-stream"})
    assert 400 <= r.status_code < 500, r.status_code


@pytest.mark.parametrize("variante", ["utf-16 com entidade", "doctype depois de 4096 bytes"])
def test_doctype_e_entidade_sao_recusados_em_qualquer_codificacao(variante):
    """O módulo declara 'XML com DOCTYPE/ENTITY recusado'. Um MSPDI em UTF-16 com
    <!DOCTYPE Project [<!ENTITY a "EXPANDIDA">]> e um MSPDI UTF-8 com 5000 espaços antes do DOCTYPE
    têm de ser recusados como a variante UTF-8 simples. Os dois são aceitos."""
    if variante == "utf-16 com entidade":
        dados = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE Project [<!ENTITY a "EXPANDIDA">]>'
                 + CORPO_MSPDI.replace("<Name>", "<Name>&a;", 1)).encode("utf-16")
    else:
        dados = MSPDI.split("?>", 1)[0] + "?>" + " " * 5000 + "<!DOCTYPE Project>" + CORPO_MSPDI
    with pytest.raises(ErroImportacao):
        importar_mspdi(dados)


@pytest.mark.parametrize("coluna", ["task_id", "status_code"])
def test_xer_sem_coluna_essencial_nao_e_importado_em_silencio(coluna):
    """A fixture tem relações e atividades com progresso. Renomeando a coluna no %F da tabela TASK,
    o resultado tem de ser ErroImportacao ou trazer um aviso que cite a coluna. Hoje: importação 'limpa',
    com 0 relações (task_id) ou sem nenhuma atividade com progresso (status_code)."""
    texto = XER.replace(f"\t{coluna}\t", "\tCOLUNA_X\t", 1)
    assert texto != XER
    try:
        _, _, _, meta = importar_xer(texto)
    except ErroImportacao:
        return
    assert any(coluna in a for a in meta["avisos"])
