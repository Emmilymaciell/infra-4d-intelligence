"""Interoperabilidade IFC 4.3 (protótipo R07): exportar → reabrir → vínculo → validação → malha → API.

Sem critério numérico de aceite: as contagens esperadas são derivadas da própria base sintética
(regra de peças do visualizador, reescrita aqui de forma independente do exportador) e a
validação exige ZERO erros de esquema e de regras EXPRESS. Se ``ifcopenshell`` não estiver
instalado no .venv, o módulo inteiro é pulado (e isso aparece como SKIP, não como verde).
"""

import json
import struct

import pytest

ifcopenshell = pytest.importorskip("ifcopenshell")
import ifcopenshell.api.project  # noqa: E402
import ifcopenshell.api.pset  # noqa: E402
import ifcopenshell.api.root  # noqa: E402
import ifcopenshell.api.sequence  # noqa: E402
import ifcopenshell.util.element  # noqa: E402
import ifcopenshell.validate  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from infra4d.cenarios import Projeto  # noqa: E402
from infra4d.ifc import PSET_VINCULO, SCHEMA  # noqa: E402
from infra4d.ifc import exportar as exp  # noqa: E402
from infra4d.ifc import importar as imp  # noqa: E402
from infra4d.ifc import rotas  # noqa: E402

from infra4d.cenarios import DATASET_PADRAO  # noqa: E402

OBRAS = ("ferrovia", "rodovia")
# Expectativa ESCRITA À MÃO (não importada do exportador): serviço → (classe IFC, PredefinedType)
ESPERADO = {
    "ferrovia": {"SUP": ("IfcEarthworksCut", "TOPSOILREMOVAL"), "TER": ("IfcEarthworksFill", "EMBANKMENT"),
                 "DRE": ("IfcPipeSegment", "CULVERT"), "SUB": ("IfcCourse", "USERDEFINED"),
                 "LAS": ("IfcCourse", "BALLASTBED"), "DOR": ("IfcTrackElement", "SLEEPER"),
                 "GRA": ("IfcRail", "RAIL"), "SOL": ("IfcFastener", "WELD")},
    "rodovia": {"SUP": ("IfcEarthworksCut", "TOPSOILREMOVAL"), "TER": ("IfcEarthworksFill", "EMBANKMENT"),
                "DRE": ("IfcPipeSegment", "CULVERT"), "SBB": ("IfcCourse", "PAVEMENT"),
                "BGS": ("IfcCourse", "PAVEMENT"), "IMP": ("IfcCourse", "USERDEFINED"),
                "CBU": ("IfcPavement", "FLEXIBLE"), "SHV": ("IfcSurfaceFeature", "LINEMARKING"),
                "SVV": ("IfcSign", "PICTORAL"), "DEF": ("IfcRailing", "GUARDRAIL")},
}
OAE_ESPERADO = {"OAE-FUN": ("IfcPile", "NOTDEFINED"), "OAE-MES": ("IfcColumn", "PIERSTEM"),
                "OAE-SUE": ("IfcBeam", "GIRDER_SEGMENT")}
INSTALACAO = {"ferrovia": ("IfcRailway", "IfcRailwayPart"), "rodovia": ("IfcRoad", "IfcRoadPart")}


@pytest.fixture(scope="module", params=OBRAS)
def obra(request):
    return request.param


@pytest.fixture(scope="module")
def projeto(obra):
    return Projeto.carregar(DATASET_PADRAO.parent / f"{obra}_ficticia.json")


@pytest.fixture(scope="module")
def dados(projeto):
    return projeto.dados


@pytest.fixture(scope="module")
def esperados(dados, obra):
    """{elemento_id: atividade} pela regra do web/viewer3d.js, escrita sem usar exportar.pecas."""
    oaes = {o["id"]: o for o in dados["oaes"]}
    out = {}
    for a in dados["atividades"]:
        if a.get("tipo") != "tarefa" or a.get("km_ini") is None:
            continue
        if a.get("oae_id"):
            vaos = oaes[a["oae_id"]]["vaos"]
            n = vaos if a["servico_id"] == "OAE-SUE" else vaos + 1
        elif a.get("servico_id") in ESPERADO[obra]:
            n = max(1, int(abs(a["km_fim"] - a["km_ini"]) + 0.5))  # Math.round do JS
        else:
            continue
        for i in range(n):
            out[f"{a['id']}-E{i + 1:02d}"] = a
    return out


@pytest.fixture(scope="module")
def arquivo_ifc(dados, tmp_path_factory):
    caminho = tmp_path_factory.mktemp("ifc") / "obra.ifc"
    resumo = exp.exportar(dados, caminho)
    return caminho, resumo


@pytest.fixture(scope="module")
def modelo(arquivo_ifc):
    return ifcopenshell.open(str(arquivo_ifc[0]))


def _elementos(f):
    return [e for e in f.by_type("IfcElement") if ifcopenshell.util.element.get_pset(e, PSET_VINCULO)]


# --------------------------------------------------------------------------- exportação

def test_reabre_como_ifc4x3(modelo, obra):
    assert modelo.schema_identifier == SCHEMA == "IFC4X3_ADD2"
    assert len(modelo.by_type("IfcProject")) == 1
    assert len(modelo.by_type(INSTALACAO[obra][0])) == 1
    assert len(modelo.by_type("IfcAlignmentHorizontal")) == 1
    assert len(modelo.by_type("IfcAlignmentHorizontalSegment")) > 0


def test_estrutura_espacial(modelo, dados, obra):
    partes = modelo.by_type(INSTALACAO[obra][1])
    assert len(partes) == len(dados["lotes"])
    assert all(p.UsageType == "LONGITUDINAL" for p in partes)
    pontes = modelo.by_type("IfcBridge")
    assert {p.Description.split(" ")[0] for p in pontes} == {o["id"] for o in dados["oaes"]}
    # ferrovia agregada ao sítio, sítio ao projeto
    fer = modelo.by_type(INSTALACAO[obra][0])[0]
    assert ifcopenshell.util.element.get_aggregate(fer).is_a("IfcSite")


def test_contagem_de_elementos_igual_as_pecas_esperadas(modelo, esperados, arquivo_ifc):
    els = _elementos(modelo)
    assert len(els) == len(esperados) == arquivo_ifc[1]["elementos"]
    ids = [ifcopenshell.util.element.get_pset(e, PSET_VINCULO)["ElementoId"] for e in els]
    assert len(set(ids)) == len(ids)
    assert set(ids) == set(esperados)
    assert len({e.GlobalId for e in els}) == len(els)


def test_classe_ifc_por_servico(modelo, obra):
    esperado = {**ESPERADO[obra], **OAE_ESPERADO}
    vistos = set()
    for e in _elementos(modelo):
        sid = ifcopenshell.util.element.get_pset(e, PSET_VINCULO)["ServicoId"]
        assert (e.is_a(), e.PredefinedType) == esperado[sid], (sid, e)
        vistos.add(sid)
    assert vistos == set(esperado)  # todo serviço com peça apareceu


