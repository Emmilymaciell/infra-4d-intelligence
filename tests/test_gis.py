"""Exportação GeoJSON (RFC 7946) com georreferência FICTÍCIA: estrutura, ida e volta, propriedades = API."""

import math

import pytest
from fastapi.testclient import TestClient

from infra4d.api import criar_app
from infra4d.cenarios import CENARIOS, DATASET_PADRAO, Projeto, executar
from infra4d.gis import ANCORAS, CAMADAS, ErroGis, Georref, geojson, georref_da_obra
from infra4d.recursos import conflitos_balanco
from infra4d.referencia_linear import Eixo

OBRAS = {"ferrovia": DATASET_PADRAO, "rodovia": DATASET_PADRAO.parent / "rodovia_ficticia.json"}


# ------------------------------------------------------------------ validador estrutural (RFC 7946)
def _posicao(p, lon0, lat0):
    assert isinstance(p, list) and len(p) in (2, 3) and all(isinstance(v, (int, float)) for v in p), p
    lon, lat = p[0], p[1]
    assert -180 <= lon <= 180 and -90 <= lat <= 90, p
    # ordem [lon, lat]: perto da âncora nos DOIS eixos (lat e lon das âncoras diferem em > 30°)
    assert abs(lon - lon0) < 1 and abs(lat - lat0) < 1, p


def _area_assinada(anel):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(anel, anel[1:])) / 2


def validar_feature_collection(fc, lon0, lat0):
    assert fc["type"] == "FeatureCollection" and isinstance(fc["features"], list)
    assert "crs" not in fc                                    # RFC 7946 removeu o membro crs
    for f in fc["features"]:
        assert f["type"] == "Feature" and isinstance(f["properties"], dict)
        g = f["geometry"]
        if g["type"] == "Point":
            _posicao(g["coordinates"], lon0, lat0)
        elif g["type"] == "LineString":
            assert len(g["coordinates"]) >= 2
            for p in g["coordinates"]:
                _posicao(p, lon0, lat0)
        elif g["type"] == "Polygon":
            for i, anel in enumerate(g["coordinates"]):
                assert len(anel) >= 4 and anel[0] == anel[-1], "anel não fechado"
                for p in anel:
                    _posicao(p, lon0, lat0)
                area = _area_assinada(anel)
                assert (area > 0) if i == 0 else (area < 0), "regra da mão direita"
        else:
            pytest.fail(f"tipo de geometria inesperado: {g['type']}")


# ------------------------------------------------------------------ georreferência à mão
def test_plano_tangente_valores_de_referencia():
    """Âncora 13,1° S: 1° de latitude ≈ 110,63 km (M ≈ 6.338.710 m) e 1° de longitude ≈ 108,44 km
    (N·cos φ ≈ 6.213.221 m) no WGS84. 1 km para o norte ≈ 0,0090391°; 1 km para leste ≈ 0,0092216°."""
    g = Georref(-13.1, -46.9)
    assert g.para_lonlat(0, 0) == (-46.9, -13.1)
    lon, lat = g.para_lonlat(0, 1000)
    assert lon == -46.9 and lat - (-13.1) == pytest.approx(0.0090391, abs=2e-7)
    lon, lat = g.para_lonlat(1000, 0)
    assert lat == -13.1 and lon - (-46.9) == pytest.approx(0.0092216, abs=2e-7)
    with pytest.raises(ErroGis):
        Georref(85.0, 0.0)


def test_ida_e_volta_xy_lonlat_xy():
    g = Georref(-16.2, -49.1)
    for x, y in [(0, 0), (60000, -1200), (-500, 900), (12345.678, 0.001)]:
        assert g.para_xy(*g.para_lonlat(x, y)) == pytest.approx((x, y), abs=1e-6)


@pytest.mark.parametrize("obra", list(OBRAS))
def test_ida_e_volta_pelo_geojson_ate_o_km(limite, obra):
    """Vértices publicados do eixo (8 casas) -> x/y local -> km pela referência linear = km do vértice."""
    tol = limite("tolerancia_georef_m")
    P = Projeto.carregar(OBRAS[obra])
    res = {c: executar(P, c) for c in CENARIOS}
    fc = geojson(P, res, "eixo")
    g, eixo = georref_da_obra(P.dados), Eixo.da_obra(P.dados)
    (f,) = fc["features"]
    pts = P.dados["alinhamento"]["pontos"]
    assert len(f["geometry"]["coordinates"]) == len(pts)
    for (km, x, y, cota), pos in zip(pts, f["geometry"]["coordinates"]):
        x2, y2 = g.para_xy(pos[0], pos[1])
        assert math.hypot(x2 - x, y2 - y) <= tol
        assert abs(eixo.localizar(x2, y2)["km"] - km) * 1000 <= tol
        assert pos[2] == pytest.approx(cota, abs=1e-3)


# ------------------------------------------------------------------ obras
@pytest.fixture(scope="module", params=list(OBRAS))
def saida(request):
    P = Projeto.carregar(OBRAS[request.param])
    res = {c: executar(P, c) for c in CENARIOS}
    conf = conflitos_balanco(P, res["independente"])
    return request.param, P, res, conf, geojson(P, res, "todas", None, "independente", conf)


