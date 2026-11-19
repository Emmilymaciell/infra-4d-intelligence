"""Comparação de revisões de cronograma (análise forense de mudanças).

Entrada: duas versões A e B, cada uma ``Versao(atividades, relacoes, calendarios, inicio_projeto,
data_status)``, vindas do dataset (``versao_do_cenario``), do MSPDI ou do XER (``versao_importada``).

Saída:
- atividades adicionadas/removidas; mudanças por atividade (duração, calendário, tipo, SNET, FNLT,
  status e datas reais); relações adicionadas/removidas/alteradas (tipo, lag); calendários com
  definição alterada; mudança da data de status e do início do projeto;
- término A × B (motor CPM próprio) e a ATRIBUIÇÃO do deslocamento do término a cada mudança por
  EFEITO ISOLADO: aplica só aquela mudança sobre A, recalcula e mede o Δ. O que sobra
  (Δ total − Σ efeitos isolados) é o RESÍDUO DE INTERAÇÃO, declarado: mudanças que só têm efeito
  juntas (ou que se anulam) aparecem ali, não numa atribuição inventada;
- conferência de reconstrução: A + todas as mudanças tem de dar o término de B (prova de que o
  inventário de mudanças está completo);
- alertas típicos de manipulação (não são acusação; são pontos para o fiscal conferir).

Unidades de mudança (cada uma aplicada inteira no efeito isolado):
- uma atividade modificada (todos os campos que mudaram nela juntos: duração remanescente e status
  andam juntos e não fazem sentido separados);
- uma atividade adicionada (com as relações novas que a ligam) ou removida (com as relações dela);
- uma relação entre atividades existentes nas duas versões (adicionada, removida ou alterada);
- a definição de um calendário; a data de status; o início do projeto.

Δ em dias CORRIDOS entre as datas de término exibidas (último dia trabalhado).
Custo: uma execução do motor por unidade de mudança (medido e informado em ``custo``).
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

from .calendario import ErroCalendario, iso
from .motor import AtividadeCPM, ErroRede, Relacao, ResultadoCPM, calcular

CAMPOS = ("duracao", "calendario", "tipo", "restricao_inicio", "restricao_termino", "status", "inicio_real",
          "termino_real")


@dataclass
class Versao:
    atividades: list[AtividadeCPM]
    relacoes: list[Relacao]
    calendarios: dict
    inicio_projeto: int
    data_status: int | None = None
    nomes: dict = field(default_factory=dict)
    rotulo: str = ""
    # durações derivadas da produtividade MEDIDA (cenário independente/simulado): encurtar duração aqui é
    # efeito de boletim, não edição manual (r16)
    duracao_por_medicao: bool = False

    def copia(self) -> "Versao":
        return Versao(copy.deepcopy(self.atividades), copy.deepcopy(self.relacoes), dict(self.calendarios),
                      self.inicio_projeto, self.data_status, self.nomes, self.rotulo, self.duracao_por_medicao)

    def calcular(self) -> ResultadoCPM:
        return calcular(self.atividades, self.relacoes, self.calendarios, self.inicio_projeto,
                        data_status=self.data_status)


def versao_do_cenario(projeto, cenario: str, ajustes=None) -> Versao:
    from .cenarios import montar_entrada

    ativs, rels, _ = montar_entrada(projeto, cenario, ajustes)
    ds = None if cenario == "linha_base" else projeto.data_status
    return Versao(ativs, rels, dict(projeto.calendarios), projeto.inicio_projeto, ds,
                  {a["id"]: a.get("nome", a["id"]) for a in projeto.dados["atividades"]}, f"cenário {cenario}",
                  duracao_por_medicao=cenario in ("independente", "simulado"))


def versao_importada(dados, rotulo: str = "importado") -> Versao:
    ativs, rels, cals, meta = dados
    return Versao(ativs, rels, cals, meta["inicio_projeto"], meta.get("data_status"), meta.get("nomes", {}),
                  f"{rotulo} ({meta.get('formato')})")


# =============================================================================
# Inventário de mudanças
# =============================================================================
@dataclass
class Mudanca:
    id: str
    tipo: str  # atividade_modificada | atividade_adicionada | atividade_removida | relacao_* | calendario | ...
    descricao: str
    aplicar: object = field(repr=False)  # função(Versao) -> None (muta a cópia)
    detalhe: dict = field(default_factory=dict)


def _fmt(campo, v):
    if v is None:
        return "—"
    if campo in ("restricao_inicio", "restricao_termino", "inicio_real", "termino_real"):
        return iso(v)
    return str(v)


def _chave_rel(r: Relacao):
    return (r.predecessora, r.sucessora, r.tipo)


def inventariar(a: Versao, b: Versao) -> list[Mudanca]:
    mud: list[Mudanca] = []
    aa, ab = {x.id: x for x in a.atividades}, {x.id: x for x in b.atividades}
    adicionadas, removidas = sorted(set(ab) - set(aa)), sorted(set(aa) - set(ab))

    # ------------------------------------------------------------ atividades
    for i in sorted(set(aa) & set(ab)):
        x, y = aa[i], ab[i]
        dif = {c: (getattr(x, c), getattr(y, c)) for c in CAMPOS if getattr(x, c) != getattr(y, c)}
        if not dif:
            continue
        novo = copy.deepcopy(y)

        def ap(v, i=i, novo=novo):
            v.atividades = [copy.deepcopy(novo) if t.id == i else t for t in v.atividades]

        desc = "; ".join(f"{c} {_fmt(c, d[0])} → {_fmt(c, d[1])}" for c, d in dif.items())
        mud.append(Mudanca(f"ativ:{i}", "atividade_modificada", f"{i}: {desc}", ap,
                           {"atividade": i, "campos": {c: [_fmt(c, d[0]), _fmt(c, d[1])] for c, d in dif.items()}}))

    rels_a = {_chave_rel(r): r for r in a.relacoes}
    rels_b = {_chave_rel(r): r for r in b.relacoes}
    # relação nova que toca atividade adicionada pertence à adicionada de maior id entre as pontas
    # (assim, aplicando as unidades em ordem, as duas pontas já existem quando ela entra)
    dono = {}
    for k in rels_b:
        if k not in rels_a:
            novas_pontas = [x for x in (k[0], k[1]) if x in adicionadas]
            if novas_pontas:
                dono[k] = max(novas_pontas)
    for i in adicionadas:
        novo = copy.deepcopy(ab[i])
        ligadas = [copy.deepcopy(rels_b[k]) for k, d in dono.items() if d == i]

        def ap(v, novo=novo, ligadas=ligadas):
            v.atividades.append(copy.deepcopy(novo))
            ids = {t.id for t in v.atividades}
            v.relacoes += [copy.deepcopy(r) for r in ligadas if r.predecessora in ids and r.sucessora in ids]

        mud.append(Mudanca(f"add:{i}", "atividade_adicionada",
                           f"{i} adicionada ({novo.duracao} d.u., {len(ligadas)} relações)", ap,
                           {"atividade": i, "relacoes": [f"{r.predecessora}->{r.sucessora} {r.tipo}{r.lag:+d}"
                                                         for r in ligadas]}))
    for i in removidas:
        def ap(v, i=i):
            v.atividades = [t for t in v.atividades if t.id != i]
            v.relacoes = [r for r in v.relacoes if i not in (r.predecessora, r.sucessora)]

        n = sum(1 for k in rels_a if i in (k[0], k[1]))
        mud.append(Mudanca(f"rem:{i}", "atividade_removida", f"{i} removida (com {n} relações)", ap, {"atividade": i}))

    # ------------------------------------------------------------ relações entre atividades comuns
    comuns = set(aa) & set(ab)
    pares = sorted({(k[0], k[1]) for k in list(rels_a) + list(rels_b) if k[0] in comuns and k[1] in comuns})
    for p, s in pares:
        ra = sorted([r for k, r in rels_a.items() if (k[0], k[1]) == (p, s)], key=lambda r: (r.tipo, r.lag))
        rb = sorted([r for k, r in rels_b.items() if (k[0], k[1]) == (p, s)], key=lambda r: (r.tipo, r.lag))
        sa, sb = {(r.tipo, r.lag) for r in ra}, {(r.tipo, r.lag) for r in rb}
        if sa == sb:
            continue
        if len(ra) == 1 and len(rb) == 1:
            tipo_m, desc = "relacao_alterada", (f"{p}->{s}: {ra[0].tipo}{ra[0].lag:+d} → {rb[0].tipo}{rb[0].lag:+d}")
        elif not ra:
            tipo_m, desc = "relacao_adicionada", f"{p}->{s}: " + ", ".join(f"{t}{l:+d}" for t, l in sorted(sb)) + " adicionada"
        elif not rb:
            tipo_m, desc = "relacao_removida", f"{p}->{s}: " + ", ".join(f"{t}{l:+d}" for t, l in sorted(sa)) + " removida"
        else:
            tipo_m, desc = "relacao_alterada", (f"{p}->{s}: {sorted(sa)} → {sorted(sb)}")
        novas = [copy.deepcopy(r) for r in rb]

        def ap(v, p=p, s=s, novas=novas):
            v.relacoes = [r for r in v.relacoes if (r.predecessora, r.sucessora) != (p, s)] + copy.deepcopy(novas)

        mud.append(Mudanca(f"rel:{p}->{s}", tipo_m, desc, ap,
                           {"predecessora": p, "sucessora": s, "antes": [f"{t}{l:+d}" for t, l in sorted(sa)],
                            "depois": [f"{t}{l:+d}" for t, l in sorted(sb)]}))


    # ------------------------------------------------------------ calendários e parâmetros
    for cid in sorted(set(a.calendarios) | set(b.calendarios)):
        ca, cb = a.calendarios.get(cid), b.calendarios.get(cid)
        if ca is None or cb is None:
            if cb is not None:
                def ap(v, cid=cid, cb=cb):
                    v.calendarios = {**v.calendarios, cid: cb}
                mud.append(Mudanca(f"cal:{cid}", "calendario_adicionado", f"calendário {cid} adicionado", ap,
                                   {"calendario": cid}))
            continue  # calendário removido: só deixa de ser usado (as atividades que o usavam mudaram)
        if (ca.dias_semana, ca.nao_uteis) != (cb.dias_semana, cb.nao_uteis):
            mais, menos = sorted(cb.nao_uteis - ca.nao_uteis), sorted(ca.nao_uteis - cb.nao_uteis)

            def ap(v, cid=cid, cb=cb):
                v.calendarios = {**v.calendarios, cid: cb}

            mud.append(Mudanca(f"cal:{cid}", "calendario", f"calendário {cid}: dias da semana {ca.dias_semana} → "
                                                           f"{cb.dias_semana}; +{len(mais)} / −{len(menos)} dias não úteis",
                               ap, {"calendario": cid, "nao_uteis_novos": [d.isoformat() for d in mais[:50]],
                                    "nao_uteis_retirados": [d.isoformat() for d in menos[:50]]}))
    if a.data_status != b.data_status:
        def ap(v, ds=b.data_status):
            v.data_status = ds
        mud.append(Mudanca("param:data_status", "data_status",
                           f"data de status {iso(a.data_status) or '—'} → {iso(b.data_status) or '—'}", ap))
    if a.inicio_projeto != b.inicio_projeto:
        def ap(v, ini=b.inicio_projeto):
            v.inicio_projeto = ini
        mud.append(Mudanca("param:inicio", "inicio_projeto",
                           f"início do projeto {iso(a.inicio_projeto)} → {iso(b.inicio_projeto)}", ap))
    return mud


# =============================================================================
# Comparação
# =============================================================================
def _termino(v: Versao) -> tuple[int | None, str | None]:
    try:
        return v.calcular().termino_projeto_data, None
    except (ErroRede, ErroCalendario) as e:
        return None, str(e)


def _preparar(base: Versao, m: Mudanca, b: Versao) -> Versao:
    """Cópia de A com a mudança aplicada; calendários de B que a mudança precise são somados."""
    v = base.copia()
    v.calendarios = {**b.calendarios, **base.calendarios}  # calendário novo de B disponível sem mudar os de A
    m.aplicar(v)
    return v


CAMPOS_PROGRESSO = {"status", "inicio_real", "termino_real"}


def agrupar_progresso(mud: list[Mudanca]) -> list[Mudanca]:
    """Junta "data de status + progresso" numa unidade composta: a mudança da data de status e todas as
    atividades cuja mudança envolve status ou datas reais (a duração remanescente vai junto, por ser da
    mesma unidade). Isolados, esses efeitos são tecnicamente certos mas enganam quem lê (avançar só a
    data de status, sem o progresso, empurra a obra inteira; o progresso sozinho, sem a data, pouco
    move). As demais mudanças continuam separadas."""
    membros = [m for m in mud if m.tipo == "data_status" or (
        m.tipo == "atividade_modificada" and CAMPOS_PROGRESSO & set(m.detalhe.get("campos", {})))]
    if not membros:
        return mud
    ids = [m.id for m in membros]

    def ap(v, membros=membros):
        for m in membros:
            m.aplicar(v)

    ds = next((m.descricao for m in membros if m.tipo == "data_status"), "data de status inalterada")
    n_at = sum(1 for m in membros if m.tipo == "atividade_modificada")
    grupo = Mudanca("grupo:progresso", "progresso", f"{ds}; progresso/status de {n_at} atividade(s)", ap,
                    {"membros": ids, "atividades": [m.detalhe["atividade"] for m in membros
                                                    if m.tipo == "atividade_modificada"]})
    return [grupo] + [m for m in mud if m.id not in set(ids)]


class ErroComparacao(ValueError):
    """Comparação recusada (ex.: efeitos isolados acima do teto de execuções do motor)."""


MAX_EFEITOS_ISOLADOS = 2_000  # teto de execuções do motor por comparação (uma por unidade de mudança)


def comparar_revisoes(a: Versao, b: Versao, efeitos_isolados: bool = True, agrupar_progresso_: bool = True,
                      max_efeitos: int = MAX_EFEITOS_ISOLADOS) -> dict:
    """``agrupar_progresso_`` (padrão True): data de status + progresso como UMA unidade composta;
    False = modo detalhado (cada atividade e a data de status separadas). Com efeitos isolados, mais de
    ``max_efeitos`` unidades de mudança é recusado (``ErroComparacao``): peça efeitos_isolados=false."""
    t0 = time.perf_counter()
    ra, rb = a.calcular(), b.calcular()
    ta, tb = ra.termino_projeto_data, rb.termino_projeto_data
    mud = inventariar(a, b)
    if agrupar_progresso_:
        mud = agrupar_progresso(mud)
    if efeitos_isolados and len(mud) > max_efeitos:
        raise ErroComparacao(f"{len(mud)} unidades de mudança: efeito isolado exigiria {len(mud)} execuções do "
                             f"motor (teto {max_efeitos}); repita com efeitos_isolados=false")
    n_motor = 2
    efeitos = {}
    if efeitos_isolados:
        for m in mud:
            t, erro = _termino(_preparar(a, m, b))
            n_motor += 1
            efeitos[m.id] = (None if t is None else t - ta, erro)
    # reconstrução: A + todas as mudanças = B?
    v = a.copia()
    v.calendarios = {**b.calendarios, **a.calendarios}
    for m in sorted(mud, key=lambda m: (m.tipo != "calendario_adicionado", m.tipo != "calendario")):
        m.aplicar(v)
    t_rec, erro_rec = _termino(v)
    n_motor += 1
    delta = tb - ta
    soma = sum(e[0] for e in efeitos.values() if e[0] is not None)
    crit_a, crit_b = set(ra.caminho_critico), set(rb.caminho_critico)
    lista = []
    for m in mud:
        e, erro = efeitos.get(m.id, (None, None))
        lista.append({"id": m.id, "tipo": m.tipo, "descricao": m.descricao, "detalhe": m.detalhe,
                      "efeito_isolado_dias": e, "erro_isolado": erro,
                      "na_cadeia_critica_A": bool({m.detalhe.get("atividade"), m.detalhe.get("predecessora"),
                                                   m.detalhe.get("sucessora")} & crit_a)})
    lista.sort(key=lambda x: (-(abs(x["efeito_isolado_dias"]) if x["efeito_isolado_dias"] is not None else -1),
                              x["id"]))
    por_tipo = {}
    for x in lista:
        por_tipo[x["tipo"]] = por_tipo.get(x["tipo"], 0) + 1
    sem_efeito = [x["id"] for x in lista if x["erro_isolado"]]
    return {
        "a": a.rotulo, "b": b.rotulo, "modo": "agrupado" if agrupar_progresso_ else "detalhado",
        "termino_a": iso(ta), "termino_b": iso(tb), "delta_dias_corridos": delta,
        "n_mudancas": len(lista), "por_tipo": por_tipo,
        "mudancas": lista,
        "atribuicao": None if not efeitos_isolados else {
            "soma_efeitos_isolados": soma,
            "residuo_interacao": delta - soma,
            "sem_efeito_calculavel": sem_efeito,
            "regra": "efeito isolado = término(A + só esta mudança) − término(A), em dias corridos; resíduo = "
                     "Δ total − soma dos efeitos isolados (interação entre mudanças: efeitos que só existem juntos, "
                     "ou que se sobrepõem/anulam). Mudança cujo efeito isolado não é calculável (rede inválida "
                     "sozinha) entra com 0 na soma e aparece em sem_efeito_calculavel.",
        },
        "reconstrucao": {"termino": iso(t_rec), "confere_com_b": t_rec == tb, "erro": erro_rec},
        "alertas": alertas(a, b, ra, rb, mud),
        "caminho_critico": {"so_em_A": sorted(crit_a - crit_b), "so_em_B": sorted(crit_b - crit_a)},
        "custo": {"execucoes_do_motor": n_motor, "segundos": round(time.perf_counter() - t0, 3)},
    }


# =============================================================================
# Alertas
# =============================================================================
def alertas(a: Versao, b: Versao, ra: ResultadoCPM, rb: ResultadoCPM, mud: list[Mudanca]) -> list[dict]:
    """Padrões típicos de manipulação. São pontos para o fiscal conferir, não conclusões."""
    out = []
    aa, ab = {x.id: x for x in a.atividades}, {x.id: x for x in b.atividades}
    crit_a, crit_b = set(ra.caminho_critico), set(rb.caminho_critico)
    lags_a = {_chave_rel(r): r.lag for r in a.relacoes}
    for r in b.relacoes:
        k = _chave_rel(r)
        if r.lag < 0 and (k not in lags_a or lags_a[k] >= 0):
            out.append({"tipo": "lag_negativo_novo", "gravidade": "alta" if r.sucessora in crit_b else "media",
                        "mensagem": f"{r.predecessora}->{r.sucessora} {r.tipo}{r.lag:+d}: lag negativo (lead) novo",
                        "atividades": [r.predecessora, r.sucessora]})
        elif k in lags_a and lags_a[k] < 0 and r.lag < lags_a[k]:
            out.append({"tipo": "lead_aumentado", "gravidade": "alta" if r.sucessora in crit_b else "media",
                        "mensagem": f"{r.predecessora}->{r.sucessora} {r.tipo}: lead {lags_a[k]:+d} → {r.lag:+d} "
                                    "(sobreposição maior)", "atividades": [r.predecessora, r.sucessora]})
        elif (k in lags_a and lags_a[k] > 0 and 0 <= r.lag < lags_a[k]
              and r.predecessora in crit_a and r.sucessora in crit_a):
            out.append({"tipo": "lag_reduzido_em_relacao_critica", "gravidade": "media",
                        "mensagem": f"{r.predecessora}->{r.sucessora} {r.tipo}: lag {lags_a[k]:+d} → {r.lag:+d} com as "
                                    "duas pontas críticas em A (confira a justificativa técnica)",
                        "atividades": [r.predecessora, r.sucessora]})
    for i in sorted(set(aa) & set(ab)):
        x, y = aa[i], ab[i]
        for campo, nome in (("restricao_inicio", "SNET"), ("restricao_termino", "FNLT")):
            if getattr(y, campo) is not None and getattr(y, campo) != getattr(x, campo) and (i in crit_b or i in crit_a):
                out.append({"tipo": "restricao_nova_no_caminho_critico", "gravidade": "alta",
                            "mensagem": f"{i}: {nome} {_fmt(campo, getattr(x, campo))} → {_fmt(campo, getattr(y, campo))} "
                                        "em atividade do caminho crítico (restrição pode mascarar a lógica)",
                            "atividades": [i]})
        # Não se emite quando B tem duração derivada de produtividade MEDIDA (independente/simulado): aí o
        # encurtamento vem de boletins. O texto só afirma o que foi verificado (r16).
        if (y.duracao < x.duracao and i in crit_a and y.status == "nao_iniciada" and x.status == "nao_iniciada"
                and not b.duracao_por_medicao):
            out.append({"tipo": "duracao_critica_encurtada_sem_progresso", "gravidade": "alta",
                        "mensagem": f"{i}: duração {x.duracao} → {y.duracao} d.u. em atividade crítica ainda não "
                                    "iniciada nas duas versões; confira se há medição ou ajuste que justifique",
                        "atividades": [i]})
        if x.calendario != y.calendario and (i in crit_a or i in crit_b):
            out.append({"tipo": "calendario_trocado_em_atividade_critica", "gravidade": "media",
                        "mensagem": f"{i}: calendário {x.calendario} → {y.calendario} em atividade do caminho crítico",
                        "atividades": [i]})
    for i in sorted(set(ab) - set(aa)):
        y = ab[i]
        if i in crit_b and (y.restricao_inicio is not None or y.restricao_termino is not None):
            out.append({"tipo": "restricao_nova_no_caminho_critico", "gravidade": "alta",
                        "mensagem": f"{i}: atividade nova, crítica, com restrição", "atividades": [i]})
    rels_b = {_chave_rel(r) for r in b.relacoes}
    for r in a.relacoes:
        if _chave_rel(r) not in rels_b and r.predecessora in crit_a and r.sucessora in crit_a:
            out.append({"tipo": "relacao_critica_removida", "gravidade": "alta",
                        "mensagem": f"{r.predecessora}->{r.sucessora} {r.tipo}{r.lag:+d} removida: as duas pontas eram "
                                    "críticas em A", "atividades": [r.predecessora, r.sucessora]})
    return out
