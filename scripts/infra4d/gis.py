"""Exportação GeoJSON (RFC 7946) para QGIS e outros SIG. Python puro, sem pyproj.

GEORREFERÊNCIA FICTÍCIA (declarada em ``meta`` da saída e em cada execução):
- as obras do beta têm coordenadas LOCAIS em metros (``alinhamento.pontos``: x para leste, y para norte);
- uma ÂNCORA lat/lon fictícia por tipo de obra, num ponto plausível do interior do Brasil (não é traçado
  real; a obra não existe), corresponde a x = 0, y = 0;
- projeção PLANO TANGENTE LOCAL (equiretangular na âncora com os raios de curvatura do elipsoide WGS84):
      lat = lat0 + y / M(lat0)        lon = lon0 + x / (N(lat0) · cos lat0)      (em radianos)
  M = raio meridiano e N = raio do primeiro vertical na âncora. A inversa é exata (ida e volta limitada só
  pelo arredondamento das coordenadas publicadas, 8 casas decimais ≈ 1 mm). A distorção em relação a uma
  projeção geodésica rigorosa cresce com a distância à âncora (ordem de 1e-4 relativo em dezenas de km):
  serve para VISUALIZAR, não para locação.

RFC 7946: WGS84 implícito (sem membro "crs"), posições em ordem [lon, lat] (altitude opcional como 3º valor),
anéis de polígono fechados e com a REGRA DA MÃO DIREITA (externo anti-horário).

Camadas: eixo, lotes, segmentos, atividades (estado 4D na data pedida), marcos, restricoes (pendentes),
conflitos (de linha de balanço projetados), estacas (a cada km) e faixa (polígono de faixa de domínio
FICTÍCIA por lote, para exercitar a regra da mão direita).
"""

from __future__ import annotations

from .obra import tipo_obra
import math

from .calendario import iso
from .cenarios import CENARIOS, Projeto
from .painel import estado_4d
from .referencia_linear import Eixo

CAMADAS = ("eixo", "lotes", "segmentos", "atividades", "marcos", "restricoes", "conflitos", "estacas", "faixa")
CASAS = 8                     # 1e-8 grau ≈ 1,1 mm
# âncoras FICTÍCIAS (x = 0, y = 0 do alinhamento local) — interior do Brasil, sem obra real associada
ANCORAS = {"ferrovia": (-16.20, -49.10), "rodovia": (-13.10, -46.90)}
LARGURA_FAIXA_M = {"ferrovia": 40.0, "rodovia": 60.0}   # faixa de domínio FICTÍCIA (largura total) [OG]
A_WGS84 = 6378137.0
F_WGS84 = 1 / 298.257223563
E2 = F_WGS84 * (2 - F_WGS84)


class ErroGis(ValueError):
    """Parâmetro de exportação inválido."""


class Georref:
    """Plano tangente local na âncora (lat0, lon0) — FICTÍCIA."""

    def __init__(self, lat0: float, lon0: float):
        if not (-80 <= lat0 <= 80 and -180 <= lon0 <= 180):
            raise ErroGis("âncora fora do intervalo suportado")
        self.lat0, self.lon0 = lat0, lon0
        phi = math.radians(lat0)
        w = 1 - E2 * math.sin(phi) ** 2
        self.raio_meridiano = A_WGS84 * (1 - E2) / w ** 1.5
        self.raio_normal = A_WGS84 / math.sqrt(w)
        self._cos = math.cos(phi)

    def para_lonlat(self, x: float, y: float) -> tuple[float, float]:
        lat = self.lat0 + math.degrees(y / self.raio_meridiano)
        lon = self.lon0 + math.degrees(x / (self.raio_normal * self._cos))
        return lon, lat

    def para_xy(self, lon: float, lat: float) -> tuple[float, float]:
        y = math.radians(lat - self.lat0) * self.raio_meridiano
        x = math.radians(lon - self.lon0) * self.raio_normal * self._cos
        return x, y

    def descricao(self) -> dict:
        return {"tipo": "plano tangente local (equiretangular na âncora, raios de curvatura WGS84)",
                "ancora_lat": self.lat0, "ancora_lon": self.lon0, "datum": "WGS84 (EPSG:4326, RFC 7946)",
                "ancora_ficticia": True,
                "uso": "visualização; distorção relativa ~1e-4 a dezenas de km da âncora — não serve para locação"}


def georref_da_obra(dados: dict) -> Georref:
    tipo = tipo_obra(dados)  # declarado (P8): sem padrão "ferrovia"
    lat0, lon0 = ANCORAS[tipo]
    return Georref(lat0, lon0)


# ---------------------------------------------------------------------------- geometria
def _pos(g: Georref, x: float, y: float, z: float | None = None) -> list[float]:
    lon, lat = g.para_lonlat(x, y)
    p = [round(lon, CASAS), round(lat, CASAS)]
    if z is not None:
        p.append(round(z, 3))
    return p


