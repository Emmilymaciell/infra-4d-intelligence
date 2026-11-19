"""Terraplenagem: seções, volumes por estaca e DIAGRAMA DE MASSAS (Brückner). Python puro.

Método (conhecimento técnico geral de projeto de terraplenagem; ver docs/research/R06):

- **Altura no eixo** ``h = cota do greide − cota do terreno``: ``h > 0`` é ATERRO, ``h < 0`` é CORTE.
- **Seção simplificada** (terreno transversal plano, sem seção mista): plataforma de largura ``L`` e
  taludes ``1(V):n(H)``. Área = ``|h| · (L + n·|h|)`` (trapézio). ``n`` separado para corte e aterro.
- **Volume entre estacas** pela MÉDIA DAS ÁREAS: ``V = (A_i + A_{i+1}) / 2 · d``, separado em corte e
  aterro. Num intervalo com PASSAGEM corte/aterro, o intervalo é dividido no ponto de passagem (h linear):
  corte = A_i/2 · d1 e aterro = A_{i+1}/2 · d2 (revisão r9). Dentro desse intervalo há COMPENSAÇÃO LOCAL de
  ``min(Vc, Fh·Va)``, com DMT = (d1 + d2)/3 (distância entre os centroides das duas cunhas).
- **Fator de homogeneização** ``Fh`` (contração): o aterro compactado é convertido para volume de corte
  equivalente, ``Va · Fh``. **Empolamento** ``e``: só para o volume SOLTO transportado (bota-fora).
- **Ordenada de Brückner** acumulada ``O_i = Σ (Vc − Fh·Va)``: ramo ascendente = predomínio de corte.
- **Linha de compensação** horizontal em ``O = 0`` (início da obra). Cada ONDA entre dois cruzamentos
  da curva com a linha é um trecho compensado: volume = SOMA DAS SUBIDAS da ordenada dentro da onda (das
  descidas, para onda abaixo da linha) — numa onda de um só pico isso é o pico, numa onda composta não
  (revisão r9); momento de transporte = área entre a curva e a linha (m³·m); **DMT = momento ÷ volume**.
  Onda acima da linha: transporte no sentido do km crescente; abaixo: decrescente.
- **Ponta final aberta**: se a curva termina fora da linha, ``|O_fim|`` é BOTA-FORA (O_fim > 0, sobra de
  corte) ou EMPRÉSTIMO (O_fim < 0), em volume de corte equivalente; o volume compensado da onda final é
  ``min(subidas, descidas)`` e o momento é medido contra uma linha secundária no nível ``O_fim``
  (simplificação declarada).
- **Conservação** (verificada em teste): corte = compensado + bota-fora e Fh·aterro = compensado + empréstimo,
  com compensado = ondas longitudinais + compensação local.
- **Pontos de passagem**: km em que ``h`` troca de sinal (interpolação linear entre estacas).

O TERRENO NATURAL das obras do beta é SINTÉTICO (``terreno_sintetico``): greide menos uma ondulação
senoidal declarada. Os números servem para confrontar coerência de ordem de grandeza, não são projeto.
"""

from __future__ import annotations

from .obra import tipo_obra
import math
from dataclasses import asdict, dataclass

from .referencia_linear import Eixo, ErroReferencia


class ErroMassas(ValueError):
    """Entrada inválida para o cálculo de massas."""


@dataclass(frozen=True)
class Secao:
    largura_plataforma_m: float
    talude_corte_h: float = 1.5     # 1(V):1,5(H)
    talude_aterro_h: float = 1.5

    def __post_init__(self):
        vals = (self.largura_plataforma_m, self.talude_corte_h, self.talude_aterro_h)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vals):
            raise ErroMassas(f"seção com valor não numérico ou não finito: {vals!r}")
        if self.largura_plataforma_m <= 0 or self.talude_corte_h < 0 or self.talude_aterro_h < 0:
            raise ErroMassas("seção inválida: largura da plataforma deve ser > 0 e taludes >= 0 (revisão r9)")

    def area(self, h: float) -> tuple[float, float]:
        """(área de corte, área de aterro) em m² para a altura ``h`` no eixo."""
        if h < 0:
            d = -h
            return d * (self.largura_plataforma_m + self.talude_corte_h * d), 0.0
        return 0.0, h * (self.largura_plataforma_m + self.talude_aterro_h * h)


