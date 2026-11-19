"""Adaptador MSPDI (MS Project XML): ida e volta, fixture escrita à mão e rotas.

Compatibilidade com o MS Project real NÃO é alegada: aqui se verifica a ida e
volta com o próprio exportador e uma fixture sintética escrita à mão conforme a
especificação pública do MSPDI.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from infra4d.calendario import iso
from infra4d.cenarios import Projeto, executar, montar_entrada
from infra4d.importadores import ErroImportacao, exportar_mspdi, importar_mspdi
from infra4d.importadores import rotas
from infra4d.motor import calcular

RAIZ_FIX = __import__("pathlib").Path(__file__).resolve().parents[1] / "examples" / "fixtures"
FIXTURE = RAIZ_FIX / "mspdi_minimo.xml"
NS = "{http://schemas.microsoft.com/project}"


@pytest.fixture(scope="module")
def projeto():
    return Projeto.carregar()


def _calcular_importado(dados):
    ativs, rels, cals, meta = dados
    res = calcular(ativs, rels, cals, meta["inicio_projeto"], data_status=meta["data_status"])
    return res, {a.id: a for a in ativs}, cals


def _datas(res, por_id, cals):
    """{id: (inicio exibido, termino exibido)} em ISO."""
    return {aid: (iso(r.data_inicio(cals[por_id[aid].calendario], por_id[aid])),
                  iso(r.data_termino(cals[por_id[aid].calendario], por_id[aid])))
            for aid, r in res.atividades.items()}


# ----------------------------------------------------------------- ida e volta
@pytest.mark.parametrize("cenario", ["independente", "construtora", "linha_base"])
def test_ida_e_volta_reproduz_datas_e_termino(projeto, cenario):
    resultado = executar(projeto, cenario)
    xml = exportar_mspdi(projeto, resultado)
    res, por_id, cals = _calcular_importado(importar_mspdi(xml))

    ref_a, ref_r, _ = montar_entrada(projeto, cenario)
    ds = None if cenario == "linha_base" else projeto.data_status
    ref = calcular(ref_a, ref_r, projeto.calendarios, projeto.inicio_projeto, data_status=ds)

    assert set(res.atividades) == set(ref.atividades)
    nao_iniciadas = [a.id for a in ref_a if a.status == "nao_iniciada"]
    assert nao_iniciadas, "o cenário precisa ter atividades não iniciadas para o teste valer"
    for aid in nao_iniciadas:
        assert (res.atividades[aid].es, res.atividades[aid].ef) == \
               (ref.atividades[aid].es, ref.atividades[aid].ef), aid
    # mais forte que o pedido: TODAS as atividades, inclusive em andamento e concluídas
    for aid in ref.atividades:
        assert (res.atividades[aid].es, res.atividades[aid].ef) == \
               (ref.atividades[aid].es, ref.atividades[aid].ef), aid
    assert res.termino_projeto == ref.termino_projeto
    assert iso(res.termino_projeto_data) == resultado["termino"]
    assert sorted(res.caminho_critico) == sorted(ref.caminho_critico)


def test_ida_e_volta_preserva_status_tipos_restricoes_e_relacoes(projeto):
    resultado = executar(projeto, "independente")
    ativs, rels, cals, meta = importar_mspdi(exportar_mspdi(projeto, resultado))
    ref_a, ref_r, _ = montar_entrada(projeto, "independente")
    assert {a.id: (a.duracao, a.tipo, a.status, a.inicio_real, a.termino_real, a.restricao_inicio, a.calendario)
            for a in ativs} == \
           {a.id: (a.duracao, a.tipo, a.status, a.inicio_real, a.termino_real, a.restricao_inicio, a.calendario)
            for a in ref_a}
    assert sorted((r.predecessora, r.sucessora, r.tipo, r.lag) for r in rels) == \
           sorted((r.predecessora, r.sucessora, r.tipo, r.lag) for r in ref_r)
    for cid, cal in cals.items():
        assert cal.dias_semana == projeto.calendarios[cid].dias_semana
        assert cal.nao_uteis == projeto.calendarios[cid].nao_uteis
    assert meta["data_status"] == projeto.data_status
    assert meta["inicio_projeto"] == projeto.inicio_projeto
    assert meta["avisos"] == []


def test_exportacao_codifica_tipos_de_relacao_e_lag_conforme_especificacao(projeto):
    xml = exportar_mspdi(projeto, executar(projeto, "independente"))
    raiz = ET.fromstring(xml.encode("utf-8"))
    assert raiz.tag == f"{NS}Project"
    tipos_lags = {(pl.findtext(f"{NS}Type"), pl.findtext(f"{NS}LinkLag"))
                  for pl in raiz.iter(f"{NS}PredecessorLink")}
    # base sintética tem SS+5 e FF+2: Type 3 = SS, 0 = FF; 1 dia = 8 h = 4800 décimos de minuto
    assert ("3", str(5 * 4800)) in tipos_lags
    assert ("0", str(2 * 4800)) in tipos_lags
    assert ("1", "0") in tipos_lags
    duracoes = [t.findtext(f"{NS}Duration") for t in raiz.iter(f"{NS}Task")]
    assert all(re.fullmatch(r"PT\d+H0M0S", d) for d in duracoes)
    snet = [t for t in raiz.iter(f"{NS}Task") if t.findtext(f"{NS}ConstraintType") == "4"]
    assert len(snet) == sum(1 for a in projeto.dados["atividades"] if a.get("restricao_inicio"))
    assert all(t.findtext(f"{NS}ConstraintDate") for t in snet)
    assert raiz.find(f"{NS}Calendars/{NS}Calendar/{NS}Exceptions/{NS}Exception") is not None
    notas = " ".join(t.findtext(f"{NS}Notes") or "" for t in raiz.iter(f"{NS}Task"))
    assert "produtividade=" in notas and "serviço=" in notas


# --------------------------------------------------------- fixture escrita à mão
# Calendário seg–sex, feriado 06/03/2026 (sexta). Início do projeto 02/03/2026 (segunda).
#   A 3d             : 02, 03, 04/03                        → término 04/03
#   B 5d  FS A       : 05, [06 feriado], 09, 10, 11, 12/03  → término 12/03
#   C 4d  SS B +2d   : 2 dias úteis a partir de 05 (05, 09) → início 10/03; 10..13 → término 13/03
#   D 3d  FS C       : 16, 17, 18/03                        → término 18/03
#   F 2d  FS A, SNET 11/03 : restrição vence (A termina 04) → 11, 12/03
#   G 2d  FF D       : termina junto com D (18) → 17, 18/03
#   E marco FS D, FS F → marco de término em 18/03; término do projeto 18/03/2026
#   Folga total de F: termina 12/03 e E pode esperar até o fim de 18/03 → 13, 16, 17, 18 = 4 dias úteis
ESPERADO_MSPDI = {
    "UID1": ("2026-03-02", "2026-03-04"),
    "UID2": ("2026-03-05", "2026-03-12"),
    "UID3": ("2026-03-10", "2026-03-13"),
    "UID4": ("2026-03-16", "2026-03-18"),
    "UID5": ("2026-03-11", "2026-03-12"),
    "UID6": ("2026-03-17", "2026-03-18"),
    "UID7": ("2026-03-18", "2026-03-18"),
}


def test_fixture_mspdi_escrita_a_mao_bate_com_o_calculo_manual():
    dados = importar_mspdi(FIXTURE.read_bytes())
    ativs, rels, cals, meta = dados
    assert len(ativs) == 7  # UID 0 (resumo do projeto) ignorada
    assert {(r.predecessora, r.sucessora, r.tipo, r.lag) for r in rels} == {
        ("UID1", "UID2", "FS", 0), ("UID2", "UID3", "SS", 2), ("UID3", "UID4", "FS", 0),
        ("UID1", "UID5", "FS", 0), ("UID4", "UID6", "FF", 0), ("UID4", "UID7", "FS", 0),
        ("UID5", "UID7", "FS", 0)}
    por_id = {a.id: a for a in ativs}
    assert por_id["UID7"].tipo == "marco_termino"
    assert por_id["UID5"].restricao_inicio == date(2026, 3, 11).toordinal()
    assert cals["Padrao"].dias_semana == (0, 1, 2, 3, 4)
    assert cals["Padrao"].nao_uteis == frozenset({date(2026, 3, 6)})
    assert meta["data_status"] is None
    assert meta["nomes"]["UID2"] == "B Escavacao"

    res, por_id, cals = _calcular_importado(dados)
    assert _datas(res, por_id, cals) == ESPERADO_MSPDI
    assert iso(res.termino_projeto_data) == "2026-03-18"
    assert res.atividades["UID5"].folga_total == 4
    assert set(res.caminho_critico) >= {"UID1", "UID2", "UID3", "UID4", "UID7"}
    assert "UID5" not in res.caminho_critico


def test_fixture_mspdi_sem_feriado_muda_o_resultado():
    """Detector: se o feriado não fosse lido, B terminaria um dia antes (11/03)."""
    xml = FIXTURE.read_text(encoding="utf-8")
    sem = re.sub(r"<Exceptions>.*?</Exceptions>", "", xml, flags=re.S)
    res, por_id, cals = _calcular_importado(importar_mspdi(sem))
    assert _datas(res, por_id, cals)["UID2"] == ("2026-03-05", "2026-03-11")
    assert _datas(res, por_id, cals) != ESPERADO_MSPDI


# ------------------------------------------------------------- casos de borda
_MINI = """<?xml version="1.0"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <StartDate>2026-03-02T08:00:00</StartDate><StatusDate>{status}</StatusDate><CalendarUID>2</CalendarUID>
  <Calendars>
    <Calendar><UID>1</UID><Name>Base</Name><IsBaseCalendar>1</IsBaseCalendar>
      <WeekDays>
        <WeekDay><DayType>1</DayType><DayWorking>0</DayWorking></WeekDay>
        <WeekDay><DayType>7</DayType><DayWorking>0</DayWorking></WeekDay>
        <WeekDay><DayType>0</DayType><DayWorking>0</DayWorking>
          <TimePeriod><FromDate>2026-03-04T00:00:00</FromDate><ToDate>2026-03-05T23:59:00</ToDate></TimePeriod>
        </WeekDay>
      </WeekDays>
    </Calendar>
    <Calendar><UID>2</UID><Name>Derivado</Name><IsBaseCalendar>0</IsBaseCalendar><BaseCalendarUID>1</BaseCalendarUID>
      <WeekDays><WeekDay><DayType>7</DayType><DayWorking>1</DayWorking></WeekDay></WeekDays>
    </Calendar>
  </Calendars>
  <Tasks>
    <Task><UID>1</UID><Name>Resumo</Name><Summary>1</Summary></Task>
    <Task><UID>2</UID><Name>X</Name><Duration>PT20H0M0S</Duration>
      <ActualStart>2026-03-02T08:00:00</ActualStart><RemainingDuration>PT12H0M0S</RemainingDuration>
      <ConstraintType>6</ConstraintType>
      <PredecessorLink><PredecessorUID>1</PredecessorUID><Type>1</Type></PredecessorLink></Task>
  </Tasks>
