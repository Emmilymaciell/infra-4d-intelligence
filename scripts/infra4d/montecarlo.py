"""Faixa de confiança da previsão independente (Monte Carlo sobre a produtividade MEDIDA).

Método v1 (padrão; preservado BIT A BIT quando ``rho=0``, ``com_riscos=False``, ``com_chuva=False``):
- Cada atividade por quantidade, ainda em aberto, usa a MESMA hierarquia de fontes do
  cenário independente: boletins da própria atividade → do (lote, serviço) → do serviço.
- Em cada iteração, reamostra os BOLETINS da fonte (bootstrap) e usa a razão
  Σ quantidade ÷ Σ equipes·dia — o mesmo estimador do determinístico, por isso a
  distribuição fica centrada nele (revisão adversarial, rodada 2).
- Fontes da mesma (lote, serviço) compartilham a reamostragem na iteração (correlação
  dentro da frente de trabalho); entre frentes, independentes.
- Boletim órfão, de equipes·dia <= 0 ou de reamostragem com produção 0 é descartado; sem
  boletim utilizável, planejada × U(0,85; 1,15) — CENTRADA em 1,0, o mesmo substituto (planejada × 1)
  que o cenário independente usa; assim o determinístico fica no centro da faixa (revisão r10: com
  U(0,80; 1,05), média 0,925, o determinístico de obra sem boletins caía abaixo do mínimo). Nas obras
  sintéticas toda frente em aberto tem boletim em algum nível, então a v1 delas não muda (há teste).
- Cada iteração roda o MESMO motor CPM (cenário "simulado" com ajustes por atividade).

Extensões v2 (opcionais, declaradas; cada uma usa um gerador PRÓPRIO derivado da semente,
para não alterar a sequência da v1):
- ``rho`` > 0 — correlação entre FRENTES do mesmo serviço (pode alargar a faixa quando a cadeia
  determinante atravessa frentes correlacionadas; se ela está numa frente só, quase não muda) por cópula gaussiana de fator
  comum: u_frente = Φ(√rho·Z_serviço + √(1−rho)·ε_frente). A produtividade da frente é o
  quantil u da distribuição bootstrap da fonte (400 réplicas pré-calculadas por fonte,
  semente fixa). Com rho > 0 o amostrador é o de quantis (mesma marginal da v1, salvo o erro
  de discretização das 400 réplicas); rho = 0 usa o amostrador da v1.
- ``com_riscos`` — eventos discretos [{id, descricao, probabilidade, atividade_id,
  impacto_dias_uteis}] de ``meta.riscos`` ou da lista passada; sem nenhum, uma lista
  SINTÉTICA padrão (marcada ``sintetico: true``) sobre a cadeia crítica do independente.
  Ocorrendo, soma o impacto à duração (dias úteis do calendário da atividade).
- ``com_chuva`` — dias extras perdidos: cada dia corrido dos meses chuvosos, da data de
  status até término + 1 ano, perde-se com probabilidade ``p_chuva``; os dias perdidos
  entram como não úteis nos calendários das atividades por quantidade (frente de campo).

Não modela: correlação ENTRE serviços diferentes, curva de aprendizado, recursos.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import replace
from datetime import date
from statistics import NormalDist

from .calendario import Calendario, ordinal
from .cenarios import Ajuste, Projeto, executar, montar_entrada
from .motor import calcular

MESES_CHUVOSOS_PADRAO = (11, 12, 1, 2, 3)
# P4 recalibrado na r19 (analogia como centro): cobertura da realidade simulada por [P10, P90] nas datas da MTA
# (passo 56 dias, 40 it., 4 marcos × 7 datas = 28 por obra), contra o nominal de 80 %:
#   alargamento   rodovia   ferrovia
#   desligado      6/28      14/28
#   0,1           10/28      16/28
#   0,2           11/28      20/28
#   0,3           15/28      18/28
#   0,5           26/28      21/28   <- o mais perto do nominal nas duas (84 % somadas)
ALARGAMENTO_PADRAO = 0.50
ALARGAMENTO_MAX_RECOMENDADO = 0.6  # teto proposto para a rota: 0,9 leva o P90 da rodovia a 2028
P_CHUVA_PADRAO = 0.08
_N = NormalDist()
_REPLICAS = 400


def _boletins(projeto: Projeto, medicoes: list[dict] | None = None):
    ativ = projeto.atividades
    por = {"atividade": defaultdict(list), "lote_servico": defaultdict(list), "servico": defaultdict(list)}
    for m in (projeto.dados.get("medicoes", []) if medicoes is None else medicoes):
        a = ativ.get(m.get("atividade_id"))
        if a is None or m.get("equipes_dias", 0) <= 0 or m.get("quantidade", 0) < 0:
            continue
        b = (float(m["quantidade"]), float(m["equipes_dias"]))
        por["atividade"][a["id"]].append(b)
        por["lote_servico"][(a.get("lote_id"), a.get("servico_id"))].append(b)
        por["servico"][a.get("servico_id")].append(b)
    return por


def _fonte(por, a):
    for nivel, chave in (("atividade", a["id"]), ("lote_servico", (a.get("lote_id"), a.get("servico_id"))),
                         ("servico", a.get("servico_id"))):
        bs = por[nivel].get(chave)
        if bs and sum(q for q, _ in bs) > 0:
            return (nivel, chave), bs
    return None, None


def _replicas(semente: int, chave, bs) -> list[float]:
    """Distribuição bootstrap (ordenada) do estimador Σq ÷ Σe da fonte; zeros descartados."""
    r = random.Random(f"{semente}|boot|{chave!r}")
    out = []
    for _ in range(_REPLICAS):
        amostra = [r.choice(bs) for _ in bs]
        e = sum(y for _, y in amostra)
        p = sum(x for x, _ in amostra) / e if e > 0 else 0.0
        if p > 0:
            out.append(p)
    return sorted(out)


def riscos_padrao(projeto: Projeto, det: dict) -> list[dict]:
    """Lista SINTÉTICA (não vem da obra): 3 eventos sobre tarefas em aberto da cadeia crítica do
    independente — a 1ª, a do meio e a última —, probabilidades 30/20/10 % e impactos 10/15/20
    dias úteis. Serve para demonstrar o mecanismo; não é premissa de engenharia."""
    crit = [i for i in det["caminho_critico"]
            if det["atividades"][i]["status"] != "concluida" and det["atividades"][i]["duracao"] > 0
            and projeto.atividades[i].get("tipo", "tarefa") == "tarefa"]
    if not crit:
        return []
    escolhidas = list(dict.fromkeys([crit[0], crit[len(crit) // 2], crit[-1]]))
    params = [(0.30, 10), (0.20, 15), (0.10, 20)]
    return [{"id": f"R-SINT-{n + 1}", "descricao": f"evento sintético de demonstração em {aid}",
             "probabilidade": p, "atividade_id": aid, "impacto_dias_uteis": imp, "sintetico": True}
            for n, (aid, (p, imp)) in enumerate(zip(escolhidas, params))]


def _validar_riscos(projeto: Projeto, riscos: list[dict]) -> list[dict]:
    out = []
    for r in riscos:
        if not isinstance(r, dict):
            raise ValueError("risco deve ser um objeto {id, descricao, probabilidade, atividade_id, impacto_dias_uteis}")
        faltam = [k for k in ("id", "probabilidade", "atividade_id", "impacto_dias_uteis") if r.get(k) is None]
        if faltam:
            raise ValueError(f"risco {r.get('id', '?')}: faltam {', '.join(faltam)}")
        try:
            p, imp_bruto, aid = float(r["probabilidade"]), float(r["impacto_dias_uteis"]), r["atividade_id"]
        except (TypeError, ValueError):
            raise ValueError(f"risco {r.get('id')}: probabilidade e impacto devem ser numéricos") from None
        if not math.isfinite(imp_bruto) or imp_bruto != int(imp_bruto):
            raise ValueError(f"risco {r.get('id')}: impacto_dias_uteis deve ser inteiro (recebido {imp_bruto:g}); "
                             f"o modelo soma dias úteis inteiros à duração")
        imp = int(imp_bruto)
        if not 0 <= p <= 1:
            raise ValueError(f"risco {r.get('id')}: probabilidade fora de [0, 1]")
        if imp < 0:
            raise ValueError(f"risco {r.get('id')}: impacto negativo")
        a = projeto.atividades.get(aid)
        if a is None or a.get("tipo", "tarefa") != "tarefa":
            raise ValueError(f"risco {r.get('id')}: atividade {aid!r} inexistente ou marco")
        out.append(dict(r, probabilidade=p, impacto_dias_uteis=imp))
    return out


def _cpm(projeto: Projeto, ajustes: list[Ajuste], extra: dict[str, int], cals: dict[str, Calendario]):
    """Mesmo cálculo de ``executar(projeto, "simulado", ajustes)`` + durações extras: (resultado, atividades)."""
    ativs, rels, _ = montar_entrada(projeto, "simulado", ajustes)
    if extra:
        ativs = [replace(a, duracao=a.duracao + extra[a.id])
                 if a.id in extra and a.status != "concluida" else a for a in ativs]
    return calcular(ativs, rels, cals, projeto.inicio_projeto, data_status=projeto.data_status), ativs


def _termino(projeto: Projeto, ajustes: list[Ajuste], extra: dict[str, int], cals: dict[str, Calendario]) -> int:
    return _cpm(projeto, ajustes, extra, cals)[0].termino_projeto_data


def _filtrar_por_estado(projeto: Projeto, estados) -> tuple[list[dict] | None, dict]:
    """Boletins (``medicoes``) cujo boletim estendido da FISCALIZAÇÃO está num dos ``estados``.

    O estado vem de ``fiscalizacao.boletins_estendidos`` (diários sintéticos da obra), casado por
    (atividade, semana do boletim). Sem o módulo de fiscalização, usa TODOS e declara."""
    meds = projeto.dados.get("medicoes", [])
    if estados is None:
        return None, {"filtro": None, "origem_estado": "sem filtro: todos os boletins (padrão da v1)",
                      "total": len(meds), "usados": len(meds), "descartados": 0, "sem_estado": 0}
    estados = tuple(estados)
    try:
        from . import fiscalizacao
    except Exception as e:  # noqa: BLE001 — módulo de outro agente; ausência é declarada, não fatal
        return None, {"filtro": list(estados), "origem_estado": f"indisponível ({type(e).__name__}): "
                      "fiscalização ausente, usados TODOS os boletins", "total": len(meds), "usados": len(meds),
                      "descartados": 0, "sem_estado": len(meds)}
    invalidos = [e for e in estados if e not in fiscalizacao.ESTADOS]
    if invalidos or not estados:
        raise ValueError(f"estados inválidos {invalidos or '(vazio)'}; use {list(fiscalizacao.ESTADOS)}")
    diarios = fiscalizacao.diarios_da_obra(projeto)
    semana = {(r["atividade_id"], r["data"]): r["semana_boletim"] for r in diarios}
    estado = {}
    for b in fiscalizacao.boletins_estendidos(projeto, diarios):
        sem = semana.get((b["atividade_id"], b["periodo_ini"]))
        if sem is not None:
            estado[(b["atividade_id"], sem)] = b["estado"]
    usados, sem_estado = [], 0
    for m in meds:
        e = estado.get((m.get("atividade_id"), m.get("semana_inicio")))
        if e is None:
            sem_estado += 1
        elif e in estados:
            usados.append(m)
    return usados, {"filtro": list(estados),
                    "origem_estado": "fiscalizacao: estado do boletim estendido (diários SINTÉTICOS da obra)",
                    "total": len(meds), "usados": len(usados), "descartados": len(meds) - len(usados),
                    "sem_estado": sem_estado,
                    "nota": "boletim sem diário correspondente não tem estado e é descartado quando há filtro; "
                            "o 'deterministico' continua sendo o cenário independente com TODOS os boletins"}


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def _percentis(terminos: list[int]) -> dict:
    def p(q: float) -> int:
        return terminos[min(len(terminos) - 1, int(q * len(terminos)))]

    def iso(o: int) -> str:
        return date.fromordinal(o).isoformat()

    return {"p10": iso(p(0.10)), "p50": iso(p(0.50)), "p80": iso(p(0.80)), "p90": iso(p(0.90)),
            "min": iso(terminos[0]), "max": iso(terminos[-1]),
            "largura_p10_p90_dias": p(0.90) - p(0.10)}


def simular(projeto: Projeto, iteracoes: int = 200, semente: int = 7, rho: float = 0.0,
            com_riscos: bool = False, com_chuva: bool = False, riscos: list[dict] | None = None,
            meses_chuvosos: tuple[int, ...] = MESES_CHUVOSOS_PADRAO, p_chuva: float = P_CHUVA_PADRAO,
            comparar_v1: bool = True, com_criticidade: bool = False, estados: tuple[str, ...] | None = None,
            incerteza_sem_medicao: bool = False, alargamento: float = ALARGAMENTO_PADRAO,
            por_marco: bool = False) -> dict:
    """``com_criticidade``: índice de criticidade por atividade e por (lote, serviço) — fração das iterações
    em que ficou crítica (folga total <= 0 ou no caminho mais longo) — e a "cruciality" (correlação de
    Pearson entre a duração sorteada e o término). ``estados``: usa só os boletins cujo boletim estendido
    da fiscalização está nesses estados. Os dois são opcionais; com os padrões a saída é a da v1.

    ``incerteza_sem_medicao`` (P4 do BACKLOG; padrão DESLIGADO, sem efeito nos números atuais): frente
    (lote, serviço) SEM boletim próprio ganha incerteza ALARGADA, sorteada por iteração e por frente:
    - COM analogia (o mesmo serviço medido noutro lote — a fonte da v1): a produtividade da analogia continua
      o CENTRO; multiplica-se por (índice medida/planejada de um lote desse serviço ÷ média aritmética dos
      índices do serviço) × U(1 − alargamento, 1 + alargamento). E[rel] = 1 e E[1/rel] >= 1: a duração média
      nunca fica mais otimista que a analogia (revisão r19: sortear entre TODAS as frentes antecipava o P50);
    - SEM analogia: planejada × índice sorteado entre as frentes medidas da OBRA × U(1 ± alargamento).
    Gerador próprio (semente|sem_medicao): a sequência da v1 nas demais frentes não muda.
    A saída marca quais grupos usaram o modo. ``por_marco``: percentis do término de cada marco de término."""
    if not 10 <= iteracoes <= 2000:
        raise ValueError("iteracoes deve estar entre 10 e 2000")
    if not 0 <= rho <= 1 or isinstance(rho, bool):
        raise ValueError("rho deve estar entre 0 e 1")
    if not 0 <= alargamento < 1 or isinstance(alargamento, bool):
        raise ValueError("alargamento deve estar em [0, 1)")
    if not 0 <= p_chuva <= 1:
        raise ValueError("p_chuva deve estar entre 0 e 1")
    v2 = rho > 0 or com_riscos or com_chuva
    rng = random.Random(semente)
    meds_filtradas, fonte_bol = _filtrar_por_estado(projeto, estados)
    por = _boletins(projeto, meds_filtradas)
    alvo = [a for a in projeto.dados["atividades"]
            if a.get("quantidade_total") and a.get("status") != "concluida"]
    fontes = {a["id"]: _fonte(por, a) for a in alvo}
    # P4: frentes sem boletim PRÓPRIO (fonte = analogia do serviço ou nenhuma) e índices medida/planejada da obra
    sem_medicao: set[str] = set()
    indices: list[float] = []
    idx_serv: dict[str, list[float]] = defaultdict(list)
    if incerteza_sem_medicao:
        plan_frente = {}
        for a in projeto.dados["atividades"]:
            if a.get("quantidade_total") and a.get("produtividade_planejada"):
                plan_frente.setdefault((a.get("lote_id"), a.get("servico_id")), float(a["produtividade_planejada"]))
        for k, bs in sorted(por["lote_servico"].items(), key=lambda kv: str(kv[0])):
            q, e = sum(x for x, _ in bs), sum(y for _, y in bs)
            if e > 0 and q > 0 and plan_frente.get(k):
                indices.append(q / e / plan_frente[k])
                idx_serv[k[1]].append(q / e / plan_frente[k])
        if indices:
            sem_medicao = {a["id"] for a in alvo if fontes[a["id"]][0] is None
                           or fontes[a["id"]][0][0] not in ("atividade", "lote_servico")}
    rng_sm = random.Random(f"{semente}|sem_medicao")
    marcos_t = [a["id"] for a in projeto.dados["atividades"] if a.get("tipo") == "marco_termino"] if por_marco else []
    termino_marcos: dict[str, list[int]] = defaultdict(list)
    det = executar(projeto, "independente")

    # ---------------------------------------------------------------- v2: preparação
    lista_riscos: list[dict] = []
    origem_riscos = None
    if com_riscos:
        if riscos is not None:
            lista_riscos, origem_riscos = _validar_riscos(projeto, riscos), "lista passada"
        elif projeto.dados.get("meta", {}).get("riscos"):
            lista_riscos, origem_riscos = _validar_riscos(projeto, projeto.dados["meta"]["riscos"]), "meta.riscos"
        else:
            lista_riscos, origem_riscos = riscos_padrao(projeto, det), "SINTÉTICA padrão (não é dado da obra)"
    rng_v2 = random.Random(f"{semente}|v2")
    replicas = {}
    if rho > 0:
        for a in alvo:
            chave, bs = fontes[a["id"]]
            if bs and chave not in replicas:
                replicas[chave] = _replicas(semente, chave, bs)
    cals_chuva = {c for a in alvo for c in [a["calendario"]]}
    dias_chuva_janela = []
    if com_chuva:
        fim = ordinal(det["termino"]) + 366
        dias_chuva_janela = [d for d in range(projeto.data_status, fim + 1)
                             if date.fromordinal(d).month in meses_chuvosos]
    ocorrencias = defaultdict(int)
    dias_perdidos_total = 0

    terminos = []
    crit_n: dict[str, int] = defaultdict(int)
    grupo_n: dict[tuple, int] = defaultdict(int)
    duracoes: dict[str, list[int]] = defaultdict(list)
    terminos_ordem: list[int] = []
    tarefas = [a["id"] for a in projeto.dados["atividades"]
               if a.get("tipo", "tarefa") == "tarefa" and a.get("status") != "concluida"]

    def registrar(criticas: set[str], dur: dict[str, int], termino: int) -> None:
        terminos_ordem.append(termino)
        grupos = set()
        for i in tarefas:
            duracoes[i].append(dur[i])
            if i in criticas:
                crit_n[i] += 1
                a = projeto.atividades[i]
                grupos.add((a.get("lote_id"), a.get("servico_id")))
        for g in grupos:
            grupo_n[g] += 1

    for _ in range(iteracoes):
        sorteio_frente: dict = {}
        fator_sm: dict = {}
        ajustes = []
        z_serv: dict = {}
        u_frente: dict = {}
        for a in alvo:
            chave, bs = fontes[a["id"]]
            frente = (a.get("lote_id"), a.get("servico_id"))
            if frente not in sorteio_frente:
                sorteio_frente[frente] = rng.random()  # consumido SEMPRE: preserva a sequência da v1
            if rho > 0:
                serv = a.get("servico_id")
                if serv not in z_serv:
                    z_serv[serv] = rng_v2.gauss(0.0, 1.0)
                if frente not in u_frente:
                    x = math.sqrt(rho) * z_serv[serv] + math.sqrt(1 - rho) * rng_v2.gauss(0.0, 1.0)
                    u_frente[frente] = min(1 - 1e-12, max(1e-12, _N.cdf(x)))
                u = u_frente[frente]
                reps = replicas.get(chave) if bs else None
                if reps:
                    prod = reps[min(len(reps) - 1, int(u * len(reps)))]
                else:
                    prod = a["produtividade_planejada"] * (0.85 + 0.30 * u)
            else:
                # semente em TEXTO: random.Random(str) é determinística entre processos (hash() não é)
                sub = random.Random(f"{sorteio_frente[frente]!r}|{chave!r}")
                prod = 0.0
                if bs:
                    amostra = [sub.choice(bs) for _ in bs]
                    q = sum(x for x, _ in amostra)
                    e = sum(y for _, y in amostra)
                    prod = q / e if e > 0 else 0.0
                if prod <= 0:
                    prod = a["produtividade_planejada"] * sub.uniform(0.85, 1.15)
            if a["id"] in sem_medicao:
                # r19: frente com ANALOGIA (mesmo serviço medido noutro lote) mantém a analogia como centro e só
                # ganha a dispersão ENTRE OS LOTES desse serviço (índice ÷ média aritmética dos índices do serviço:
                # E[rel] = 1, E[1/rel] >= 1 -> a duração média nunca fica mais otimista) × U(1 ± a). Sem analogia:
                # planejada × índice sorteado entre as frentes medidas da OBRA × U(1 ± a).
                if frente not in fator_sm:
                    serv = a.get("servico_id")
                    u = rng_sm.uniform(1 - alargamento, 1 + alargamento)
                    if chave is not None and chave[0] == "servico" and idx_serv.get(serv):
                        lst = idx_serv[serv]
                        fator_sm[frente] = ("analogia", rng_sm.choice(lst) / (sum(lst) / len(lst)) * u)
                    else:
                        fator_sm[frente] = ("obra", rng_sm.choice(indices) * u)
                modo_sm, f_sm = fator_sm[frente]
                prod = (prod if modo_sm == "analogia" else a["produtividade_planejada"]) * f_sm
            ajustes.append(Ajuste(produtividade=prod, atividade_id=a["id"]))
        if not v2:
            r_it = executar(projeto, "simulado", ajustes)
            terminos.append(ordinal(r_it["termino"]))
            for m in marcos_t:
                termino_marcos[m].append(ordinal(r_it["atividades"][m]["termino"]))
            if com_criticidade:
                registrar({i for i in tarefas if r_it["atividades"][i]["critica"]},
                          {i: r_it["atividades"][i]["duracao"] for i in tarefas}, terminos[-1])
            continue
        extra: dict[str, int] = defaultdict(int)
        for r in lista_riscos:
            if rng_v2.random() < r["probabilidade"]:
                extra[r["atividade_id"]] += r["impacto_dias_uteis"]
                ocorrencias[r["id"]] += 1
        cals = projeto.calendarios
        if com_chuva:
            perdidos = frozenset(date.fromordinal(d) for d in dias_chuva_janela if rng_v2.random() < p_chuva)
            dias_perdidos_total += len(perdidos)
            if perdidos:
                cals = dict(cals)
                for cid in cals_chuva:
                    c = projeto.calendarios[cid]
                    cals[cid] = Calendario(c.id, c.nome, c.dias_semana, c.nao_uteis | perdidos)
        res_it, ativs_it = _cpm(projeto, ajustes, extra, cals)
        terminos.append(res_it.termino_projeto_data)
        if marcos_t:
            por_id_it = {a.id: a for a in ativs_it}
            for m in marcos_t:
                am = por_id_it[m]
                termino_marcos[m].append(res_it.atividades[m].data_termino(cals[am.calendario], am))
        if com_criticidade:
            d_it = {a.id: a.duracao for a in ativs_it}
            registrar({i for i in tarefas if res_it.atividades[i].critica}, {i: d_it[i] for i in tarefas},
                      terminos[-1])
    terminos.sort()

    pct = _percentis(terminos)
    saida = {
        "iteracoes": iteracoes, "semente": semente,
        "deterministico": det["termino"],
        **{k: pct[k] for k in ("p10", "p50", "p80", "p90", "min", "max")},
        "histograma": _histograma(terminos),
        "metodo": "bootstrap ponderado dos boletins (Σq ÷ Σequipes·dia) com a mesma hierarquia de fontes do "
                  "cenário independente; correlação dentro da frente (lote, serviço); CPM completo por iteração",
        "limitacoes": "sem correlação entre serviços, sem eventos de risco discretos, sem chuva estocástica: "
                      "a faixa tende a ser estreita",
        "versao": "v2" if v2 else "v1",
        "parametros": {"rho": rho, "com_riscos": com_riscos, "com_chuva": com_chuva},
        "largura_p10_p90_dias": pct["largura_p10_p90_dias"],
        "fonte_boletins": fonte_bol,
        **({"marcos": {m: {k: v for k, v in _percentis(sorted(ts)).items()} for m, ts in termino_marcos.items()}}
           if por_marco else {}),
        **({"incerteza_sem_medicao": {
            "ativo": bool(sem_medicao), "alargamento": alargamento, "indices_observados": len(indices),
            "indices": [round(x, 4) for x in indices],
            "indices_por_servico": {k: [round(x, 4) for x in v] for k, v in sorted(idx_serv.items())},
            "grupos": sorted({f"{projeto.atividades[i].get('lote_id')}/{projeto.atividades[i].get('servico_id')}"
                              for i in sem_medicao}),
            "atividades": sorted(sem_medicao),
            "regra": "frente sem boletim próprio. COM analogia (o mesmo serviço medido noutro lote): produtividade da "
                     "analogia × (índice de um lote do serviço ÷ média dos índices do serviço) × U(1 ± alargamento) "
                     "— o centro continua a analogia. SEM analogia: planejada × índice sorteado entre as frentes "
                     "medidas da obra × U(1 ± alargamento)",
            **({} if indices else {"nota": "nenhuma frente medida na obra: modo sem efeito"})}}
           if incerteza_sem_medicao else {}),
    }
    if estados is not None:
        saida["parametros"]["estados"] = list(estados)
    if com_criticidade:
        ativs_ic = []
        for i in tarefas:
            a = projeto.atividades[i]
            c = _pearson(duracoes[i], terminos_ordem)
            ativs_ic.append({"id": i, "nome": a.get("nome"), "lote_id": a.get("lote_id"),
                             "servico_id": a.get("servico_id"), "indice": round(crit_n[i] / iteracoes, 6),
                             "correlacao_duracao_termino": None if c is None else round(c, 6),
                             "duracao_media": round(sum(duracoes[i]) / iteracoes, 3)})
        ativs_ic.sort(key=lambda x: (-x["indice"], -abs(x["correlacao_duracao_termino"] or 0), x["id"]))
        grupos = [{"lote_id": g[0], "servico_id": g[1], "indice": round(n / iteracoes, 6)}
                  for g, n in grupo_n.items()]
        todos_g = {(projeto.atividades[i].get("lote_id"), projeto.atividades[i].get("servico_id")) for i in tarefas}
        grupos += [{"lote_id": g[0], "servico_id": g[1], "indice": 0.0} for g in todos_g if g not in grupo_n]
        grupos.sort(key=lambda x: (-x["indice"], str(x["lote_id"]), str(x["servico_id"])))
        saida["criticidade"] = {
            "iteracoes": iteracoes,
            "definicao": "índice = fração das iterações em que a tarefa ficou crítica (folga total <= 0 ou no "
                         "caminho mais longo); grupo (lote, serviço) = fração das iterações com ao menos uma "
                         "tarefa do grupo crítica; cruciality = correlação de Pearson entre a duração sorteada e "
                         "o término (None se a duração não varia)",
            "erro_padrao_max": round(0.5 / math.sqrt(iteracoes), 4),
            "atividades": ativs_ic, "grupos": grupos,
        }
    if v2:
        saida["limitacoes"] = ("modela correlação entre frentes do mesmo serviço (rho), riscos discretos e chuva "
                               "conforme 'parametros'; não modela correlação entre serviços diferentes")
        saida["v2"] = {
            "rho": rho,
            "correlacao": ("cópula gaussiana de fator comum por serviço sobre os quantis do bootstrap"
                           if rho > 0 else "nenhuma entre frentes (amostrador da v1)"),
            "riscos": {"origem": origem_riscos, "lista": lista_riscos,
                       "frequencia_observada": {r["id"]: round(ocorrencias[r["id"]] / iteracoes, 4)
                                                for r in lista_riscos}} if com_riscos else None,
            "chuva": {"meses": list(meses_chuvosos), "p_dia_perdido": p_chuva,
                      "calendarios": sorted(cals_chuva),
                      "media_dias_perdidos_por_iteracao": round(dias_perdidos_total / iteracoes, 2)}
            if com_chuva else None,
        }
        if comparar_v1:
            v1 = simular(projeto, iteracoes, semente, comparar_v1=False)
            saida["faixa_v1"] = {k: v1[k] for k in ("p10", "p50", "p80", "p90", "largura_p10_p90_dias")}
            saida["faixa_v2"] = {k: saida[k] for k in ("p10", "p50", "p80", "p90", "largura_p10_p90_dias")}
    return saida


def _histograma(terminos: list[int], classes: int = 12) -> list[dict]:
    lo, hi = terminos[0], terminos[-1]
    larg = max(1, (hi - lo + classes) // classes)
    cont = defaultdict(int)
    for t in terminos:
        cont[(t - lo) // larg] += 1
    return [{"de": date.fromordinal(lo + i * larg).isoformat(), "ate": date.fromordinal(lo + (i + 1) * larg - 1).isoformat(),
             "n": cont[i]} for i in range(max(cont) + 1)]
