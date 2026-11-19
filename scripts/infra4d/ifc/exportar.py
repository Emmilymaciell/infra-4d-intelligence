"""Exporta a base sintética para IFC 4.3 (IFC4X3_ADD2) com IfcOpenShell — genérico por tipo de obra.

Estrutura gerada (``meta.tipo_obra`` / ``ferrovia.tipo``: "ferrovia" ou "rodovia")::

    IfcProject
     └ IfcSite
        └ IfcRailway | IfcRoad
           ├ IfcRailwayPart | IfcRoadPart  (um por lote, UsageType LONGITUDINAL)  ← elementos de linha
           │  ├ IfcGeographicElement TERRAIN (hospedeiro dos IfcEarthworksCut da supressão)
           │  └ IfcBridge (OAE do lote)
           │     └ IfcBridgePart FOUNDATION / PIER / SUPERSTRUCTURE  ← elementos da OAE
     IfcAlignment (agregado ao projeto, referenciado na instalação)
       horizontal semântico pelo método PI (vértices a cada km do eixo sintético) + representação "Axis"
     IfcWorkSchedule "Linha de base" com um IfcTask por atividade, IfcRelSequence por relação
       e IfcRelAssignsToProduct elemento → tarefa (a tarefa "produz" o elemento: 4D nativo)

Peças: mesma convenção do visualizador (``web/viewer3d.js`` + ``web/secoes.js``): serviços de
linha → uma peça por km (``n = max(1, round(km_fim - km_ini))``, arredondamento do JS); estilos
com ``marcadores`` → 4 blocos por peça; serviço sem estilo conhecido → camada genérica empilhada
(``IfcBuiltElement`` com ObjectType = serviço); estilo ``None`` (SIN, LIB) → sem peça. OAE →
superestrutura em ``vaos`` peças, fundação e mesoestrutura em ``vaos + 1`` apoios.
``ElementoId = <atividade_id>-E<nn>``.

SIMPLIFICAÇÕES DECLARADAS (protótipo, dados fictícios):
- Geometria: prismas trapezoidais (IfcExtrudedAreaSolid) extrudados na CORDA entre os km
  inicial e final de cada parte, com seção tirada do visualizador. Não é IfcSectionedSolidHorizontal
  nem posicionamento linear (IfcLinearPlacement) sobre o alinhamento.
- As peças seguem a polilinha ``alinhamento.pontos`` do JSON (km → x, y, cota). O IfcAlignment
  semântico usa os vértices de km inteiro dessa polilinha como PIs, com raio de concordância;
  por isso o eixo IFC passa *perto* (não exatamente) dos pontos intermediários.
- Sem perfil vertical semântico (IfcAlignmentVertical): a cota está só na geometria das peças.
- Sem georreferenciamento (IfcMapConversion): coordenadas locais em metros, origem no km 0.
- Terraplenagem não distingue corte de aterro no dado sintético → IfcEarthworksFill EMBANKMENT.
- Rodovia: camadas como elementos soltos por km (IfcCourse/IfcPavement), sem IfcPavement agregador.
"""

from __future__ import annotations

from ..obra import ErroTipoObra
from ..obra import tipo_obra as _tipo_declarado
import bisect
import math
import time
import uuid
from pathlib import Path

import numpy as np

import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.api.aggregate
import ifcopenshell.api.alignment
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit

from . import PSET_VINCULO, SCHEMA
from . import quantidades as qt
from ..referencia_linear import Eixo as EixoReferencia
from ..referencia_linear import Estaca

RAIZ = Path(__file__).resolve().parents[3]
SAIDA = RAIZ / "output" / "ifc"
SAIDA_PADRAO = SAIDA / "ferrovia_ficticia.ifc"

# Instalação por tipo de obra: (facility, parte por lote)
INSTALACAO = {"ferrovia": ("IfcRailway", "IfcRailwayPart"), "rodovia": ("IfcRoad", "IfcRoadPart")}

# Serviço → (classe IFC, PredefinedType, ObjectType se USERDEFINED)
CLASSES_COMUNS = {
    "SUP": ("IfcEarthworksCut", "TOPSOILREMOVAL", None),
    "TER": ("IfcEarthworksFill", "EMBANKMENT", None),
    "DRE": ("IfcPipeSegment", "CULVERT", None),
    "OAE-FUN": ("IfcPile", "NOTDEFINED", None),
    "OAE-MES": ("IfcColumn", "PIERSTEM", None),
    "OAE-SUE": ("IfcBeam", "GIRDER_SEGMENT", None),
}
CLASSES_POR_TIPO = {
    "ferrovia": {
        "SUB": ("IfcCourse", "USERDEFINED", "SUBBALLAST"),
        "LAS": ("IfcCourse", "BALLASTBED", None),
        "DOR": ("IfcTrackElement", "SLEEPER", None),
        "GRA": ("IfcRail", "RAIL", None),
        "SOL": ("IfcFastener", "WELD", None),
    },
    "rodovia": {
        "SBB": ("IfcCourse", "PAVEMENT", None),             # sub-base granular
        "BGS": ("IfcCourse", "PAVEMENT", None),             # base de brita graduada simples
        "IMP": ("IfcCourse", "USERDEFINED", "PRIMECOAT"),   # imprimação (película sobre a base)
        "CBU": ("IfcPavement", "FLEXIBLE", None),           # revestimento CBUQ
        "SHV": ("IfcSurfaceFeature", "LINEMARKING", None),  # sinalização horizontal (faixas)
        "SVV": ("IfcSign", "PICTORAL", None),               # sinalização vertical (placas)
        "DEF": ("IfcRailing", "GUARDRAIL", None),           # defensas
    },
}
# Onde uma marcação (IfcSurfaceFeature) adere, em ordem de preferência; sem nenhum → terreno do lote.
HOSPEDEIRO_SUPERFICIE = ("CBU", "IMP", "BGS", "SBB", "TER")
PARTE_OAE = {"OAE-FUN": "FOUNDATION", "OAE-MES": "PIER", "OAE-SUE": "SUPERSTRUCTURE"}


def _C(c, wb, wt, h0, t):
    return dict(c=c, wb=wb, wt=wt, h0=h0, t=t)


