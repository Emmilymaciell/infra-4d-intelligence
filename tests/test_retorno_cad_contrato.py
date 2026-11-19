"""Revisão independente do contrato de componentes CAD declarados.

Os testes verificam campos, intervalos e agregação. Não validam BRep nem
transformam volume de um fragmento em quantidade contratual da atividade.
"""
import copy
import math

import pytest

from infra4d.cad_contrato import validar_componentes


ATIVIDADE = "OAE3-SUE"


@pytest.fixture
def malha():
    # Seis faces já validadas pelo contrato de malha a montante. A partição
    # abaixo não pretende provar dois sólidos fechados ou seus volumes BRep.
    return {
        "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                     [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
        "faces": [[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1],
                  [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]],
        "matrix_world": [[1, 0, 0, 100], [0, 1, 0, 200],
                         [0, 0, 1, 300], [0, 0, 0, 1]],
        "unidade": "m",
        "ilustrativa": True,
    }


@pytest.fixture
def componentes():
    return [
        {"componente_id": "Tabuleiro-A", "nome": "Tabuleiro A",
         "atividade_id": ATIVIDADE, "tipo_nativo": "Part::Box",
         "face_inicio": 0, "face_quantidade": 3,
         "volume_m3": 6.0, "area_m2": 22.0,
         "cor_rgb": [0.25, 0.5, 0.75], "material": "Concreto ilustrativo",
         "parametros_mm": {"Length": 1000.0, "Width": 2000.0, "Height": 3000.0}},
        {"componente_id": "Tabuleiro-B", "nome": "Tabuleiro B",
         "atividade_id": ATIVIDADE, "tipo_nativo": "Part::Box",
         "face_inicio": 3, "face_quantidade": 3,
         "volume_m3": 0.12, "area_m2": 1.48,
         "cor_rgb": [0.0, 1.0, 0.5], "material": "Material de estudo",
         "parametros_mm": {"Length": 400.0, "Width": 500.0, "Height": 600.0}},
    ]


def test_dois_componentes_cobrem_seis_faces_e_somam_medidas_declaradas(malha, componentes):
    antes = copy.deepcopy((malha, componentes))
    resultado = validar_componentes(malha, componentes, ATIVIDADE)
    assert resultado["componentes_contagem"] == 2
    assert resultado["volume_m3"] == 6.12
    assert resultado["area_m2"] == 23.48
    assert (malha, componentes) == antes
    # A atividade de planejamento pode ter 3 un. Aqui há dois componentes
    # ilustrativos: não multiplicar o volume por 3 nem chamar contagem de avanço.
    assert resultado["volume_m3"] != 6.12 * 3


def test_zero_em_medidas_declaradas_e_cor_nos_limites_sao_permitidos(malha, componentes):
    for c in componentes:
        c["volume_m3"] = 0.0
        c["area_m2"] = 0.0
        c["cor_rgb"] = [0.0, 1.0, 0.0]
    resultado = validar_componentes(malha, componentes, ATIVIDADE)
    assert resultado["volume_m3"] == 0
    assert resultado["area_m2"] == 0
    assert resultado["componentes_contagem"] == 2


@pytest.mark.parametrize("valor", [None, [], {}, "componentes", True])
def test_lista_ausente_vazia_ou_tipo_incorreto_e_recusado(malha, valor):
    with pytest.raises(ValueError):
        validar_componentes(malha, valor, ATIVIDADE)


@pytest.mark.parametrize("valor", [None, [], "componente", 1, True])
def test_item_precisa_ser_objeto(malha, componentes, valor):
    componentes[0] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("campo", ["componente_id", "nome", "atividade_id", "tipo_nativo",
                                    "face_inicio", "face_quantidade", "volume_m3", "area_m2",
                                    "cor_rgb", "material", "parametros_mm"])
def test_campo_obrigatorio_ausente_e_recusado(malha, componentes, campo):
    componentes[0].pop(campo)
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("valor", ["", "   ", None, 1, True, []])
def test_componente_id_precisa_ser_texto_estavel_nao_vazio(malha, componentes, valor):
    componentes[0]["componente_id"] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


def test_ids_duplicados_nao_sao_somados_em_dobro(malha, componentes):
    componentes[1]["componente_id"] = componentes[0]["componente_id"]
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("valor", ["OAE3-MES", "", None, 3, True])
def test_componente_de_outra_atividade_nao_e_federado(malha, componentes, valor):
    componentes[0]["atividade_id"] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("valor", ["Part::Feature", "Mesh::Feature", "", None, True])