def test_globalids_deterministicos(dados, modelo):
    """Exportar de novo dá os MESMOS GlobalIds (GLB e vínculo de chamadas diferentes casam)."""
    f2, _ = exp.construir(dados, incluir_4d=False)
    g1 = {e.Name: e.GlobalId for e in _elementos(modelo)}
    g2 = {e.Name: e.GlobalId for e in _elementos(f2)}
    assert g1 == g2


def test_todo_elemento_tem_pset_com_atividade_existente(modelo, dados, esperados):
    atividades = {a["id"]: a for a in dados["atividades"]}
    for e in _elementos(modelo):
        ps = ifcopenshell.util.element.get_pset(e, PSET_VINCULO)
        a = atividades.get(ps["AtividadeId"])
        assert a is not None, ps
        assert esperados[ps["ElementoId"]]["id"] == a["id"]
        assert ps["ServicoId"] == a["servico_id"]
        assert ps["LoteId"] == a["lote_id"]
        assert a["km_ini"] - 0.01 <= ps["KmInicial"] < ps["KmFinal"] <= a["km_fim"] + 0.01
        assert e.Representation is not None


def test_cronograma_4d_nativo_integrado_ao_exportador(modelo, dados, projeto):
    """O exportador grava o cronograma nativo por cenário (detalhes e ida e volta: test_ifc_cronograma.py)."""
    from infra4d.cenarios import executar
    crons = {c.Identification: c for c in modelo.by_type("IfcWorkSchedule")}
    assert set(crons) == {"linha_base", "construtora", "independente"}
    n = len(dados["atividades"])
    assert len(modelo.by_type("IfcTask")) == 3 * n
    assert len(modelo.by_type("IfcRelSequence")) == 3 * len(dados["relacoes"])
    lb = {t.Identification: t.TaskTime for rel in crons["linha_base"].Controls for t in rel.RelatedObjects}
    api = executar(projeto, "linha_base")["atividades"]
    assert {aid: (tt.ScheduleStart[:10], tt.ScheduleFinish[:10]) for aid, tt in lb.items()} == \
           {aid: (x["inicio"], x["termino"]) for aid, x in api.items()}
    for e in _elementos(modelo):  # um IfcRelAssignsToProduct por peça, com a tarefa nos 3 cenários
        ps = ifcopenshell.util.element.get_pset(e, PSET_VINCULO)
        rels = [r for r in e.ReferencedBy if r.is_a("IfcRelAssignsToProduct")]
        assert len(rels) == 1 and [t.Identification for t in rels[0].RelatedObjects] == [ps["AtividadeId"]] * 3


def test_globalids_das_tarefas_estaveis(dados, modelo):
    f2, _ = exp.construir(dados, posicionamento="local")
    g1 = {(t.Identification, t.GlobalId) for t in modelo.by_type("IfcTask")}
    g2 = {(t.Identification, t.GlobalId) for t in f2.by_type("IfcTask")}
    assert g1 == g2 and len({g for _, g in g1}) == len(g1)


# --------------------------------------------------------------------------- validação

def test_validacao_ifcopenshell_sem_erros(modelo, obra):
    """Ferrovia: esquema + regras EXPRESS. Rodovia: só esquema (decisão do orquestrador na etapa 5: com
    3 cronogramas a validação EXPRESS leva ~26 s por obra)."""
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(modelo, log, express_rules=(obra == "ferrovia"))
    assert log.statements == [], [str(s)[:300] for s in log.statements[:5]]


def test_validacao_detecta_erro_real(modelo, tmp_path):
    """Controle negativo: o detector acusa o defeito que de fato apareceu no 1º protótipo."""
    f = ifcopenshell.file.from_string(modelo.to_string())
    f.by_type("IfcBridgePart")[0].UsageType = None
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log)
    assert any("UsageType" in str(s.get("attribute", "")) for s in log.statements)


# --------------------------------------------------------------------------- importação

def test_ida_e_volta_da_tabela_de_vinculo(arquivo_ifc, dados, esperados):
    r = imp.ler(arquivo_ifc[0], dados)
    linhas = r["vinculos"]
    assert {l["elemento_id"]: l["atividade_id"] for l in linhas} == {k: a["id"] for k, a in esperados.items()}
    assert all(l["fonte"] == "pset" and l["conflito"] is None for l in linhas)
    assert r["resumo"]["com_vinculo"] == len(esperados) and r["resumo"]["sem_vinculo"] == 0
    v = r["verificacao"]
    assert v["elementos_casados"] == len(esperados)
    assert v["elementos_sem_atividade"] == []
    assert v["elemento_id_fora_da_convencao"] == []
    assert v["obra_confere"] is True and v["divergencias"] == []
    tarefas = {a["id"] for a in dados["atividades"] if a.get("tipo") == "tarefa"}
    assert set(v["atividades_sem_elemento"]) == tarefas - {a["id"] for a in esperados.values()}


def test_vinculo_so_por_relacao_de_produto(modelo, esperados):
    """Sem o Pset, o vínculo sai do 4D nativo (IfcRelAssignsToProduct)."""
    f = ifcopenshell.file.from_string(modelo.to_string())
    for e in f.by_type("IfcElement"):
        for rel in list(e.IsDefinedBy or ()):
            if rel.is_a("IfcRelDefinesByProperties") and rel.RelatingPropertyDefinition.Name == PSET_VINCULO:
                ifcopenshell.api.pset.remove_pset(f, product=e, pset=rel.RelatingPropertyDefinition)
    linhas = imp.tabela_vinculo(f)
    assert len(linhas) == len(esperados)
    assert all(l["fonte"] == "produto" for l in linhas)
    por_nome = {l["nome"]: l["atividade_id"] for l in linhas}  # Name = ElementoId no exportador
    assert por_nome == {k: a["id"] for k, a in esperados.items()}


def _ifc_minimo():
    f = ifcopenshell.api.project.create_file(version=SCHEMA)
    ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="mini")
    cron = ifcopenshell.api.sequence.add_work_schedule(f, name="c")
    return f, cron


