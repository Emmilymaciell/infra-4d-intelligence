"""Descritores puros de um TRECHO demonstrativo de OAE, não dimensionado.

Três vãos de 12 m (36 m de geometria) dentro da faixa de atividade de 400 m.
Part::Box no FreeCAD usa dimensões/posições locais em milímetros; a matriz
reutilizada da publicação transforma metros locais em metros da obra fictícia.
Cada caixa será editável no aplicativo. Não depende de FreeCAD no processo API.
O piloto usa eixo local reto e cota média, sem reconstrução de curva, rampa ou
superelevação do corredor. Não substitui o alinhamento publicado da atividade.

Os quantitativos de planejamento se REPETEM como metadados de vínculo: NÃO somar
esses valores por componente. A quantidade contratual vem uma vez por atividade
do pacote original. Volume/contagem geométrica são QTO ilustrativo separado.
"""
from __future__ import annotations

import math

from .interop_freecad import preparar_componentes


_CORES = {
    "concreto": [0.70, 0.70, 0.67],
    "apoio": [0.20, 0.22, 0.23],
    "aco": [0.39, 0.44, 0.48],
    "lastro": [0.48, 0.50, 0.52],
    "dormente": [0.66, 0.63, 0.57],
}
_IDS = {
    "FUN": "OAE3-FUN", "MES": "OAE3-MES", "SUE": "OAE3-SUE",
    "LAS": "L3-S04-LAS", "DOR": "L3-S04-DOR", "GRA": "L3-S04-GRA",
}


def _metadados(pacote):
    por_id = {}
    for feature in pacote.get("features", []):
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise ValueError("feição sem propriedades de vínculo")
        props = feature["properties"]
        aid = props.get("atividade_id")
        if not isinstance(aid, str) or aid in por_id:
            raise ValueError("atividade_id ausente ou duplicado no pacote")
        por_id[aid] = props
    for aid in _IDS.values():
        if aid not in por_id:
            raise ValueError(f"trecho demonstrativo exige atividade {aid}")
        props = por_id[aid]
        if not isinstance(props.get("unidade"), str) or not props["unidade"].strip():
            raise ValueError(f"unidade de planejamento ausente: {aid}")
        for campo in ("quantidade_total", "quantidade_executada"):
            valor = props.get(campo)
            if type(valor) not in (int, float) or not math.isfinite(valor) or valor < 0:
                raise ValueError(f"quantidade inválida: {aid}.{campo}")
        if props["quantidade_executada"] > props["quantidade_total"]:
            raise ValueError(f"executado maior que total: {aid}")
    return por_id


