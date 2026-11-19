"""Gerador determinístico da RODOVIA FICTÍCIA de demonstração (2º caso).

TODOS OS DADOS SÃO SINTÉTICOS. Nenhum número representa obra, contrato,
construtora ou medição real. Premissas e faixas: docs/research/R06-premissas-rodovia.md
(ordem de grandeza, marcadas [OG] quando sem fonte).

Mesmo esquema JSON e mesmo mecanismo da ferrovia (``dados_sinteticos.py``):
1. rede planejada (quantidade ÷ produtividade planejada) -> linha de base;
2. FATOR DE DESEMPENHO por (lote, serviço) -> "realidade simulada" pelo MESMO motor CPM;
3. corte na data de status -> início/término reais e executado;
4. boletins semanais com ruído; o último boletim fecha a soma no executado.

Chaves de topo idênticas às da ferrovia (inclusive ``ferrovia``, que é a chave que o
código consome para "a obra"); a diferença é declarada em ``meta.tipo_obra = "rodovia"``.

Narrativa da demo: CBUQ do Lote 2 limitado pela usina de asfalto (crítico, abaixo do
planejado); defensas metálicas com folga.

Uso:  python -m infra4d.dados_sinteticos_rodovia  (grava examples/synthetic/rodovia_ficticia.json)
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

from .calendario import Calendario, iso
from .dados_sinteticos import FERIADOS_FIXOS
from .sintetico_comum import (SERVICOS_OAE, calcular_rede, cortar_na_data_de_status, servico_cadastro,
                              sortear_fatores)

RAIZ = Path(__file__).resolve().parents[2]
DATASET_RODOVIA = RAIZ / "examples" / "synthetic" / "rodovia_ficticia.json"

SEMENTE = 20261113
VERSAO_PREMISSAS = "P-2026.11-rod-a"
DATA_STATUS = date(2026, 11, 9)
INICIO = date(2025, 12, 1)
KM_SEGMENTO = 4.0
SEGMENTOS_POR_LOTE = 4
N_LOTES = 3
USI_CENTRAL = 300   # dias corridos após o início: LO da usina central (L2/L3)
DEF_L3 = 400        # dias corridos após o início: entrega das defensas do L3 (pendente na data de status)
EXTENSAO_KM = KM_SEGMENTO * SEGMENTOS_POR_LOTE * N_LOTES  # 48 km
ORIGEM_BOLETIM = "SINTÉTICA — gerada por dados_sinteticos_rodovia.py"
FAIXA_FATOR_SORTEADO = (0.88, 1.04)  # fator dos pares (lote, serviço) fora de FATOR_DESEMPENHO


def iso_rel(dias: int) -> str:
    """Data relativa ao início da obra."""
    return (INICIO + timedelta(days=dias)).isoformat()


# Pista nova da duplicação: 7,2 m + acostamentos 2 x 2,5 m (plataforma ~13 m). [OG]
# id, nome, disciplina, unidade, qtd/km, produtividade planejada (un/equipe·dia), equipes, calendário,
# composição da equipe, equipamentos
SERVICOS = [
    ("SUP", "Supressão vegetal e limpeza da faixa", "Terraplenagem", "ha", 3.5, 2.0, 1, "CAL-TERRA",
     "1 encarregado, 10 ajudantes, 2 motosserristas", ["Trator de esteira D6", "Escavadeira 20 t"]),
    ("TER", "Terraplenagem (corte, aterro e compactação)", "Terraplenagem", "m³", 60000.0, 2200.0, 2, "CAL-TERRA",
     "frota: 1 encarregado, 1 operador de escavadeira, 8 motoristas, 3 operadores de compactação",
     ["Escavadeira 35 t", "8 caminhões basculantes", "Motoniveladora", "Rolo pé-de-carneiro", "Caminhão-pipa"]),
    ("DRE", "Drenagem (bueiros e dispositivos)", "Drenagem", "m", 320.0, 30.0, 1, "CAL-TERRA",
     "1 encarregado, 2 pedreiros, 6 ajudantes, 1 operador", ["Retroescavadeira", "Caminhão munck", "Betoneira"]),
    ("SBB", "Reforço do subleito e sub-base granular", "Pavimentação", "m³", 2600.0, 650.0, 1, "CAL-TERRA",
     "1 encarregado, 3 operadores, 5 motoristas", ["Motoniveladora", "Rolo pé-de-carneiro", "Rolo liso",
                                                    "5 caminhões basculantes", "Caminhão-pipa"]),
    ("BGS", "Base de brita graduada simples (BGS)", "Pavimentação", "m³", 2200.0, 600.0, 1, "CAL-OBRA",
     "1 encarregado, 3 operadores, 5 motoristas", ["Usina de solos", "Vibroacabadora/motoniveladora", "Rolo liso",
                                                   "5 caminhões basculantes"]),
    ("IMP", "Imprimação (CM-30 / EAI)", "Pavimentação", "m²", 12200.0, 9000.0, 1, "CAL-PAV",
     "1 encarregado, 1 operador de distribuidor, 2 ajudantes", ["Caminhão distribuidor de asfalto", "Vassoura mecânica"]),
    ("CBU", "Revestimento em CBUQ (binder + capa)", "Pavimentação", "t", 2000.0, 650.0, 1, "CAL-PAV",
     "1 encarregado de pavimentação, 1 operador de vibroacabadora, 2 rasteleiros, 3 operadores de rolo, 8 motoristas",
     ["Usina gravimétrica 120 t/h", "Vibroacabadora", "Rolo pneumático", "Rolo tandem", "8 caminhões basculantes"]),
    ("SHV", "Sinalização horizontal (pintura e tachas)", "Sinalização e segurança", "m", 3000.0, 4000.0, 1, "CAL-PAV",
     "1 encarregado, 1 operador, 4 ajudantes", ["Caminhão de pintura de faixas", "Pré-marcadora"]),
    ("SVV", "Sinalização vertical (placas)", "Sinalização e segurança", "un", 6.0, 3.0, 1, "CAL-OBRA",
     "1 encarregado, 4 ajudantes", ["Caminhão munck", "Perfuratriz de solo"]),
    ("DEF", "Dispositivos de segurança (defensas metálicas)", "Sinalização e segurança", "m", 250.0, 100.0, 1,
     "CAL-OBRA", "1 encarregado, 1 operador de bate-estacas, 4 montadores", ["Bate-estacas de defensa", "Caminhão munck"]),
]

# relações dentro do segmento: (pred, succ, tipo, lag em dias úteis da sucessora)
RELACOES_SEGMENTO = [
    ("SUP", "TER", "SS", 5),
    ("TER", "DRE", "SS", 10), ("TER", "DRE", "FF", 5),
    ("TER", "SBB", "SS", 15), ("TER", "SBB", "FF", 5),
    ("DRE", "SBB", "SS", 10),
    ("SBB", "BGS", "SS", 5), ("SBB", "BGS", "FF", 2),
    ("BGS", "IMP", "SS", 3), ("BGS", "IMP", "FF", 1),
    ("IMP", "CBU", "SS", 3), ("IMP", "CBU", "FF", 2),   # cura da imprimação (~72 h) antes do CBUQ
    ("CBU", "SHV", "FS", 5),                             # sinalização definitiva após cura do CBUQ
    ("CBU", "SVV", "SS", 5),
    ("CBU", "DEF", "SS", 5),
]
# frente única por lote (continuidade da equipe/usina entre segmentos)
FRENTE_UNICA = ["SUP", "TER", "DRE", "SBB", "BGS", "IMP", "CBU", "SHV", "SVV", "DEF"]

OAES = [  # id, nome, lote, segmento (1..4), km, estacas, vãos
    ("OAE1", "Ponte sobre o Ribeirão Fictício", "L1", 2, 6.3, 32, 4),
    ("OAE2", "Viaduto do Entroncamento Sintético", "L2", 3, 25.4, 40, 5),
    ("OAE3", "Ponte sobre o Rio Inventado", "L3", 1, 33.8, 48, 6),
]

# "realidade simulada": fator por (lote, serviço). Hand-set para a narrativa da demo.
FATOR_DESEMPENHO = {
    ("L2", "CBU"): 0.60,   # usina do L2 limitada (britagem/CAP) — crítico e abaixo do planejado
    ("L1", "TER"): 0.90, ("L2", "TER"): 0.94, ("L3", "TER"): 0.84,
    ("L2", "BGS"): 0.90, ("L1", "DEF"): 0.82,
}


# serviço de duração fixa do fechamento do lote (cadastro [OG])
SERVICO_LIB = servico_cadastro(
    "LIB", "Vistoria, cadastro as built e liberação ao tráfego", "Recebimento", "vb", None,
    "1 engenheiro, 2 topógrafos, 1 técnico de laboratório, 2 ajudantes",
    ["Estação total", "Veículo de apoio", "Viga Benkelman (deflexões)"],
    duracao_fixa_dias=15)


# `sensivel_chuva`: marca BOOLEANA explícita (ADR-0005 / revisão r13) — quem precisa saber se o calendário
# para com chuva testa a marca, nunca o texto do nome.
def _calendarios(rng: random.Random) -> list[dict]:
    feriados = []
    for ano in range(2025, 2030):
        feriados += [f"{ano}-{md}" for md in FERIADOS_FIXOS]
    chuva, umido = [], []
    d = date(2025, 1, 1)
    while d <= date(2029, 12, 31):
        r = rng.random()
        if d.month in (11, 12, 1, 2, 3) and r < 0.30:
            chuva.append(d)
        elif d.month in (10, 4) and r < 0.12:
            chuva.append(d)
        d += timedelta(days=1)
    # pavimentação: além da chuva, perde o dia seguinte com superfície úmida em ~60% dos casos
    for c in chuva:
        if rng.random() < 0.60:
            umido.append(c + timedelta(days=1))
    chuva_iso = [x.isoformat() for x in chuva]
    pav_iso = sorted(set(chuva_iso + [x.isoformat() for x in umido] + feriados))
    return [
        {"id": "CAL-OBRA", "sensivel_chuva": False, "nome": "Obra 6x1 (seg–sáb) com feriados nacionais fixos",
         "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": feriados},
        {"id": "CAL-TERRA", "sensivel_chuva": True, "nome": "Terraplenagem/drenagem/sub-base 6x1 + chuva (sintética, nov–mar forte, out/abr fraca)",
         "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": sorted(set(feriados + chuva_iso))},
        {"id": "CAL-PAV", "sensivel_chuva": True, "nome": "Imprimação/CBUQ/pintura 6x1: sem chuva E sem superfície úmida no dia seguinte",
         "dias_semana": [0, 1, 2, 3, 4, 5], "nao_uteis": pav_iso},
        {"id": "CAL-ADM", "sensivel_chuva": False, "nome": "Administrativo 5x2 com feriados",
         "dias_semana": [0, 1, 2, 3, 4], "nao_uteis": feriados},
    ]


def _montar_rede():
    lotes, segmentos, atividades, relacoes = [], [], [], []

    def rel(p, s, t="FS", lag=0):
        relacoes.append({"predecessora": p, "sucessora": s, "tipo": t, "lag": lag})

    atividades.append({"id": "M-OS", "nome": "Ordem de serviço (início contratual)", "tipo": "marco_inicio",
                       "calendario": "CAL-OBRA", "lote_id": None, "segmento_id": None, "servico_id": None,
                       "disciplina": "Marcos"})
    construtoras = {"L1": "Consórcio Fictício Planalto", "L2": "Construtora Fictícia Cerrado",
                    "L3": "Consórcio Fictício Chapada"}
    km_lote = SEGMENTOS_POR_LOTE * KM_SEGMENTO
    for li in range(N_LOTES):
        lid = f"L{li + 1}"
        km0 = li * km_lote
        lotes.append({"id": lid, "nome": f"Lote {li + 1}", "km_ini": km0, "km_fim": km0 + km_lote,
                      "construtora": construtoras[lid]})
        for si in range(SEGMENTOS_POR_LOTE):
            sid = f"{lid}-S{si + 1:02d}"
            a, b = km0 + si * KM_SEGMENTO, km0 + (si + 1) * KM_SEGMENTO
            segmentos.append({"id": sid, "lote_id": lid, "km_ini": a, "km_fim": b,
                              "estaca_ini": round(a * 50), "estaca_fim": round(b * 50)})  # estaca de 20 m
            for (cod, nome, disc, un, qkm, prod, eq, cal, _c, _e) in SERVICOS:
                atividades.append({
                    "id": f"{sid}-{cod}", "nome": f"{nome} — {sid} (km {a:.0f}–{b:.0f})", "tipo": "tarefa",
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
        ult = f"{lid}-S{SEGMENTOS_POR_LOTE:02d}"
        atividades.append({"id": f"{lid}-LIB", "nome": f"Vistoria, cadastro as built e liberação ao tráfego — {lid}",
                           "tipo": "tarefa", "lote_id": lid, "segmento_id": None, "servico_id": "LIB",
                           "disciplina": "Recebimento", "duracao_fixa": 15, "calendario": "CAL-OBRA",
                           "km_ini": km0, "km_fim": km0 + km_lote})
        for cod in ("SHV", "SVV", "DEF"):
            rel(f"{ult}-{cod}", f"{lid}-LIB")
        atividades.append({"id": f"M-{lid}-FIM", "nome": f"Conclusão do {lid}", "tipo": "marco_termino",
                           "lote_id": lid, "segmento_id": None, "servico_id": None, "disciplina": "Marcos",
                           "calendario": "CAL-OBRA"})
        rel(f"{lid}-LIB", f"M-{lid}-FIM")

    # restrições (SNET) — sintéticas
    restricoes = [
        {"id": "R-LI-L3", "descricao": "Licença de instalação do Lote 3 (sintética)",
         "atividade_id": "L3-S01-SUP", "data_liberacao": iso_rel(70)},
        {"id": "R-DES-L2S2", "descricao": "Desapropriação km 20–24 (sintética)",
         "atividade_id": "L2-S02-SUP", "data_liberacao": iso_rel(140)},
        {"id": "R-JAZ-L1", "descricao": "Jazida de cascalho/brita do Lote 1 liberada (ANM + licença) — sintética",
         "atividade_id": "L1-S01-SBB", "data_liberacao": iso_rel(150)},
        {"id": "R-USI-L1", "descricao": "Usina de asfalto do Lote 1 licenciada (LO) e calibrada",
         "atividade_id": "L1-S01-CBU", "data_liberacao": iso_rel(260)},
        {"id": "R-USI-C", "descricao": "Usina central de asfalto (atende L2 e L3) licenciada (LO) e calibrada",
         "atividade_id": "L2-S01-CBU", "data_liberacao": iso_rel(USI_CENTRAL)},
        {"id": "R-DEF-L3", "descricao": "Entrega das defensas metálicas do Lote 3 (fornecedor, sintética)",
         "atividade_id": "L3-S01-DEF", "data_liberacao": iso_rel(DEF_L3)},
    ]
    for r in restricoes:
        # data PREVISTA no planejamento (conhecida desde o início). No mundo sintético a liberação real acontece
        # na data prevista; o campo existe para a fotografia de uma data passada (MTA/backtest) não usar a data
        # REAL de liberação, que é informação futura (R12).
        r["data_liberacao_planejada"] = r["data_liberacao"]
        r["situacao"] = "liberada" if r["data_liberacao"] <= DATA_STATUS.isoformat() else "pendente"
        next(a for a in atividades if a["id"] == r["atividade_id"])["restricao_inicio"] = r["data_liberacao"]

    # OAEs: fundação -> mesoestrutura -> superestrutura -> CBUQ do segmento (lajes de aproximação)
    elementos_oae = []
    for oid, nome, lid, seg, km, estacas, vaos in OAES:
        sid = f"{lid}-S{seg:02d}"
        partes = [
            ("FUN", "Fundações (estacas)", "un", estacas, 2.0, 1),
            ("MES", "Mesoestrutura (pilares e travessas)", "un", vaos + 1, 0.12, 1),
            ("SUE", "Superestrutura (vigas, tabuleiro e lajes de aproximação)", "un", vaos, 0.10, 1),
        ]
        prev = None
        for cod, pn, un, q, prod, eq in partes:
            aid = f"{oid}-{cod}"
            atividades.append({
                "id": aid, "nome": f"{pn} — {nome}", "tipo": "tarefa", "lote_id": lid, "segmento_id": sid,
                "servico_id": f"OAE-{cod}", "disciplina": "Obras de arte especiais", "km_ini": km - 0.2,
                "km_fim": km + 0.2, "unidade": un, "quantidade_total": float(q), "produtividade_planejada": prod,
                "equipes": eq, "calendario": "CAL-OBRA", "oae_id": oid,
            })
            rel(prev or f"{sid}-SUP", aid, "FS" if prev else "SS", 0 if prev else 10)
            prev = aid
        rel(prev, f"{sid}-CBU", "FS", 10)
        elementos_oae.append({"id": oid, "nome": nome, "lote_id": lid, "segmento_id": sid, "km": km, "vaos": vaos})

    atividades.append({"id": "M-FIM", "nome": "Conclusão da rodovia (liberação total ao tráfego)",
                       "tipo": "marco_termino", "lote_id": None, "segmento_id": None, "servico_id": None,
                       "disciplina": "Marcos", "calendario": "CAL-OBRA"})
    # usina central compartilhada: a equipe de CBUQ do L3 só começa depois de fechar o L2 (recurso único)
    rel("L2-S04-CBU", "L3-S01-CBU", "FS", 3)
    for i in range(N_LOTES):
        rel(f"M-L{i + 1}-FIM", "M-FIM")
    return lotes, segmentos, atividades, relacoes, restricoes, elementos_oae


NOME_OBRA = "rodovia"
GABARITO = Path(__file__).resolve().parents[2] / "examples" / "synthetic" / "gabarito" / f"{NOME_OBRA}_gabarito.json"


def _mundo(semente: int):
    """Rede, calendários, fatores verdadeiros e a realidade simulada (mesma sequência de rng do ``gerar``)."""
    rng = random.Random(semente)
    cals = {c["id"]: Calendario.de_dict(c) for c in _calendarios(rng)}
    lotes, segmentos, atividades, relacoes, restricoes, oaes = _montar_rede()
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
        "obra": NOME_OBRA, "gerador": "scripts/infra4d/dados_sinteticos_rodovia.py", "semente": semente, "versao_premissas": VERSAO_PREMISSAS,
        "fatores_desempenho_simulados": {f"{k[0]}/{k[1]}": v for k, v in sorted(fatores.items())},
        "termino_realidade_simulada": {a["id"]: iso(cals[a["calendario"]].ultimo_dia_util(real.atividades[a["id"]].ef))
                                       for a in atividades},
    }


def gerar(semente: int = SEMENTE) -> dict:
    rng = random.Random(semente)
    cal_dicts = _calendarios(rng)
    cals = {c["id"]: Calendario.de_dict(c) for c in cal_dicts}
    lotes, segmentos, atividades, relacoes, restricoes, oaes = _montar_rede()

    base = calcular_rede(atividades, relacoes, cals, INICIO)
    fatores = sortear_fatores(atividades, FATOR_DESEMPENHO, rng, FAIXA_FATOR_SORTEADO)
    real = calcular_rede(atividades, relacoes, cals, INICIO, fator=lambda a: fatores[(a["lote_id"], a["servico_id"])])
    medicoes = cortar_na_data_de_status(atividades, base, real, cals, fatores, rng, DATA_STATUS, ORIGEM_BOLETIM)

    meta = {
        # marca EXPLÍCITA e booleana: quem precisa saber se a obra é fictícia testa `meta.ficticio is True`,
        # nunca o texto do aviso (revisão r6: "NÃO é fictício" passava no teste por substring)
        "ficticio": True,
        "aviso": "DADOS INTEIRAMENTE FICTÍCIOS — gerados para demonstração. Não representam obra, contrato, "
                 "empresa, rodovia ou medição real.",
        "tipo_obra": "rodovia",
        "gerador": "scripts/infra4d/dados_sinteticos_rodovia.py",
        "semente": semente,
        "versao_premissas": VERSAO_PREMISSAS,
        "premissas": "docs/research/R06-premissas-rodovia.md",
        "inicio_projeto": INICIO.isoformat(),
        "data_status": DATA_STATUS.isoformat(),
        "calendario_obra": "CAL-OBRA",
        "termino_linha_base": iso(cals["CAL-OBRA"].ultimo_dia_util(base.termino_projeto)),
        "termino_realidade_simulada_oculta": "não exportado (o motor não deve ver o futuro)",
        "gabarito": "fora do dataset (P9): examples/synthetic/gabarito/, só para avaliação",
    }
    alinhamento = []
    for i in range(0, round(EXTENSAO_KM * 10) + 1):
        km = i * 0.1
        x = km * 1000.0
        y = 650.0 * math.sin(km / 7.5) + 220.0 * math.sin(km / 2.9)
        z = 30.0 * math.sin(km / 5.5) + 9.0 * math.sin(km / 2.1)
        alinhamento.append([round(km, 1), round(x, 1), round(y, 1), round(z, 2)])
    return {
        "meta": meta,
        # chave "ferrovia" mantida por compatibilidade de esquema: é "a obra" para o código que a consome
        "ferrovia": {"id": "BR-FIC-999", "nome": "BR-FIC 999 — Rodovia Fictícia do Planalto Sintético (duplicação)",
                     "extensao_km": EXTENSAO_KM, "tipo": "rodovia", "pista": "duplicação (nova pista 7,2 m + "
                     "acostamentos 2 × 2,5 m)", "pavimento": "flexível: sub-base granular, BGS, imprimação, CBUQ"},
        "lotes": lotes,
        "segmentos": segmentos,
        "servicos": [{"id": s[0], "nome": s[1], "disciplina": s[2], "unidade": s[3], "quantidade_por_km": s[4],
                      "produtividade_planejada": s[5], "equipes_padrao": s[6], "calendario": s[7],
                      "equipe": s[8], "equipamentos": s[9]} for s in SERVICOS] + SERVICOS_OAE + [SERVICO_LIB],
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
    dados = gerar()
    DATASET_RODOVIA.parent.mkdir(parents=True, exist_ok=True)
    DATASET_RODOVIA.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    GABARITO.parent.mkdir(parents=True, exist_ok=True)
    GABARITO.write_text(json.dumps(gabarito(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"gravado {DATASET_RODOVIA} — {len(dados['atividades'])} atividades, "
          f"{len(dados['relacoes'])} relações, {len(dados['medicoes'])} boletins; "
          f"LB termina {dados['meta']['termino_linha_base']}")


if __name__ == "__main__":
    main()