# Seções (m) espelhadas de web/secoes.js (COMUNS, POR_TIPO, ALIAS, camada genérica) e OAE_SEC de
# web/viewer3d.js: c = deslocamento lateral, wb/wt = base/topo, h0 = cota da base relativa ao eixo,
# t = espessura. ``None`` = serviço sem peça física. SE O JS MUDAR, ESTE BLOCO TEM DE ACOMPANHAR.
COMUNS = {
    "SUP": {"prismas": [_C(0, 26, 26, -0.14, 0.12)]},
    "DRE": {"prismas": [_C(-9.2, 1.4, 1.4, -0.1, 0.7), _C(9.2, 1.4, 1.4, -0.1, 0.7)]},
    "LIB": None,
}
POR_TIPO = {
    "ferrovia": {
        "TER": {"prismas": [_C(0, 17, 12, 0, 1.5)]},
        "SUB": {"prismas": [_C(0, 9.5, 8, 1.5, 0.35)]},
        "LAS": {"prismas": [_C(0, 5.2, 3.4, 1.85, 0.35)]},
        "DOR": {"prismas": [_C(0, 2.8, 2.8, 2.2, 0.14)]},
        "GRA": {"prismas": [_C(-0.8, 0.18, 0.18, 2.34, 0.2), _C(0.8, 0.18, 0.18, 2.34, 0.2)]},
        "SOL": {"prismas": [_C(0.8, 0.7, 0.7, 2.34, 0.6)], "marcadores": True},
        "SIN": None,
    },
    "rodovia": {
        "SUP": {"prismas": [_C(0, 38, 38, -0.14, 0.12)]},
        "DRE": {"prismas": [_C(-15.5, 1.4, 1.4, -0.1, 0.7), _C(15.5, 1.4, 1.4, -0.1, 0.7)]},
        "TER": {"prismas": [_C(0, 30, 26, 0, 1.2)]},
        "SBB": {"prismas": [_C(0, 26, 25.2, 1.2, 0.3)]},
        "BGS": {"prismas": [_C(0, 25.2, 24.4, 1.5, 0.2)]},
        "IMP": {"prismas": [_C(0, 24.4, 24.4, 1.7, 0.05)]},
        "CBU": {"prismas": [_C(0, 24.4, 23.8, 1.75, 0.12)]},
        "SHV": {"prismas": [_C(-11.4, 0.25, 0.25, 1.87, 0.04), _C(-3.7, 0.25, 0.25, 1.87, 0.04),
                            _C(-0.3, 0.2, 0.2, 1.87, 0.04), _C(0.3, 0.2, 0.2, 1.87, 0.04),
                            _C(3.7, 0.25, 0.25, 1.87, 0.04), _C(11.4, 0.25, 0.25, 1.87, 0.04)]},
        "SVV": {"prismas": [_C(-14, 0.5, 0.5, 1.2, 2.6), _C(14, 0.5, 0.5, 1.2, 2.6)], "marcadores": True},
        "DEF": {"prismas": [_C(-12.6, 0.35, 0.35, 1.87, 0.75), _C(12.6, 0.35, 0.35, 1.87, 0.75)]},
    },
}
ALIAS = {
    "rodovia": {"SBL": "SBB", "SUBBASE": "SBB", "BAS": "BGS", "CBUQ": "CBU", "REV": "CBU", "SIN": "SHV"},
    "ferrovia": {},
}
OAE_SEC = {
    "FUN": [_C(-2.6, 1.2, 1.2, -6, 3), _C(2.6, 1.2, 1.2, -6, 3)],
    "MES": [_C(0, 4.5, 3.2, -3, 5.7)],
    "SUE": [_C(0, 7.5, 7.5, 2.7, 0.6)],
}
_AUSENTE = object()


_NS_GUID = uuid.UUID("6f1c2d0e-4a4b-5c8e-9d3f-1b2a3c4d5e6f")  # namespace fixo do INFRA 4D


def guid_estavel(obra_id: str, chave: str) -> str:
    """GlobalId DETERMINÍSTICO (uuid5 → base64 do IFC): o mesmo elemento sai com o mesmo GlobalId em
    toda exportação, então GLB, tabela de vínculo e IFC baixados em momentos diferentes casam."""
    return ifcopenshell.guid.compress(uuid.uuid5(_NS_GUID, f"{obra_id}/{chave}").hex)


# Tolerância de posição das peças com IfcLinearPlacement (m). É a MESMA de
# project.yaml → verificacao.limites.tolerancia_posicao_ifc_m (test_ifc confere a igualdade).
TOLERANCIA_PROJECAO_M = 0.001


class ErroExportacao(ValueError):
    """O projeto não é exportável por este protótipo."""


def tipo_obra(dados: dict) -> str:
    """Tipo DECLARADO (P8): ``meta.tipo_obra`` pelo helper único; sem padrão "ferrovia". Ausente ou
    desconhecido vira ``ErroExportacao`` (a rota IFC já o traduz em 422 com o motivo)."""
    try:
        return _tipo_declarado(dados)
    except ErroTipoObra as e:
        raise ErroExportacao(f"exportação IFC cobre {sorted(INSTALACAO)}: {e}") from None


def classe_ifc(tipo: str, servico_id: str) -> tuple[str, str | None, str | None]:
    """(classe, PredefinedType, ObjectType). Serviço sem mapeamento → IfcBuiltElement genérico."""
    sid = ALIAS.get(tipo, {}).get(servico_id, servico_id)
    return (CLASSES_POR_TIPO.get(tipo, {}).get(sid) or CLASSES_COMUNS.get(sid)
            or ("IfcBuiltElement", None, servico_id))


def _js_round(x: float) -> int:
    """Math.round do JS (meio para cima), não o arredondamento bancário do Python."""
    return math.floor(x + 0.5)


def estilo_conhecido(tipo: str, sid: str):
    if tipo not in POR_TIPO:
        raise ErroExportacao(f"tipo de obra sem estilos: {tipo!r}")
    t = tipo
    sid = ALIAS.get(t, {}).get(sid, sid)
    if sid in POR_TIPO[t]:
        return POR_TIPO[t][sid]
    if sid in COMUNS:
        return COMUNS[sid]
    return _AUSENTE


def plano_de_estilos(dados: dict) -> dict:
    """Espelho de ``planoDeEstilos`` (web/secoes.js): {servico_id: estilo | None}."""
    tipo = tipo_obra(dados)
    t = tipo
    inicio: dict[str, str] = {}
    for a in dados["atividades"]:
        if a.get("tipo") != "tarefa" or not a.get("servico_id") or a.get("oae_id"):
            continue
        ini = a.get("inicio_lb") or "9999"
        if a["servico_id"] not in inicio or ini < inicio[a["servico_id"]]:
            inicio[a["servico_id"]] = ini
    estilos, genericos = {}, []
    for sid in inicio:
        e = estilo_conhecido(tipo, sid)
        if e is _AUSENTE:
            genericos.append(sid)
        else:
            estilos[sid] = e
    genericos.sort(key=lambda s: (inicio[s], s))
    topo = 0.0
    for e in {**COMUNS, **POR_TIPO[t]}.values():
        if e and not e.get("marcadores"):
            topo = max([topo] + [p["h0"] + p["t"] for p in e["prismas"]])
    h = topo + 0.15
    for i, sid in enumerate(genericos):
        w = max(2.5, 7 - i * 0.8)
        estilos[sid] = {"prismas": [_C(0, w, w, h, 0.22)], "generico": True}
        h += 0.3
    return estilos