def _kms_entre(eixo: Eixo, a: float, b: float) -> list[float]:
    a, b = min(a, b), max(a, b)
    a, b = max(a, eixo.km_inicial), min(b, eixo.km_final)
    if b < a:
        return []
    return [a] + [k for k in eixo.kms if a < k < b] + ([b] if b > a else [])


def _linha(g: Georref, eixo: Eixo, a: float, b: float) -> dict | None:
    kms = _kms_entre(eixo, a, b)
    if len(kms) < 2:
        return None
    coords = []
    for k in kms:
        p = eixo.ponto_em(k)
        coords.append(_pos(g, p["x"], p["y"], p["cota"]))
    return {"type": "LineString", "coordinates": coords}


def _ponto(g: Georref, eixo: Eixo, km: float) -> dict:
    km = min(max(km, eixo.km_inicial), eixo.km_final)
    p = eixo.ponto_em(km)
    return {"type": "Point", "coordinates": _pos(g, p["x"], p["y"], p["cota"])}


def _faixa(g: Georref, eixo: Eixo, a: float, b: float, largura: float) -> dict | None:
    """Polígono da faixa (±largura/2 do eixo). Anel externo ANTI-HORÁRIO (mão direita): segue a borda
    DIREITA no sentido do km e volta pela ESQUERDA."""
    kms = _kms_entre(eixo, a, b)
    if len(kms) < 2:
        return None
    meia = largura / 2
    dir_, esq = [], []
    for k in kms:
        p = eixo.ponto_em(k)
        th = math.radians(p["rumo_graus"])
        nx, ny = math.cos(th), -math.sin(th)               # normal à direita
        dir_.append(_pos(g, p["x"] + meia * nx, p["y"] + meia * ny))
        esq.append(_pos(g, p["x"] - meia * nx, p["y"] - meia * ny))
    anel = dir_ + esq[::-1]
    anel.append(anel[0])
    return {"type": "Polygon", "coordinates": [anel]}


def _feature(camada: str, geom: dict | None, props: dict) -> dict | None:
    if geom is None:
        return None
    return {"type": "Feature", "geometry": geom, "properties": {"camada": camada, **props}}