# Premissas por tipo de obra [OG] — ver R06
SECAO_PADRAO = {"ferrovia": Secao(12.0), "rodovia": Secao(13.0)}
FATOR_HOMOGENEIZACAO = 1.25
EMPOLAMENTO = 0.25
# ondulação do terreno sintético: h(km) = Σ A·sen(2π·km/λ + φ)   (FICTÍCIA)
ONDULACAO_TERRENO = [(4.5, 1.7, 0.0), (1.8, 0.45, 1.1)]   # (amplitude m, comprimento de onda km, fase rad)
# greide 0,3 m abaixo da média do terreno: mais corte que aterro geométrico, para que corte ≈ Fh·aterro
# (greide "aproximadamente compensado", como um projetista buscaria). FICTÍCIO.
DESLOCAMENTO_GREIDE_M = -0.3
LIMIAR_COERENCIA = 0.20   # |diferença| <= 20 % => "coerente" (classificação, não critério de aceite)


def terreno_sintetico(km: float, cota_greide: float) -> float:
    """Cota do terreno natural SINTÉTICA: greide − (ondulação + deslocamento) (h positivo = aterro)."""
    h = DESLOCAMENTO_GREIDE_M + sum(a * math.sin(2 * math.pi * km / lam + fi) for a, lam, fi in ONDULACAO_TERRENO)
    return cota_greide - h


# ---------------------------------------------------------------------------- núcleo
def calcular_massas(kms: list[float], greide: list[float], terreno: list[float], secao: Secao,
                    fh: float = FATOR_HOMOGENEIZACAO, empolamento: float = EMPOLAMENTO) -> dict:
    """Volumes, ordenadas de Brückner, pontos de passagem e compensações.

    ``kms`` estritamente crescentes (km), ``greide`` e ``terreno`` em metros, mesmo tamanho.
    """
    n = len(kms)
    if n < 2 or len(greide) != n or len(terreno) != n:
        raise ErroMassas("precisa de pelo menos 2 estacas e listas de mesmo tamanho")
    if any(not b > a for a, b in zip(kms, kms[1:])):
        raise ErroMassas("km das estacas deve ser estritamente crescente")
    if not (fh > 0 and empolamento >= 0):
        raise ErroMassas("fator de homogeneização deve ser > 0 e empolamento >= 0")
    if not all(math.isfinite(v) for v in list(kms) + list(greide) + list(terreno)):
        raise ErroMassas("valores não finitos no perfil")

    hs = [g - t for g, t in zip(greide, terreno)]
    areas = [secao.area(h) for h in hs]
    estacas, ordenada = [], 0.0
    tot_c = tot_a = 0.0
    locais = []
    for i in range(n):
        vc = va = 0.0
        if i:
            d = (kms[i] - kms[i - 1]) * 1000.0
            h0, h1 = hs[i - 1], hs[i]
            if h0 * h1 < 0:
                # passagem dentro do intervalo: divide no ponto de passagem (h linear)
                d1 = d * abs(h0) / (abs(h0) + abs(h1))
                d2 = d - d1
                a0, a1 = areas[i - 1], areas[i]
                vc = a0[0] / 2 * d1 + a1[0] / 2 * d2
                va = a0[1] / 2 * d1 + a1[1] / 2 * d2
                loc = min(vc, fh * va)
                if loc > 0:
                    dmt = (d1 + d2) / 3.0
                    locais.append({"km_ini": kms[i - 1], "km_fim": kms[i], "volume_m3": loc, "dmt_m": dmt,
                                   "momento_m3m": loc * dmt, "momento_m3km": loc * dmt / 1000.0})
            else:
                vc = (areas[i - 1][0] + areas[i][0]) / 2 * d
                va = (areas[i - 1][1] + areas[i][1]) / 2 * d
            ordenada += vc - fh * va
            tot_c += vc
            tot_a += va
        estacas.append({"km": kms[i], "cota_greide": greide[i], "cota_terreno": terreno[i], "h": hs[i],
                        "area_corte_m2": areas[i][0], "area_aterro_m2": areas[i][1],
                        "volume_corte_m3": vc, "volume_aterro_m3": va, "ordenada_m3": ordenada})
    xs = [k * 1000.0 for k in kms]
    ords = [e["ordenada_m3"] for e in estacas]
    ondas, final = compensar(xs, ords)
    comp_long = sum(o["volume_m3"] for o in ondas)
    comp_local = sum(o["volume_m3"] for o in locais)
    comp = comp_long + comp_local
    momento = sum(o["momento_m3m"] for o in ondas) + sum(o["momento_m3m"] for o in locais)
    return {
        "metodo": "seção trapezoidal (terreno transversal plano) + média das áreas + Brückner com linha em O = 0",
        "secao": asdict(secao), "fator_homogeneizacao": fh, "empolamento": empolamento,
        "estacas": estacas,
        "pontos_passagem_km": pontos_passagem(kms, hs),
        "compensacoes": ondas,
        "compensacoes_locais": locais,
        "volume_livre": volume_livre(xs, ords),
        "total": {
            "volume_corte_m3": tot_c, "volume_aterro_m3": tot_a,
            "volume_aterro_equivalente_corte_m3": fh * tot_a,
            "volume_compensado_m3": comp,
            "volume_compensado_longitudinal_m3": comp_long,
            "volume_compensado_local_m3": comp_local,
            "momento_transporte_m3km": momento / 1000.0,
            "dmt_media_m": momento / comp if comp > 0 else None,
            "bota_fora_m3": max(0.0, final), "emprestimo_m3": max(0.0, -final),
            "bota_fora_solto_m3": max(0.0, final) * (1 + empolamento),
            "ordenada_final_m3": ords[-1],
        },
    }


