"""Produtividade de terraplenagem em função da DMT (geometria -> cronograma). Python puro.

Modelo de CICLO de frota (premissas [OG], conhecimento técnico geral; ver docs/research/R06):

- 1 EQUIPE do dataset = 1 frota = 1 escavadeira + ``n_caminhoes`` basculantes (o texto da equipe de TER
  no dataset diz "8 motoristas / 8 caminhões basculantes").
- Escavadeira: produção horária SOLTA = 3600 / ciclo_s × caçamba × enchimento; × eficiência × horas/dia.
- Caminhão: ciclo(DMT) [min] = carga + fixo (manobra, basculamento, posicionamento)
  + DMT/v_carregado + DMT/v_vazio, com carga = capacidade ÷ produção instantânea da escavadeira.
  Produção da frota de caminhões = n × capacidade × 60 / ciclo × eficiência × horas/dia.
- Produção da FROTA = min(escavadeira, caminhões), em m³ SOLTO/dia, convertida para m³ de CORTE
  (in situ) ÷ (1 + empolamento).
- A quantidade da atividade TER do dataset é corte + aterro geométricos (mesma definição de
  ``massas.coerencia``). Para escavar o necessário ao segmento é preciso ``max(Vc, Fh·Va)`` de corte
  (sobra vai a bota-fora, falta vem de empréstimo). Logo:
  produtividade geométrica [m³ TER / equipe·dia] = produção da frota [m³ corte/dia] × (Vc + Va) / max(Vc, Fh·Va).
- DMT do SEGMENTO: média ponderada pelas ondas de Brückner que tocam o segmento (momento e volume
  rateados pela fração da onda dentro do segmento) + bota-fora/empréstimo com ``dmt_externa_m``
  (jazida/bota-fora a distância declarada), localizado pelos trechos de ``massas["volume_livre"]``
  e rateado pela fração de cada trecho dentro do segmento (revisão r12).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .cenarios import Ajuste, Projeto, executar
from .calendario import ordinal
from .massas import FATOR_HOMOGENEIZACAO, massas_da_obra, volume_no_intervalo


class ErroProdutividade(ValueError):
    """Parâmetro de frota inválido."""


@dataclass(frozen=True)
class ParametrosFrota:
    cacamba_m3: float = 2.0            # escavadeira ~35 t [OG]
    ciclo_escavadeira_s: float = 22.0
    enchimento: float = 0.85
    eficiencia: float = 0.70           # ~42 min produtivos por hora [OG]
    horas_dia: float = 8.0
    n_caminhoes: int = 8
    capacidade_caminhao_m3: float = 10.0   # solto
    v_carregado_kmh: float = 15.0      # estrada de serviço [OG]
    v_vazio_kmh: float = 25.0
    tempo_fixo_min: float = 3.0        # manobra + basculamento + posicionamento
    empolamento: float = 0.25
    fator_homogeneizacao: float = FATOR_HOMOGENEIZACAO
    dmt_externa_m: float = 3000.0      # empréstimo / bota-fora fora do eixo [OG]

    def __post_init__(self):
        for k, v in asdict(self).items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ErroProdutividade(f"parâmetro de frota inválido (não numérico ou não finito): {k} = {v!r}")
            if k == "empolamento":
                ok = v >= 0
            elif k == "enchimento" or k == "eficiencia":
                ok = 0 < v <= 1
            elif k == "n_caminhoes":
                ok = isinstance(v, int) and v >= 1        # frota sem caminhão não transporta (revisão r12)
            else:
                ok = v > 0
            if not ok:
                raise ErroProdutividade(f"parâmetro de frota inválido: {k} = {v!r}")

    @property
    def escavadeira_solto_h(self) -> float:
        """Produção instantânea (sem eficiência), m³ solto/h."""
        return 3600.0 / self.ciclo_escavadeira_s * self.cacamba_m3 * self.enchimento


def ciclo_caminhao_min(dmt_m: float, p: ParametrosFrota = ParametrosFrota()) -> float:
    if not dmt_m >= 0:
        raise ErroProdutividade(f"DMT inválida: {dmt_m!r}")
    carga = p.capacidade_caminhao_m3 / (p.escavadeira_solto_h / 60.0)
    km = dmt_m / 1000.0
    return carga + p.tempo_fixo_min + km / p.v_carregado_kmh * 60.0 + km / p.v_vazio_kmh * 60.0


def producao_frota(dmt_m: float, p: ParametrosFrota = ParametrosFrota()) -> dict:
    """Produção diária da frota (1 equipe) para a DMT dada."""
    esc = p.escavadeira_solto_h * p.eficiencia * p.horas_dia
    ciclo = ciclo_caminhao_min(dmt_m, p)
    cam = p.n_caminhoes * p.capacidade_caminhao_m3 * 60.0 / ciclo * p.eficiencia * p.horas_dia
    solto = min(esc, cam)
    return {"dmt_m": dmt_m, "ciclo_caminhao_min": ciclo,
            "escavadeira_m3_solto_dia": esc, "caminhoes_m3_solto_dia": cam,
            "producao_m3_solto_dia": solto, "producao_m3_corte_dia": solto / (1 + p.empolamento),
            "limitante": "escavadeira" if esc <= cam else "caminhões"}


def dmt_de_equilibrio_m(p: ParametrosFrota = ParametrosFrota()) -> float:
    """DMT em que caminhões e escavadeira produzem o mesmo: abaixo dela a escavadeira limita.
    0 se os caminhões já limitam com DMT 0 (frota subdimensionada)."""
    esc = p.escavadeira_solto_h * p.eficiencia * p.horas_dia
    ciclo_max = p.n_caminhoes * p.capacidade_caminhao_m3 * 60.0 * p.eficiencia * p.horas_dia / esc
    folga = ciclo_max - ciclo_caminhao_min(0.0, p)
    return max(0.0, folga / (60.0 / p.v_carregado_kmh + 60.0 / p.v_vazio_kmh) * 1000.0)


# ---------------------------------------------------------------------------- DMT por segmento
def _sobreposicao(a: float, b: float, ini: float, fim: float) -> float:
    """Fração de [ini, fim] dentro de [a, b] (trecho de comprimento zero: 1 se estiver dentro)."""
    if fim - ini <= 0:
        return 1.0 if a <= ini <= b else 0.0
    return max(0.0, min(b, fim) - max(a, ini)) / (fim - ini)


def dmt_por_segmento(dados: dict, massas: dict, p: ParametrosFrota = ParametrosFrota()) -> dict[str, dict]:
    if "volume_livre" not in massas:
        raise ErroProdutividade("diagrama de massas sem 'volume_livre' (gere com massas.calcular_massas)")
    out = {}
    for s in dados.get("segmentos", []):
        a, b = min(s["km_ini"], s["km_fim"]), max(s["km_ini"], s["km_fim"])
        vol = mom = vol_ext = 0.0
        for o in massas["compensacoes"]:
            comp = o["km_fim"] - o["km_ini"]
            sob = min(b, o["km_fim"]) - max(a, o["km_ini"])
            if comp <= 0 or sob <= 0:
                continue
            f = sob / comp
            vol += o["volume_m3"] * f
            mom += o["momento_m3m"] * f
        # bota-fora / empréstimo: localizado pelo diagrama (revisão r12; antes dependia da marca `aberta`)
        for t in massas["volume_livre"]:
            vol_ext += t["volume_m3"] * _sobreposicao(a, b, t["km_ini"], t["km_fim"])
        mom_ext = vol_ext * p.dmt_externa_m
        vt = vol + vol_ext
        out[s["id"]] = {"volume_compensado_m3": vol, "volume_externo_m3": vol_ext,
                        "momento_m3m": mom + mom_ext, "dmt_m": (mom + mom_ext) / vt if vt > 0 else 0.0}
    return out


def fator_quantidade(vc: float, va: float, fh: float) -> float:
    """m³ de TER (corte + aterro) por m³ de corte escavado: (Vc + Va) / max(Vc, Fh·Va). 1 se não há volume."""
    esc = max(vc, fh * va)
    return (vc + va) / esc if esc > 0 else 1.0


# ---------------------------------------------------------------------------- análise da obra
def analisar(projeto: Projeto, p: ParametrosFrota = ParametrosFrota(), passo_m: float = 20.0) -> dict:
    dados = projeto.dados
    massas = massas_da_obra(dados, passo_m)
    dmts = dmt_por_segmento(dados, massas, p)
    ativ = projeto.atividades
    linhas, ajustes = [], []
    for s in dados.get("segmentos", []):
        a = ativ.get(f"{s['id']}-TER")
        if not a or not a.get("quantidade_total"):
            continue
        vc, va = volume_no_intervalo(massas["estacas"], min(s["km_ini"], s["km_fim"]), max(s["km_ini"], s["km_fim"]))
        fq = fator_quantidade(vc, va, p.fator_homogeneizacao)
        pf = producao_frota(dmts[s["id"]]["dmt_m"], p)
        geo = pf["producao_m3_corte_dia"] * fq
        med, fonte = projeto.produtividade_efetiva(a)
        plan = a["produtividade_planejada"]
        status = a.get("status", "nao_iniciada")
        linhas.append({
            "segmento_id": s["id"], "atividade_id": a["id"], "status": status, "unidade": a.get("unidade"),
            "dmt_m": dmts[s["id"]]["dmt_m"], "volume_externo_m3": dmts[s["id"]]["volume_externo_m3"],
            "volume_corte_m3": vc, "volume_aterro_m3": va, "fator_quantidade": fq,
            "ciclo_caminhao_min": pf["ciclo_caminhao_min"], "limitante": pf["limitante"],
            "producao_m3_corte_dia": pf["producao_m3_corte_dia"],
            "produtividade_geometrica": geo, "produtividade_planejada": plan,
            "produtividade_medida": med, "fonte_medida": fonte,
            "geometrica_sobre_planejada": geo / plan, "medida_sobre_geometrica": med / geo if geo else None,
        })
        if status != "concluida":
            ajustes.append({"atividade_id": a["id"], "produtividade": round(geo, 3)})
    ind = executar(projeto, "independente")
    efeito = None
    if ajustes:
        sim = executar(projeto, "simulado", [Ajuste(**x) for x in ajustes])
        efeito = {"termino_independente": ind["termino"], "termino_pela_geometria": sim["termino"],
                  "delta_dias_corridos": ordinal(sim["termino"]) - ordinal(ind["termino"]),
                  "cadeia_determinante": sim["cadeia_determinante"]}
    return {
        "aviso": "Produtividade pela DMT com premissas de frota [OG] e terreno SINTÉTICO: ordem de grandeza, "
                 "não orçamento nem projeto de terraplenagem.",
        "parametros": asdict(p),
        "dmt_equilibrio_m": dmt_de_equilibrio_m(p),
        "metodo": "produção = min(escavadeira, n·cap·60/ciclo(DMT)) × eficiência × horas ÷ (1+empolamento) "
                  "× (Vc+Va)/max(Vc, Fh·Va)",
        "segmentos": linhas,
        "ajustes_recomendados": ajustes,
        "efeito_no_termino": efeito,
        "massas_total": massas["total"],
    }
