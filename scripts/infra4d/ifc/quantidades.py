"""Quantidades por peça (BIM → 4D/5D): geometria da peça → Qto oficial IFC 4.3 + quantidade do serviço.

Duas quantidades por elemento, que NÃO se confundem:

- **geométrica**: medida da própria geometria esquemática da peça (prismas trapezoidais do
  exportador: volume = Σ área_da_seção × comprimento da corda). Vai para os ``Qto_*BaseQuantities``
  OFICIAIS da classe (nomes conferidos contra o template de Qto do IFC4X3 que acompanha o
  IfcOpenShell — há teste) e para ``INFRA4D_Quantidade.QuantidadeGeometrica``.
- **contratual**: ``quantidade_total`` da atividade rateada entre as suas peças (inteiros por maior
  resto quando a unidade é ``un``). Vai para ``INFRA4D_Quantidade.QuantidadeContratual`` e é a que
  liga o modelo ao orçamento (5D) sem mudar o total.

A razão geométrica/contratual por serviço é REPORTADA (``coerencia``), não escondida: a peça é
esquemática (seção tirada do visualizador), então ela não reproduz a quantidade de projeto.

Unidades: o modelo está em SI (m, m², m³, kg). A unidade do serviço define o TIPO da quantidade:
m³ → IfcQuantityVolume; m e km → IfcQuantityLength; m² e ha → IfcQuantityArea;
t → IfcQuantityWeight (kg no modelo); un → IfcQuantityCount (inteiro: IfcCountMeasure no IFC4X3_ADD2).
"""

from __future__ import annotations

import math

QSET_SERVICO = "INFRA4D_Quantidade"

# unidade do serviço → (tipo IFC da quantidade, fator: valor no modelo (SI) = valor_na_unidade × fator)
UNIDADES = {
    "m³": ("IfcQuantityVolume", 1.0),
    "m": ("IfcQuantityLength", 1.0),
    "km": ("IfcQuantityLength", 1000.0),
    "m²": ("IfcQuantityArea", 1.0),
    "ha": ("IfcQuantityArea", 10000.0),
    "t": ("IfcQuantityWeight", 1000.0),
    "kg": ("IfcQuantityWeight", 1.0),
    "un": ("IfcQuantityCount", 1.0),
}
ATRIBUTO_VALOR = {"IfcQuantityVolume": "VolumeValue", "IfcQuantityLength": "LengthValue",
                  "IfcQuantityArea": "AreaValue", "IfcQuantityWeight": "WeightValue",
                  "IfcQuantityCount": "CountValue"}

# Premissa FICTÍCIA do protótipo (não vem do dataset nem do R06): massa específica do CBUQ
# compactado, para levar volume da peça a toneladas. Valor típico de literatura, declarado no R07.
DENSIDADE_T_M3 = {"CBU": 2.4}