def pontos_passagem(kms: list[float], hs: list[float]) -> list[float]:
    """km em que o greide cruza o terreno (h troca de sinal). Estaca com h = 0 entre sinais opostos conta 1 vez."""
    out = []
    ultimo_sinal = 0
    for i, h in enumerate(hs):
        s = (h > 0) - (h < 0)
        if s == 0:
            continue
        if ultimo_sinal and s != ultimo_sinal:
            j = max(k for k in range(i) if hs[k] != 0)        # última estaca não nula antes desta
            if j == i - 1:
                out.append(kms[j] + (kms[i] - kms[j]) * hs[j] / (hs[j] - h))
            else:
                out.append(kms[j + 1])                           # h = 0 exatamente numa estaca
        ultimo_sinal = s
    return out


def _cruzamentos(xs: list[float], ys: list[float]) -> list[tuple[float, float]]:
    """Polilinha com os cruzamentos de y = 0 inseridos."""
    pts = [(xs[0], ys[0])]
    for i in range(1, len(xs)):
        y0, y1 = ys[i - 1], ys[i]
        if (y0 > 0 > y1) or (y0 < 0 < y1):
            pts.append((xs[i - 1] + (xs[i] - xs[i - 1]) * y0 / (y0 - y1), 0.0))
        pts.append((xs[i], y1))
    return pts


def _area_acima(pts: list[tuple[float, float]], nivel: float) -> float:
    """∫ max(0, |y| − nivel) dx, exata para a polilinha (corta cada trecho no nível)."""
    tot = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        a, b = abs(y0) - nivel, abs(y1) - nivel
        dx = x1 - x0
        if a >= 0 and b >= 0:
            tot += (a + b) / 2 * dx
        elif a > 0 or b > 0:
            pos = max(a, b)
            tot += pos * (dx * pos / (pos - min(a, b))) / 2
    return tot


def _ondas(xs: list[float], ords: list[float], eps: float = 1e-9) -> list[list[tuple[float, float]]]:
    """Polilinha da ordenada partida nos toques da linha O = 0."""
    pts = _cruzamentos(xs, ords)
    ondas, atual = [], [pts[0]]
    for p in pts[1:]:
        atual.append(p)
        if abs(p[1]) <= eps:
            ondas.append(atual)
            atual = [p]
    if len(atual) > 1:
        ondas.append(atual)
    return ondas


