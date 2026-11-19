"""Contratos de autoria externa: origem inviolável, diff e merge isolado."""
import copy

import pytest

from infra4d.cenarios import Projeto
from infra4d.interop import (ErroInterop, aplicar_revisao, checksum, exportar_pacote,
                            reconciliar_revisao)
from infra4d.interop_pacote import gerar, registrar_retorno


@pytest.fixture(scope="module")
def projeto():
    return Projeto.carregar()


@pytest.fixture(scope="module")
def baseline(projeto):
    return exportar_pacote(projeto)


@pytest.fixture()
def revisao(baseline):
    r = copy.deepcopy(baseline)
    r["meta"]["revision"] = "qgis-r1"
    return r


def alvo(pacote):
    return next(f for f in pacote["features"] if f["properties"]["atividade_id"] == "L3-S04-TER")


def test_exportacao_vinculada_e_estavel(projeto, baseline):
    assert baseline == exportar_pacote(projeto)
    assert baseline["meta"]["crs"] == "EPSG:4326"
    assert baseline["meta"]["ficticio"] is True
    assert all(f["properties"]["atividade_id"] in projeto.atividades for f in baseline["features"])
    assert all(f["properties"]["tipo_dado"] == "ficticio" for f in baseline["features"])


def test_quantidade_critica_recalcula_em_copia_sem_mudar_demo(projeto, baseline, revisao):
    original = checksum(projeto.dados)
    p = alvo(revisao)["properties"]
    p["quantidade_total"] *= 1.2
    novo, rel = aplicar_revisao(projeto, baseline, revisao)
    assert checksum(projeto.dados) == original
    assert novo is not projeto and novo.dados is not projeto.dados
    assert rel["termino_depois"] > rel["termino_antes"]
    assert rel["ids_preservados"] == len(baseline["features"])
    assert rel["dataset_original_alterado"] is False


def test_escala_blender_nunca_vira_quantidade(projeto):
    b = exportar_pacote(projeto, "Blender")
    r = copy.deepcopy(b)
    r["meta"]["revision"] = "blender-r1"
    alvo(r)["properties"]["transformacao_visual"] = {"escala": [1, 1, 1.25]}
    novo, rel = aplicar_revisao(projeto, b, r)
    assert novo.dados == projeto.dados
    assert rel["termino_antes"] == rel["termino_depois"]
    assert rel["mudancas"][0]["campo"] == "transformacao_visual"


def test_geometria_alterada_exige_revisao_sem_quantidade_inferida(projeto, baseline, revisao):
    alvo(revisao)["geometry"]["coordinates"][0][0] += .00001
    novo, rel = aplicar_revisao(projeto, baseline, revisao)
    assert novo.dados == projeto.dados
    assert rel["mudancas"][0]["campo"] == "geometry"
    assert rel["aprovacao_necessaria"]


@pytest.mark.parametrize("campo,valor", [("unidade", "kg"), ("servico_id", "TROCA"),
                                       ("atividade_id", "NOVA"), ("visibilidade_demo", 1),
                                       ("quantidade_executada", -1)])
def test_recusa_alteracao_protegida(projeto, baseline, revisao, campo, valor):
    alvo(revisao)["properties"][campo] = valor
    with pytest.raises(ErroInterop):
        reconciliar_revisao(projeto, baseline, revisao)


@pytest.mark.parametrize("valor", [True, -1, float("nan"), float("inf"), "100"])
def test_quantidade_invalida_nao_muda_fonte(projeto, baseline, revisao, valor):
    antes = checksum(projeto.dados)
    alvo(revisao)["properties"]["quantidade_total"] = valor
    with pytest.raises(ErroInterop):
        reconciliar_revisao(projeto, baseline, revisao)
    assert checksum(projeto.dados) == antes


def test_baseline_e_revisao_coniventes_nao_contornam_canonico(projeto, baseline, revisao):
    b = copy.deepcopy(baseline)
    alvo(b)["properties"]["unidade"] = "kg"
    alvo(revisao)["properties"]["unidade"] = "kg"
    with pytest.raises(ErroInterop, match="baseline adulterada"):
        reconciliar_revisao(projeto, b, revisao)


@pytest.mark.parametrize("meta", [None, [], "texto"])
def test_meta_invalido_e_erro_contratual(projeto, baseline, revisao, meta):
    revisao["meta"] = meta
    with pytest.raises(ErroInterop, match="meta deve ser objeto"):
        reconciliar_revisao(projeto, baseline, revisao)