def test_estrutura_valida_e_marca_ficticia(saida):
    obra, P, res, conf, fc = saida
    lat0, lon0 = ANCORAS[obra]
    validar_feature_collection(fc, lon0, lat0)
    assert fc["meta"]["ficticio"] is True and "FICTÍCIA" in fc["meta"]["aviso"]
    assert fc["meta"]["georreferencia"]["ancora_ficticia"] is True
    camadas = {f["properties"]["camada"] for f in fc["features"]}
    assert camadas == set(CAMADAS)
    faixas = [f for f in fc["features"] if f["properties"]["camada"] == "faixa"]
    assert len(faixas) == len(P.dados["lotes"]) and all(f["geometry"]["type"] == "Polygon" for f in faixas)


def test_contagens_por_camada(saida):
    obra, P, res, conf, fc = saida
    por = {}
    for f in fc["features"]:
        por.setdefault(f["properties"]["camada"], []).append(f)
    d = P.dados
    tarefas = [a for a in d["atividades"] if a.get("tipo", "tarefa") == "tarefa" and a.get("km_ini") is not None]
    assert len(por["atividades"]) == len(tarefas)
    assert len(por["marcos"]) == sum(a.get("tipo") in ("marco_inicio", "marco_termino") for a in d["atividades"])
    assert len(por["restricoes"]) == sum(r["situacao"] == "pendente" for r in d["restricoes"])
    assert len(por["conflitos"]) == conf["n_conflitos"]
    assert len(por["estacas"]) == int(d["ferrovia"]["extensao_km"]) + 1
    assert por["estacas"][1]["properties"]["estaca"] == "50+00,00"
    assert len(por["segmentos"]) == len(d["segmentos"]) and len(por["lotes"]) == len(d["lotes"])


def test_atividades_com_as_propriedades_da_api(saida):
    """Estado 4D, crítica e términos iguais aos de /api/estado4d e /api/cenarios na mesma data."""
    obra, P, res, conf, fc = saida
    data = "2027-02-01"
    c = TestClient(criar_app(fontes={obra: P}))
    j = c.get("/api/gis/geojson", params={"obra": obra, "camada": "atividades", "data": data})
    assert j.status_code == 200 and j.headers["content-type"].startswith("application/geo+json")
    e4 = c.get("/api/estado4d", params={"obra": obra, "data": data}).json()["atividades"]
    cen = c.get("/api/cenarios/independente", params={"obra": obra}).json()["atividades"]
    feats = j.json()["features"]
    assert feats
    for f in feats:
        p = f["properties"]
        e = e4[p["id"]]
        assert (p["estado_4d"], p["fracao"], p["fracao_lb"], p["critica"]) == (e["estado"], e["fracao"], e["fracao_lb"],
                                                                             e["critica"])
        assert p["percentual_executado"] == round(100 * e["fracao"], 2)
        assert (p["folga_total"], p["termino_independente"]) == (cen[p["id"]]["folga_total"], cen[p["id"]]["termino"])


def test_geometria_da_atividade_cobre_o_trecho(saida):
    obra, P, res, conf, fc = saida
    g, eixo = georref_da_obra(P.dados), Eixo.da_obra(P.dados)
    for f in fc["features"]:
        if f["properties"]["camada"] != "atividades":
            continue
        ini, fim = sorted((f["properties"]["km_ini"], f["properties"]["km_fim"]))
        cs = f["geometry"]["coordinates"]
        k0 = eixo.localizar(*g.para_xy(*cs[0][:2]))["km"]
        k1 = eixo.localizar(*g.para_xy(*cs[-1][:2]))["km"]
        assert k0 == pytest.approx(max(ini, eixo.km_inicial), abs=1e-4)
        assert k1 == pytest.approx(min(fim, eixo.km_final), abs=1e-4)


# ------------------------------------------------------------------ rota
def test_rota_camadas_e_erros():
    P = Projeto.carregar(OBRAS["rodovia"])
    c = TestClient(criar_app(fontes={"rodovia": P}))
    assert "rotas_gis" in c.app.state.rotas_ligadas
    for cam in CAMADAS:
        r = c.get("/api/gis/geojson", params={"obra": "rodovia", "camada": cam})
        assert r.status_code == 200, cam
        assert {f["properties"]["camada"] for f in r.json()["features"]} == {cam}
    for params, codigo in (({"camada": "xx"}, 422), ({"data": "2027-13-01"}, 422), ({"data": "20270101"}, 422),
                           ({"cenario": "zz"}, 422), ({"obra": "nada"}, 404)):
        assert c.get("/api/gis/geojson", params={"obra": "rodovia", **params}).status_code == codigo, params


def test_conflito_no_ponto_de_cruzamento_quando_ha(saida):
    """Conflito com cruzamento analítico (sucessora alcança a antecessora) fica no km do cruzamento;
    sem cruzamento, no km do início do alerta."""
    obra, P, res, conf, fc = saida
    g, eixo = georref_da_obra(P.dados), Eixo.da_obra(P.dados)
    feats = [f for f in fc["features"] if f["properties"]["camada"] == "conflitos"]
    assert len(feats) == len(conf["conflitos"])
    com_cruz = 0
    for f, c in zip(feats, conf["conflitos"]):
        esperado = c["cruzamento"]["km"] if c.get("cruzamento") else c["km"]
        com_cruz += bool(c.get("cruzamento"))
        km = eixo.localizar(*g.para_xy(*f["geometry"]["coordinates"][:2]))["km"]
        assert km == pytest.approx(esperado, abs=1e-5) and f["properties"]["km"] == esperado
    if obra == "rodovia":
        assert com_cruz > 0