def test_vinculo_por_relacao_de_processo_e_conflito():
    f, cron = _ifc_minimo()
    t1 = ifcopenshell.api.sequence.add_task(f, work_schedule=cron, name="x", identification="L1-S01-TER")
    t2 = ifcopenshell.api.sequence.add_task(f, work_schedule=cron, name="y", identification="L1-S01-SUB")
    e1 = ifcopenshell.api.root.create_entity(f, ifc_class="IfcEarthworksFill", name="aterro qualquer")
    e2 = ifcopenshell.api.root.create_entity(f, ifc_class="IfcCourse", name="camada")
    e3 = ifcopenshell.api.root.create_entity(f, ifc_class="IfcWall", name="sem vinculo")
    ifcopenshell.api.sequence.assign_process(f, relating_process=t1, related_object=e1)
    ps = ifcopenshell.api.pset.add_pset(f, product=e2, name=PSET_VINCULO)
    ifcopenshell.api.pset.edit_pset(f, pset=ps, properties={"AtividadeId": "L1-S01-SUB", "ElementoId": "L1-S01-SUB-E01"})
    ifcopenshell.api.sequence.assign_process(f, relating_process=t1, related_object=e2)  # discorda do Pset
    linhas = {l["nome"]: l for l in imp.tabela_vinculo(f)}
    assert linhas["aterro qualquer"]["atividade_id"] == "L1-S01-TER"
    assert linhas["aterro qualquer"]["fonte"] == "processo"
    assert linhas["camada"]["atividade_id"] == "L1-S01-SUB" and linhas["camada"]["fonte"] == "pset"
    assert linhas["camada"]["conflito"] == ["L1-S01-TER"]
    assert linhas["sem vinculo"]["atividade_id"] is None
    assert t2  # tarefa sem elemento: não deve quebrar a leitura


def test_bytes_que_nao_sao_ifc_sao_recusados():
    with pytest.raises(ValueError):
        imp.abrir(b"isto nao e um IFC")


# --------------------------------------------------------------------------- malha

def test_malha_json(modelo, esperados):
    m = imp.malha_json(modelo)
    assert len(m["elementos"]) == len(esperados)
    for el in m["elementos"]:
        nv = len(el["vertices"]) // 3
        assert nv > 0 and len(el["faces"]) % 3 == 0 and max(el["faces"]) < nv
        assert min(el["vertices"]) >= 0  # relativo à origem = canto mínimo
    assert {el["elemento_id"] for el in m["elementos"]} == set(esperados)
    json.dumps(m)  # serializável


def test_glb_nativo(modelo, tmp_path, esperados):
    r = imp.exportar_glb(modelo, tmp_path / "m.glb")
    assert r["elementos"] == len(esperados)
    b = (tmp_path / "m.glb").read_bytes()
    magic, versao, total = struct.unpack("<4sII", b[:12])
    assert magic == b"glTF" and versao == 2 and total == len(b)
    tam, tipo = struct.unpack("<I4s", b[12:20])
    gltf = json.loads(b[20:20 + tam])
    assert tipo == b"JSON" and gltf["meshes"]
    nomes = {n.get("name") for n in gltf.get("nodes", [])}
    gid = _elementos(modelo)[0].GlobalId
    assert any(gid in (n or "") for n in nomes), list(nomes)[:5]


# --------------------------------------------------------------------------- router

@pytest.fixture(scope="module")
def cliente(projeto):
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[rotas.obter_projeto] = lambda: projeto
    return TestClient(app)


def test_router_exportar_e_vinculos(cliente, esperados, dados):
    r = cliente.get("/api/ifc/exportar")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"] and ".ifc" in r.headers["content-disposition"]
    assert r.content.startswith(b"ISO-10303-21")
    r2 = cliente.post("/api/ifc/vinculos", content=r.content, headers={"Content-Type": "application/octet-stream"})
    assert r2.status_code == 200, r2.text
    corpo = r2.json()
    assert corpo["resumo"]["schema"] == "IFC4X3_ADD2"
    assert corpo["verificacao"]["elementos_casados"] == len(esperados)
    # acentos sobrevivem à ida e volta HTTP (STEP codifica como \X2\)
    nomes = {l["nome"] for l in corpo["vinculos"]}
    assert nomes == set(esperados)
    f = imp.abrir(r.content)
    assert f.by_type("IfcProject")[0].LongName == dados["ferrovia"]["nome"]
    assert {l["nome"] for l in corpo["vinculos"]} == set(esperados)


def test_router_erros(cliente):
    assert cliente.post("/api/ifc/vinculos", content=b"").status_code == 400
    assert cliente.post("/api/ifc/vinculos", content=b"nada a ver").status_code == 422


def test_tipo_de_obra_sem_mapeamento_e_recusado_com_motivo(dados):
    """Tipo de obra sem mapeamento IFC: recusa explícita, nunca uma instalação errada."""
    outro = json.loads(json.dumps(dados))
    outro["meta"]["tipo_obra"] = "hidrovia"
    with pytest.raises(exp.ErroExportacao):
        exp.construir(outro)
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[rotas.obter_projeto] = lambda: Projeto(outro)
    c = TestClient(app)
    for rota in ("/api/ifc/exportar", "/api/ifc/glb", "/api/ifc/vinculo"):
        r = c.get(rota)
        assert r.status_code == 422 and "hidrovia" in r.json()["detail"], rota


def _nos_glb(conteudo: bytes) -> list[dict]:
    magic, versao, total = struct.unpack("<4sII", conteudo[:12])
    assert magic == b"glTF" and versao == 2 and total == len(conteudo)
    tam, tipo = struct.unpack("<I4s", conteudo[12:20])
    assert tipo == b"JSON"
    return json.loads(conteudo[20:20 + tam])["nodes"]


def test_router_glb_e_vinculo_casam(cliente, esperados, obra):
    """GLB (node.name = GlobalId) e tabela de vínculo da mesma obra casam 1:1 — contrato do frontend."""
    rg = cliente.get("/api/ifc/glb")
    assert rg.status_code == 200 and rg.headers["content-type"] == "model/gltf-binary"
    nos = {n["name"] for n in _nos_glb(rg.content) if "mesh" in n}
    rv = cliente.get("/api/ifc/vinculo")
    assert rv.status_code == 200
    v = rv.json()
    assert v["tipo_obra"] == obra and v["sistema"]["glb_y_up"] is True
    gids = {e["global_id"] for e in v["elementos"]}
    assert nos == gids and len(gids) == len(esperados)
    assert {e["elemento_id"]: e["atividade_id"] for e in v["elementos"]} == {k: a["id"] for k, a in esperados.items()}
    assert v["alinhamentos"]["quantidade"] == 1 and v["alinhamentos"]["itens"][0]["estaca_inicial"] == 0.0
    # o .ifc baixado pela outra rota tem os MESMOS GlobalIds
    f = imp.abrir(cliente.get("/api/ifc/exportar").content)
    assert {e.GlobalId for e in _elementos(f)} == gids


# --------------------------------------------------------------------------- integração com api.py

@pytest.fixture(scope="module")
def cliente_api():
    from infra4d.api import criar_app
    return TestClient(criar_app())


def test_api_real_liga_o_modulo_ifc(cliente_api):
    app = cliente_api.app
    assert "ifc.rotas" in app.state.rotas_ligadas, app.state.rotas_indisponiveis.get("ifc.rotas")
    saude = cliente_api.get("/api/saude").json()
    assert "ifc.rotas" in saude["modulos"]["ligados"]
    assert "ifc.rotas" not in saude["modulos"]["indisponiveis"]


