"""Motor CPM independente.

Suporta:
- relações FS, SS, FF, SF com lag (positivo ou negativo), lag no calendário
  da PREDECESSORA (padrão do Primavera P6);
- calendário por atividade, inclusive diferentes entre predecessora e sucessora;
- marcos de início e de término (duração 0);
- restrição "início não antes de" (SNET);
- data de status: atividades concluídas usam datas reais; em andamento usam
  a duração REMANESCENTE a partir da data de status (progress override:
  em andamento ignora as predecessoras e não é restringida/restringe por
  relações já satisfeitas — política aplicada IGUALMENTE na ida e na volta);
  não iniciadas não começam antes da data de status;
- folga total, folga livre (nunca maior que a total), caminho crítico
  (folga total <= tolerância OU no caminho mais longo) e cadeia determinante;
- detecção de ciclos e validação de entrada (inclusive datas reais incoerentes).

Não faz nivelamento de recursos: isso é camada separada (ver ADR-0003).
Convenção de datas: fronteiras semiabertas, ver ``calendario.py``.

Regra de calendários mistos (revisão adversarial, 2026-11-12):
- FS/SS: a sucessora começa no primeiro dia útil DELA a partir do alvo.
- FF/SF: a sucessora não pode terminar antes do último dia efetivamente
  trabalhado pela predecessora (tempo real), e não só em tempo de trabalho.
- A passada para trás usa as inversas exatas dessas regras
  (``Calendario.inicio_mais_tardio`` / ``fim_mais_tardio``).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from .calendario import HORIZONTE_FIM, HORIZONTE_INICIO, Calendario, ErroCalendario, iso

TIPOS_RELACAO = ("FS", "SS", "FF", "SF")
TIPOS_ATIVIDADE = ("tarefa", "marco_inicio", "marco_termino")
STATUS = ("nao_iniciada", "em_andamento", "concluida")


class ErroRede(ValueError):
    """Rede de atividades inválida (referência inexistente, duração negativa...)."""


class CicloNaRede(ErroRede):
    """A rede contém um ciclo e não tem solução CPM."""

    def __init__(self, ciclo: list[str]):
        self.ciclo = ciclo
        super().__init__("ciclo na rede de atividades: " + " -> ".join(ciclo))


@dataclass
class AtividadeCPM:
    id: str
    duracao: int  # dias úteis: total (não iniciada) ou remanescente (em andamento)
    calendario: str
    tipo: str = "tarefa"
    status: str = "nao_iniciada"
    inicio_real: int | None = None  # ordinal (dia)
    termino_real: int | None = None  # ordinal (último dia trabalhado)
    restricao_inicio: int | None = None  # SNET, ordinal
    # FNLT ("término não depois de"): ÚLTIMO dia em que pode haver trabalho. Só afeta as datas
    # tardias (como no P6); folga total NEGATIVA é legítima quando a rede não cabe no prazo.
    restricao_termino: int | None = None


@dataclass
class Relacao:
    predecessora: str
    sucessora: str
    tipo: str = "FS"
    lag: int = 0


@dataclass
class ResultadoAtividade:
    id: str
    es: int
    ef: int
    ls: int | None = None
    lf: int | None = None
    folga_total: int | None = None
    folga_livre: int | None = None
    critica: bool = False
    caminho_mais_longo: bool = False
    determinante: str | None = None  # quem fixou o início cedo
    determinantes: list[str] = field(default_factory=list)  # todas as predecessoras que empatam
    motivo_inicio: str = ""
    # Tipo de cada fronteira: True = "fim de dia" (dia útil anterior trabalhado);
    # False = "início de dia". Tarefa: ES início, EF fim. Instante (duração 0):
    # os dois iguais, herdados de quem o fixou (revisão adversarial, rodada 2).
    fim_es: bool = False
    fim_ef: bool = True
    # em andamento: onde o trabalho REMANESCENTE recomeça (data de status ou, com lógica
    # retida, depois das predecessoras FS/FF ainda abertas)
    inicio_restante: int | None = None

    def instante(self) -> bool:
        return self.es == self.ef

    def data_inicio(self, cal: Calendario, ativ: AtividadeCPM) -> int:
        if ativ.tipo == "marco_termino":
            return self.data_termino(cal, ativ)
        return self.es

    def data_termino(self, cal: Calendario, ativ: AtividadeCPM) -> int:
        """Data exibível do término.

        - tarefa com trabalho / concluída: último dia trabalhado (EF − 1);
        - marco de início e tarefa de duração 0 não iniciada: o próprio início;
        - marco de término: se a fronteira é "fim de dia", o dia que terminou
          (EF − 1); se é "início de dia", o primeiro dia útil a partir dela —
          nunca antes do evento que o disparou.
        """
        if ativ.status == "concluida":
            return self.ef - 1 if ativ.tipo != "marco_inicio" else self.es
        if ativ.tipo == "marco_inicio" or (ativ.tipo == "tarefa" and ativ.duracao == 0):
            return self.es
        if ativ.tipo == "marco_termino":
            return self.ef - 1 if self.fim_ef else cal.proximo_util(self.ef)
        return self.ef - 1

    def como_dict(self, cal: Calendario, ativ: AtividadeCPM) -> dict:
        return {
            "id": self.id,
            "inicio": iso(self.data_inicio(cal, ativ)),
            "termino": iso(self.data_termino(cal, ativ)),
            "es": iso(self.es),
            "ef": iso(self.ef),
            "ls": iso(self.ls),
            "lf": iso(self.lf),
            "folga_total": self.folga_total,
            "folga_livre": self.folga_livre,
            "critica": self.critica,
            "caminho_mais_longo": self.caminho_mais_longo,
            # em andamento: onde o REMANESCENTE recomeça (data de status ou, com lógica retida, depois
            # das predecessoras abertas). Consumidores de recursos devem contar a partir daqui (rodada 5)
            "inicio_restante": iso(self.inicio_restante),
            "determinante": self.determinante,
            "motivo_inicio": self.motivo_inicio,
        }


@dataclass
class ResultadoCPM:
    atividades: dict[str, ResultadoAtividade]
    termino_projeto: int  # fronteira (exclusiva)
    termino_projeto_data: int  # último dia (exibível)
    ordem: list[str]
    caminho_critico: list[str]
    cadeia_determinante: list[str] = field(default_factory=list)
    caminho_mais_longo: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
def _validar(ativs: dict[str, AtividadeCPM], rels: list[Relacao], cals: dict[str, Calendario],
             data_status: int | None) -> None:
    if not ativs:
        raise ErroRede("rede vazia: nenhuma atividade para calcular")
    for a in ativs.values():
        if a.duracao < 0:
            raise ErroRede(f"atividade {a.id}: duração negativa ({a.duracao})")
        if a.tipo not in TIPOS_ATIVIDADE:
            raise ErroRede(f"atividade {a.id}: tipo desconhecido {a.tipo!r}")
        if a.status not in STATUS:
            raise ErroRede(f"atividade {a.id}: status desconhecido {a.status!r}")
        if a.tipo != "tarefa" and a.duracao != 0:
            raise ErroRede(f"atividade {a.id}: marco precisa ter duração 0")
        if a.calendario not in cals:
            raise ErroRede(f"atividade {a.id}: calendário {a.calendario!r} inexistente")
        if a.status in ("em_andamento", "concluida") and a.inicio_real is None:
            raise ErroRede(f"atividade {a.id}: {a.status} exige início real")
        if a.status == "concluida":
            if a.termino_real is None:
                raise ErroRede(f"atividade {a.id}: concluída exige término real")
            if a.termino_real < a.inicio_real:
                raise ErroRede(f"atividade {a.id}: término real anterior ao início real")
            if data_status is not None and a.termino_real >= data_status:
                raise ErroRede(f"atividade {a.id}: concluída com término real na data de status ou depois")
        if a.status == "em_andamento" and data_status is not None and a.inicio_real >= data_status:
            raise ErroRede(f"atividade {a.id}: em andamento com início real na data de status ou depois")
        for nome, v in (("início real", a.inicio_real), ("término real", a.termino_real),
                        ("restrição", a.restricao_inicio), ("restrição de término", a.restricao_termino)):
            if v is not None and not (HORIZONTE_INICIO.toordinal() <= v <= HORIZONTE_FIM.toordinal()):
                raise ErroRede(f"atividade {a.id}: {nome} fora do horizonte dos calendários "
                               f"({HORIZONTE_INICIO} a {HORIZONTE_FIM})")
    vistos = set()
    for r in rels:
        if r.tipo not in TIPOS_RELACAO:
            raise ErroRede(f"relação {r.predecessora}->{r.sucessora}: tipo {r.tipo!r} inválido")
        for x in (r.predecessora, r.sucessora):
            if x not in ativs:
                raise ErroRede(f"relação {r.predecessora}->{r.sucessora}: atividade {x!r} inexistente")
        if r.predecessora == r.sucessora:
            raise CicloNaRede([r.predecessora, r.sucessora])
        chave = (r.predecessora, r.sucessora, r.tipo)
        if chave in vistos:
            raise ErroRede(f"relação duplicada {r.predecessora}->{r.sucessora} {r.tipo}")
        vistos.add(chave)


def _ordenar(ids: list[str], rels: list[Relacao]) -> list[str]:
    grau = {i: 0 for i in ids}
    succ = defaultdict(list)
    for r in rels:
        grau[r.sucessora] += 1
        succ[r.predecessora].append(r.sucessora)
    fila = deque(i for i in ids if grau[i] == 0)
    ordem = []
    while fila:
        n = fila.popleft()
        ordem.append(n)
        for s in succ[n]:
            grau[s] -= 1
            if grau[s] == 0:
                fila.append(s)
    if len(ordem) != len(ids):
        restantes = {i for i in ids if grau[i] > 0}
        raise CicloNaRede(_achar_ciclo(restantes, succ))
    return ordem


def _achar_ciclo(nos: set[str], succ) -> list[str]:
    # poda os nós a JUSANTE do ciclo (sem sucessora dentro do conjunto)
    nos = set(nos)
    mudou = True
    while mudou:
        mudou = False
        for n in list(nos):
            if not any(s in nos for s in succ[n]):
                nos.discard(n)
                mudou = True
    inicio = sorted(nos)[0]
    caminho, pos = [], {}
    atual = inicio
    while atual not in pos:
        pos[atual] = len(caminho)
        caminho.append(atual)
        atual = next(s for s in succ[atual] if s in nos)
    return caminho[pos[atual]:] + [atual]


def _ef_minimo_por_alvo(cal_s: Calendario, cal_p: Calendario, alvo: int) -> int:
    """Menor fronteira de término da sucessora que não termina antes do último dia
    efetivamente trabalhado pela predecessora antes do ``alvo`` (FF/SF)."""
    ultimo_trab_pred = cal_p.ultimo_dia_util(alvo)
    return cal_s.proximo_util(ultimo_trab_pred) + 1


# ---------------------------------------------------------------------------
def calcular(
    atividades: list[AtividadeCPM],
    relacoes: list[Relacao],
    calendarios: dict[str, Calendario],
    inicio_projeto: int,
    data_status: int | None = None,
    tolerancia_critica: int = 0,
    logica_progresso: str = "sobrepor",
) -> ResultadoCPM:
    """Executa passada para frente, para trás, folgas e caminho crítico.

    logica_progresso:
      - "sobrepor" (progress override, padrão): o remanescente de uma atividade em andamento
        começa na data de status, ignorando as predecessoras.
      - "retida" (retained logic, padrão do P6): o remanescente só recomeça depois que as
        predecessoras FS/FF ainda abertas o permitirem; SS/SF já foram satisfeitas pelo início real.
    """
    if logica_progresso not in ("sobrepor", "retida"):
        raise ErroRede(f"logica_progresso desconhecida: {logica_progresso!r}")
    retida = logica_progresso == "retida"
    ativs = {a.id: a for a in atividades}
    if len(ativs) != len(atividades):
        raise ErroRede("ids de atividade duplicados")
    _validar(ativs, relacoes, calendarios, data_status)
    ordem = _ordenar(list(ativs), relacoes)

    preds = defaultdict(list)
    succs = defaultdict(list)
    for r in relacoes:
        preds[r.sucessora].append(r)
        succs[r.predecessora].append(r)

    res: dict[str, ResultadoAtividade] = {}
    piso = inicio_projeto if data_status is None else max(inicio_projeto, data_status)
    calendarios[next(iter(ativs.values())).calendario]._indice(piso)  # piso dentro do horizonte

    # ------------------------------------------------------------ para frente
    for aid in ordem:
        a = ativs[aid]
        cal = calendarios[a.calendario]
        if a.status == "concluida":
            res[aid] = ResultadoAtividade(aid, a.inicio_real, a.termino_real + 1,
                                          motivo_inicio="data real (concluída)")
            continue
        if a.status == "em_andamento":
            base = data_status if data_status is not None else a.inicio_real
            base = max(base, a.inicio_real)
            motivo, det, dets = "em andamento: remanescente a partir da data de status", None, []
            if retida:
                cands = []
                for r in preds[aid]:
                    if r.tipo not in ("FS", "FF"):
                        continue  # SS/SF: o início real já as satisfez
                    if ativs[r.predecessora].status == "concluida":
                        # predecessora concluída: a relação é tida como satisfeita (o que a docstring e o
                        # painel prometem: só predecessoras ABERTAS seguram o remanescente). Escolha
                        # declarada; o comportamento exato do P6 com lag de concluída NÃO foi verificado.
                        continue
                    p, pr = ativs[r.predecessora], res[r.predecessora]
                    pcal = calendarios[p.calendario]
                    alvo = pcal.somar(pr.ef, r.lag)
                    if r.tipo == "FS":
                        c = cal.proximo_util(alvo)
                    else:
                        try:
                            c = cal.subtrair(_ef_minimo_por_alvo(cal, pcal, alvo), a.duracao)
                        except ErroCalendario:
                            continue
                    cands.append((c, r.predecessora, f"lógica retida: {r.tipo}{'+' if r.lag >= 0 else ''}"
                                                      f"{r.lag} de {r.predecessora}"))
                for c, pid, txt in cands:
                    if c > base:
                        base, det, motivo = c, pid, txt
                ini_r = cal.proximo_util(base)
                dets = sorted({pid for c, pid, _ in cands if cal.proximo_util(c) == ini_r})
            ini_r = cal.proximo_util(base) if a.duracao > 0 else base
            ef = cal.somar(ini_r, a.duracao) if a.duracao > 0 else base
            res[aid] = ResultadoAtividade(aid, a.inicio_real, ef, motivo_inicio=motivo, determinante=det,
                                          determinantes=dets, inicio_restante=ini_r)
            continue

        d = a.duracao
        # instante de início: marco de início ou tarefa sem trabalho remanescente — ocorre no
        # início de um dia útil. Marco de término é instante "solto" (não é ajustado).
        ajusta_inicio = d > 0 or a.tipo != "marco_termino"
        es, motivo, det, fim = piso, ("data de status" if data_status else "início do projeto"), None, False
        if a.restricao_inicio is not None and a.restricao_inicio > es:
            es, motivo = a.restricao_inicio, "restrição 'início não antes de'"
        candidatos = []  # (es_candidato, pred, texto, tipo_da_fronteira)
        for r in preds[aid]:
            p, pr = ativs[r.predecessora], res[r.predecessora]
            pcal = calendarios[p.calendario]
            de_fim = r.tipo in ("FS", "FF")
            fonte = pr.ef if de_fim else pr.es
            # tipo da fronteira-alvo: lag>0 termina num dia trabalhado (fim); lag<0 cai num
            # início de dia útil; lag 0 herda o tipo da fronteira de origem.
            tipo_alvo = True if r.lag > 0 else False if r.lag < 0 else (pr.fim_ef if de_fim else pr.fim_es)
            if r.tipo in ("FS", "SS"):
                c = pcal.somar(fonte, r.lag)
                if ajusta_inicio:
                    c = cal.proximo_util(c)
            else:  # FF / SF: limita o TÉRMINO da sucessora
                alvo = pcal.somar(fonte, r.lag)
                if d > 0:
                    ef_min = _ef_minimo_por_alvo(cal, pcal, alvo)
                    try:
                        c = cal.subtrair(ef_min, d)
                    except ErroCalendario:
                        continue  # pediria início antes do horizonte: o piso vence
                else:
                    c = cal.proximo_util(alvo) if ajusta_inicio else alvo
            candidatos.append((c, r.predecessora, f"{r.tipo}{'+' if r.lag >= 0 else ''}{r.lag} de {r.predecessora}",
                               tipo_alvo))
        for c, pid, txt, tipo_alvo in candidatos:
            # empate: prefere a candidata em forma "início" (mais tardia em tempo real) — rodada 3
            if c > es or (c == es and (det is None or (fim and not tipo_alvo))):
                es, det, motivo, fim = c, pid, txt, tipo_alvo
        if ajusta_inicio:
            es = cal.proximo_util(es)
        elif not fim:
            # marco de término em forma "início": normaliza para o início do próximo dia útil DO
            # SEU calendário (equivalente em tempo de trabalho). Sem isso, num feriado a volta o
            # puxava para antes do ES e criava folga −1 sem restrição (rodada 4)
            es = cal.proximo_util(es)
        ef = cal.somar(es, d)
        dets = sorted({pid for c, pid, _, _ in candidatos
                       if (cal.proximo_util(c) if ajusta_inicio else c) == es})
        if det is not None and det not in dets:
            dets.append(det)
        if d > 0:
            fim_es, fim_ef = False, True
        elif a.tipo == "marco_termino":
            fim_es = fim_ef = fim
        else:
            fim_es = fim_ef = False
        res[aid] = ResultadoAtividade(aid, es, ef, determinante=det, determinantes=dets, motivo_inicio=motivo,
                                      fim_es=fim_es, fim_ef=fim_ef)

    termino = max(r.ef for r in res.values())

    # ------------------------------------------------------------- para trás
    for aid in reversed(ordem):
        a = ativs[aid]
        r_a = res[aid]
        if a.status == "concluida":
            continue
        cal = calendarios[a.calendario]
        d = a.duracao
        instante = d == 0 and a.status == "nao_iniciada"
        # Instante em forma "fim de dia" (fixado pelo fim de uma predecessora) usa a inversa de
        # FIM; em forma "início" usa a inversa de INÍCIO. Misturar as formas dava folga -1 em
        # cadeia de marcos após uma sexta-feira (rodada 3).
        inst_fim = instante and r_a.fim_ef
        if instante and not inst_fim and r_a.ef != termino:
            # instante de início solto só pode ocorrer até o início do ÚLTIMO dia trabalhado da obra;
            # na fronteira final ele seria exibido depois do término (rodada 3)
            lf = cal.inicio_mais_tardio(termino - 1, 0)
        else:
            lf = termino
        for r in succs[aid]:
            s, sr = ativs[r.sucessora], res[r.sucessora]
            if s.status == "concluida":
                continue
            if s.status == "em_andamento":
                # sobrepor: sucessora já iniciada não restringe (ida e volta coerentes).
                # retida: FS/FF continuam restringindo o REMANESCENTE dela.
                if not (retida and r.tipo in ("FS", "FF")):
                    continue
                # recuar a duração da SUCESSORA no calendário DELA (rodada 4: usava o da predecessora)
                t = (calendarios[s.calendario].subtrair(sr.lf, s.duracao) if r.tipo == "FS"
                     else cal.proximo_util(sr.lf))
                lf = min(lf, cal.fim_mais_tardio(t, r.lag) if not instante else cal.inicio_mais_tardio(t, r.lag))
                continue
            if a.status == "em_andamento" and r.tipo in ("SS", "SF"):
                continue  # o início da predecessora já aconteceu
            suc_instante = sr.es == sr.ef and s.duracao == 0
            if r.tipo in ("FS", "SS"):
                t = sr.ls
            else:
                # sucessora instante: a ida usa o próprio alvo, então a volta não ajusta o LF
                t = sr.lf if suc_instante else cal.proximo_util(sr.lf)
            if inst_fim:
                c = cal.fim_mais_tardio(t, r.lag)
            elif instante:
                c = cal.inicio_mais_tardio(t, r.lag)
            elif r.tipo in ("FS", "FF"):
                c = cal.fim_mais_tardio(t, r.lag)
            else:  # SS / SF
                c = cal.somar(cal.inicio_mais_tardio(t, r.lag), d)
            lf = min(lf, c)
        rt = a.restricao_termino
        if d > 0:
            if rt is not None:
                lf = min(lf, rt + 1)  # FNLT: fim do último dia permitido
            lf = cal.fim_ajustado(lf)
        elif instante and not inst_fim and a.tipo != "marco_termino":
            lf = cal.inicio_mais_tardio(lf, 0)  # instante de início só ocorre no início de um dia útil
        if instante:
            lf = max(lf, r_a.es) if r_a.ef == termino else lf
            # FNLT DEPOIS da guarda do último instante: antes, a guarda anulava o FNLT justamente
            # no marco final da obra — o marco contratual (rodada 4)
            if rt is not None:
                lim = rt + 1 if (inst_fim or a.tipo == "marco_termino") else cal.inicio_mais_tardio(rt, 0)
                lf = min(lf, lim)
        r_a.lf = lf
        r_a.ls = cal.subtrair(lf, d) if a.status == "nao_iniciada" else r_a.es
        r_a.folga_total = cal.dias_uteis_entre(r_a.ef, lf)

    # ------------------------------------------------------------ folga livre
    for aid in ordem:
        a = ativs[aid]
        r_a = res[aid]
        if a.status == "concluida":
            continue
        cal = calendarios[a.calendario]
        instante = a.duracao == 0 and a.status == "nao_iniciada"
        folgas = [r_a.folga_total]
        for r in succs[aid]:
            s, sr = ativs[r.sucessora], res[r.sucessora]
            if s.status == "em_andamento" and retida and r.tipo in ("FS", "FF"):
                t = sr.inicio_restante if r.tipo == "FS" else cal.proximo_util(sr.ef)
                lim = cal.inicio_mais_tardio(t, r.lag) if instante else cal.fim_mais_tardio(t, r.lag)
                folgas.append(cal.dias_uteis_entre(r_a.es if instante else r_a.ef, lim))
                continue
            if s.status != "nao_iniciada":
                continue
            if a.status == "em_andamento" and r.tipo in ("SS", "SF"):
                continue
            suc_instante = sr.es == sr.ef and s.duracao == 0
            if instante:
                t = sr.es if r.tipo in ("FS", "SS") else (sr.ef if suc_instante else cal.proximo_util(sr.ef))
                lim = cal.fim_mais_tardio(t, r.lag) if r_a.fim_ef else cal.inicio_mais_tardio(t, r.lag)
                folgas.append(cal.dias_uteis_entre(r_a.es, lim))
            elif suc_instante and r.tipo in ("FF", "SF"):
                lim = (cal.fim_mais_tardio(sr.ef, r.lag) if r.tipo == "FF"
                       else cal.inicio_mais_tardio(sr.ef, r.lag))
                folgas.append(cal.dias_uteis_entre(r_a.ef if r.tipo == "FF" else r_a.es, lim))
            elif r.tipo == "FS":
                folgas.append(cal.dias_uteis_entre(r_a.ef, cal.fim_mais_tardio(sr.es, r.lag)))
            elif r.tipo == "SS":
                folgas.append(cal.dias_uteis_entre(r_a.es, cal.inicio_mais_tardio(sr.es, r.lag)))
            elif r.tipo == "FF":
                folgas.append(cal.dias_uteis_entre(r_a.ef, cal.fim_mais_tardio(cal.proximo_util(sr.ef), r.lag)))
            else:
                folgas.append(cal.dias_uteis_entre(r_a.es, cal.inicio_mais_tardio(cal.proximo_util(sr.ef), r.lag)))
        r_a.folga_livre = max(0, min(folgas))

    # ------------------------------------------- caminho mais longo (driving)
    finais = [i for i in ordem if res[i].ef == termino]
    longo, pilha = set(), list(finais)
    while pilha:
        n = pilha.pop()
        if n in longo:
            continue
        longo.add(n)
        pilha.extend(res[n].determinantes)
    for aid in ordem:
        r_a = res[aid]
        if ativs[aid].status == "concluida":
            continue
        r_a.caminho_mais_longo = aid in longo
        r_a.critica = r_a.folga_total <= tolerancia_critica or r_a.caminho_mais_longo
    criticas = [aid for aid in ordem if res[aid].critica]

    # cadeia determinante: do término do projeto para trás pelo "determinante"
    final = max(ordem, key=lambda i: (res[i].ef, ativs[i].tipo == "marco_termino"))
    cadeia, atual, guarda = [], final, set()
    while atual and atual not in guarda:
        guarda.add(atual)
        cadeia.append(atual)
        atual = res[atual].determinante
    cadeia.reverse()

    termino_data = max(res[i].data_termino(calendarios[ativs[i].calendario], ativs[i]) for i in ordem)
    return ResultadoCPM(
        atividades=res,
        termino_projeto=termino,
        termino_projeto_data=termino_data,
        ordem=ordem,
        caminho_critico=criticas,
        cadeia_determinante=cadeia,
        caminho_mais_longo=[i for i in ordem if i in longo and ativs[i].status != "concluida"],
    )