# Qto OFICIAL por classe: (nome do conjunto, {quantidade: (tipo IFC, chave da medida)})
# Medidas: comprimento_eixo, comprimento_total, largura, espessura, area_secao, area_planta, volume, altura
QTO_OFICIAL = {
    "IfcEarthworksFill": ("Qto_EarthworksFillBaseQuantities", {
        "Length": ("IfcQuantityLength", "comprimento_eixo"), "Width": ("IfcQuantityLength", "largura"),
        "Depth": ("IfcQuantityLength", "espessura"), "CompactedVolume": ("IfcQuantityVolume", "volume")}),
    "IfcEarthworksCut": ("Qto_EarthworksCutBaseQuantities", {
        "Length": ("IfcQuantityLength", "comprimento_eixo"), "Width": ("IfcQuantityLength", "largura"),
        "Depth": ("IfcQuantityLength", "espessura"), "UndisturbedVolume": ("IfcQuantityVolume", "volume")}),
    "IfcCourse": ("Qto_CourseBaseQuantities", {
        "Length": ("IfcQuantityLength", "comprimento_eixo"), "Width": ("IfcQuantityLength", "largura"),
        "Thickness": ("IfcQuantityLength", "espessura"), "Volume": ("IfcQuantityVolume", "volume")}),
    "IfcPavement": ("Qto_PavementBaseQuantities", {
        "Length": ("IfcQuantityLength", "comprimento_eixo"), "Width": ("IfcQuantityLength", "largura"),
        "Depth": ("IfcQuantityLength", "espessura"), "GrossArea": ("IfcQuantityArea", "area_planta"),
        "NetArea": ("IfcQuantityArea", "area_planta"), "GrossVolume": ("IfcQuantityVolume", "volume"),
        "NetVolume": ("IfcQuantityVolume", "volume")}),
    "IfcPipeSegment": ("Qto_PipeSegmentBaseQuantities", {
        "Length": ("IfcQuantityLength", "comprimento_total"),
        "GrossCrossSectionArea": ("IfcQuantityArea", "area_secao")}),
    "IfcRail": ("Qto_RailBaseQuantities", {
        "Length": ("IfcQuantityLength", "comprimento_total"), "Volume": ("IfcQuantityVolume", "volume")}),
    "IfcRailing": ("Qto_RailingBaseQuantities", {"Length": ("IfcQuantityLength", "comprimento_total")}),
    "IfcSurfaceFeature": ("Qto_SurfaceFeatureBaseQuantities", {
        "Area": ("IfcQuantityArea", "area_planta"), "Length": ("IfcQuantityLength", "comprimento_total")}),
    "IfcSign": ("Qto_SignBaseQuantities", {
        "Height": ("IfcQuantityLength", "altura"), "Width": ("IfcQuantityLength", "largura")}),
    "IfcPile": ("Qto_PileBaseQuantities", {
        "GrossVolume": ("IfcQuantityVolume", "volume"), "NetVolume": ("IfcQuantityVolume", "volume")}),
    "IfcColumn": ("Qto_ColumnBaseQuantities", {
        "GrossVolume": ("IfcQuantityVolume", "volume"), "NetVolume": ("IfcQuantityVolume", "volume")}),
    "IfcBeam": ("Qto_BeamBaseQuantities", {
        "Length": ("IfcQuantityLength", "comprimento_eixo"), "GrossVolume": ("IfcQuantityVolume", "volume"),
        "NetVolume": ("IfcQuantityVolume", "volume")}),
    # IfcTrackElement, IfcFastener e IfcBuiltElement: o template IFC4X3 NÃO tem Qto_*BaseQuantities
    # para essas classes (só Qto_BodyGeometryValidation) → apenas INFRA4D_Quantidade.
}


def medidas(partes_xyz: list[tuple[tuple, tuple, dict]]) -> dict:
    """Medidas de uma peça a partir das partes [(ponto_a, ponto_b, seção)] em coordenadas do modelo (m)."""
    comp_total = volume = area_planta = 0.0
    trechos: dict[tuple, float] = {}
    for pa, pb, s in partes_xyz:
        L = math.dist(pa, pb)
        comp_total += L
        volume += (s["wb"] + s["wt"]) / 2 * s["t"] * L
        area_planta += s["wb"] * L
        trechos[(round(pa[0], 6), round(pa[1], 6), round(pb[0], 6), round(pb[1], 6))] = L
    s0 = max((p[2] for p in partes_xyz), key=lambda s: s["wb"])
    return {
        "comprimento_eixo": sum(trechos.values()),   # trechos distintos ao longo do eixo
        "comprimento_total": comp_total,              # metros lineares de material (linhas paralelas somam)
        "largura": s0["wb"], "espessura": max(p[2]["t"] for p in partes_xyz),
        "altura": max(p[2]["t"] for p in partes_xyz),
        "area_secao": (s0["wb"] + s0["wt"]) / 2 * s0["t"],
        "area_planta": area_planta, "volume": volume, "contagem": len(partes_xyz),
    }


def quantidade_geometrica(unidade: str, servico_id: str, m: dict) -> float | None:
    """Quantidade da peça NA UNIDADE DO SERVIÇO, derivada só da geometria (None = não derivável)."""
    if unidade == "m³":
        return m["volume"]
    if unidade == "m":
        return m["comprimento_total"]
    if unidade == "km":
        return m["comprimento_eixo"] / 1000.0
    if unidade == "m²":
        return m["area_planta"]
    if unidade == "ha":
        return m["area_planta"] / 10000.0
    if unidade == "t":
        dens = DENSIDADE_T_M3.get(servico_id)
        return None if dens is None else m["volume"] * dens
    if unidade == "un":
        return float(m["contagem"])
    return None


def rateio(total: float, n: int, inteiro: bool) -> list[float]:
    """Divide ``total`` entre ``n`` peças. Inteiro: maior resto (soma exata); senão, partes iguais."""
    if n <= 0:
        return []
    if not inteiro:
        return [total / n] * n
    base = [math.floor(total / n)] * n
    for i in range(int(round(total - sum(base)))):
        base[i] += 1
    return [float(x) for x in base]


def para_modelo(unidade: str, valor: float) -> float:
    return valor * UNIDADES[unidade][1]


def de_modelo(unidade: str, valor: float) -> float:
    return valor / UNIDADES[unidade][1]