def test_api_real_por_obra(cliente_api, esperados, obra, dados):
    r = cliente_api.get("/api/ifc/exportar", params={"obra": obra})
    assert r.status_code == 200 and r.content.startswith(b"ISO-10303-21")
    f = imp.abrir(r.content)
    assert len(f.by_type(INSTALACAO[obra][0])) == 1
    r2 = cliente_api.post("/api/ifc/vinculos", params={"obra": obra}, content=r.content,
                          headers={"Content-Type": "application/octet-stream"})
    assert r2.status_code == 200
    v = r2.json()["verificacao"]
    assert v["elementos_casados"] == len(esperados) and v["obra_confere"] is True and v["divergencias"] == []
    rv = cliente_api.get("/api/ifc/vinculo", params={"obra": obra})
    assert rv.status_code == 200 and rv.json()["obra"] == dados["ferrovia"]["id"]
    assert cliente_api.get("/api/ifc/glb", params={"obra": obra}).content[:4] == b"glTF"
    # obra desconhecida: 404 vindo do obter_estado do orquestrador, em todas as rotas
    for rota in ("/api/ifc/exportar", "/api/ifc/glb", "/api/ifc/vinculo"):
        assert cliente_api.get(rota, params={"obra": "nao-existe"}).status_code == 404
    # IFC desta obra conferido contra a OUTRA: ids de atividade se repetem entre obras, então o
    # casamento por id sozinho engana (achado do teste); a verificação tem de denunciar a troca
    outra = next(o for o in OBRAS if o != obra)
    r4 = cliente_api.post("/api/ifc/vinculos", params={"obra": outra}, content=r.content)
    assert r4.status_code == 200
    v4 = r4.json()["verificacao"]
    assert v4["obra_confere"] is False and v4["projeto_ifc"] == dados["ferrovia"]["id"]


def test_ligar_guarda_obter_estado_por_app(projeto):
    """Dois apps no mesmo processo não compartilham o obter_estado."""
    chamadas = []

    class _Est:
        def __init__(self, p):
            self.projeto = p

    def obter_estado(obra=None):
        chamadas.append(obra)
        return _Est(projeto)

    app = FastAPI()
    rotas.ligar(app, obter_estado)
    outro = FastAPI()
    outro.include_router(rotas.router)  # sem ligar: cai na base padrão
    corpo = TestClient(outro).get("/api/ifc/exportar", params={"incluir_4d": False}).content
    assert chamadas == []
    assert TestClient(app).post("/api/ifc/vinculos", params={"obra": "x"}, content=corpo).status_code == 200
    assert chamadas == ["x"]


def test_sem_ifcopenshell_o_modulo_de_rotas_levanta_importerror():
    import subprocess
    import sys
    from pathlib import Path
    codigo = ("import sys; sys.modules['ifcopenshell'] = None\n"
              "try:\n    import infra4d.ifc.rotas\nexcept ImportError:\n    sys.exit(0)\nsys.exit(1)\n")
    raiz = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-c", codigo], cwd=raiz / "scripts", capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr


def test_divergencia_de_servico_e_km_e_denunciada(arquivo_ifc, dados):
    linhas = imp.tabela_vinculo(imp.abrir(arquivo_ifc[0]))
    linhas[0] = dict(linhas[0], servico_id="XXX")
    linhas[1] = dict(linhas[1], km_ini=999.0, km_fim=1000.0)
    v = imp.verificar(linhas, dados)
    assert {d["global_id"] for d in v["divergencias"]} == {linhas[0]["global_id"], linhas[1]["global_id"]}


# --------------------------------------------------------------------------- E4 (R05): IFC oficial de terceiros
#
# OPCIONAL: baixa para output/ifc/externos/ (ignorado pelo Git; NUNCA versionar). Sem rede → SKIP.
# INFRA4D_SEM_REDE=1 força o SKIP. Se o arquivo do upstream mudar (SHA-256 diferente do registrado
# no R07), SKIP com o motivo: as conclusões do R07 valem para o arquivo com aquele hash.
# Licenças: Certification-datasets = CC BY 4.0; IFC4.x-specification-models = "all rights reserved
# until formal release" (só baixar e testar, sem redistribuir).

_CERT = ("https://raw.githubusercontent.com/buildingSMART/Certification-datasets/main/"
         "IFC%204.3.2.0%20(IFC%204.3%20ADD2)/Simple-Scene/")
_SPEC = "https://raw.githubusercontent.com/buildingSMART/IFC4.x-specification-models/main/models/"
EXTERNOS = {
    "Infra-Rail.ifc": (_CERT + "Infra-Rail.ifc",
                       "c9073051e17796b8b59f96cf268207f4011c08eedeaa791774480c33e9defbb3"),
    "Infra-Road.ifc": (_CERT + "Infra-Road.ifc",
                       "a3cb29433d7176bd31ff7535a596b5d7cd4eb7f2fb0eb6eee451612063c1f167"),
    "segmented-reference-curve.ifc": (
        _SPEC + "alignment-geometries-and-linear-positioning/segmented-reference-curve/segmented-reference-curve.ifc",
        "d4320f2fcc7e9c385f89c56c3002a54127f8d9fb4c5a5a447bd7238806b1eadf"),
    "linear-placement-of-signal.ifc": (
        _SPEC + "alignment-geometries-and-linear-positioning/linear-placement-of-signal/linear-placement-of-signal.ifc",
        "3c6b97f7a82f1a1d114233702e876f387a03701be0d8a621685e5773ce664c97"),
    "construction-scheduling-task.ifc": (
        _SPEC + "construction-scheduling/construction-scheduling-task/construction-scheduling-task.ifc",
        "abbb30934dd36ea1370d7464300cd5a33c85ebd438ab10ed2fd258823514fb7d"),
}


def _externo(nome: str):
    import hashlib
    import os
    import urllib.request
    from pathlib import Path
    url, sha = EXTERNOS[nome]
    pasta = Path(__file__).resolve().parents[1] / "output" / "ifc" / "externos"
    caminho = pasta / nome
    h = lambda: hashlib.sha256(caminho.read_bytes()).hexdigest()  # noqa: E731
    if not (caminho.exists() and h() == sha):
        if os.environ.get("INFRA4D_SEM_REDE") == "1":
            pytest.skip("INFRA4D_SEM_REDE=1")
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                caminho.write_bytes(resp.read())
        except OSError as e:
            pytest.skip(f"sem rede para baixar {nome}: {e}")
        if h() != sha:
            pytest.skip(f"{nome} mudou no upstream (sha256 {h()}); atualizar R07 antes de reconfirmar")
    return caminho


@pytest.fixture(scope="module", params=sorted(EXTERNOS))
def externo(request):
    caminho = _externo(request.param)
    return request.param, imp.abrir(caminho)