</Project>"""


def test_calendario_derivado_formato_antigo_e_avisos():
    ativs, rels, cals, meta = importar_mspdi(_MINI.format(status="2026-03-03T08:00:00"))
    assert [a.id for a in ativs] == ["UID2"]
    a = ativs[0]
    assert a.calendario == "Derivado"
    assert cals["Derivado"].dias_semana == (0, 1, 2, 3, 4, 5)  # herda seg–sex e liga o sábado
    assert cals["Derivado"].nao_uteis == frozenset({date(2026, 3, 4), date(2026, 3, 5)})  # herdadas (DayType 0)
    assert a.status == "em_andamento" and a.duracao == 2  # 12 h ÷ 8 h = 1,5 → 2 (com aviso)
    assert rels == []  # predecessora era resumo
    texto = " | ".join(meta["avisos"])
    assert "resumo" in texto and "FNET" in texto and "arredondado" in texto


def test_xml_com_doctype_e_recusado():
    with pytest.raises(ErroImportacao, match="DOCTYPE"):
        importar_mspdi('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><Project/>')


def test_xml_que_nao_e_mspdi_e_recusado():
    with pytest.raises(ErroImportacao, match="Project"):
        importar_mspdi("<Outro/>")
    with pytest.raises(ErroImportacao, match="XML inválido"):
        importar_mspdi("<Project")


# --------------------------------------------------------------------- rotas
class _EstadoFake:
    def __init__(self, projeto):
        self.projeto = projeto
        self._cache = {}

    def resultado(self, c):
        if c not in self._cache:
            self._cache[c] = executar(self.projeto, c)
        return self._cache[c]


@pytest.fixture
def cliente(projeto):
    from fastapi import HTTPException
    est = _EstadoFake(projeto)

    def obter_estado(obra=None):
        if obra not in (None, "ferrovia"):
            raise HTTPException(404, f"obra desconhecida: {obra}")
        return est

    app = FastAPI()
    rotas.ligar(app, obter_estado)
    return TestClient(app)


def test_rota_exportar_e_reimportar_pela_api(cliente, projeto):
    r = cliente.get("/api/cronograma/exportar/mspdi", params={"cenario": "independente", "obra": "ferrovia"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert "attachment" in r.headers["content-disposition"]
    r2 = cliente.post("/api/cronograma/importar", params={"obra": "ferrovia"}, content=r.content,
                      headers={"Content-Type": "text/xml"})
    assert r2.status_code == 200, r2.text
    corpo = r2.json()
    assert corpo["formato"] == "mspdi"
    assert corpo["n_atividades"] == len(projeto.dados["atividades"])
    assert corpo["n_relacoes"] == len(projeto.dados["relacoes"])
    assert corpo["termino_calculado"] == executar(projeto, "independente")["termino"]
    assert corpo["limitacoes"]


def test_rota_importar_fixture_e_erros(cliente):
    r = cliente.post("/api/cronograma/importar", content=FIXTURE.read_bytes(),
                     headers={"Content-Type": "application/xml"})
    assert r.status_code == 200, r.text
    assert r.json()["termino_calculado"] == "2026-03-18"
    assert r.json()["n_atividades"] == 7
    assert cliente.get("/api/cronograma/exportar/mspdi", params={"cenario": "x"}).status_code == 422
    assert cliente.get("/api/cronograma/exportar/mspdi", params={"obra": "nenhuma"}).status_code == 404
    assert cliente.post("/api/cronograma/importar", content=b"lixo",
                        headers={"Content-Type": "text/plain"}).status_code == 415
    assert cliente.post("/api/cronograma/importar", content=b"",
                        headers={"Content-Type": "text/plain"}).status_code == 400
    assert cliente.post("/api/cronograma/importar", content=b"--x\r\n",
                        headers={"Content-Type": "multipart/form-data; boundary=x"}).status_code == 415
    assert cliente.post("/api/cronograma/importar", content=b"<Project",
                        headers={"Content-Type": "text/xml"}).status_code == 422


def test_comparar_cronograma_da_construtora_com_o_independente(cliente, projeto):
    """Ponte de auditoria: exporta o cenário 'construtora', manda de volta como se fosse o arquivo
    da construtora e compara com o independente do motor."""
    xml = cliente.get("/api/cronograma/exportar/mspdi", params={"cenario": "construtora"}).content
    r = cliente.post("/api/cronograma/comparar", params={"obra": "ferrovia", "cenario": "independente"},
                     content=xml, headers={"Content-Type": "text/xml"})
    assert r.status_code == 200, r.text
    c = r.json()
    cons, ind = executar(projeto, "construtora"), executar(projeto, "independente")
    assert c["termino_importado"] == cons["termino"]
    assert c["termino_motor"] == ind["termino"]
    assert c["delta_termino_dias_corridos"] == \
        date.fromisoformat(ind["termino"]).toordinal() - date.fromisoformat(cons["termino"]).toordinal()
    assert c["delta_termino_dias_corridos"] > 0  # independente prevê depois (dados da demo)
    assert c["n_casadas"] == len(projeto.dados["atividades"])
    assert c["so_no_importado"] == [] and c["so_no_motor"] == []
    for linha in c["atividades"]:
        aid = linha["id"]
        assert linha["termino_importado"] == cons["atividades"][aid]["termino"], aid
        assert linha["termino_motor"] == ind["atividades"][aid]["termino"], aid
        assert linha["delta_duracao"] == ind["atividades"][aid]["duracao"] - cons["atividades"][aid]["duracao"]
        assert linha["delta_termino_dias_corridos"] == (date.fromisoformat(linha["termino_motor"]).toordinal()
                                                        - date.fromisoformat(linha["termino_importado"]).toordinal())
    assert c["n_com_diferenca"] > 0
    # ordenado pela maior diferença de término
    deltas = [abs(x["delta_termino_dias_corridos"]) for x in c["atividades"]]
    assert deltas == sorted(deltas, reverse=True)


def test_comparar_fixture_sem_ids_em_comum_e_obra_desconhecida(cliente):
    r = cliente.post("/api/cronograma/comparar", content=FIXTURE.read_bytes(), headers={"Content-Type": "text/xml"})
    assert r.status_code == 200
    assert r.json()["n_casadas"] == 0 and len(r.json()["so_no_importado"]) == 7
    assert cliente.post("/api/cronograma/comparar", params={"obra": "nenhuma"}, content=FIXTURE.read_bytes(),
                        headers={"Content-Type": "text/xml"}).status_code == 404


def test_rota_sem_ligar_responde_503():
    rotas._reserva["obter_estado"] = None
    app = FastAPI()
    app.include_router(rotas.router)
    assert TestClient(app).get("/api/cronograma/exportar/mspdi").status_code == 503


def test_ligado_no_app_real_multi_obra():
    from infra4d.api import criar_app
    c = TestClient(criar_app())
    saude = c.get("/api/saude").json()
    assert "importadores.rotas" in saude["modulos"]["ligados"], saude["modulos"]
    for obra in saude["obras"]:
        r = c.get("/api/cronograma/exportar/mspdi", params={"obra": obra})
        assert r.status_code == 200, (obra, r.text[:300])
        r2 = c.post("/api/cronograma/importar", params={"obra": obra}, content=r.content,
                    headers={"Content-Type": "text/xml"})
        assert r2.status_code == 200, (obra, r2.text[:300])
        ref = c.get("/api/cenarios/independente", params={"obra": obra})
        assert ref.status_code == 200, ref.text[:300]
        assert r2.json()["termino_calculado"] == ref.json()["termino"], obra
    assert c.get("/api/cronograma/exportar/mspdi", params={"obra": "inexistente"}).status_code == 404


# ------------------------------------------- robustez (rodada 5 da revisão adversarial)
def _com_excecao(de, ate, n=1):
    bloco = "".join(f"<Exception><TimePeriod><FromDate>{de}T00:00:00</FromDate><ToDate>{ate}T23:59:00</ToDate>"
                    f"</TimePeriod><Type>1</Type><DayWorking>0</DayWorking></Exception>" for _ in range(n))
    return FIXTURE.read_text(encoding="utf-8").replace("<Exceptions>", "<Exceptions>" + bloco, 1)


def test_excecao_gigante_e_recortada_ao_horizonte_sem_travar(limite):
    import time
    t0 = time.perf_counter()
    from infra4d.calendario import ErroCalendario
    dados = importar_mspdi(_com_excecao("0001-01-01", "9998-12-31", n=5))
    cals = dados[2]
    assert any("recortada" in a for a in dados[3]["avisos"])
    assert len(cals["Padrao"].nao_uteis) > 7000  # o horizonte inteiro virou não útil...
    with pytest.raises(ErroCalendario):  # ...e a rede não cabe mais: o motor recusa (a rota dá 422), não trava
        _calcular_importado(dados)
    dt = time.perf_counter() - t0
    assert dt < limite("tempo_maximo_recalculo_s"), f"{dt:.2f} s"


@pytest.mark.parametrize("trecho,valor", [("<MinutesPerDay>inf</MinutesPerDay>", None),
                                          ("<MinutesPerDay>nan</MinutesPerDay>", None),
                                          ("<MinutesPerDay>" + "9" * 5000 + "</MinutesPerDay>", None)])
def test_numeros_nao_finitos_ou_enormes_viram_erro_de_importacao(trecho, valor):
    xml = FIXTURE.read_text(encoding="utf-8").replace("<StartDate>", trecho + "<StartDate>", 1)
    with pytest.raises(ErroImportacao):
        importar_mspdi(xml)


def test_duracao_absurda_e_recusada():
    xml = FIXTURE.read_text(encoding="utf-8").replace("<Duration>PT24H0M0S", "<Duration>PT" + "9" * 400 + "H0M0S", 1)
    with pytest.raises(ErroImportacao, match="limite|finito"):
        importar_mspdi(xml)


def test_heranca_de_calendario_profunda_e_recusada_e_rasa_aceita():
    def cadeia(n):
        cals = "".join(f"<Calendar><UID>{i}</UID><Name>C{i}</Name><BaseCalendarUID>{i + 1 if i < 100 + n - 1 else 1}"
                       f"</BaseCalendarUID></Calendar>" for i in range(100, 100 + n))
        xml = FIXTURE.read_text(encoding="utf-8").replace("<Calendars>", "<Calendars>" + cals, 1)
        return xml.replace("<CalendarUID>1</CalendarUID>", "<CalendarUID>100</CalendarUID>")
    _, _, cals, _ = importar_mspdi(cadeia(10))  # 10 níveis herdando do Padrao (feriado incluso)
    assert cals["C100"].nao_uteis == frozenset({date(2026, 3, 6)})
    with pytest.raises(ErroImportacao, match="níveis"):
        importar_mspdi(cadeia(80))


@pytest.mark.parametrize("variante", ["utf16", "tarde", "entidade_interna"])
def test_dtd_recusada_em_qualquer_codificacao_e_posicao(variante):
    xml = FIXTURE.read_text(encoding="utf-8")
    corpo = xml.split("?>", 1)[1]
    if variante == "utf16":
        dados = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE Project [<!ENTITY a "X">]>' + corpo).encode("utf-16")
    elif variante == "tarde":
        dados = xml.split("?>", 1)[0] + "?>" + " " * 6000 + "<!DOCTYPE Project>" + corpo
    else:
        dados = xml.split("?>", 1)[0] + '?><!DOCTYPE Project [<!ENTITY a "X">]>' + corpo
    with pytest.raises(ErroImportacao, match="DOCTYPE"):
        importar_mspdi(dados)


def test_xml_em_utf16_sem_dtd_continua_aceito():
    xml = FIXTURE.read_text(encoding="utf-8").replace('encoding="UTF-8"', 'encoding="UTF-16"', 1)
    assert len(importar_mspdi(xml.encode("utf-16"))[0]) == 7
    assert len(importar_mspdi(xml)[0]) == 7  # str com declaração UTF-16 também


def test_encoding_desconhecido_e_erro_de_importacao():
    xml = FIXTURE.read_text(encoding="utf-8").replace('encoding="UTF-8"', 'encoding="utf-99"', 1)
    with pytest.raises(ErroImportacao):
        importar_mspdi(xml.encode("utf-8"))


def test_reexportar_logica_retida_esta_declarado():
    from infra4d.importadores import LIMITACOES_MSPDI
    assert any("lógica retida" in x for x in LIMITACOES_MSPDI)