# ---------------------------------------------------------------------------- camadas
def geojson(projeto: Projeto, resultados: dict[str, dict], camada: str = "todas", data: int | None = None,
            cenario: str = "independente", conflitos: dict | None = None) -> dict:
    """FeatureCollection RFC 7946. ``resultados``: cenário -> resultado de ``cenarios.executar`` (todos os
    cenários de ``CENARIOS``). ``data``: ordinal da data do estado 4D (padrão: data de status).
    ``conflitos``: saída de ``recursos.conflitos_balanco`` (necessária para a camada conflitos)."""
    if camada != "todas" and camada not in CAMADAS:
        raise ErroGis(f"camada desconhecida: {camada} (use {', '.join(CAMADAS)} ou todas)")
    if cenario not in CENARIOS:
        raise ErroGis(f"cenário desconhecido: {cenario}")
    dados = projeto.dados
    meta = dados.get("meta", {})
    tipo = tipo_obra(dados)
    g = georref_da_obra(dados)
    eixo = Eixo.da_obra(dados)
    t = projeto.data_status if data is None else data
    quero = set(CAMADAS) if camada == "todas" else {camada}
    feats: list[dict | None] = []

    if "eixo" in quero:
        feats.append(_feature("eixo", _linha(g, eixo, eixo.km_inicial, eixo.km_final),
                              {"id": dados["ferrovia"].get("id"), "nome": dados["ferrovia"].get("nome"),
                               "extensao_km": dados["ferrovia"].get("extensao_km"), "tipo_obra": tipo}))
    if "lotes" in quero:
        for l in dados.get("lotes", []):
            feats.append(_feature("lotes", _linha(g, eixo, l["km_ini"], l["km_fim"]),
                                  {k: l.get(k) for k in ("id", "nome", "km_ini", "km_fim", "construtora")}))
    if "segmentos" in quero:
        for s in dados.get("segmentos", []):
            feats.append(_feature("segmentos", _linha(g, eixo, s["km_ini"], s["km_fim"]),
                                  {k: s.get(k) for k in ("id", "lote_id", "km_ini", "km_fim", "estaca_ini", "estaca_fim")}))
    if "faixa" in quero:
        for l in dados.get("lotes", []):
            feats.append(_feature("faixa", _faixa(g, eixo, l["km_ini"], l["km_fim"], LARGURA_FAIXA_M[tipo]),
                                  {"id": f"FAIXA-{l['id']}", "lote_id": l["id"], "largura_m": LARGURA_FAIXA_M[tipo],
                                   "ficticia": True}))
    if "atividades" in quero:
        res = resultados[cenario]
        est = estado_4d(projeto, res, resultados["linha_base"], t)
        for a in dados["atividades"]:
            if a.get("tipo", "tarefa") != "tarefa" or a.get("km_ini") is None or a.get("km_fim") is None:
                continue
            r, e = res["atividades"][a["id"]], est[a["id"]]
            feats.append(_feature("atividades", _linha(g, eixo, a["km_ini"], a["km_fim"]), {
                "id": a["id"], "nome": a.get("nome"), "servico_id": a.get("servico_id"), "lote_id": a.get("lote_id"),
                "segmento_id": a.get("segmento_id"), "km_ini": a["km_ini"], "km_fim": a["km_fim"],
                "status": r["status"], "estado_4d": e["estado"], "fracao": e["fracao"], "fracao_lb": e["fracao_lb"],
                "desvio": e["desvio"], "percentual_executado": round(100 * e["fracao"], 2),
                "critica": r["critica"], "folga_total": r["folga_total"],
                "inicio": r["inicio"], "termino": r["termino"],
                **{f"termino_{c}": resultados[c]["atividades"][a["id"]]["termino"] for c in CENARIOS},
            }))
    if "marcos" in quero:
        lotes = {l["id"]: l for l in dados.get("lotes", [])}
        km_fim_obra = eixo.km_final
        res = resultados[cenario]
        for a in dados["atividades"]:
            tipo_a = a.get("tipo", "tarefa")
            if tipo_a == "tarefa":
                continue
            # regra declarada: marco de lote no início/fim do lote; marco geral no início/fim da obra
            l = lotes.get(a.get("lote_id"))
            if tipo_a == "marco_inicio":
                km = l["km_ini"] if l else eixo.km_inicial
            else:
                km = l["km_fim"] if l else km_fim_obra
            r = res["atividades"][a["id"]]
            feats.append(_feature("marcos", _ponto(g, eixo, km), {
                "id": a["id"], "nome": a.get("nome"), "tipo": tipo_a, "lote_id": a.get("lote_id"), "km": km,
                "estaca": eixo.estaca(min(max(km, eixo.km_inicial), eixo.km_final)),
                "data": r["termino"], "critica": r["critica"], "status": r["status"],
                **{f"data_{c}": resultados[c]["atividades"][a["id"]]["termino"] for c in CENARIOS},
            }))
    if "restricoes" in quero:
        res = resultados[cenario]
        for rest in dados.get("restricoes", []):
            if rest.get("situacao") != "pendente":
                continue
            a = projeto.atividades.get(rest["atividade_id"], {})
            if a.get("km_ini") is None:
                continue
            r = res["atividades"][a["id"]]
            feats.append(_feature("restricoes", _ponto(g, eixo, a["km_ini"]), {
                "id": rest["id"], "descricao": rest.get("descricao"), "data_liberacao": rest.get("data_liberacao"),
                "atividade_id": a["id"], "km": a["km_ini"], "folga_total": r["folga_total"], "critica": r["critica"]}))
    if "conflitos" in quero:
        if conflitos is None:
            raise ErroGis("camada conflitos precisa do resultado de recursos.conflitos_balanco")
        for i, c in enumerate(conflitos.get("conflitos", [])):
            cruz = c.get("cruzamento")
            km = cruz["km"] if cruz else c["km"]
            feats.append(_feature("conflitos", _ponto(g, eixo, km), {
                "id": f"CONF-{i + 1:03d}", "lote_id": c.get("lote"), "segmento_id": c.get("segmento"),
                "atividades": c.get("atividades"), "servicos": c.get("servicos"), "km": km,
                "data": cruz["data"] if cruz else c.get("data"), "ultrapassagem": c.get("ultrapassagem"),
                "distancia_km_min": c.get("distancia_km_min"), "folga_dias_min": c.get("folga_dias_min"),
                "fonte": c.get("fonte"), "posicao": "cruzamento" if cruz else "inicio do alerta"}))
    if "estacas" in quero:
        k = math.ceil(eixo.km_inicial - 1e-9)
        while k <= eixo.km_final + 1e-9:
            km = float(k)
            feats.append(_feature("estacas", _ponto(g, eixo, km), {"km": km, "estaca": eixo.estaca(km)}))
            k += 1
    return {
        "type": "FeatureCollection",
        "meta": {
            "ficticio": True,
            "aviso": "GEORREFERÊNCIA FICTÍCIA: obra, traçado e âncora inventados para demonstração. "
                     + str(meta.get("aviso", "")),
            "obra_tipo": tipo, "georreferencia": g.descricao(), "camada": camada, "cenario": cenario,
            "data_estado_4d": iso(t), "data_status": meta.get("data_status"), "casas_decimais": CASAS,
        },
        "features": [f for f in feats if f is not None],
    }