def test_externo_valida_sem_erro(externo):
    nome, f = externo
    assert f.schema_identifier == "IFC4X3_ADD2"
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    assert log.statements == [], (nome, [str(s)[:200] for s in log.statements[:3]])


def test_externo_alinhamento_declarado_ou_ausente(externo):
    """Nos Infra-* não há eixo: "sem alinhamento" explícito. Nos spec models, só o que o arquivo declara."""
    nome, f = externo
    al = imp.alinhamentos(f)
    if nome.startswith("Infra-") or nome.startswith("construction-"):
        assert al == {"quantidade": 0, "mensagem": imp.SEM_ALINHAMENTO, "itens": []}
        return
    assert al["quantidade"] == 1 and al["mensagem"] is None
    item = al["itens"][0]
    assert item["horizontal"] and item["vertical"] and item["superelevacao"]
    if nome == "segmented-reference-curve.ifc":
        # o arquivo tem referente "Start Station" SEM valor de estaca: não se inventa estaca
        assert item["estaca_inicial"] is None and item["estaca_final"] is None
        assert item["comprimento_horizontal"] > 0
    else:
        # estaca final calculada (inicial + soma dos segmentos) = referente "End" declarado no arquivo
        fim = {r["nome"]: r["estaca"] for r in item["referentes"]}["End"]
        assert item["estaca_final"] == pytest.approx(fim, abs=1e-3)


def test_externo_ficha_e_vinculo(externo):
    nome, f = externo
    linhas = imp.tabela_vinculo(f)
    if nome.startswith("Infra-"):
        assert f.by_type("IfcMapConversion")  # georreferenciados (R05)
        assert f.by_type("IfcRailway" if "Rail" in nome else "IfcRoad")
        assert linhas and all(l["atividade_id"] is None for l in linhas)  # sem 4D: nada a vincular
    elif nome.startswith("construction-"):
        # 4D de terceiro: vínculo sai de IfcRelAssignsToProduct, sem o nosso Pset
        assert linhas and all(l["fonte"] == "produto" and l["atividade_id"] for l in linhas)


# --------------------------------------------------------------------------- quantidades (BIM → 4D/5D)

import ifcopenshell.geom  # noqa: E402
import ifcopenshell.util.classification  # noqa: E402
import ifcopenshell.util.pset  # noqa: E402
import ifcopenshell.util.shape  # noqa: E402

from infra4d import orcamento  # noqa: E402
from infra4d.ifc import quantidades as qtd  # noqa: E402
from infra4d.ifc import requisitos as req  # noqa: E402

_TIPO_TEMPLATE = {"Q_LENGTH": "IfcQuantityLength", "Q_AREA": "IfcQuantityArea", "Q_VOLUME": "IfcQuantityVolume",
                  "Q_WEIGHT": "IfcQuantityWeight", "Q_COUNT": "IfcQuantityCount"}


def test_qto_usa_nomes_oficiais_do_template_ifc4x3(modelo):
    """Todo Qto_* gravado existe no template oficial da classe, com o mesmo nome e tipo de quantidade."""
    tpl = ifcopenshell.util.pset.get_template("IFC4X3")
    vistos = set()
    for e in _elementos(modelo):
        for nome, qs in req.quantidades_do_elemento(e).items():
            if not nome.startswith("Qto_"):
                continue
            oficiais = {q.Name: q for q in tpl.get_applicable(e.is_a(), qto_only=True, schema="IFC4X3")}
            assert nome in oficiais, (e.is_a(), nome)
            campos = {p.Name: _TIPO_TEMPLATE[p.TemplateType] for p in oficiais[nome].HasPropertyTemplates}
            for qn, q in qs.items():
                assert qn in campos and q.is_a(campos[qn]), (e.is_a(), nome, qn, q.is_a())
            vistos.add((e.is_a(), nome))
    assert vistos  # houve Qto oficial


def _obra_minima(servico: str, unidade: str, quantidade: float) -> dict:
    """Uma atividade de 1 km num eixo reto (0,0,0)→(1000,0,0): volume da peça conhecido à mão."""
    return {
        "meta": {"aviso": "DADOS FICTÍCIOS de teste", "tipo_obra": "ferrovia"},
        "ferrovia": {"id": "TESTE", "nome": "Obra mínima de teste"},
        "lotes": [{"id": "L1", "nome": "Lote 1", "km_ini": 0.0, "km_fim": 1.0}],
        "segmentos": [{"id": "L1-S01", "lote_id": "L1", "km_ini": 0.0, "km_fim": 1.0}],
        "servicos": [{"id": servico, "unidade": unidade}],
        "oaes": [], "relacoes": [],
        "atividades": [{"id": f"L1-S01-{servico}", "nome": "peça de teste", "tipo": "tarefa", "lote_id": "L1",
                        "segmento_id": "L1-S01", "servico_id": servico, "km_ini": 0.0, "km_fim": 1.0,
                        "unidade": unidade, "quantidade_total": quantidade,
                        "inicio_lb": "2026-01-05", "termino_lb": "2026-01-30"}],
        "alinhamento": {"pontos": [[0.0, 0.0, 0.0, 0.0], [0.5, 500.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0]]},
    }


def _qset(el, nome):
    return {k: v[3] for k, v in req.quantidades_do_elemento(el)[nome].items()}


def test_peca_simples_volume_conhecido_a_mao():
    # TER: seção trapezoidal base 17 m, topo 12 m, altura 1,5 m; peça de km 0,003 a 0,997 = 994 m
    f, _ = exp.construir(_obra_minima("TER", "m³", 70000.0), incluir_4d=False)
    (el,) = f.by_type("IfcEarthworksFill")
    esperado = (17 + 12) / 2 * 1.5 * 994.0  # 21.619,5 m³
    qto = _qset(el, "Qto_EarthworksFillBaseQuantities")
    assert qto["CompactedVolume"] == pytest.approx(esperado, rel=1e-9)
    assert qto["Length"] == pytest.approx(994.0) and qto["Width"] == 17 and qto["Depth"] == 1.5
    srv = _qset(el, qtd.QSET_SERVICO)
    assert srv["QuantidadeGeometrica"] == pytest.approx(esperado, rel=1e-9)
    assert srv["QuantidadeContratual"] == pytest.approx(70000.0)
    # conferência independente: volume da MALHA triangulada pelo IfcOpenShell
    malha = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), el)
    assert ifcopenshell.util.shape.get_volume(malha.geometry) == pytest.approx(esperado, rel=1e-6)