# ---------------------------------------------------------------------------
# Peças (independente de IFC: é a convenção elemento ↔ atividade)
# ---------------------------------------------------------------------------

def pecas(dados: dict) -> list[dict]:
    """Lista de peças {elemento_id, atividade, i, n, partes=[(km_a, km_b, secao)]}."""
    oaes = {o["id"]: o for o in dados.get("oaes", [])}
    plano = plano_de_estilos(dados)
    saida = []
    for a in dados["atividades"]:
        if a.get("tipo") != "tarefa" or a.get("km_ini") is None or a.get("km_fim") is None:
            continue
        lista: list[list] = []
        if a.get("oae_id"):
            k0, k1 = float(a["km_ini"]), float(a["km_fim"])
            o = oaes.get(a["oae_id"])
            tipo = (a.get("servico_id") or "").replace("OAE-", "")
            sec = OAE_SEC.get(tipo)
            if not o or not sec:
                continue
            vaos = o.get("vaos") or 3
            dk = (k1 - k0) / vaos
            if tipo == "SUE":
                for i in range(vaos):
                    lista.append([(k0 + i * dk + 0.004, k0 + (i + 1) * dk - 0.004, s) for s in sec])
            else:
                meia = 0.004 if tipo == "FUN" else 0.006
                for i in range(vaos + 1):
                    k = k0 + i * dk
                    lista.append([(k - meia, k + meia, s) for s in sec])
        else:
            estilo = plano.get(a.get("servico_id"))
            if not estilo:
                continue  # sem peça física (SIN, LIB) ou sem serviço
            k0, k1 = sorted((float(a["km_ini"]), float(a["km_fim"])))
            if k1 - k0 < 1e-6:
                continue
            sec = estilo["prismas"]
            n = max(1, _js_round(k1 - k0))
            dk = (k1 - k0) / n
            for i in range(n):
                ka = k0 + i * dk
                kb = ka + dk
                if estilo.get("marcadores"):
                    lista.append([(ka + f * dk - 0.006, ka + f * dk + 0.006, s)
                                  for f in (0.125, 0.375, 0.625, 0.875) for s in sec])
                else:
                    lista.append([(ka + 0.003, kb - 0.003, s) for s in sec])
        for i, partes in enumerate(lista):
            saida.append({"elemento_id": f"{a['id']}-E{i + 1:02d}", "atividade": a, "i": i, "n": len(lista),
                          "partes": partes})
    return saida

class Eixo:
    """Interpola (x, y, cota) por km na polilinha ``alinhamento.pontos`` [km, x, y, cota]."""

    def __init__(self, pontos: list[list[float]]):
        self.p = sorted(pontos)
        self.km = [q[0] for q in self.p]

    def __call__(self, km: float) -> tuple[float, float, float]:
        j = min(max(bisect.bisect_right(self.km, km), 1), len(self.km) - 1)
        a, b = self.p[j - 1], self.p[j]
        f = 0.0 if b[0] == a[0] else (km - a[0]) / (b[0] - a[0])
        return tuple(a[k] + f * (b[k] - a[k]) for k in (1, 2, 3))


# ---------------------------------------------------------------------------
# Geometria
# ---------------------------------------------------------------------------

def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def _solido(f, origem, pa, pb, s, R=None):
    """Prisma trapezoidal de pa a pb (coords absolutas), em coords relativas à origem do elemento.

    ``R`` (3×3, colunas = eixos X, Y, Z do posicionamento do elemento em coordenadas do mundo): quando o
    elemento usa IfcLinearPlacement, o sistema local gira com a tangente do eixo; a posição e as
    direções do sólido são levadas para esse sistema (Rᵀ·v), e a peça fica no MESMO lugar no mundo."""
    d = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
    comp = math.sqrt(sum(c * c for c in d))
    z = _norm(d)
    x = _norm((-z[1], z[0], 0.0))  # lateral horizontal; y local = z × x ≈ para cima
    loc = tuple(pa[k] - origem[k] for k in range(3))
    if R is not None:
        loc, z, x = (tuple(R.T @ np.asarray(v, dtype=float)) for v in (loc, z, x))
    c, wb, wt, h0, t = s["c"], s["wb"], s["wt"], s["h0"], s["t"]
    pts = [(c - wb / 2, h0), (c + wb / 2, h0), (c + wt / 2, h0 + t), (c - wt / 2, h0 + t)]
    curva = f.createIfcPolyline([f.createIfcCartesianPoint((float(u), float(v))) for u, v in pts + pts[:1]])
    perfil = f.createIfcArbitraryClosedProfileDef("AREA", None, curva)
    pos = f.createIfcAxis2Placement3D(
        f.createIfcCartesianPoint(tuple(float(c) for c in loc)),
        f.createIfcDirection(tuple(float(c) for c in z)),
        f.createIfcDirection(tuple(float(c) for c in x)))
    return f.createIfcExtrudedAreaSolid(perfil, pos, f.createIfcDirection((0.0, 0.0, 1.0)), float(comp))