def volume_livre(xs: list[float], ords: list[float], eps: float = 1e-9) -> list[dict]:
    """ONDE está o volume livre (bota-fora ou empréstimo) — trechos em km com o volume de cada um.

    Regra declarada (revisão r12): o volume livre |O_fim| sai da onda final aberta, nos trechos em que a
    curva atinge PELA PRIMEIRA VEZ cada nível entre 0 e |O_fim| (máximo corrente de |O|, limitado a |O_fim|).
    A soma dos trechos é exatamente |O_fim|. O_fim > 0: sobra de corte (bota-fora); O_fim < 0: falta de aterro
    (empréstimo). Sem ponta aberta, lista vazia.
    """
    final = ords[-1] if abs(ords[-1]) > eps else 0.0
    if not final:
        return []
    onda = _ondas(xs, ords, eps)[-1]
    teto = abs(final)
    tipo = "bota-fora" if final > 0 else "empréstimo"
    out, m = [], 0.0
    for (x0, y0), (x1, y1) in zip(onda, onda[1:]):
        a, b = abs(y0), abs(y1)
        if b > m and m < teto:
            lo, hi = max(a, m), min(b, teto)
            if hi > lo:
                xa = x0 + (lo - a) / (b - a) * (x1 - x0)
                xb = x0 + (hi - a) / (b - a) * (x1 - x0)
                if out and abs(out[-1]["_x1"] - xa) < 1e-9:      # trechos contíguos viram um só
                    out[-1]["_x1"] = xb
                    out[-1]["volume_m3"] += hi - lo
                else:
                    out.append({"_x0": xa, "_x1": xb, "volume_m3": hi - lo, "tipo": tipo})
        m = max(m, b)
    return [{"km_ini": t["_x0"] / 1000.0, "km_fim": t["_x1"] / 1000.0, "volume_m3": t["volume_m3"], "tipo": t["tipo"]}
            for t in out]


def compensar(xs: list[float], ords: list[float], eps: float = 1e-9) -> tuple[list[dict], float]:
    """Ondas de compensação contra a linha O = 0. Devolve (ondas, ordenada final livre)."""
    ondas = _ondas(xs, ords, eps)
    final = ords[-1] if abs(ords[-1]) > eps else 0.0
    out = []
    for k, w in enumerate(ondas):
        pico = max(abs(y) for _, y in w)
        if pico <= eps:
            continue
        sinal = max((y for _, y in w), key=abs)
        # trabalha com |O|: "subida" = afastamento crescente da linha (corte, se a onda está acima;
        # aterro vindo de diante, se abaixo); "descida" = volta para a linha
        subidas = sum(max(0.0, abs(b) - abs(a)) for (_, a), (_, b) in zip(w, w[1:]))
        descidas = sum(max(0.0, abs(a) - abs(b)) for (_, a), (_, b) in zip(w, w[1:]))
        livre = abs(final) if (k == len(ondas) - 1 and final) else 0.0
        vol = min(subidas, descidas) if livre else subidas
        if vol <= eps:
            continue
        momento = _area_acima(w, livre)
        out.append({"km_ini": w[0][0] / 1000.0, "km_fim": w[-1][0] / 1000.0, "volume_m3": vol,
                    "momento_m3m": momento, "momento_m3km": momento / 1000.0, "dmt_m": momento / vol,
                    "sentido": "km crescente" if sinal > 0 else "km decrescente",
                    "aberta": bool(livre)})
    return out, final


# ---------------------------------------------------------------------------- obras
def perfil_da_obra(dados: dict, passo_m: float = 20.0) -> tuple[list[float], list[float], list[float]]:
    if not (math.isfinite(passo_m) and 1.0 <= passo_m <= 1000.0):
        raise ErroMassas("passo_m deve estar entre 1 e 1000 m")
    try:
        eixo = Eixo.da_obra(dados)
    except ErroReferencia as e:
        raise ErroMassas(str(e)) from None
    n = int(math.floor((eixo.km_final - eixo.km_inicial) * 1000.0 / passo_m + 1e-9))
    kms = [round(eixo.km_inicial + i * passo_m / 1000.0, 9) for i in range(n + 1)]
    if eixo.km_final - kms[-1] > 1e-9:
        kms.append(eixo.km_final)
    greide = [eixo.ponto_em(k)["cota"] for k in kms]
    terreno = [terreno_sintetico(k, g) for k, g in zip(kms, greide)]
    return kms, greide, terreno