def test_pecas_simples_por_unidade():
    # DRE (m): duas linhas paralelas de 994 m = 1.988 m lineares
    f, _ = exp.construir(_obra_minima("DRE", "m", 420.0), incluir_4d=False)
    (el,) = f.by_type("IfcPipeSegment")
    assert _qset(el, qtd.QSET_SERVICO)["QuantidadeGeometrica"] == pytest.approx(1988.0)
    # SUP (ha): faixa de 26 m x 994 m = 25.844 m² = 2,5844 ha (o modelo guarda m²)
    f, _ = exp.construir(_obra_minima("SUP", "ha", 4.0), incluir_4d=False)
    (el,) = f.by_type("IfcEarthworksCut")
    q = req.quantidades_do_elemento(el)[qtd.QSET_SERVICO]["QuantidadeGeometrica"]
    assert q.is_a("IfcQuantityArea") and q.AreaValue == pytest.approx(25844.0)
    # GRA (km de via): dois trilhos, mas a quantidade do serviço é o eixo = 0,994 km (o modelo guarda 994 m)
    f, _ = exp.construir(_obra_minima("GRA", "km", 1.0), incluir_4d=False)
    (el,) = f.by_type("IfcRail")
    assert _qset(el, qtd.QSET_SERVICO)["QuantidadeGeometrica"] == pytest.approx(994.0)
    assert _qset(el, "Qto_RailBaseQuantities")["Length"] == pytest.approx(1988.0)  # metros de trilho


def test_rateio_inteiro_soma_exata():
    assert qtd.rateio(48, 7, inteiro=True) == [7.0, 7.0, 7.0, 7.0, 7.0, 7.0, 6.0]
    assert sum(qtd.rateio(8335, 5, inteiro=True)) == 8335
    assert qtd.rateio(10.0, 4, inteiro=False) == [2.5] * 4


def test_quantidade_contratual_fecha_com_o_dataset(modelo, dados):
    c = req.coerencia(modelo, dados)
    assert c["atividades"]
    for linha in c["atividades"]:
        assert linha["soma_contratual"] == pytest.approx(linha["quantidade_total"], rel=1e-9), linha
        assert linha["razao_geometrica"] is not None and linha["razao_geometrica"] > 0, linha  # diferença REPORTADA


def test_custo_pelo_modelo_igual_ao_orcamento(modelo, dados, projeto, obra):
    cm = req.custo_modelo(modelo, dados, obra)
    bac = {linha["atividade_id"]: linha["bac"] for linha in orcamento.orcar_atividades(projeto)}
    assert cm["elementos_sem_composicao"] == 0 and cm["ficticio"] is True
    for aid, v in cm["por_atividade_contratual"].items():
        assert v == pytest.approx(bac[aid], rel=1e-9), aid
    sem_peca = set(bac) - set(cm["por_atividade_contratual"])
    assert sem_peca == {a["id"] for a in dados["atividades"] if a.get("servico_id") in ("SIN", "LIB")}


def test_classificacao_ficticia_por_composicao(modelo, obra):
    for e in _elementos(modelo):
        ps = ifcopenshell.util.element.get_pset(e, PSET_VINCULO)
        (ref,) = ifcopenshell.util.classification.get_references(e)
        assert ref.Identification == orcamento.COMPOSICOES[obra][ps["ServicoId"]]["codigo"]
        assert ref.Identification.startswith("FIC-")
        assert ref.ReferencedSource.Name == orcamento.SISTEMA_CLASSIFICACAO


# --------------------------------------------------------------------------- requisitos de informação

def _status(r):
    return {x["id"]: x["status"] for x in r["requisitos"]}


def test_requisitos_modelo_exportado_aprovado(modelo, dados):
    r = req.verificar(modelo, dados)
    assert r["aprovado"] is True, [(x["id"], x["lista_reprovados"][:2]) for x in r["requisitos"]]
    assert set(_status(r).values()) == {"aprovado"}
    assert r["elementos_construtivos"] == len(_elementos(modelo))


def test_requisitos_detectam_cada_falha(modelo, dados):
    """Cada requisito é visto FALHAR: o modelo é estragado de um jeito por requisito."""
    f = ifcopenshell.file.from_string(modelo.to_string())
    els = sorted(_elementos(f), key=lambda e: e.Name)
    a, b, c, d, e5, e6 = els[:6]
    b.GlobalId = a.GlobalId                                                      # R1
    for rel in list(c.ReferencedBy):                                              # R2 + R6
        if rel.is_a("IfcRelAssignsToProduct"):
            f.remove(rel)
    for rel in list(c.IsDefinedBy):
        if rel.is_a("IfcRelDefinesByProperties") and rel.RelatingPropertyDefinition.Name == PSET_VINCULO:
            ifcopenshell.api.pset.remove_pset(f, product=c, pset=rel.RelatingPropertyDefinition)
    for rel in list(d.HasAssociations):                                           # R3
        if rel.is_a("IfcRelAssociatesClassification"):
            outros = [o for o in rel.RelatedObjects if o != d]
            if outros:
                rel.RelatedObjects = outros
            else:
                f.remove(rel)
    for rel in list(e5.IsDefinedBy):                                              # R4
        if rel.is_a("IfcRelDefinesByProperties") and rel.RelatingPropertyDefinition.is_a("IfcElementQuantity"):
            f.remove(rel)
    ps = ifcopenshell.util.element.get_pset(e6, PSET_VINCULO)                     # R5: estaca fora do eixo
    ifcopenshell.api.pset.edit_pset(f, pset=f.by_id(ps["id"]), properties={"KmFinal": 999.0})
    r = req.verificar(f, dados)
    falhas = {x["id"]: {y["global_id"] for y in x["lista_reprovados"]} for x in r["requisitos"]}
    assert falhas["R1"] == {a.GlobalId}
    assert c.GlobalId in falhas["R2"] and c.GlobalId in falhas["R6"]
    assert falhas["R3"] == {d.GlobalId}
    assert e5.GlobalId in falhas["R4"]
    assert falhas["R5"] == {e6.GlobalId}
    assert r["aprovado"] is False and r["conclusao"].startswith("REPROVADO")
    for rel in list(f.by_type("IfcRelPositions")):          # sem IfcRelPositions e sem IfcLinearPlacement
        f.remove(rel)
    for e in req.elementos_construtivos(f):  # inclui o elemento que perdeu o Pset
        if e.ObjectPlacement.is_a("IfcLinearPlacement"):
            cp = e.ObjectPlacement.CartesianPosition
            e.ObjectPlacement = f.createIfcLocalPlacement(None, cp)
    r5 = next(x for x in req.verificar(f, dados)["requisitos"] if x["id"] == "R5")
    assert r5["status"] == "reprovado" and r5["aprovados"] == 0


# os oficiais da buildingSMART REPROVAM nos nossos requisitos: o relatório tem de dizer isso
_TODOS_REPROVADOS_MENOS_R1 = {"R1": "aprovado", "R2": "reprovado", "R3": "reprovado", "R4": "reprovado",
                              "R5": "reprovado", "R6": "reprovado"}
