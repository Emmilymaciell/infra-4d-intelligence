"""Gerador determinístico da FERROVIA FICTÍCIA de demonstração.

TODOS OS DADOS SÃO SINTÉTICOS. Nenhum número representa obra, contrato,
construtora ou medição real. Faixas de ordem de grandeza: docs/research/R03.

Como os dados ficam coerentes entre si:
1. Monta a rede planejada (quantidade ÷ produtividade planejada) -> linha de base.
2. Aplica um FATOR DE DESEMPENHO por (lote, serviço) — a "realidade simulada" —
   e roda o MESMO motor CPM para obter o que "aconteceu".
3. Corta na data de status: o que começou antes vira início real; o que
   terminou vira término real; o executado sai da taxa simulada.
4. Gera boletins semanais (quantidade, equipes·dia) com ruído controlado.
   A produtividade efetiva do cenário independente é recalculada DESSES
   boletins, não do fator — a rastreabilidade é: boletim -> média -> duração.

Uso:  python -m infra4d.dados_sinteticos  (grava examples/synthetic/ferrovia_ficticia.json)
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from .calendario import Calendario, iso
from .sintetico_comum import (SERVICOS_OAE, calcular_rede, cortar_na_data_de_status, servico_cadastro,
                              sortear_fatores)

SEMENTE = 20261112
VERSAO_PREMISSAS = "P-2026.11-a"
DATA_STATUS = date(2026, 11, 9)
INICIO = date(2025, 11, 3)
KM_SEGMENTO = 5.0
SEGMENTOS_POR_LOTE = 4
OFFSET_TRILHO_L3 = 430  # dias corridos após o início: pedido de trilho do L3 em trânsito
FAIXA_FATOR_SORTEADO = (0.86, 1.04)  # fator dos pares (lote, serviço) fora de FATOR_DESEMPENHO
ORIGEM_BOLETIM = "SINTÉTICA — gerada por dados_sinteticos.py"


def iso_rel(dias: int) -> str:
    """Data relativa ao início da obra (as restrições sintéticas acompanham o início)."""
    return (INICIO + timedelta(days=dias)).isoformat()

FERIADOS_FIXOS = ["01-01", "04-21", "05-01", "09-07", "10-12", "11-02", "11-15", "11-20", "12-25"]

# id, nome, disciplina, unidade, qtd/km, produtividade planejada (un/equipe·dia), equipes, calendário,
# composição da equipe, equipamentos
SERVICOS = [
    ("SUP", "Supressão vegetal e limpeza", "Infraestrutura", "ha", 4.0, 2.0, 1, "CAL-TERRA",
     "1 encarregado, 12 ajudantes, 2 motosserristas", ["Trator de esteira D6", "Escavadeira 20 t"]),
    ("TER", "Terraplenagem (corte e aterro)", "Infraestrutura", "m³", 70000.0, 2400.0, 2, "CAL-TERRA",
     "frota: 1 encarregado, 1 operador de escavadeira, 8 motoristas, 3 operadores de compactação",
     ["Escavadeira 35 t", "8 caminhões basculantes", "Motoniveladora", "Rolo pé-de-carneiro", "Caminhão-pipa"]),
    ("DRE", "Drenagem (bueiros e dispositivos)", "Infraestrutura", "m", 420.0, 35.0, 1, "CAL-TERRA",
     "1 encarregado, 2 pedreiros, 6 ajudantes, 1 operador", ["Retroescavadeira", "Caminhão munck"]),
    ("SUB", "Sublastro", "Superestrutura", "m³", 2200.0, 650.0, 1, "CAL-VIA",
     "1 encarregado, 3 operadores, 4 motoristas", ["Motoniveladora", "Rolo liso", "4 caminhões", "Caminhão-pipa"]),
    ("DOR", "Distribuição de dormentes", "Superestrutura", "un", 1667.0, 1400.0, 1, "CAL-VIA",
     "1 encarregado, 2 operadores de pórtico, 8 ajudantes", ["Pórtico de dormentes", "Caminhões prancha"]),
    ("GRA", "Assentamento de grade (trilho TR-68)", "Via permanente", "km", 1.0, 0.45, 1, "CAL-VIA",
     "1 encarregado de via, 30 ajudantes de via, 2 operadores", ["Pórticos de lançamento", "Fixadora", "Vagões plataforma"]),
    ("LAS", "Lastro, levante e socaria", "Via permanente", "m³", 2000.0, 560.0, 1, "CAL-VIA",
     "1 encarregado, 3 operadores de via, 10 ajudantes", ["Socadora", "Reguladora de lastro", "Composição de lastro (hopper)"]),
    ("SOL", "Soldagem aluminotérmica", "Via permanente", "un", 8.4, 6.0, 1, "CAL-VIA",
     "1 soldador líder, 3 soldadores, 2 esmerilhadores", ["Kit aluminotérmico", "Esmerilhadeira de perfil"]),
]

# relações dentro do segmento: (pred, succ, tipo, lag)
RELACOES_SEGMENTO = [
    ("SUP", "TER", "SS", 5),
    ("TER", "DRE", "SS", 10), ("TER", "DRE", "FF", 5),
    ("TER", "SUB", "SS", 15), ("TER", "SUB", "FF", 5),
    ("DRE", "SUB", "SS", 10),
    ("SUB", "DOR", "SS", 5), ("SUB", "DOR", "FF", 2),
    ("DOR", "GRA", "SS", 2), ("DOR", "GRA", "FF", 1),
    ("GRA", "LAS", "SS", 5), ("GRA", "LAS", "FF", 3),
    ("LAS", "SOL", "SS", 5), ("LAS", "SOL", "FF", 2),
]
# serviços com frente única por lote (continuidade da equipe entre segmentos)
FRENTE_UNICA = ["SUP", "TER", "DRE", "SUB", "DOR", "GRA", "LAS", "SOL"]

OAES = [  # id, nome, lote, segmento (1..4), km, estacas, vãos
    ("OAE1", "Ponte sobre o Rio Fictício Claro", "L1", 3, 12.4, 48, 6),
    ("OAE2", "Viaduto Ferroviário da Serra Inventada", "L2", 2, 26.8, 64, 8),
    ("OAE3", "Ponte sobre o Córrego Simulado", "L3", 4, 57.1, 24, 3),
]

# "realidade simulada": fator de desempenho por (lote, serviço). Hand-set para a narrativa.
FATOR_DESEMPENHO = {
    ("L1", "TER"): 0.86, ("L2", "TER"): 0.93, ("L3", "TER"): 0.78,
    ("L2", "LAS"): 0.62, ("L1", "GRA"): 0.90, ("L2", "DRE"): 0.80,
}


# serviço de duração fixa do fechamento do lote (cadastro [OG])
SERVICO_SIN = servico_cadastro(
    "SIN", "Sinalização, testes e liberação do lote", "Sistemas", "vb", None,
    "1 engenheiro de sistemas, 2 técnicos de sinalização, 4 eletricistas, 1 equipe de via para testes",
    ["Carro-controle de geometria", "Caminhão munck", "Instrumentos de teste de sinalização"],
    duracao_fixa_dias=25)


# `sensivel_chuva`: marca BOOLEANA explícita (ADR-0005 / revisão r13) — quem precisa saber se o calendário
# para com chuva testa a marca, nunca o texto do nome.
def _calendarios(rng: random.Random) -> list[dict]:
    feriados = []
    for ano in range(2025, 2030):
        feriados += [f"{ano}-{md}" for md in FERIADOS_FIXOS]
    chuva = []  # dias perdidos por chuva: dez–mar, ~1 em cada 3 dias (sintético)
    d = date(2025, 1, 1)
    while d <= date(2029, 12, 31):
        if d.month in (12, 1, 2, 3) and rng.random() < 0.33:
            chuva.append(d.isoformat())
        d += timedelta(days=1)
    return [
        {"id": "CAL-OBRA", "sensivel_chuva": False, "nome": "Obra 6x1 (seg–sáb) com feriados nacionais fixos",
         "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": feriados},
        {"id": "CAL-TERRA", "sensivel_chuva": True, "nome": "Terraplenagem/drenagem 6x1 + dias de chuva (sintéticos, dez–mar)",
         "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": sorted(set(feriados + chuva))},
        {"id": "CAL-VIA", "sensivel_chuva": False, "nome": "Via permanente 6x1 com feriados",
         "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": feriados},
        {"id": "CAL-ADM", "sensivel_chuva": False, "nome": "Administrativo 5x2 com feriados",
         "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": feriados},
    ]


def _montar_rede():
    lotes, segmentos, atividades, relacoes = [], [], [], []
    serv = {s[0]: s for s in SERVICOS}

    def rel(p, s, t="FS", lag=0):
        relacoes.append({"predecessora": p, "sucessora": s, "tipo": t, "lag": lag})

    atividades.append({"id": "M-OS", "nome": "Ordem de serviço (início contratual)", "tipo": "marco_inicio",
                       "calendario": "CAL-OBRA", "lote_id": None, "segmento_id": None, "servico_id": None,
                       "disciplina": "Marcos"})
    construtoras = {"L1": "Consórcio Fictício Alfa", "L2": "Consórcio Fictício Beta", "L3": "Construtora Fictícia Gama"}
    for li in range(3):
        lid = f"L{li + 1}"
        km0 = li * SEGMENTOS_POR_LOTE * KM_SEGMENTO
        lotes.append({"id": lid, "nome": f"Lote {li + 1}", "km_ini": km0,
                      "km_fim": km0 + SEGMENTOS_POR_LOTE * KM_SEGMENTO, "construtora": construtoras[lid]})
        for si in range(SEGMENTOS_POR_LOTE):
            sid = f"{lid}-S{si + 1:02d}"
            a, b = km0 + si * KM_SEGMENTO, km0 + (si + 1) * KM_SEGMENTO
            segmentos.append({"id": sid, "lote_id": lid, "km_ini": a, "km_fim": b,
                              "estaca_ini": round(a * 50), "estaca_fim": round(b * 50)})
            for (cod, nome, disc, un, qkm, prod, eq, cal, _c, _e) in SERVICOS:
                aid = f"{sid}-{cod}"
                atividades.append({
                    "id": aid, "nome": f"{nome} — {sid} (km {a:.0f}–{b:.0f})", "tipo": "tarefa",
                    "lote_id": lid, "segmento_id": sid, "servico_id": cod, "disciplina": disc,
                    "km_ini": a, "km_fim": b, "unidade": un,
                    "quantidade_total": round(qkm * KM_SEGMENTO, 2), "produtividade_planejada": prod,
                    "equipes": eq, "calendario": cal,
                })
            for p, s, t, lag in RELACOES_SEGMENTO:
                rel(f"{sid}-{p}", f"{sid}-{s}", t, lag)
            if si > 0:
                ant = f"{lid}-S{si:02d}"
                for cod in FRENTE_UNICA:
                    rel(f"{ant}-{cod}", f"{sid}-{cod}", "FS", 0)
            else:
                rel("M-OS", f"{sid}-SUP")
        # sinalização/testes e conclusão do lote
        atividades.append({"id": f"{lid}-SIN", "nome": f"Sinalização, testes e liberação — {lid}", "tipo": "tarefa",
                           "lote_id": lid, "segmento_id": None, "servico_id": "SIN", "disciplina": "Sistemas",
                           "duracao_fixa": 25, "calendario": "CAL-OBRA", "km_ini": km0, "km_fim": km0 + 20})
        rel(f"{lid}-S{SEGMENTOS_POR_LOTE:02d}-SOL", f"{lid}-SIN")
        atividades.append({"id": f"M-{lid}-FIM", "nome": f"Conclusão do {lid}", "tipo": "marco_termino",
                           "lote_id": lid, "segmento_id": None, "servico_id": None, "disciplina": "Marcos",
                           "calendario": "CAL-OBRA"})
        rel(f"{lid}-SIN", f"M-{lid}-FIM")

    # restrições (SNET) — sintéticas
    restricoes = [
        {"id": "R-LI-L3", "descricao": "Licença de instalação do Lote 3 (sintética)",
         "atividade_id": "L3-S01-SUP", "data_liberacao": iso_rel(85)},
        {"id": "R-TRI-L1", "descricao": "1ª entrega de trilhos TR-68 no estaleiro do Lote 1",
         "atividade_id": "L1-S01-GRA", "data_liberacao": iso_rel(200)},
        {"id": "R-TRI-L2", "descricao": "Entrega de trilhos TR-68 no Lote 2",
         "atividade_id": "L2-S01-GRA", "data_liberacao": iso_rel(260)},
        {"id": "R-TRI-L3", "descricao": "Entrega de trilhos TR-68 no Lote 3 (pedido em trânsito)",
         "atividade_id": "L3-S01-GRA", "data_liberacao": iso_rel(OFFSET_TRILHO_L3)},
        {"id": "R-DES-L2S3", "descricao": "Desapropriação km 30–35 (sintética)",
         "atividade_id": "L2-S03-SUP", "data_liberacao": iso_rel(150)},
    ]
    for r in restricoes:
        # data PREVISTA no planejamento (conhecida desde o início). No mundo sintético a liberação real acontece
        # na data prevista; o campo existe para a fotografia de uma data passada (MTA/backtest) não usar a data
        # REAL de liberação, que é informação futura (R12).
        r["data_liberacao_planejada"] = r["data_liberacao"]
        r["situacao"] = "liberada" if r["data_liberacao"] <= DATA_STATUS.isoformat() else "pendente"
        next(a for a in atividades if a["id"] == r["atividade_id"])["restricao_inicio"] = r["data_liberacao"]

    # OAEs: fundação -> mesoestrutura -> superestrutura -> grade do segmento
    elementos_oae = []
    for oid, nome, lid, seg, km, estacas, vaos in OAES:
        sid = f"{lid}-S{seg:02d}"
        partes = [
            ("FUN", "Fundações (estacas)", "un", estacas, 2.0, 1, "Perfuratriz de estacas, guindaste"),
            ("MES", "Mesoestrutura (pilares e travessas)", "un", vaos + 1, 0.12, 1, "Formas, guindaste"),
            ("SUE", "Superestrutura (vigas e tabuleiro)", "un", vaos, 0.10, 1, "Treliça lançadeira"),
        ]
        prev = None
        for cod, pn, un, q, prod, eq, equip in partes:
            aid = f"{oid}-{cod}"
            atividades.append({
                "id": aid, "nome": f"{pn} — {nome}", "tipo": "tarefa", "lote_id": lid, "segmento_id": sid,
                "servico_id": f"OAE-{cod}", "disciplina": "Obras de arte especiais", "km_ini": km - 0.2,
                "km_fim": km + 0.2, "unidade": un, "quantidade_total": float(q), "produtividade_planejada": prod,
                "equipes": eq, "calendario": "CAL-OBRA", "oae_id": oid,
            })
            rel(prev or f"{sid}-SUP", aid, "FS" if prev else "SS", 0 if prev else 10)
            prev = aid
        rel(prev, f"{sid}-GRA", "FS", 5)
        elementos_oae.append({"id": oid, "nome": nome, "lote_id": lid, "segmento_id": sid, "km": km, "vaos": vaos})

    atividades.append({"id": "M-FIM", "nome": "Conclusão da ferrovia (operação assistida liberada)",
                       "tipo": "marco_termino", "lote_id": None, "segmento_id": None, "servico_id": None,
                       "disciplina": "Marcos", "calendario": "CAL-OBRA"})
    for lid in ("L1", "L2", "L3"):
        rel(f"M-{lid}-FIM", "M-FIM")
    return lotes, segmentos, atividades, relacoes, restricoes, elementos_oae, serv


NOME_OBRA = "ferrovia"
GABARITO = Path(__file__).resolve().parents[2] / "examples" / "synthetic" / "gabarito" / f"{NOME_OBRA}_gabarito.json"


def _mundo(semente: int):
    """Rede, calendários, fatores verdadeiros e a realidade simulada (mesma sequência de rng do ``gerar``)."""
    rng = random.Random(semente)
    cals = {c["id"]: Calendario.de_dict(c) for c in _calendarios(rng)}
    lotes, segmentos, atividades, relacoes, restricoes, oaes, serv = _montar_rede()
    fatores = sortear_fatores(atividades, FATOR_DESEMPENHO, rng, FAIXA_FATOR_SORTEADO)
    real = calcular_rede(atividades, relacoes, cals, INICIO, fator=lambda a: fatores[(a["lote_id"], a["servico_id"])])
    return atividades, cals, fatores, real


def realidade_simulada(semente: int = SEMENTE) -> dict[str, str]:
    """Término de cada atividade na REALIDADE SIMULADA (o "futuro" que o gerador usa e NÃO exporta no dataset).
    Serve SÓ para avaliação (backtest/atribuição), via ``sintetico_comum.gabarito``."""
    atividades, cals, _f, real = _mundo(semente)
    return {a["id"]: iso(cals[a["calendario"]].ultimo_dia_util(real.atividades[a["id"]].ef)) for a in atividades}


def gabarito(semente: int = SEMENTE) -> dict:
    """GABARITO do mundo sintético (P9): fatores de desempenho verdadeiros e términos da realidade simulada.
    Fica FORA do dataset publicado, em ``examples/synthetic/gabarito/``; só a avaliação o lê."""
    atividades, cals, fatores, real = _mundo(semente)
    return {
        "ficticio": True,
        "aviso": "GABARITO FICTÍCIO do mundo sintético: só para AVALIAR previsões (backtest, atribuição do erro). "
                 "Nenhum módulo de previsão pode ler este arquivo.",
        "obra": NOME_OBRA, "gerador": "scripts/infra4d/dados_sinteticos.py", "semente": semente, "versao_premissas": VERSAO_PREMISSAS,
        "fatores_desempenho_simulados": {f"{k[0]}/{k[1]}": v for k, v in sorted(fatores.items())},
        "termino_realidade_simulada": {a["id"]: iso(cals[a["calendario"]].ultimo_dia_util(real.atividades[a["id"]].ef))
                                       for a in atividades},
    }


def gerar(semente: int = SEMENTE) -> dict:
    rng = random.Random(semente)
    cal_dicts = _calendarios(rng)
    cals = {c["id"]: Calendario.de_dict(c) for c in cal_dicts}
    lotes, segmentos, atividades, relacoes, restricoes, oaes, serv = _montar_rede()

    # 1) linha de base; 2) realidade simulada; 3) corte na data de status + boletins (sintetico_comum)
    base = calcular_rede(atividades, relacoes, cals, INICIO)
    fatores = sortear_fatores(atividades, FATOR_DESEMPENHO, rng, FAIXA_FATOR_SORTEADO)
    real = calcular_rede(atividades, relacoes, cals, INICIO, fator=lambda a: fatores[(a["lote_id"], a["servico_id"])])
    medicoes = cortar_na_data_de_status(atividades, base, real, cals, fatores, rng, DATA_STATUS, ORIGEM_BOLETIM)

    meta = {
        # marca EXPLÍCITA e booleana: quem precisa saber se a obra é fictícia testa `meta.ficticio is True`,
        # nunca o texto do aviso (revisão r6: "NÃO é fictício" passava no teste por substring)
        "ficticio": True,
        "tipo_obra": "ferrovia",   # declarado (antes era implícito: ausência = ferrovia)
        "aviso": "DADOS INTEIRAMENTE FICTÍCIOS — gerados para demonstração. Não representam obra, contrato, "
                 "empresa ou medição real.",
        "gerador": "scripts/infra4d/dados_sinteticos.py",
        "semente": semente,
        "versao_premissas": VERSAO_PREMISSAS,
        "inicio_projeto": INICIO.isoformat(),
        "data_status": DATA_STATUS.isoformat(),
        "calendario_obra": "CAL-OBRA",
        "termino_linha_base": iso(cals["CAL-OBRA"].ultimo_dia_util(base.termino_projeto)),
        "termino_realidade_simulada_oculta": "não exportado (o motor não deve ver o futuro)",
        "gabarito": "fora do dataset (P9): examples/synthetic/gabarito/, só para avaliação",
    }
    alinhamento = []
    for i in range(0, 601):
        km = i * 0.1
        x = km * 1000.0
        y = 900.0 * math.sin(km / 9.0) + 350.0 * math.sin(km / 3.7)
        z = 40.0 * math.sin(km / 6.0) + 12.0 * math.sin(km / 1.9)
        alinhamento.append([round(km, 1), round(x, 1), round(y, 1), round(z, 2)])
    return {
        "meta": meta,
        "ferrovia": {"id": "EF-FIC", "nome": "Ferrovia Fictícia Vale do Sintético (EF-FIC)",
                     "extensao_km": 60.0, "bitola": "larga (1,60 m)", "via": "singela", "trilho": "TR-68"},
        "lotes": lotes,
        "segmentos": segmentos,
        "servicos": [{"id": s[0], "nome": s[1], "disciplina": s[2], "unidade": s[3], "quantidade_por_km": s[4],
                      "produtividade_planejada": s[5], "equipes_padrao": s[6], "calendario": s[7],
                      "equipe": s[8], "equipamentos": s[9]} for s in SERVICOS] + SERVICOS_OAE + [SERVICO_SIN],
        "calendarios": cal_dicts,
        "atividades": atividades,
        "relacoes": relacoes,
        "restricoes": restricoes,
        "oaes": oaes,
        "medicoes": medicoes,
        "alinhamento": {"colunas": ["km", "x_m", "y_m", "cota_m"], "pontos": alinhamento,
                        "nota": "eixo sintético; coordenadas locais em metros"},
    }


def main():
    from .cenarios import DATASET_PADRAO
    dados = gerar()
    DATASET_PADRAO.parent.mkdir(parents=True, exist_ok=True)
    DATASET_PADRAO.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    GABARITO.parent.mkdir(parents=True, exist_ok=True)
    GABARITO.write_text(json.dumps(gabarito(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"gravado {DATASET_PADRAO} — {len(dados['atividades'])} atividades, "
          f"{len(dados['relacoes'])} relações, {len(dados['medicoes'])} boletins; "
          f"LB termina {dados['meta']['termino_linha_base']}")


if __name__ == "__main__":
    main()