def secao_da_obra(dados: dict) -> Secao:
    return SECAO_PADRAO[tipo_obra(dados)]  # tipo declarado (P8): sem padrão "ferrovia"


def massas_da_obra(dados: dict, passo_m: float = 20.0) -> dict:
    kms, greide, terreno = perfil_da_obra(dados, passo_m)
    r = calcular_massas(kms, greide, terreno, secao_da_obra(dados))
    eixo = Eixo.da_obra(dados)
    for e in r["estacas"]:
        e["estaca"] = eixo.estaca(e["km"])
    r["passo_m"] = passo_m
    r["aviso"] = ("TERRENO NATURAL SINTÉTICO (greide − ondulação senoidal e deslocamento declarados em massas.py). "
                  "Volumes e DMT são ordem de grandeza para demonstração, não projeto de terraplenagem.")
    return r


def volume_no_intervalo(estacas: list[dict], km_ini: float, km_fim: float) -> tuple[float, float]:
    """(corte, aterro) dos intervalos entre estacas contidos em [km_ini, km_fim] (intervalo parcial: proporcional)."""
    vc = va = 0.0
    for a, b in zip(estacas, estacas[1:]):
        lo, hi = max(a["km"], km_ini), min(b["km"], km_fim)
        if hi <= lo:
            continue
        f = (hi - lo) / (b["km"] - a["km"])
        vc += b["volume_corte_m3"] * f
        va += b["volume_aterro_m3"] * f
    return vc, va


def coerencia(dados: dict, passo_m: float = 20.0, massas: dict | None = None) -> dict:
    """Confronta o volume geométrico (corte + aterro) por segmento com a quantidade da atividade TER.

    Não altera o dataset: só relata a diferença.
    """
    r = massas or massas_da_obra(dados, passo_m)
    ativ = {a["id"]: a for a in dados.get("atividades", [])}
    linhas = []
    for s in dados.get("segmentos", []):
        a = ativ.get(f"{s['id']}-TER")
        vc, va = volume_no_intervalo(r["estacas"], s["km_ini"], s["km_fim"])
        geo = vc + va
        q = a.get("quantidade_total") if a else None
        dif = None if q is None else geo - q
        rel = None if not q else dif / q   # q = 0 ou ausente: diferença relativa indefinida
        linhas.append({
            "segmento_id": s["id"], "lote_id": s.get("lote_id"), "km_ini": s["km_ini"], "km_fim": s["km_fim"],
            "atividade_id": a["id"] if a else None, "unidade": a.get("unidade") if a else None,
            "volume_corte_m3": vc, "volume_aterro_m3": va, "volume_geometrico_m3": geo,
            "quantidade_dataset_m3": q, "diferenca_m3": dif, "diferenca_relativa": rel,
            "situacao": ("sem atividade TER" if q is None else
                         "sem quantidade" if rel is None else
                         "coerente" if abs(rel) <= LIMIAR_COERENCIA else
                         "acima do dataset" if rel > 0 else "abaixo do dataset"),
        })
    geo_t = sum(x["volume_geometrico_m3"] for x in linhas)
    q_t = sum(x["quantidade_dataset_m3"] or 0 for x in linhas)
    return {
        "criterio": ("volume geométrico do segmento = corte + aterro (média das áreas, m³ in situ/compactado) "
                     "vs quantidade_total da atividade TER do segmento; 'coerente' se |diferença| <= "
                     f"{LIMIAR_COERENCIA:.0%} (classificação [OG], não critério de aceite)"),
        "aviso": r["aviso"],
        "segmentos": linhas,
        "total": {"volume_geometrico_m3": geo_t, "quantidade_dataset_m3": q_t,
                  "diferenca_m3": geo_t - q_t, "diferenca_relativa": (geo_t - q_t) / q_t if q_t else None,
                  "n_coerentes": sum(x["situacao"] == "coerente" for x in linhas), "n_segmentos": len(linhas)},
    }