def test_baseline_normalizada_pelo_javascript_aceita_numeros_sem_aceitar_bool(projeto, baseline, revisao):
    def normalizar(v):
        if isinstance(v, dict):
            return {k: normalizar(x) for k, x in v.items()}
        if isinstance(v, list):
            return [normalizar(x) for x in v]
        return int(v) if isinstance(v, float) and v.is_integer() else v
    b, r = normalizar(baseline), normalizar(revisao)
    assert reconciliar_revisao(projeto, b, r)["ids_preservados"] == len(b["features"])
    b["features"][0]["properties"]["visibilidade_demo"] = 1
    r["features"][0]["properties"]["visibilidade_demo"] = 1
    with pytest.raises(ErroInterop, match="baseline adulterada"):
        reconciliar_revisao(projeto, b, r)


@pytest.mark.parametrize("mudanca", ["crs", "duplicado", "removido", "nan", "latitude", "poligono", "vazio", "mesma_revisao"])
def test_revisoes_adversas_recusadas(projeto, baseline, revisao, mudanca):
    if mudanca == "crs":
        revisao["meta"]["crs"] = "EPSG:3857"
    elif mudanca == "duplicado":
        revisao["features"].append(copy.deepcopy(revisao["features"][0]))
    elif mudanca == "removido":
        revisao["features"].pop()
    elif mudanca == "nan":
        alvo(revisao)["geometry"]["coordinates"][0][0] = float("nan")
    elif mudanca == "latitude":
        alvo(revisao)["geometry"]["coordinates"][0][1] = 91
    elif mudanca == "poligono":
        alvo(revisao)["geometry"]["type"] = "Polygon"
    elif mudanca == "vazio":
        revisao["features"] = []
    else:
        revisao["meta"]["revision"] = baseline["meta"]["revision"]
    with pytest.raises(ErroInterop):
        reconciliar_revisao(projeto, baseline, revisao)


def test_obra_alterada_depois_publicacao_exige_nova_base(projeto, baseline, revisao):
    dados = copy.deepcopy(projeto.dados)
    dados["meta"]["aviso"] += " revisão"
    with pytest.raises(ErroInterop, match="obra mudou"):
        reconciliar_revisao(Projeto(dados), baseline, revisao)


def test_sem_marca_ficticia_recusa_exportar(projeto):
    dados = copy.deepcopy(projeto.dados)
    dados["meta"]["ficticio"] = "true"
    with pytest.raises(ErroInterop):
        exportar_pacote(Projeto(dados))


def test_pacote_nao_finge_nativos_e_preserva_revisao(projeto, tmp_path):
    destino = tmp_path / "pacote"
    manifesto = gerar(projeto, destino)
    assert manifesto["estado_inicial"]["QGIS"] == "formato gerado"
    assert list(destino.rglob("*.blend")) == []
    assert list(destino.rglob("*.qgz")) == []
    assert (destino / "01-gis-qgis" / "interop_qgis.py").is_file()
    assert (destino / "00-manifesto" / "SHA256SUMS.txt").is_file()
    with pytest.raises(FileExistsError):
        gerar(projeto, destino)


def test_relatorio_de_retorno_preserva_evidencia(projeto, baseline, revisao, tmp_path):
    import json
    b, r, saida = (tmp_path / n for n in ("baseline.json", "revisao.json", "retorno.json"))
    for caminho, valor in ((b, baseline), (r, revisao)):
        caminho.write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")
    rel = registrar_retorno(projeto, b, r, saida)
    assert rel["ids_preservados"] == len(baseline["features"])
    assert saida.is_file()
    with pytest.raises(FileExistsError):
        registrar_retorno(projeto, b, r, saida)


def test_complemento_usa_exportadores_legitimos_e_preserva_arquivos(projeto, tmp_path):
    from xml.etree import ElementTree as ET
    from infra4d.interop_pacote import complementar
    destino = tmp_path / "pacote"
    gerar(projeto, destino)
    rel = complementar(projeto, destino)
    xml = destino / "05-cronograma" / "independente.xml"
    raiz = ET.fromstring(xml.read_text(encoding="utf-8"))
    assert raiz.tag.endswith("Project")
    assert "ERMHDR" in (destino / "05-cronograma" / "independente.xer").read_text(encoding="utf-8")
    csv = (destino / "06-quantitativos" / "quantidades-ficticias.csv").read_text(encoding="utf-8-sig")
    assert "L3-S04-TER;TER;L3;m³;350000" in csv
    assert not list(destino.rglob("*.FCStd")) and not list(destino.rglob("*.blend"))
    assert not rel["apps_gui_homologados"]
    # Complementar não é permissão para sobrescrever um arquivo revisado.
    xml.write_text("preservar revisão externa", encoding="utf-8")
    complementar(projeto, destino)
    assert xml.read_text(encoding="utf-8") == "preservar revisão externa"