def test_tipo_nativo_diferente_nao_comprova_caixa_parametrica(malha, componentes, valor):
    componentes[0]["tipo_nativo"] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("campo,valor", [
    ("face_inicio", -1), ("face_inicio", True), ("face_inicio", 0.5),
    ("face_inicio", "0"), ("face_inicio", None),
    ("face_quantidade", 0), ("face_quantidade", -1), ("face_quantidade", True),
    ("face_quantidade", 1.5), ("face_quantidade", "3"), ("face_quantidade", None),
])
def test_intervalo_exige_indices_inteiros_sem_bool(malha, componentes, campo, valor):
    componentes[0][campo] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("caso", ["sobreposicao", "lacuna", "fora_do_limite", "inicio_omitido",
                                   "fim_omitido", "ordem_invertida"])
def test_intervalos_cobrem_todas_as_faces_uma_vez(malha, componentes, caso):
    if caso == "sobreposicao":
        componentes[1]["face_inicio"] = 2
    elif caso == "lacuna":
        componentes[1]["face_inicio"] = 4
    elif caso == "fora_do_limite":
        componentes[1]["face_quantidade"] = 4
    elif caso == "inicio_omitido":
        componentes[0]["face_inicio"] = 1
        componentes[0]["face_quantidade"] = 2
    elif caso == "fim_omitido":
        componentes[1]["face_quantidade"] = 2
    else:
        componentes.reverse()
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("campo", ["volume_m3", "area_m2"])
@pytest.mark.parametrize("valor", [True, False, -0.01, math.nan, math.inf, -math.inf,
                                    "6.0", None, []])
def test_medidas_recusam_bool_negativo_nao_finito_e_texto(malha, componentes, campo, valor):
    componentes[0][campo] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("valor", [None, "#ffffff", [], [0.0, 1.0], [0.0] * 4,
                                    [True, 0.0, 0.0], [0.0, False, 0.0],
                                    [-0.01, 0.0, 0.0], [1.01, 0.0, 0.0],
                                    [math.nan, 0.0, 0.0], [math.inf, 0.0, 0.0],
                                    ["0.5", 0.0, 0.0]])
def test_cor_deve_ser_rgb_finito_no_intervalo_unitario(malha, componentes, valor):
    componentes[0]["cor_rgb"] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("valor", [None, 12, True, []])
def test_material_precisa_ser_texto(malha, componentes, valor):
    componentes[0]["material"] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("valor", [None, [], "dimensoes", True, {}])
def test_parametros_precisam_ser_objeto_com_dimensoes(malha, componentes, valor):
    componentes[0]["parametros_mm"] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("dimensao", ["Length", "Width", "Height"])
def test_todas_as_dimensoes_sao_obrigatorias(malha, componentes, dimensao):
    componentes[0]["parametros_mm"].pop(dimensao)
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("dimensao", ["Length", "Width", "Height"])
@pytest.mark.parametrize("valor", [0, -1, True, False, math.nan, math.inf, -math.inf,
                                    "1000 mm", None])
def test_dimensoes_mm_positivas_finitas_sem_bool(malha, componentes, dimensao, valor):
    componentes[0]["parametros_mm"][dimensao] = valor
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)


@pytest.mark.parametrize("contagem", [1, 500])
def test_limites_inclusivos_de_componentes(malha, componentes, contagem):
    malha["faces"] = [[0, 1, 2] for _ in range(contagem)]
    lista = []
    for i in range(contagem):
        c = copy.deepcopy(componentes[0])
        c.update(componente_id=f"componente-{i}", face_inicio=i, face_quantidade=1)
        lista.append(c)
    resultado = validar_componentes(malha, lista, ATIVIDADE)
    assert resultado["componentes_contagem"] == contagem
    assert resultado["volume_m3"] == 6 * contagem


def test_mais_de_quinhentos_componentes_e_recusado(malha, componentes):
    malha["faces"] = [[0, 1, 2] for _ in range(501)]
    lista = []
    for i in range(501):
        c = copy.deepcopy(componentes[0])
        c.update(componente_id=f"componente-{i}", face_inicio=i, face_quantidade=1)
        lista.append(c)
    with pytest.raises(ValueError):
        validar_componentes(malha, lista, ATIVIDADE)


def test_soma_de_medidas_nao_pode_transbordar_para_infinito(malha, componentes):
    for c in componentes:
        c["volume_m3"] = 1e308
    with pytest.raises(ValueError):
        validar_componentes(malha, componentes, ATIVIDADE)
