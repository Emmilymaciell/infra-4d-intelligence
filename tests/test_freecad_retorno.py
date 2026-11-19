"""Edição controlada e componentes de retorno CAD: sem inferência de quantidade contratual."""
import copy
import pytest

from infra4d.cenarios import Projeto
from infra4d.interop import exportar_pacote, aplicar_revisao, ErroInterop
from infra4d.interop_freecad_retorno import validar_edicoes


@pytest.mark.parametrize('adulteracao', ['id', 'manifesto'])
def test_grupo_com_shape_agregada_nao_duplica_pecas_e_id_adulterado_recusado(adulteracao):
    import json
    from types import SimpleNamespace as NS
    from infra4d.interop_freecad import preparar_componentes
    from infra4d.interop_freecad_retorno import _objetos
    base = exportar_pacote(Projeto.carregar(), "FreeCAD")
    descritores, matriz = preparar_componentes(base)
    forma = NS(isNull=lambda: False, isValid=lambda: True, Volume=1)
    grupo = NS(TypeId="App::DocumentObjectGroup", Shape=forma, Aviso="100% FICTICIO",
               TransformacaoLocalMetros=json.dumps(matriz))
    props = {f['properties']['atividade_id']: f['properties'] for f in base['features']}
    objetos = []
    for d in descritores:
        p = props[d['atividade_id']]
        objetos.append(NS(Name=d['nome'], TypeId='Part::Box', Shape=forma, AtividadeId=d['atividade_id'],
            ElementoId=p['elemento_id'], ModelId=base['meta']['model_id'], TipoDado='ficticio',
            UnidadePlanejamento=p['unidade'], QuantidadePlanejamento=p['quantidade_total'],
            QuantidadeExecutada=p['quantidade_executada']))
    doc = NS(Objects=[grupo, *objetos], getObject=lambda nome: grupo if nome == 'INFRA4D' else None)
    assert _objetos(doc, base)[0] == objetos
    if adulteracao == 'id':
        objetos[0].ComponenteId = 'id-adulterado'
        mensagem = 'identidade do componente'
    else:
        grupo.ManifestoComponentes = json.dumps({objetos[0].Name: 'outra-atividade'})
        mensagem = 'manifesto nativo'
    with pytest.raises(ValueError, match=mensagem):
        _objetos(doc, base)


@pytest.mark.parametrize("valor", [None, [], {"Tabuleiro": {}}, {"Tabuleiro": {"Height": True}},
    {"Tabuleiro": {"Height": -1}}, {"Tabuleiro": {"Height": float("inf")}},
    {"Tabuleiro": {"Height": 1000001}}, {"Tabuleiro": {"AtividadeId": "outra"}},
    {"Tabuleiro": {"QuantidadePlanejamento": 4}}, {"Tabuleiro": {"Height": "1500 mm"}}])
def test_edicoes_recusadas(valor):
    with pytest.raises(ValueError):
        validar_edicoes(valor)


def test_edicoes_geometricas_explicitas_sem_mutar_job():
    valor = {"Tabuleiro": {"Height": 1500}}
    assert validar_edicoes(valor) == valor
    assert validar_edicoes({}) == {}


def retorno_com_componentes():
    projeto = Projeto.carregar()
    b = exportar_pacote(projeto, "FreeCAD")
    r = copy.deepcopy(b); r["meta"]["revision"] = "r2"
    f = next(f for f in r["features"] if f["properties"]["atividade_id"] == "OAE3-SUE")
    f["properties"]["geometria_local_m"] = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 1]],
        "faces": [[0, 1, 2]], "matrix_world": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        "unidade": "m", "ilustrativa": True}
    f["properties"]["componentes_nativos"] = [{"componente_id": "tabuleiro", "nome": "Tabuleiro",
        "atividade_id": "OAE3-SUE", "tipo_nativo": "Part::Box", "face_inicio": 0, "face_quantidade": 1,
        "volume_m3": 144, "volume_anterior_m3": 120, "area_m2": 220,
        "parametros_mm": {"Length": 12000, "Width": 8000, "Height": 1500},
        "cor_rgb": [.5, .5, .5], "material": "concreto fictício"}]
    return projeto, b, r, f


def test_derivado_cad_atualiza_sem_mudar_unidades_avanco_ou_cpm():
    p, b, r, f = retorno_com_componentes()
    antes = copy.deepcopy(p.dados)
    novo, rel = aplicar_revisao(p, b, r)
    assert p.dados == antes == novo.dados
    q = rel["derivados_geometricos"]["OAE3-SUE"]
    assert q["volume_m3"] == 144 and q["volume_anterior_m3"] == 120 and q["delta_volume_m3"] == 24
    assert f["properties"]["quantidade_total"] == 3 and f["properties"]["unidade"] == "un"
    assert rel["termino_antes"] == rel["termino_depois"]


def test_componente_sem_malha_ou_com_vinculo_alterado_recusado():
    p, b, r, f = retorno_com_componentes()
    f["properties"]["componentes_nativos"][0]["atividade_id"] = "outra"
    with pytest.raises(ErroInterop, match="componentes"):
        aplicar_revisao(p, b, r)
    f["properties"].pop("geometria_local_m")
    with pytest.raises(ErroInterop, match="malha"):
        aplicar_revisao(p, b, r)