def preparar_oae(pacote):
    """Retorna (descritores Part::Box, matriz 4x4), sem alterar a publicação.

    Geometria ilustrativa parcial, sem verificação de capacidade estrutural,
    geotecnia, hidráulica ou gabarito ferroviário. Valores não são projeto.
    Trilhos têm 1.600 mm entre as faces internas dos boletos ilustrativos.
    Todas as posições são locais; Shape.tessellate deve ser convertido uma só
    vez mm -> m antes de aplicar a matriz, conforme interop_freecad.
    """
    if not isinstance(pacote, dict) or not isinstance(pacote.get("meta"), dict):
        raise ValueError("publicação deve declarar metadados")
    if pacote["meta"].get("ficticio") is not True or pacote["meta"].get("source_app") != "FreeCAD":
        raise ValueError("exigida publicação fictícia do adaptador FreeCAD")
    por_id = _metadados(pacote)
    pontos = por_id[_IDS["SUE"]].get("pontos_locais_m")
    if (not isinstance(pontos, list) or len(pontos) != 2
            or any(not isinstance(p, list) or len(p) != 3 for p in pontos)
            or any(type(v) not in (int, float) or not math.isfinite(v) for p in pontos for v in p)):
        raise ValueError("matriz deve ter origem finita em pontos_locais_m")
    if pontos[0][:2] == pontos[1][:2]:
        raise ValueError("eixo local horizontal degenerado")
    # Mantém a mesma origem/rotação da prova anterior, sem importar biblioteca CAD.
    _, matriz = preparar_componentes(pacote)
    if any(not math.isfinite(float(v)) for linha in matriz for v in linha):
        raise ValueError("matriz da publicação deve ser finita")
    descritores = []

    def caixa(nome, grupo, papel, dimensoes, posicao, material="concreto"):
        if len(dimensoes) != 3 or len(posicao) != 3 or any(d <= 0 for d in dimensoes):
            raise ValueError("caixa deve ter três dimensões positivas")
        props = por_id[_IDS[grupo]]
        descritores.append({
            "nome": nome, "atividade_id": _IDS[grupo],
            "dimensoes_mm": list(dimensoes), "posicao_mm": list(posicao),
            "unidade_planejamento": props["unidade"],
            "quantidade_planejamento": props["quantidade_total"],
            "quantidade_executada": props["quantidade_executada"],
            "material": material, "cor": list(_CORES[material]), "papel": papel,
            "ilustrativa": True, "abrangencia": "trecho parcial de 36 m; atividade abrange 400 m",
        })

    # Apoios nas estações -18/-6/+6/+18 m. Blocos, pilares, travessas e aparelhos
    # se encontram por faces; os sólidos permanecem separados e editáveis.
    for apoio, x in enumerate((-18000, -6000, 6000, 18000), 1):
        caixa(f"OAE3_FUN_BLOCO_A{apoio:02}", "FUN", "bloco", (4000, 6000, 1500), (x - 2000, -3000, -11500))
        for fila, dx in enumerate((-1000, 1000), 1):
            for coluna, y in enumerate((-2000, 0, 2000), 1):
                caixa(f"OAE3_FUN_ESTACA_A{apoio:02}_F{fila}_C{coluna}", "FUN", "estaca",
                      (500, 500, 6000), (x + dx - 250, y - 250, -17500))
        for lado, y in (("E", -2000), ("D", 2000)):
            caixa(f"OAE3_MES_PILAR_A{apoio:02}_{lado}", "MES", "pilar",
                  (1200, 1200, 8550), (x - 600, y - 600, -10000))
        caixa(f"OAE3_MES_TRAVESSA_A{apoio:02}", "MES", "travessa",
              (1400, 6500, 800), (x - 700, -3250, -1450))

    for vao in range(3):
        inicio = -18000 + vao * 12000
        a, comprimento = inicio + 50, 11900  # junta ilustrativa de 100 mm entre vãos
        tag = f"V{vao + 1:02}"
        caixa(f"OAE3_SUE_TABULEIRO_{tag}", "SUE", "tabuleiro", (comprimento, 7500, 600), (a, -3750, 1250))
        for lado, y in (("E", -2500), ("D", 2500)):
            caixa(f"OAE3_SUE_VIGA_{tag}_{lado}", "SUE", "viga", (comprimento, 600, 1700), (a, y - 300, -450))
            for extremidade, x in (("INI", inicio + 400), ("FIM", inicio + 11600)):
                caixa(f"OAE3_MES_APOIO_{tag}_{lado}_{extremidade}", "MES", "apoio",
                      (600, 700, 200), (x - 300, y - 350, -650), "apoio")
        for lado, y in (("E", -3250), ("D", 3250)):
            caixa(f"OAE3_SUE_PASSEIO_{tag}_{lado}", "SUE", "passeio", (comprimento, 1000, 350), (a, y - 500, 1850))
        for lado, y in (("E", -3600), ("D", 3600)):
            for poste in range(6):
                x = a + 200 + poste * 2300
                caixa(f"OAE3_SUE_POSTE_{tag}_{lado}_{poste + 1:02}", "SUE", "poste_guarda_corpo",
                      (100, 100, 1100), (x - 50, y - 50, 2200), "aco")
            caixa(f"OAE3_SUE_CORRIMAO_{tag}_{lado}", "SUE", "corrimao",
                  (11600, 100, 100), (a + 150, y - 50, 3300), "aco")

        # Seção em degraus aproxima visualmente o lastro trapezoidal sem usar
        # booleanas CAD ou sólidos intersectantes. Não é composição de orçamento.
        for nivel, (largura, z, h) in enumerate(((5200, 1850, 150), (4200, 2000, 150), (3400, 2150, 50)), 1):
            caixa(f"VIA_LAS_{tag}_N{nivel}", "LAS", "lastro", (comprimento, largura, h), (a, -largura / 2, z), "lastro")

        # Perfil de trilho em três caixas tocantes. Boletos de 75 mm, centros a
        # +/-837,5 mm: vão livre entre faces internas = 1600 mm, sem norma alegada.
        for lado, y in (("E", -837.5), ("D", 837.5)):
            for nome, largura, z, h in (("PATIM", 180, 2340, 30), ("ALMA", 35, 2370, 130), ("BOLETO", 75, 2500, 40)):
                caixa(f"VIA_GRA_{tag}_{lado}_{nome}", "GRA", "trilho_" + nome.lower(),
                      (comprimento, largura, h), (a, y - largura / 2, z), "aco")

    # Sessenta dormentes a 600 mm, sem ocupar as juntas entre os vãos.
    for i, x in enumerate(range(-17700, 18000, 600), 1):
        caixa(f"VIA_DOR_D{i:03}", "DOR", "dormente", (240, 2800, 140), (x - 120, -1400, 2200), "dormente")
    return descritores, matriz