class CurvaEixo:
    """O eixo IFC (IfcCompositeCurve base do IfcAlignment) avaliado pelo PRÓPRIO IfcOpenShell:
    quadro (tangente X, normal à esquerda Y, Z para cima) e projeção de um ponto do mundo na curva
    (Newton sobre a distância ao longo, a partir do chute da polilinha do JSON).

    Avalia segmento a segmento (``alignment.evaluate_segment``): dá o MESMO quadro que
    ``evaluate_representation`` sobre a curva inteira (diferença 0 medida) e é ~40× mais rápido.
    ``alignment.generate_vertices`` NÃO funciona no 0.9.0.post1 ("Setting not available")."""

    def __init__(self, curva):
        self.curva = curva
        self.segmentos = list(curva.Segments)
        # SegmentLength tem SINAL (arco à direita percorre a circunferência-mãe ao contrário)
        comp = [abs(float(getattr(sg.SegmentLength, "wrappedValue", sg.SegmentLength))) for sg in self.segmentos]
        self.inicios = [0.0]
        for c in comp:
            self.inicios.append(self.inicios[-1] + c)
        self.comprimento = self.inicios[-1]

    def quadro(self, dist: float) -> tuple[np.ndarray, np.ndarray]:
        dist = min(max(float(dist), 0.0), self.comprimento)
        i = min(max(bisect.bisect_right(self.inicios, dist) - 1, 0), len(self.segmentos) - 1)
        M = np.asarray(ifcopenshell.api.alignment.evaluate_segment(self.segmentos[i], dist - self.inicios[i])).T
        return M[:3, :3], M[:3, 3]

    def _amostrar(self, passo: float = 50.0) -> None:
        """Amostra da curva (≥ 3 pontos por segmento, ≤ ``passo`` m) para o chute GLOBAL da projeção."""
        ds, pts = [], []
        for i, sg in enumerate(self.segmentos):
            comp = self.inicios[i + 1] - self.inicios[i]
            n = max(3, math.ceil(comp / passo) + 1)
            for j in range(n if i == len(self.segmentos) - 1 else n - 1):
                d = self.inicios[i] + comp * j / (n - 1)
                ds.append(d)
                pts.append(self.quadro(d)[1])
        self._ds = np.asarray(ds)
        self._pts = np.asarray(pts)

    def _dist2(self, P: np.ndarray, d: float) -> float:
        o = self.quadro(d)[1]
        return float(np.dot(P - o, P - o))

    def projetar(self, ponto, chute: float | None = None) -> dict:
        """Pé da perpendicular do ponto na curva: busca GLOBAL na amostra (não depende do chute; r15: com
        deflexão > ~100° o Newton a partir do chute oscilava e o resíduo de 112 m era aceito), refino de
        Newton dentro do intervalo entre as amostras vizinhas e, se não convergir, seção áurea.

        Ponto ANTES do início ou DEPOIS do fim do eixo (r15: a distância era presa em [0, L] e a peça saía
        deslocada em silêncio): a componente ao longo da tangente na ponta vai em ``longitudinal``
        (IfcPointByDistanceExpression.OffsetLongitudinal). Qualquer resíduo restante acima de
        ``TOLERANCIA_PROJECAO_M`` é ERRO (``ErroExportacao``), nunca peça fora do lugar."""
        if not hasattr(self, "_ds"):
            self._amostrar()
        P = np.asarray(ponto, dtype=float)
        dif = self._pts - P
        i = int(np.argmin(np.einsum("ij,ij->i", dif, dif)))
        lo, hi = float(self._ds[max(i - 1, 0)]), float(self._ds[min(i + 1, len(self._ds) - 1)])
        dist, convergiu = float(self._ds[i]), False
        for _ in range(15):
            R, o = self.quadro(dist)
            novo = min(max(dist + float(np.dot(P - o, R[:, 0])), lo), hi)
            if abs(novo - dist) < 1e-9:
                dist, convergiu = novo, True
                break
            dist = novo
        if not convergiu:  # seção áurea no intervalo [lo, hi]
            g = (math.sqrt(5) - 1) / 2
            a_, b_ = lo, hi
            c_, d_ = b_ - g * (b_ - a_), a_ + g * (b_ - a_)
            fc, fd = self._dist2(P, c_), self._dist2(P, d_)
            for _ in range(80):
                if fc < fd:
                    b_, d_, fd = d_, c_, fc
                    c_ = b_ - g * (b_ - a_)
                    fc = self._dist2(P, c_)
                else:
                    a_, c_, fc = c_, d_, fd
                    d_ = a_ + g * (b_ - a_)
                    fd = self._dist2(P, d_)
                if b_ - a_ < 1e-9:
                    break
            dist = (a_ + b_) / 2
        R, o = self.quadro(dist)
        v = P - o
        tang = float(np.dot(v, R[:, 0]))
        longitudinal = 0.0
        if (dist <= 1e-9 and tang < 0) or (dist >= self.comprimento - 1e-9 and tang > 0):
            longitudinal = tang  # fora da extensão do eixo: prolonga pela tangente da ponta
        v = v - longitudinal * R[:, 0]
        lat, vert = float(np.dot(v, R[:, 1])), float(np.dot(v, R[:, 2]))
        residuo = float(np.linalg.norm(v - lat * R[:, 1] - vert * R[:, 2]))
        if residuo > TOLERANCIA_PROJECAO_M:
            raise ErroExportacao(
                f"projeção no eixo IFC sem solução dentro da tolerância: ponto {tuple(round(c, 3) for c in P)} "
                f"fica {residuo:.3f} m fora do pé da perpendicular (distância {dist:.3f} m) — "
                f"tolerância {TOLERANCIA_PROJECAO_M} m")
        return {"dist": dist, "lateral": lat, "vertical": vert, "longitudinal": longitudinal,
                "R": R, "o": o, "residuo": residuo}


def _comprimento_polilinha(pontos) -> list[tuple[float, float]]:
    """[(km, comprimento acumulado em planta)] da polilinha do JSON: chute inicial da projeção."""
    acc, out = 0.0, []
    pts = sorted(pontos)
    for i, q in enumerate(pts):
        if i:
            acc += math.dist(pts[i - 1][1:3], q[1:3])
        out.append((q[0], acc))
    return out


def _chute(tabela, km: float) -> float:
    kms = [t[0] for t in tabela]
    j = min(max(bisect.bisect_right(kms, km), 1), len(kms) - 1)
    (k0, c0), (k1, c1) = tabela[j - 1], tabela[j]
    return c0 + (c1 - c0) * (0.0 if k1 == k0 else (km - k0) / (k1 - k0))


def _posicionamento_linear(f, curva: CurvaEixo, proj: dict):
    loc = f.create_entity("IfcPointByDistanceExpression",
                          DistanceAlong=f.create_entity("IfcLengthMeasure", float(proj["dist"])),
                          OffsetLateral=float(proj["lateral"]), OffsetVertical=float(proj["vertical"]),
                          OffsetLongitudinal=float(proj["longitudinal"]) if proj.get("longitudinal") else None,
                          BasisCurve=curva.curva)
    # CartesianPosition (posição "de reserva" para leitores sem avaliação de curva) calculada aqui com o
    # MESMO quadro: alignment.update_fallback_position faz o núcleo C++ despejar linhas de depuração em
    # UTF-16 no stdout ("local z: … delta: …") a cada chamada — inaceitável dentro da API.
    R = proj["R"]
    ponto = (proj["o"] + proj.get("longitudinal", 0.0) * R[:, 0] + proj["lateral"] * R[:, 1]
             + proj["vertical"] * R[:, 2])
    cart = f.createIfcAxis2Placement3D(f.createIfcCartesianPoint(tuple(float(c) for c in ponto)),
                                       f.createIfcDirection(tuple(float(c) for c in R[:, 2])),
                                       f.createIfcDirection(tuple(float(c) for c in R[:, 0])))
    return f.create_entity("IfcLinearPlacement",
                           RelativePlacement=f.create_entity("IfcAxis2PlacementLinear", Location=loc),
                           CartesianPosition=cart)


