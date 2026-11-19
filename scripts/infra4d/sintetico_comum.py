"""Mecânica comum às obras FICTÍCIAS (ferrovia, rodovia, ...).

TODOS OS DADOS PRODUZIDOS AQUI SÃO SINTÉTICOS.

1. ``calcular_rede``     : duração = ceil(quantidade ÷ (produtividade × fator × equipes)) e CPM.
2. ``sortear_fatores``   : fator de desempenho por (lote, serviço) — a "realidade simulada".
3. ``cortar_na_data_de_status``: datas de linha de base, status, início/término reais,
   executado e boletins semanais com ruído (o último boletim fecha a soma no executado).

A ordem das chamadas ao ``rng`` faz parte do contrato: os JSON versionados em
``examples/synthetic/`` são conferidos byte a byte contra os geradores.
"""

from __future__ import annotations

import math
import random
from datetime import date
from typing import Callable

from .calendario import Calendario, iso
from .motor import AtividadeCPM, Relacao, ResultadoCPM, calcular


def calcular_rede(atividades: list[dict], relacoes: list[dict], cals: dict[str, Calendario], inicio: date,
                  fator: Callable[[dict], float] | None = None) -> ResultadoCPM:
    cpm = []
    for a in atividades:
        tipo = a["tipo"]
        if tipo != "tarefa":
            d = 0
        elif "quantidade_total" in a:
            f = fator(a) if fator else 1.0
            d = math.ceil(a["quantidade_total"] / (a["produtividade_planejada"] * f * a["equipes"]) - 1e-9)
        else:
            d = a["duracao_fixa"]
        cpm.append(AtividadeCPM(a["id"], d, a["calendario"], tipo=tipo,
                                restricao_inicio=date.fromisoformat(a["restricao_inicio"]).toordinal()
                                if a.get("restricao_inicio") else None))
    rels = [Relacao(r["predecessora"], r["sucessora"], r["tipo"], r["lag"]) for r in relacoes]
    return calcular(cpm, rels, cals, inicio.toordinal())


def sortear_fatores(atividades: list[dict], fixos: dict, rng: random.Random,
                    faixa: tuple[float, float]) -> dict:
    """Fator por (lote, serviço), na ordem de aparição das atividades. ``fixos`` vencem o sorteio
    (e não consomem número aleatório)."""
    fatores = {}
    for a in atividades:
        if "quantidade_total" in a:
            k = (a["lote_id"], a["servico_id"])
            if k not in fatores:
                fatores[k] = fixos.get(k, round(rng.uniform(*faixa), 3))
    return fatores


def boletins_semanais(a: dict, inicio: int, fim: int, cal: Calendario, q_total: float,
                      rng: random.Random, origem: str) -> list[dict]:
    """Boletins semanais entre ``inicio`` e ``fim`` com ruído; o último fecha a soma em ``q_total``."""
    semanas = []
    d0 = inicio
    while d0 < fim:
        d1 = min(fim, d0 + 7)
        n = cal.dias_uteis_entre(d0, d1)
        if n > 0:
            semanas.append((d0, n, rng.uniform(0.85, 1.15)))
        d0 = d1
    peso = sum(n * w for _, n, w in semanas) or 1
    saida, acumulado = [], 0.0
    for k, (d0, n, w) in enumerate(semanas):
        # o último boletim fecha a soma exatamente no executado (sem estouro por arredondamento)
        q = round(q_total - acumulado, 3) if k == len(semanas) - 1 else round(q_total * n * w / peso, 3)
        acumulado += q
        saida.append({"atividade_id": a["id"], "semana_inicio": iso(d0), "quantidade": q,
                      "equipes_dias": n * a["equipes"], "origem": origem})
    return saida


def cortar_na_data_de_status(atividades: list[dict], base: ResultadoCPM, real: ResultadoCPM,
                             cals: dict[str, Calendario], fatores: dict, rng: random.Random,
                             data_status: date, origem: str) -> list[dict]:
    """Preenche, em cada atividade, linha de base, status, datas reais e executado; devolve os boletins."""
    ds = data_status.toordinal()
    medicoes = []
    for a in atividades:
        ra, rb = real.atividades[a["id"]], base.atividades[a["id"]]
        cal = cals[a["calendario"]]
        a["inicio_lb"] = iso(rb.es)
        a["termino_lb"] = iso(cal.ultimo_dia_util(rb.ef)) if a["tipo"] != "marco_inicio" else iso(rb.es)
        if ra.es >= ds:
            a["status"] = "nao_iniciada"
            if "quantidade_total" in a:
                a["quantidade_executada"] = 0.0
            continue
        if a["tipo"] != "tarefa":
            a["status"] = "concluida"
            a["inicio_real"] = iso(ra.es if a["tipo"] == "marco_inicio" else cal.ultimo_dia_util(ra.ef))
            a["termino_real"] = a["inicio_real"]
            continue
        concluida = ra.ef <= ds
        a["status"] = "concluida" if concluida else "em_andamento"
        a["inicio_real"] = iso(ra.es)
        if concluida:
            a["termino_real"] = iso(cal.ultimo_dia_util(ra.ef))
        fim = ra.ef if concluida else ds
        dias = cal.dias_uteis_entre(ra.es, fim)
        if "quantidade_total" in a:
            taxa_dia = a["produtividade_planejada"] * fatores[(a["lote_id"], a["servico_id"])] * a["equipes"]
            q_total = a["quantidade_total"] if concluida else min(a["quantidade_total"] * 0.98, taxa_dia * dias)
            bol = boletins_semanais(a, ra.es, fim, cal, q_total, rng, origem)
            medicoes += bol
            a["quantidade_executada"] = round(sum(m["quantidade"] for m in bol), 3)
        else:
            tot = cal.dias_uteis_entre(ra.es, ra.ef)
            a["percentual_executado"] = 100.0 if concluida else round(100 * dias / max(1, tot), 1)
    return medicoes