EXTERNO_ESPERADO = {
    "Infra-Rail.ifc": _TODOS_REPROVADOS_MENOS_R1,
    "Infra-Road.ifc": _TODOS_REPROVADOS_MENOS_R1,
    # exemplo oficial de 4D: vínculo e cronograma APROVADOS; sem classificação, quantidade e eixo
    "construction-scheduling-task.ifc": {"R1": "aprovado", "R2": "aprovado", "R3": "reprovado",
                                         "R4": "reprovado", "R5": "reprovado", "R6": "aprovado"},
    # posicionamento linear oficial: R5 aprovado; nada de 4D/5D
    "linear-placement-of-signal.ifc": {"R1": "aprovado", "R2": "reprovado", "R3": "reprovado",
                                       "R4": "reprovado", "R5": "aprovado", "R6": "reprovado"},
    "segmented-reference-curve.ifc": {f"R{i}": "nao_aplicavel" for i in range(1, 7)},
}


def test_externo_requisitos(externo):
    nome, f = externo
    r = req.verificar(f)
    assert _status(r) == EXTERNO_ESPERADO[nome]
    assert r["aprovado"] is False
    if nome.startswith("segmented"):
        assert r["conclusao"].startswith("NÃO VERIFICÁVEL")
    else:
        assert r["conclusao"].startswith("REPROVADO")
        for x in r["requisitos"]:
            if x["status"] == "reprovado":
                assert x["reprovados"] == x["total"] and x["lista_reprovados"][0]["motivo"]


def test_router_requisitos(cliente):
    r = cliente.get("/api/ifc/requisitos")
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["aprovado"] is True and v["conclusao"] == "APROVADO em todos os requisitos"
    assert v["custo"]["modelo_contratual"] == pytest.approx(v["custo"]["orcamento_atividades_com_peca"], rel=1e-9)
    assert v["quantidades"]["por_servico"]
    corpo = cliente.get("/api/ifc/exportar").content
    r2 = cliente.post("/api/ifc/requisitos", content=corpo)
    assert r2.status_code == 200 and r2.json()["aprovado"] is True
    assert cliente.post("/api/ifc/requisitos", content=b"").status_code == 400
    assert cliente.post("/api/ifc/requisitos", content=b"nada a ver").status_code == 422


def test_router_requisitos_upload_oficial_reprova(cliente):
    corpo = _externo("Infra-Rail.ifc").read_bytes()
    r = cliente.post("/api/ifc/requisitos", content=corpo)
    assert r.status_code == 200
    v = r.json()
    assert v["aprovado"] is False and "R2" in v["conclusao"] and "R6" in v["conclusao"]


# --------------------------------------------------------------------------- IfcLinearPlacement e estaqueamento

import numpy as _np  # noqa: E402

import ifcopenshell.api.alignment  # noqa: E402

from infra4d.referencia_linear import Eixo as _EixoRef  # noqa: E402
from infra4d.referencia_linear import Estaca as _Estaca  # noqa: E402


def _vertices_mundo(f) -> dict:
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    out = {}
    it = ifcopenshell.geom.iterator(s, f, include=f.by_type("IfcElement"))
    if it.initialize():
        while True:
            sh = it.get()
            out[sh.guid] = _np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
            if not it.next():
                break
    return out


def test_pecas_com_ifclinearplacement_no_eixo(modelo):
    al = modelo.by_type("IfcAlignment")[0]
    base = ifcopenshell.api.alignment.get_basis_curve(al)
    for e in _elementos(modelo):
        pl = e.ObjectPlacement
        assert pl.is_a("IfcLinearPlacement"), (e.Name, pl)
        loc = pl.RelativePlacement.Location
        assert loc.is_a("IfcPointByDistanceExpression") and loc.BasisCurve == base
        assert pl.CartesianPosition is not None  # posição de reserva para leitores sem avaliação de curva


def test_posicao_igual_a_da_versao_com_placement_local(dados, modelo, limite):
    """A peça com IfcLinearPlacement fica no MESMO lugar da versão anterior (IfcLocalPlacement):
    distância de Hausdorff entre os vértices triangulados pelo IfcOpenShell, por GlobalId."""
    tol = limite("tolerancia_posicao_ifc_m")
    assert exp.TOLERANCIA_PROJECAO_M == tol  # o exportador recusa acima da MESMA tolerância do manifesto
    _, resumo = exp.construir(dados, incluir_4d=False)
    assert resumo["posicionamento"] == "IfcLinearPlacement" and resumo["residuo_projecao_m"] <= tol
    antes, _ = exp.construir(dados, incluir_4d=False, posicionamento="local")
    va, vb = _vertices_mundo(antes), _vertices_mundo(modelo)
    assert set(va) == set(vb) and len(va) == len(_elementos(modelo))
    pior = 0.0
    for g, x in va.items():
        y = vb[g]
        dd = _np.linalg.norm(x[:, None, :] - y[None, :, :], axis=2)
        pior = max(pior, dd.min(axis=1).max(), dd.min(axis=0).max())
    assert pior <= tol, pior


def test_requisito_r5_reporta_linear_placement(modelo, dados):
    r5 = next(x for x in req.verificar(modelo, dados)["requisitos"] if x["id"] == "R5")
    assert r5["status"] == "aprovado"
    assert r5["nota"] == f"modos: {{'IfcLinearPlacement': {len(_elementos(modelo))}}}"


def test_estaca_por_km_no_ifcreferent(modelo, dados, limite):
    ref = _EixoRef.da_obra(dados)
    al = modelo.by_type("IfcAlignment")[0]
    refs = [r for r in imp.alinhamentos(modelo)["itens"][0]["referentes"] if r["km"] is not None]
    kms = sorted(r["km"] for r in refs)
    assert kms == [float(k) for k in range(int(ref.km_inicial), int(ref.km_final) + 1)]
    assert all(r["tipo"] == "STATION" for r in refs)
    c = imp.comparar_estacas(modelo, dados)
    assert c["max_dif_m"] <= limite("tolerancia_estaca_m")
    # POSIÇÃO, não só texto: o referente está no pé da perpendicular do ponto do km no eixo IFC
    assert c["max_desvio_longitudinal_m"] <= limite("tolerancia_posicao_ifc_m")
    # o PRÓPRIO IfcOpenShell, a partir da estaca, acha o mesmo ponto do eixo que o referente
    for r in refs:
        d = ifcopenshell.api.alignment.distance_along_from_station(modelo, al, r["estaca"])
        assert d == pytest.approx(r["distancia_ao_longo"], abs=limite("tolerancia_estaca_m"))


def test_estaca_do_ifc_igual_a_api_referencia_km(cliente_api, modelo, obra, limite):
    """O importador lê a estaca do IfcReferent e ela bate com GET /api/referencia/km da mesma obra."""
    tol = limite("tolerancia_estaca_m")
    refs = [r for r in imp.alinhamentos(modelo)["itens"][0]["referentes"] if r["km"] is not None]
    assert refs
    for r in refs:
        resp = cliente_api.get("/api/referencia/km", params={"km": r["km"], "obra": obra})
        assert resp.status_code == 200, resp.text
        api_estaca = resp.json()["estaca"]
        assert r["estaca_texto"] == api_estaca
        assert abs(_Estaca.de_texto(api_estaca).metros - r["estaca"]) <= tol