def _estacao_de_volta(estaq, i: int, m: float) -> float:
    """Estaca (m) do trecho ANTERIOR à equação i no ponto m, na MEDIDA do projeto (referencia_linear)."""
    m0, s0 = estaq.zonas[i - 1]
    return s0 + m if i - 1 == 0 else s0 + (m - m0)


def _referentes(f, alinhamento, curva: CurvaEixo, eixo, tabela, dados: dict) -> dict:
    """Estaqueamento no IfcAlignment, coerente com ``referencia_linear``.

    O km do projeto é uma MEDIDA (como a coordenada M), não o comprimento geométrico do eixo IFC
    (60 km de medida ≈ 60,28 km de curva na ferrovia). O IFC 4.3 calcula a estaca entre referentes
    como ``Station + distância ao longo``; para que ele dê a estaca do projeto em CADA km, cada km
    inteiro vira um IfcReferent STATION com:

    - ``Pset_Stationing.Station`` = estaca do projeto naquele km (m), a mesma de ``/api/referencia/km``;
    - ``Pset_Stationing.IncomingStation`` = estaca que o IFC traria por continuidade geométrica desde o
      referente anterior (= equação de calibração; no km inicial não há);
    - ``IfcLinearPlacement`` no ponto do eixo IFC que é a projeção do ponto do km.

    Equações de estacas do projeto (``meta.equacoes_estaca``) entram do mesmo jeito; a estaca "de volta"
    na medida do projeto fica em ``INFRA4D_Referencia.EstacaAnteriorMedida``. Entre dois km a
    estaca IFC cresce 1 m por metro de curva e a do projeto 1 m por metro de medida: a diferença
    (≤ comprimento do km − 1000 m) é declarada no R07."""
    ref = EixoReferencia.da_obra(dados)
    estaq = ref.estaqueamento
    km0, km1 = ref.km_inicial, ref.km_final
    pontos: dict[float, dict] = {}
    k = math.ceil(km0 - 1e-9)
    while k <= km1 + 1e-9:
        pontos[float(k)] = {"tipo": "km"}
        k += 1
    for i, (m, _s) in enumerate(estaq.zonas[1:], start=1):
        km = m / 1000.0
        if km0 - 1e-9 <= km <= km1 + 1e-9:
            pontos.setdefault(round(km, 9), {"tipo": "km"})
            pontos[round(km, 9)].update(tipo="equacao", volta_medida=_estacao_de_volta(estaq, i, m))
    nest = ifcopenshell.api.alignment.get_stationing_nest(f, alinhamento)
    inicio = next((r for r in (nest.RelatedObjects if nest else ()) if r.is_a("IfcReferent")), None)

    def _pset_ref(r, km, extra=None):
        ps = ifcopenshell.api.pset.add_pset(f, product=r, name="INFRA4D_Referencia")
        ifcopenshell.api.pset.edit_pset(f, pset=ps, properties={"Km": float(km), **(extra or {})})

    anterior = None  # (distância ao longo, estaca)
    n_km = n_eq = 0
    if inicio is not None:  # criado por create_by_pi_method(start_station=estaca do km inicial)
        est0 = estaq.km_para_estaca(km0)
        inicio.Name, inicio.Description = est0.texto(), f"início do eixo · km {km0:g}"
        _pset_ref(inicio, km0)
        anterior = (0.0, est0.metros)
        pontos.pop(float(km0), None)
    for km in sorted(pontos):
        info = pontos[km]
        dist = curva.projetar(eixo(km), _chute(tabela, km))["dist"]
        est = estaq.km_para_estaca(km)
        volta = None if anterior is None else anterior[1] + (dist - anterior[0])
        r = ifcopenshell.api.alignment.add_stationing_referent(
            f, name=est.texto(), alignment=alinhamento, distance_along=dist, station=est.metros,
            incoming_station=volta)
        r.GlobalId = guid_estavel(dados["ferrovia"]["id"], f"estaca/{km:.6f}")
        if info["tipo"] == "equacao":
            r.Description = f"equação de estacas · km {km:g}"
            _pset_ref(r, km, {"EstacaAnteriorMedida": float(info["volta_medida"])})
            n_eq += 1
        else:
            r.Description = f"km {km:g} (calibração medida → curva)"
            _pset_ref(r, km)
            n_km += 1
        anterior = (dist, est.metros)
    return {"kilopoints": n_km, "equacoes": n_eq}


def _posicionamento(f, ponto, rel=None):
    eixo = f.createIfcAxis2Placement3D(f.createIfcCartesianPoint(tuple(float(c) for c in ponto)), None, None)
    return f.createIfcLocalPlacement(rel, eixo)