# ---------------------------------------------------------------------------- cadastro complementar
# Serviços usados por atividades que NÃO saem do laço por segmento (OAEs e o fechamento do lote) também
# precisam estar em `servicos` (integridade da exportação para BI). Valores [OG]; a produtividade das OAEs é
# a mesma que os geradores usam ao criar as atividades OAE-* (um teste confere).
def servico_cadastro(sid: str, nome: str, disciplina: str, unidade: str, produtividade: float | None,
                     equipe: str, equipamentos: list[str], calendario: str = "CAL-OBRA",
                     duracao_fixa_dias: int | None = None) -> dict:
    d = {"id": sid, "nome": nome, "disciplina": disciplina, "unidade": unidade, "quantidade_por_km": None,
         "produtividade_planejada": produtividade, "equipes_padrao": 1, "calendario": calendario,
         "equipe": equipe, "equipamentos": equipamentos}
    if duracao_fixa_dias is not None:
        d["duracao_fixa_dias"] = duracao_fixa_dias
    return d


SERVICOS_OAE = [
    servico_cadastro("OAE-FUN", "OAE — fundações (estacas)", "Obras de arte especiais", "un", 2.0,
                     "1 encarregado, 1 operador de perfuratriz, 1 operador de guindaste, 6 armadores/ajudantes",
                     ["Perfuratriz de estacas", "Guindaste", "Caminhão betoneira"]),
    servico_cadastro("OAE-MES", "OAE — mesoestrutura (pilares e travessas)", "Obras de arte especiais", "un", 0.12,
                     "1 encarregado, 6 carpinteiros, 6 armadores, 4 ajudantes",
                     ["Guindaste", "Formas metálicas", "Caminhão betoneira"]),
    servico_cadastro("OAE-SUE", "OAE — superestrutura (vigas e tabuleiro)", "Obras de arte especiais", "un", 0.10,
                     "1 encarregado, 1 operador de treliça, 8 montadores, 4 armadores",
                     ["Treliça lançadeira", "Guindaste", "Caminhão betoneira"]),
]


# ---------------------------------------------------------------------------- gabarito (P9)
GERADORES_DO_META = {"scripts/infra4d/dados_sinteticos.py": "dados_sinteticos",
                     "scripts/infra4d/dados_sinteticos_rodovia.py": "dados_sinteticos_rodovia"}


class ErroGabarito(ValueError):
    """Gabarito indisponível ou que não confere com o gerador."""


def gabarito(dados: dict) -> dict:
    """ACESSOR ÚNICO do gabarito do mundo sintético (fatores verdadeiros e realidade simulada). Só avaliação.

    Exige a marca ``meta.ficticio is True`` e um gerador reconhecido em ``meta.gerador``. O gerador RECALCULA o
    gabarito da ``meta.semente`` (fonte da verdade); se o arquivo publicado em ``examples/synthetic/gabarito/``
    for da mesma semente e do mesmo gerador, ele tem de ser idêntico ao recalculado (senão ``ErroGabarito``).
    Semente diferente da do arquivo = mundo gerado em memória (backtest por sementes): vale o recalculado.
    """
    import importlib
    import json

    meta = dados.get("meta", {}) if isinstance(dados, dict) else {}
    if meta.get("ficticio") is not True:
        raise ErroGabarito("obra sem a marca ficticio: não há gabarito")
    nome = GERADORES_DO_META.get(meta.get("gerador"))
    if nome is None:
        raise ErroGabarito(f"gerador desconhecido {meta.get('gerador')!r}: não há gabarito")
    semente = meta.get("semente")
    if isinstance(semente, bool) or not isinstance(semente, int):
        raise ErroGabarito(f"semente inválida no meta: {semente!r}")
    mod = importlib.import_module(f".{nome}", __package__)
    calc = mod.gabarito(semente)
    if mod.GABARITO.is_file():
        try:
            pub = json.loads(mod.GABARITO.read_text(encoding="utf-8"))
        except ValueError as e:
            raise ErroGabarito(f"arquivo de gabarito ilegível: {e}") from None
        if pub.get("semente") == semente and pub.get("gerador") == meta.get("gerador") and pub != calc:
            raise ErroGabarito(f"arquivo de gabarito {mod.GABARITO.name} não confere com o gerador (adulterado?)")
    return calc