def _obra_com_equacao() -> dict:
    d = _obra_minima("TER", "m³", 140000.0)
    # eixo com deflexão no km 1 (curva de concordância): distância ao longo ≠ medida do km
    d["alinhamento"]["pontos"] = [[0.0, 0.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0], [2.0, 1990.0, 140.0, 0.0]]
    d["lotes"][0]["km_fim"] = d["segmentos"][0]["km_fim"] = d["atividades"][0]["km_fim"] = 2.0
    d["meta"]["equacoes_estaca"] = [{"km": 1.0, "estaca": "60+00,00"}]  # a estaca salta de 50+00 para 60+00
    return d


def test_equacao_de_estacas_vira_incoming_station(limite):
    d = _obra_com_equacao()
    f, resumo = exp.construir(d, incluir_4d=False)
    assert resumo["posicionamento"] == "IfcLinearPlacement" and resumo["equacoes_estaca"] == 1
    refs = {r["km"]: r for r in imp.alinhamentos(f)["itens"][0]["referentes"]}
    tol = limite("tolerancia_estaca_m")
    assert refs[0.0]["estaca"] == pytest.approx(0.0, abs=tol)
    assert refs[1.0]["estaca"] == pytest.approx(1200.0, abs=tol)  # 60+00,00 (à frente da equação)
    # de volta: o que o IFC traria por continuidade = estaca anterior + curva percorrida até o km 1
    assert refs[1.0]["estaca_de_volta"] == pytest.approx(refs[1.0]["distancia_ao_longo"], abs=tol)
    assert refs[2.0]["estaca"] == pytest.approx(2200.0, abs=tol)  # 110+00,00
    assert refs[2.0]["estaca_de_volta"] == pytest.approx(
        1200.0 + refs[2.0]["distancia_ao_longo"] - refs[1.0]["distancia_ao_longo"], abs=tol)
    eq = next(r for r in f.by_type("IfcReferent") if "equação" in (r.Description or ""))
    assert ifcopenshell.util.element.get_pset(eq, "INFRA4D_Referencia")["EstacaAnteriorMedida"] == \
        pytest.approx(1000.0, abs=tol)  # 50+00,00 na medida do projeto (referencia_linear)
    assert imp.comparar_estacas(f, d)["max_dif_m"] <= tol
    al = f.by_type("IfcAlignment")[0]
    for km in (1.0, 2.0):
        assert ifcopenshell.api.alignment.distance_along_from_station(f, al, refs[km]["estaca"]) == \
            pytest.approx(refs[km]["distancia_ao_longo"], abs=tol)
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, log, express_rules=True)
    assert log.statements == [], [str(s)[:200] for s in log.statements[:3]]


def test_pis_colineares_nao_derrubam_o_alinhamento_semantico():
    """create_by_pi_method do IfcOpenShell 0.9.0.post1 divide por zero com PIs colineares."""
    assert exp._sem_colineares([(0, 0), (1000, 0), (2000, 0), (3000, 10)]) == [(0, 0), (2000, 0), (3000, 10)]
    d = _obra_com_equacao()
    d["alinhamento"]["pontos"] = [[0.0, 0.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0], [2.0, 2000.0, 0.0, 0.0]]
    f, resumo = exp.construir(d, incluir_4d=False)
    assert resumo["posicionamento"] == "IfcLinearPlacement" and "fallback" not in resumo["alinhamento"]


# --------------------------------------------------------------------------- r15: projeção robusta

def _obra_r15(pontos, trechos):
    d = _obra_minima("TER", "m³", 1000.0)
    k0, k1 = min(p[0] for p in pontos), max(p[0] for p in pontos)
    d["lotes"][0].update(km_ini=k0, km_fim=k1)
    d["segmentos"][0].update(km_ini=k0, km_fim=k1)
    base = d["atividades"][0]
    d["atividades"] = [{**base, "id": f"A{i}", "km_ini": a, "km_fim": b} for i, (a, b) in enumerate(trechos)]
    d["alinhamento"]["pontos"] = pontos
    return d


def test_projecao_sem_solucao_e_erro_e_nao_peca_deslocada(monkeypatch):
    """Se o pé da perpendicular não fecha dentro da tolerância, o exportador RECUSA (nunca desloca em silêncio).
    Simulado deixando a tolerância absurda de pequena: qualquer arredondamento vira erro."""
    d = _obra_r15([[0.0, 0.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0], [2.0, 1500.0, 866.0, 0.0]], [(0.0, 2.0)])
    monkeypatch.setattr(exp, "TOLERANCIA_PROJECAO_M", -1.0)
    with pytest.raises(exp.ErroExportacao, match="projeção no eixo IFC"):
        exp.construir(d, incluir_4d=False)


def test_peca_fora_da_extensao_usa_offset_longitudinal():
    d = _obra_r15([[0.0, 0.0, 0.0, 0.0], [1.0, 1000.0, 0.0, 0.0], [2.0, 2000.0, 0.0, 0.0]], [(-0.5, 0.0), (2.2, 2.5)])
    f, _ = exp.construir(d, incluir_4d=False)
    locs = {e.Name: e.ObjectPlacement.RelativePlacement.Location for e in _elementos(f)}
    assert locs["A0-E01"].OffsetLongitudinal == pytest.approx(-497.0, abs=1e-6)  # antes do início
    assert locs["A1-E01"].OffsetLongitudinal == pytest.approx(203.0, abs=1e-6)   # depois do fim (eixo = 2000 m)


def test_comparar_estacas_acusa_referente_fora_do_lugar(modelo, dados, limite):
    f = ifcopenshell.file.from_string(modelo.to_string())
    r = next(r for r in f.by_type("IfcReferent")
             if (ifcopenshell.util.element.get_pset(r, "INFRA4D_Referencia") or {}).get("Km") == 5.0)
    r.ObjectPlacement.RelativePlacement.Location.DistanceAlong = f.create_entity("IfcLengthMeasure", 4000.0)
    c = imp.comparar_estacas(f, dados)
    assert c["max_dif_m"] <= limite("tolerancia_estaca_m")  # o texto da estaca continua certo...
    assert c["max_desvio_longitudinal_m"] > 900.0          # ...mas a POSIÇÃO não


def test_upload_com_content_type_errado_e_415(cliente):
    for rota in ("/api/ifc/vinculos", "/api/ifc/requisitos", "/api/ifc/cronograma"):
        r = cliente.post(rota, content=b'{"a": 1}', headers={"Content-Type": "application/json"})
        assert r.status_code == 415, (rota, r.status_code)