def _sem_colineares(pis: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Tira PIs internos sem deflexão: ``alignment.create_by_pi_method`` (0.9.0.post1) dá
    ZeroDivisionError com PIs colineares, e o exportador cairia no fallback de polilinha."""
    out = list(pis[:1])
    for i in range(1, len(pis) - 1):
        a, b, c = out[-1], pis[i], pis[i + 1]
        cruz = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cruz) > 1e-9 * max(1.0, math.dist(a, b) * math.dist(b, c)):
            out.append(b)
    return out + list(pis[-1:]) if len(pis) > 1 else out


def _raios_pi(pis: list[tuple[float, float]], teto: float = 5000.0) -> list[float]:
    """Raio por PI interno que cabe na tangente (T = R·tan(Δ/2) ≤ 45% da menor tangente)."""
    raios = []
    for i in range(1, len(pis) - 1):
        a1 = math.atan2(pis[i][1] - pis[i - 1][1], pis[i][0] - pis[i - 1][0])
        a2 = math.atan2(pis[i + 1][1] - pis[i][1], pis[i + 1][0] - pis[i][0])
        delta = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
        lmin = min(math.dist(pis[i - 1], pis[i]), math.dist(pis[i], pis[i + 1]))
        raios.append(teto if delta < 1e-9 else min(teto, 0.45 * lmin / math.tan(delta / 2)))
    return raios


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------

def _quantidade(f, tipo_ifc: str, nome: str, valor: float, descricao: str | None = None):
    if tipo_ifc == "IfcQuantityCount":
        valor = int(round(valor))
    return f.create_entity(tipo_ifc, Name=nome, Description=descricao,
                           **{qt.ATRIBUTO_VALOR[tipo_ifc]: valor})


def _conjunto(f, el, nome: str, quantidades: list, metodo: str | None = None) -> None:
    eq = f.create_entity("IfcElementQuantity", GlobalId=ifcopenshell.guid.new(), Name=nome,
                         MethodOfMeasurement=metodo, Quantities=quantidades)
    f.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[el],
                    RelatingPropertyDefinition=eq)


def _gravar_quantidades(f, el, classe: str, serv: str, unidade: str | None, med: dict,
                        contratual: float | None) -> None:
    """Qto oficial da classe (se o template IFC4X3 tiver) + INFRA4D_Quantidade na unidade do serviço."""
    if classe in qt.QTO_OFICIAL:
        nome, campos = qt.QTO_OFICIAL[classe]
        qs = [_quantidade(f, tipo_ifc, q, med[chave]) for q, (tipo_ifc, chave) in campos.items()
              if med.get(chave) is not None]
        _conjunto(f, el, nome, qs, "geometria esquemática da peça (prismas do protótipo)")
    if not unidade or unidade not in qt.UNIDADES:
        return
    tipo_ifc = qt.UNIDADES[unidade][0]
    qs = []
    geo = qt.quantidade_geometrica(unidade, serv, med)
    if geo is not None:
        nota = f"unidade do serviço: {unidade}; valor em unidade SI do modelo; da geometria esquemática"
        if serv in qt.DENSIDADE_T_M3:
            nota += f"; massa específica premissa fictícia {qt.DENSIDADE_T_M3[serv]} t/m³"
        qs.append(_quantidade(f, tipo_ifc, "QuantidadeGeometrica", qt.para_modelo(unidade, geo), nota))
    if contratual is not None:
        qs.append(_quantidade(f, tipo_ifc, "QuantidadeContratual", qt.para_modelo(unidade, contratual),
                              f"unidade do serviço: {unidade}; quantidade_total da atividade rateada por peça"))
    if qs:
        _conjunto(f, el, qt.QSET_SERVICO, qs, "INFRA 4D: quantidade na unidade do serviço")


class _Classificacao:
    """IfcClassification fictícia do orçamento + uma IfcClassificationReference por composição."""

    def __init__(self, f, tipo: str):
        from .. import orcamento  # composições FICTÍCIAS (5D); só leitura
        self.f = f
        self.comps = orcamento.COMPOSICOES.get(tipo, {})
        self.sistema = None
        if self.comps:
            self.sistema = f.create_entity("IfcClassification", Source="INFRA 4D", Edition="fictícia",
                                           Name=orcamento.SISTEMA_CLASSIFICACAO,
                                           Description="Composições FICTÍCIAS do orcamento.py (não são SICRO/SINAPI)")
        self.refs: dict[str, object] = {}
        self.objetos: dict[str, list] = {}

    def associar(self, el, serv: str) -> None:
        comp = self.comps.get(serv)
        if comp is None:
            return
        if comp["codigo"] not in self.refs:
            self.refs[comp["codigo"]] = self.f.create_entity(
                "IfcClassificationReference", Identification=comp["codigo"], Name=comp["descricao"],
                ReferencedSource=self.sistema, Description=f"unidade {comp['unidade']}")
        self.objetos.setdefault(comp["codigo"], []).append(el)

    def gravar(self) -> None:
        for cod, els in self.objetos.items():
            self.f.create_entity("IfcRelAssociatesClassification", GlobalId=ifcopenshell.guid.new(),
                                 RelatedObjects=els, RelatingClassification=self.refs[cod])
        if self.sistema is not None:  # a classificação é declarada no projeto
            proj = self.f.by_type("IfcProject")[0]
            self.f.create_entity("IfcRelAssociatesClassification", GlobalId=ifcopenshell.guid.new(),
                                 RelatedObjects=[proj], RelatingClassification=self.sistema)


CENARIOS_PADRAO = ("linha_base", "construtora", "independente")


def construir(dados: dict, incluir_4d: bool = True, posicionamento: str = "linear",
              cenarios: tuple[str, ...] | list[str] = CENARIOS_PADRAO,
              ajustes: list | None = None) -> tuple[ifcopenshell.file, dict]:
    """Monta o modelo IFC em memória. Devolve (arquivo, resumo).

    ``incluir_4d``: cronograma nativo por cenário (``cronograma.adicionar``), calculado pelo motor a
    partir de ``dados``; ``simulado`` só entra quando há ``ajustes``."""
    tipo = tipo_obra(dados)
    if tipo not in INSTALACAO:
        raise ErroExportacao(f"exportação IFC cobre {sorted(INSTALACAO)}; tipo de obra '{tipo}' sem mapeamento")
    classe_inst, classe_parte = INSTALACAO[tipo]
    t0 = time.perf_counter()
    api = ifcopenshell.api
    f = api.project.create_file(version=SCHEMA)
    fer = dados["ferrovia"]
    projeto = api.root.create_entity(f, ifc_class="IfcProject", name=fer["id"])
    projeto.LongName = fer["nome"]
    projeto.Description = dados["meta"]["aviso"]
    unidades = [api.unit.add_si_unit(f, unit_type=u) for u in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT", "PLANEANGLEUNIT")]
    unidades.append(api.unit.add_si_unit(f, unit_type="MASSUNIT", prefix="KILO"))  # Weight em kg
    api.unit.assign_unit(f, units=unidades)
    modelo = api.context.add_context(f, context_type="Model")
    corpo = api.context.add_context(f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW",
                                     parent=modelo)

    sitio = api.root.create_entity(f, ifc_class="IfcSite", name=f"Sítio {fer['id']} (fictício)")
    api.aggregate.assign_object(f, products=[sitio], relating_object=projeto)
    ferrovia = api.root.create_entity(f, ifc_class=classe_inst, name=fer["nome"])
    api.aggregate.assign_object(f, products=[ferrovia], relating_object=sitio)
    origem_global = _posicionamento(f, (0.0, 0.0, 0.0))
    sitio.ObjectPlacement = origem_global
    ferrovia.ObjectPlacement = _posicionamento(f, (0.0, 0.0, 0.0), origem_global)

    lotes, terrenos = {}, {}
    for lote in dados["lotes"]:
        parte = api.root.create_entity(f, ifc_class=classe_parte, name=lote["nome"],
                                       predefined_type="USERDEFINED")
        parte.ObjectType = "LOTE_CONTRATUAL"
        parte.UsageType = "LONGITUDINAL"
        parte.Description = f"{lote['id']}: km {lote['km_ini']}–{lote['km_fim']} · {lote.get('construtora', '')}"
        parte.ObjectPlacement = _posicionamento(f, (0.0, 0.0, 0.0), ferrovia.ObjectPlacement)
        api.aggregate.assign_object(f, products=[parte], relating_object=ferrovia)
        lotes[lote["id"]] = parte
        # IfcEarthworksCut é IfcFeatureElementSubtraction: a validação exige VoidsElements.
        # O "hospedeiro" é o terreno natural do lote, sem geometria neste protótipo.
        terreno = api.root.create_entity(f, ifc_class="IfcGeographicElement", name=f"Terreno natural {lote['id']}",
                                         predefined_type="TERRAIN")
        terreno.ObjectPlacement = _posicionamento(f, (0.0, 0.0, 0.0), parte.ObjectPlacement)
        terrenos[lote["id"]] = terreno
        api.spatial.assign_container(f, products=[terreno], relating_structure=parte)

    oae_partes: dict[tuple[str, str], object] = {}
    for o in dados.get("oaes", []):
        ponte = api.root.create_entity(f, ifc_class="IfcBridge", name=o["nome"])
        ponte.Description = f"{o['id']} · km {o['km']} · {o.get('vaos')} vãos"
        ponte.ObjectPlacement = _posicionamento(f, (0.0, 0.0, 0.0), lotes[o["lote_id"]].ObjectPlacement)
        api.aggregate.assign_object(f, products=[ponte], relating_object=lotes[o["lote_id"]])
        for serv, tipo_parte in PARTE_OAE.items():
            bp = api.root.create_entity(f, ifc_class="IfcBridgePart", name=f"{o['id']} {tipo_parte.lower()}",
                                        predefined_type=tipo_parte)
            bp.UsageType = "VERTICAL"  # obrigatório em IFC4X3_ADD2 (validação acusou)
            bp.ObjectPlacement = _posicionamento(f, (0.0, 0.0, 0.0), ponte.ObjectPlacement)
            api.aggregate.assign_object(f, products=[bp], relating_object=ponte)
            oae_partes[(o["id"], serv)] = bp

    # --- alinhamento
    pontos = dados["alinhamento"]["pontos"]
    eixo = Eixo(pontos)
    # PIs: o PRIMEIRO e o ÚLTIMO ponto da polilinha e os de km inteiro entre eles (r15: com só os de km
    # inteiro, um eixo que começa no km 0,3 tinha a curva começando no km 1 e a estaca inicial do km 0,3)
    ordenados = sorted(pontos)
    pis = _sem_colineares([(q[1], q[2]) for i, q in enumerate(ordenados)
                           if i in (0, len(ordenados) - 1) or abs(q[0] - round(q[0])) < 1e-9])
    alinhamento_modo = "IfcAlignmentHorizontal (método PI) + representação Axis"
    try:
        alinhamento = api.alignment.create_by_pi_method(f, f"{fer['id']} eixo", pis, _raios_pi(pis),
                                                        start_station=EixoReferencia.da_obra(dados).estaqueamento.km_para_estaca(sorted(pontos)[0][0]).metros)
    except Exception as e:  # pragma: no cover - fallback declarado
        alinhamento_modo = f"IfcPolyline (fallback; PI falhou: {e})"
        alinhamento = api.alignment.create_as_polyline(
            f, f"{fer['id']} eixo", [f.createIfcCartesianPoint((float(x), float(y))) for x, y in pis])
    api.spatial.reference_structure(f, products=[alinhamento], relating_structure=ferrovia)
    curva_base = api.alignment.get_basis_curve(alinhamento)
    linear = posicionamento == "linear" and curva_base is not None and curva_base.is_a("IfcCompositeCurve")
    tabela = _comprimento_polilinha(pontos)
    curva = None
    n_ref = {"kilopoints": 0, "equacoes": 0}
    if linear:
        curva = CurvaEixo(curva_base)
        n_ref = _referentes(f, alinhamento, curva, eixo, tabela, dados)
    residuo_max = 0.0

    # --- elementos
    elementos_por_atividade: dict[str, list] = {}
    por_container: dict[int, list] = {}
    containers = {}
    indice: dict[tuple, object] = {}  # (segmento, serviço, i) → elemento, para hospedar marcações
    aderentes: list[tuple] = []
    lista_pecas = pecas(dados)
    unid_servico = {s_["id"]: s_.get("unidade") for s_ in dados.get("servicos", [])}
    n_por_atividade: dict[str, int] = {}
    for p in lista_pecas:
        n_por_atividade[p["atividade"]["id"]] = n_por_atividade.get(p["atividade"]["id"], 0) + 1
    contratual: dict[str, list[float]] = {}
    for aid, n in n_por_atividade.items():
        a = next(x for x in dados["atividades"] if x["id"] == aid)
        un = a.get("unidade") or unid_servico.get(a.get("servico_id"))
        if a.get("quantidade_total") is not None and un in qt.UNIDADES:
            contratual[aid] = qt.rateio(float(a["quantidade_total"]), n, inteiro=(un == "un"))
    classif = _Classificacao(f, tipo)
    for p in lista_pecas:
        a = p["atividade"]
        serv = a["servico_id"]
        classe, predef, objtipo = classe_ifc(tipo, serv)
        if predef:
            el = api.root.create_entity(f, ifc_class=classe, name=p["elemento_id"], predefined_type=predef)
        else:
            el = api.root.create_entity(f, ifc_class=classe, name=p["elemento_id"])
        el.GlobalId = guid_estavel(fer["id"], f"elemento/{p['elemento_id']}")
        if objtipo:
            el.ObjectType = objtipo
        el.Tag = p["elemento_id"]
        el.Description = f"{a.get('nome', a['id'])} — peça {p['i'] + 1}/{p['n']}"
        origem = eixo(p["partes"][0][0])
        R = None
        if linear:
            proj = curva.projetar(origem, _chute(tabela, p["partes"][0][0]))
            residuo_max = max(residuo_max, proj["residuo"])
            el.ObjectPlacement = _posicionamento_linear(f, curva, proj)
            R = proj["R"]
        else:
            el.ObjectPlacement = _posicionamento(f, origem, origem_global)
        solidos = [_solido(f, origem, eixo(ka), eixo(kb), s, R) for ka, kb, s in p["partes"]]
        rep = f.createIfcShapeRepresentation(corpo, "Body", "SweptSolid", solidos)
        el.Representation = f.createIfcProductDefinitionShape(None, None, [rep])
        km_a, km_b = p["partes"][0][0], p["partes"][-1][1]
        pset = api.pset.add_pset(f, product=el, name=PSET_VINCULO)
        props = {"AtividadeId": a["id"], "ElementoId": p["elemento_id"], "KmInicial": round(km_a, 4),
                 "KmFinal": round(km_b, 4), "ServicoId": serv, "LoteId": a.get("lote_id") or ""}
        if a.get("oae_id"):
            props["OaeId"] = a["oae_id"]
        un = a.get("unidade") or unid_servico.get(serv)
        if un:
            props["Unidade"] = un
        api.pset.edit_pset(f, pset=pset, properties=props)
        med = qt.medidas([(eixo(ka), eixo(kb), s_) for ka, kb, s_ in p["partes"]])
        _gravar_quantidades(f, el, classe, serv, un, med,
                            (contratual.get(a["id"]) or [None] * p["n"])[p["i"]])
        classif.associar(el, serv)
        if classe == "IfcEarthworksCut":
            # regra EXPRESS: elemento de subtração NÃO entra em IfcRelContainedInSpatialStructure
            # (herda a posição espacial do hospedeiro, que está contido no lote)
            f.createIfcRelVoidsElement(ifcopenshell.guid.new(), None, None, None, terrenos[a["lote_id"]], el)
            elementos_por_atividade.setdefault(a["id"], []).append(el)
            continue
        if el.is_a("IfcSurfaceFeature"):
            # regra do IFC4X3_ADD2: IfcSurfaceFeature exige AdheresToElement e não entra na estrutura
            # espacial. Hospedeiro = peça de revestimento do mesmo segmento e índice (resolvida depois).
            aderentes.append((el, a, p["i"]))
            elementos_por_atividade.setdefault(a["id"], []).append(el)
            continue
        indice[(a.get("segmento_id"), ALIAS.get(tipo, {}).get(serv, serv), p["i"])] = el
        cont = oae_partes[(a["oae_id"], serv)] if a.get("oae_id") else lotes[a["lote_id"]]
        containers[cont.id()] = cont
        por_container.setdefault(cont.id(), []).append(el)
        elementos_por_atividade.setdefault(a["id"], []).append(el)
    for cid, els in por_container.items():
        api.spatial.assign_container(f, products=els, relating_structure=containers[cid])
    classif.gravar()
    # Posicionamento em relação ao alinhamento (IFC 4.3 IfcRelPositions). As peças continuam com
    # IfcLocalPlacement (coordenadas do JSON); a estaca de cada uma está no Pset (KmInicial/KmFinal).
    todos = [el for els in elementos_por_atividade.values() for el in els]
    if todos:
        f.create_entity("IfcRelPositions", GlobalId=ifcopenshell.guid.new(), Name="Peças no eixo",
                        RelatingPositioningElement=alinhamento, RelatedProducts=todos)
    for el, a, i in aderentes:
        hosp = next((indice[k] for k in ((a.get("segmento_id"), h, i) for h in HOSPEDEIRO_SUPERFICIE)
                     if k in indice), terrenos[a["lote_id"]])
        f.create_entity("IfcRelAdheresToElement", GlobalId=ifcopenshell.guid.new(), RelatingElement=hosp,
                        RelatedSurfaceFeatures=[el])

    # --- 4D nativo: um IfcWorkSchedule por cenário, calendários, sequências e vínculo às peças
    n_tarefas = n_seq = 0
    cenarios_4d: list[str] = []
    if incluir_4d:
        from ..cenarios import Projeto
        from . import cronograma
        lista = list(cenarios) + (["simulado"] if ajustes and "simulado" not in cenarios else [])
        r4d = cronograma.adicionar(f, Projeto(dados), lista, elementos_por_atividade, ajustes=ajustes,
                                   guid=lambda chave: guid_estavel(fer["id"], chave))
        n_tarefas, n_seq, cenarios_4d = r4d["tarefas"], r4d["sequencias"], r4d["cenarios"]

    f.header.file_name.name = f"{fer['id']}.ifc"
    f.header.file_description.description = (
        "ViewDefinition [DesignTransferView]", "INFRA 4D prototipo - DADOS FICTICIOS")
    resumo = {
        "schema": f.schema_identifier,
        "tipo_obra": tipo,
        "instalacao": classe_inst,
        "posicionamento": "IfcLinearPlacement" if linear else "IfcLocalPlacement",
        "residuo_projecao_m": residuo_max,
        "referentes_km": n_ref["kilopoints"], "equacoes_estaca": n_ref["equacoes"],
        "elementos": len(lista_pecas),
        "atividades_com_elemento": len(elementos_por_atividade),
        "tarefas": n_tarefas,
        "sequencias": n_seq,
        "cenarios_4d": cenarios_4d,
        "alinhamento": alinhamento_modo,
        "segundos": round(time.perf_counter() - t0, 3),
    }
    return f, resumo


def exportar(dados: dict, caminho: Path | str | None = None, incluir_4d: bool = True,
             posicionamento: str = "linear", ajustes: list | None = None) -> dict:
    """Gera o IFC em ``caminho`` (padrão: output/ifc/<tipo>_ficticia.ifc, fora do Git). Devolve o resumo."""
    f, resumo = construir(dados, incluir_4d=incluir_4d, posicionamento=posicionamento, ajustes=ajustes)
    caminho = Path(caminho) if caminho else SAIDA / f"{tipo_obra(dados)}_ficticia.ifc"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    f.write(str(caminho))
    resumo["arquivo"] = str(caminho)
    resumo["bytes"] = caminho.stat().st_size
    return resumo


def para_texto(dados: dict, incluir_4d: bool = True, ajustes: list | None = None) -> str:
    """IFC (STEP) como texto, sem tocar o disco — usado pelo router."""
    f, _ = construir(dados, incluir_4d=incluir_4d, ajustes=ajustes)
    return f.to_string()


if __name__ == "__main__":  # PYTHONPATH=scripts python -m infra4d.ifc.exportar [caminho_do_json]
    import json
    import sys
    from ..cenarios import DATASET_PADRAO
    origem = Path(sys.argv[1]) if len(sys.argv) > 1 else DATASET_PADRAO
    print(json.dumps(exportar(json.loads(origem.read_text(encoding="utf-8-sig"))), ensure_ascii=False, indent=2))
